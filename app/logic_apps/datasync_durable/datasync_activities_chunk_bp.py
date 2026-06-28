from datetime import datetime
from io import BytesIO
import logging
import azure.functions as func
from azure.storage.blob import BlobServiceClient
import os,json,base64
import numpy as np
import pandas as pd
import requests

from app.assets.asset_datasync.assetsync_data_access import add_asset_data_in_db, add_asset_data_in_history, delete_asset_data_in_db, get_asset_table_data, inactive_asset_data, remove_asset_data_in_db,  unpairing_current_device, update_asset_data_in_db, update_new_pairing_data_in_db
from app.assets.asset_datasync.assetsync_services import get_new_existing_asset_data, print_device_pairing_date_from_df, send_asset_sync_report
from app.brake_performance.brake_performance_datasync.brake_performance_datasync_data_access import add_brake_performance_data_in_db, get_brake_performance_db_data, remove_brake_performance_asset_data_in_db, update_brake_performance_data_in_db
from app.brake_performance.brake_performance_datasync.brake_performance_datasync_services import get_bp_api_data, get_new_existing_bp_asset_data, send_bp_asset_sync_report
from app.common.constants import AudienceCode
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User, SC_User
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.func_validator import User
from app.common.helpers.common_data_access import get_all_organizations, get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token, get_all_data
from app.common.helpers.session_helpers import get_new_existing_missing_sessions_data
from app.common.helpers.unit_helpers import get_asset_api_data, get_asset_data
from app.common.scalar_api.roles_api import get_all_role
from app.common.scalar_api.user_api import get_all_user
from app.data_sharing.session_datasync.sessionsync_data_access import add_new_session_data_into_db, deactivate_sessions_missing_in_api, get_all_sessions_from_database, update_existing_sessions_data_into_db
from app.data_sharing.session_datasync.sessionsync_services import get_all_sessions_from_api, send_session_sync_report
from app.users.user_datasync.usersync_data_access import get_all_users_from_db
from app.users.user_datasync.usersync_services import send_sync_report, sync_user_db, user_role_mapping


datasync_activities_chunk_bp = func.Blueprint()

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def GetAllAssets(input: dict):
    try:
        logger = logging.getLogger("get_all_assets")
        db = Database()
        asset_list_from_db = get_asset_table_data(db=db)
        organization_id = get_tip_provider_organization(db=db)
        if organization_id is None:
            raise ScalarException(message="There is no provider Organization data in database")
        else:
            org_id=organization_id[0]
        asset_list_from_api = get_asset_api_data(db=db,org_id=org_id)
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("assetsync-data")
        try: 
            container.create_container()
        except:
            pass
        first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df= asset_list_from_db)
        logger.info(f"Device pairing date format in DB Dataframe:{first_device_pairing_date}")
        asset_db_blob = container.get_blob_client(f"assets_db_data.json")
        asset_db_blob.upload_blob(asset_list_from_db.to_json(orient="records", indent=4), overwrite=True)
        asset_api_blob = container.get_blob_client(f"assets_api_data.json")
        asset_api_blob.upload_blob(asset_list_from_api.to_json(orient="records", indent=4), overwrite=True)
        return {"status": True}
    except Exception as e:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("job-status")
        try: 
            container.create_container()
        except:
            pass
        blob = container.get_blob_client(f"Asset_Data_Sync.txt")
        blob.upload_blob(json.dumps(repr(e), indent=4), overwrite=True)
        email=Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Asset sync report - " + env
        template_name='error_asset_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        return {"status": False}
    finally:
        db.get_session().close()


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncAssets(input: dict):
    logger = logging.getLogger("sync_asset_data")
    db = Database()
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("assetsync-data")
        asset_db_data = json.loads(container.get_blob_client(input['asset_list_from_db']).download_blob().readall())
        asset_api_data = json.loads(container.get_blob_client(input['asset_list_from_api']).download_blob().readall())

        asset_list_from_api = pd.DataFrame(asset_api_data).replace({np.nan: None})
        asset_list_from_db = pd.DataFrame(asset_db_data).replace({np.nan: None})
        
        first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df= asset_list_from_db)
        logger.info(f"Device pairing date format in blob DB Dataframe:{first_device_pairing_date}")
        asset_list_from_db['Device_Pairing_Date'] = pd.to_datetime(asset_list_from_db['Device_Pairing_Date'], unit='ms', errors='coerce')
        asset_list_from_db = pd.DataFrame(asset_list_from_db).replace({np.nan: None})

        if len(asset_list_from_db) == 0:
            asset_list_from_db['assetId'] = pd.Series(dtype='object')
            asset_list_from_db['Active'] = pd.Series(dtype='object')
        if len(asset_list_from_api) > 0:
            
            new_asset_data_df, missing_asset_data_df, existing_asset_api_data_df, existing_inactive_asset_data_df, existing_unpairing_asset_data_df,\
                        existing_new_pairing_asset_data_df, existing_fresh_new_pairing_asset_data_df = get_new_existing_asset_data(asset_list_from_db, asset_list_from_api, logger)
            
            if len(new_asset_data_df) > 0:
                add_asset_data_in_db(db=db,new_asset_data=new_asset_data_df)         
            if len(existing_asset_api_data_df)>0:
                update_asset_data_in_db(db=db,existing_asset_data=existing_asset_api_data_df)
            if len(missing_asset_data_df) > 0: # Asset not found in Scalar system
                delete_asset_data_in_db(db=db,missing_asset_data=missing_asset_data_df)
            if len(existing_inactive_asset_data_df)>0:# Asset made Inactive in Scalar system
                remove_asset_data_in_db(db=db,missing_asset_data=existing_inactive_asset_data_df)
            if len(existing_unpairing_asset_data_df)>0: # Pairied asset becoming Unpairing asset
                delete_asset_data_in_db(db=db,missing_asset_data=existing_unpairing_asset_data_df)
                add_asset_data_in_history(db=db,new_asset_data=existing_unpairing_asset_data_df)
            if len(existing_new_pairing_asset_data_df)>0:# Change of pairing from old device to new device
                add_asset_data_in_db(db=db,new_asset_data=existing_new_pairing_asset_data_df)
            if len(existing_fresh_new_pairing_asset_data_df)>0:# Fresh pairing with Un-Pairied assets
                update_new_pairing_data_in_db(db=db,update_new_pairing_data=existing_fresh_new_pairing_asset_data_df)


            logger.info(f"Number of new assets :{len(new_asset_data_df)} has beed inserted successfully into the database") 
            logger.info(f"Number of existing assets :{len(existing_asset_api_data_df)} has beed updated successfully into the database")
            logger.info(f"Number of deactivated assets : {len(missing_asset_data_df)} has been deactivated in the database")          
                
            env = os.environ['SCALAR_ENV']
            params={"environment": env, 
            "execution_time": datetime.now(),
            "total_asset": len(asset_list_from_api), 
            "new_asset": len(new_asset_data_df), 
            "existing_asset": len(existing_asset_api_data_df) ,
            "deactivate_asset":len(missing_asset_data_df)
            }     
            send_asset_sync_report(api_asset_list=asset_list_from_api,new_asset_list=new_asset_data_df,update_asset_list=existing_asset_api_data_df,error_asset_list=missing_asset_data_df,params=params)  
            
            asset_response = {"status":True,
                "Total assets to be synced": len(asset_list_from_api),
                "New assets added": len(new_asset_data_df),
                "Existing assets updated": len(existing_asset_api_data_df),
                "Assets deactivated": len(missing_asset_data_df),
                }

        else:
            logger.info(f"Fetching asset from api has failed")
            asset_response = {"status":False,
                            "Error": "Could not fetch asset data"
                            }

        return asset_response
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        email=Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Asset sync report - " + env
        template_name='error_asset_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return {"status":False}
    
@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def GetAllSessions(input: dict):
    try:
        logger = logging.getLogger("sync_session_data")
        db = Database()
        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")

        provider_organization_id = provider_organization[0]
        access_token = fetch_access_token(db=db,org_id= provider_organization_id,audience= AudienceCode.DATA_SHARING)

        all_sessions_data_from_db = get_all_sessions_from_database(db=db)
        logger.info(f"Total number of sessions found in the database: {len(all_sessions_data_from_db)}")
        all_sessions_data_from_api = get_all_sessions_from_api(access_token= access_token, logger=logger)
        logger.info(f"Total number of sessions from the API: {len(all_sessions_data_from_api)}")
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("sessionsync-data")
        try: 
            container.create_container()
        except:
            pass
        session_db_blob = container.get_blob_client(f"sessions_db_data.json")
        session_db_blob.upload_blob(all_sessions_data_from_db.to_json(orient="records", indent=4), overwrite=True)
        session_api_blob = container.get_blob_client(f"sessions_api_data.json")
        session_api_blob.upload_blob(all_sessions_data_from_api.to_json(orient="records", indent=4), overwrite=True)
        return {"status": True}
    except Exception as e:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("job-status")
        try: 
            container.create_container()
        except:
            pass
        blob = container.get_blob_client(f"Session_Data_Sync.txt")
        blob.upload_blob(json.dumps(repr(e), indent=4), overwrite=True)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Session sync report - " + env
        template_name='error_session_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        return {"status": False}
    finally:
        db.get_session().close()


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncSessions(input: dict):
    logger = logging.getLogger("sync_session_data")
    db = Database()
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("sessionsync-data")
        session_db_data = json.loads(container.get_blob_client(input['all_sessions_data_from_db']).download_blob().readall())
        session_api_data = json.loads(container.get_blob_client(input['all_sessions_data_from_api']).download_blob().readall())
        all_sessions_data_from_api = pd.DataFrame(session_api_data).replace({np.nan: None})
        all_sessions_data_from_db = pd.DataFrame(session_db_data).replace({np.nan: None})
        if len(all_sessions_data_from_db) == 0:
            all_sessions_data_from_db['Session_Id'] = pd.Series(dtype='object')
        if all_sessions_data_from_api is not None and len(all_sessions_data_from_api) > 0:

            new_sessions_to_insert, sessions_to_update, sessions_to_deactivate = get_new_existing_missing_sessions_data(db_dataframe=all_sessions_data_from_db, api_dataframe=all_sessions_data_from_api, logger=logger)
            logger.info(f"New sessions to be inserted: {len(new_sessions_to_insert)}")
            logger.info(f"Existing sessions to be updated: {len(sessions_to_update)}")
            logger.info(f"Missing sessions to be deactivated: {len(sessions_to_deactivate)}")
            if len(new_sessions_to_insert) > 0:
                add_new_session_data_into_db(db=db, new_sessions_to_insert=new_sessions_to_insert)
            if len(sessions_to_update) > 0:
                update_existing_sessions_data_into_db(db=db, sessions_to_update=sessions_to_update)
            if len(sessions_to_deactivate) > 0:
                deactivate_sessions_missing_in_api(db=db, sessions_to_deactivate= sessions_to_deactivate)

            env = os.environ["SCALAR_ENV"]
            params={"environment": env, 
            "exectution_time": datetime.now(), 
            "sessions_from_db": len(all_sessions_data_from_db), 
            "sessions_from_api": len(all_sessions_data_from_api),
            "new_sessions_added":len(new_sessions_to_insert),
            "existing_sessions_updated":len(sessions_to_update),
            "deactivated_sessions": len(sessions_to_deactivate)
            }
            send_session_sync_report(new_sessions_to_insert=new_sessions_to_insert, 
                                sessions_to_update=sessions_to_update, 
                                sessions_to_deactivate=sessions_to_deactivate, params=params)
            
            api_response = {"status":True,
                "Total session to be synced": len(all_sessions_data_from_api),
                "New Sessions added": len(new_sessions_to_insert),
                "Existing sessions updated": len(sessions_to_update),
                "Deactivated sessions": len(sessions_to_deactivate),
                }

        else:
            logger.error(f"Fetching Sessions data has failed")
            api_response = {"status":False,
                            "Error": "Could not fetch sessions data"
                            }

        return api_response
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Session sync report - " + env
        template_name='error_session_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return {"status":False}
    
@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def GetAllOrgs(input: dict):
        db = Database()
        org_list = get_all_organizations(db=db)
        org_count = len(org_list)
        logging.info(f"Total active organizations: {org_count}")
        if org_list.empty:
            raise ScalarException(message="Could not retrieve any organization data from DB")
        db.get_session().close()
        return {
            "org_list":org_list.to_dict(orient="records"),
            "org_count":org_count
        }

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def GetCustomerUsers(input: dict):
    try:
        db = Database()
        access_token = fetch_access_token(db=db, org_id=input['Organization_Id'], audience=AudienceCode.USER)
        single_org_user_df = get_all_data(access_token=access_token,func=get_all_user)
        single_org_user_df = single_org_user_df[single_org_user_df['status'].isin(['Active','Pending'])]
        if single_org_user_df.empty:
            raise ScalarException(message=f"Could not retrieve any user for org: {input['Organization_Id']} from API")
        single_org_user_df['orgId'] = input['Organization_Id']
        single_org_user_df['sc_orgName'] = input['Organization_Name']
        single_org_role_df = get_all_data(access_token=access_token,func=get_all_role)
        if single_org_role_df.empty:
            raise ScalarException(message=f"Could not retrieve any role for org: {input['Organization_Id']} from API")
        return {
            "status": True,
            "users":single_org_user_df.to_dict(orient="records"),
            "roles":single_org_role_df.to_dict(orient="records")
        }
    except Exception as e:
        return {
            "status": False,
            "scalar_org_id": input['Organization_Id'],
            "error": str(e)
        }
    finally:
        db.get_session().close()

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def UploadBlobData(input: dict):
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client(input["container"])
        try:
            container.create_container()
        except Exception:
            pass
        blob = container.get_blob_client(input["blob_name"])
        blob.upload_blob(input["data"], overwrite=True)
        return {"status": True}
    except Exception as e:
        import logging as _log
        _log.error(f"UploadBlobData failed: {e}")
        return {"status": False}


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncUsers(input: dict):
    logger = logging.getLogger("sync_user_data")
    db = Database()
    try:
        send_report = input.get("send_report", True)
        org_count   = input.get("org_count", 0)

        # Accept direct list from orchestrator fan-out OR legacy blob-name string
        if isinstance(input.get("users"), str):
            blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
            container   = blob_client.get_container_client("usersync-data")
            user_data   = json.loads(container.get_blob_client(input["users"]).download_blob().readall())
            role_data   = json.loads(container.get_blob_client(input["roles"]).download_blob().readall())
        else:
            user_data = input["users"]
            role_data = input.get("roles", [])

        all_users_api_data = pd.DataFrame(user_data).replace({np.nan: None})
        all_roles_api_data = pd.DataFrame(role_data).replace({np.nan: None})
        all_users_db_data = get_all_users_from_db(db=db)
        inserted_users, updated_users, deleted_users, user_role_map, failed_users_df = sync_user_db(db=db, user_api_data=all_users_api_data, user_db_data= all_users_db_data, logger=logger)
        users_roles_mapped, failed_user_role_mapping = user_role_mapping(db=db, roles_api_data=all_roles_api_data, user_role_map=user_role_map, logger=logger)
        usersync_response = {
                "total_users_to_be_synced": len(all_users_api_data),
                "new_users_added": len(inserted_users),
                "existing_users_updated": len(updated_users),
                "deleted_users":len(deleted_users),
                "users_failed_to_sync": len(failed_users_df),
                "organization_count": org_count,
                "users_error_list": ([] if failed_users_df.empty else failed_users_df.values.tolist()),
                "users_for_role_mapping": len(users_roles_mapped),
                "users_failed_to_map_roles": len(failed_user_role_mapping),
                "user_role_mapping_error_list": ([] if failed_user_role_mapping.empty else failed_user_role_mapping.values.tolist())
        } 

        # Only the designated chunk (last in the fan-out) generates and sends the report.
        # Intermediate chunks skip this to avoid duplicate emails.
        if send_report and org_count > 0:
            usersync_report = BytesIO()
            with pd.ExcelWriter(usersync_report, engine='xlsxwriter') as writer:
                if len(all_users_api_data) > 0:
                    column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                    all_users_api_data[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Total users from API', index=None, header=True)
                if len(inserted_users) > 0:
                    inserted_users.to_excel(writer, sheet_name='New users added', index=None, header=True)
                if len(updated_users) > 0:
                    updated_users.to_excel(writer, sheet_name='Existing users updated', index=None, header=True)
                if len(deleted_users) > 0:
                    deleted_users.to_excel(writer, sheet_name='Deleted Users', index=None, header=True)
                if len(failed_users_df) > 0:
                    failed_users_df.to_excel(writer, sheet_name='User syncing error', index=None, header=True)
                if len(users_roles_mapped) > 0:
                    users_roles_mapped.to_excel(writer, sheet_name='Role Mapped for users', index=None, header=True)
                if len(failed_user_role_mapping) > 0:
                    failed_user_role_mapping.to_excel(writer, sheet_name='Role mapping error', index=None, header=True)

            send_sync_report(usersync_report=usersync_report, params=usersync_response)
        return {"status": True}
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: User sync report - " + env
        
        template_name='error_user_email.html'
        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }
        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        return {"status":False}

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def GetAllBpAssets(input: dict):
    try:
        db = Database()
        bp_asset_list_from_db = get_brake_performance_db_data(db=db)
        organization_id = get_tip_provider_organization(db=db)
        if organization_id is None:
            raise ScalarException(message="There is no provider Organization data in database")
        else:
            org_id=organization_id[0]

        bp_asset_list_from_api = get_bp_api_data(db=db,org_id=org_id)
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("brakeperformancesync-data")
        try: 
            container.create_container()
        except:
            pass
        brakeperformance_db_blob = container.get_blob_client(f"brakeperformance_db_data.json")
        brakeperformance_db_blob.upload_blob(bp_asset_list_from_db.to_json(orient="records", indent=4), overwrite=True)
        brakeperformance_api_blob = container.get_blob_client(f"brakeperformance_api_data.json")
        brakeperformance_api_blob.upload_blob(bp_asset_list_from_api.to_json(orient="records", indent=4), overwrite=True)
        return {"status": True}
    except Exception as e:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("job-status")
        try: 
            container.create_container()
        except:
            pass
        blob = container.get_blob_client(f"BrakePerformance_Data_Sync.txt")
        blob.upload_blob(json.dumps(repr(e), indent=4), overwrite=True)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Brake performance asset sync report - " + env
        template_name='error_asset_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        return {"status": False}
    finally:
        db.get_session().close()
        
@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncBrakePerformance(input: dict):
    logger = logging.getLogger("sync_brake_performance_data")
    db = Database()
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container = blob_client.get_container_client("brakeperformancesync-data")
        bp_db_data = json.loads(container.get_blob_client(input['bp_asset_list_from_db']).download_blob().readall())
        bp_api_data = json.loads(container.get_blob_client(input['bp_asset_list_from_api']).download_blob().readall())
        bp_asset_list_from_db = pd.DataFrame(bp_db_data).replace({np.nan: None})
        bp_asset_list_from_api = pd.DataFrame(bp_api_data).replace({np.nan: None})
        if len(bp_asset_list_from_db) == 0:
            bp_asset_list_from_db['assetId'] = pd.Series(dtype='object')
            bp_asset_list_from_db['Active'] = pd.Series(dtype='object')
        if len(bp_asset_list_from_api) > 0:
            new_bp_asset_data_df, existing_bp_asset_data_df, missing_bp_asset_data_df = get_new_existing_bp_asset_data(bp_asset_list_from_db, bp_asset_list_from_api)
            
            if len(new_bp_asset_data_df) > 0:
                add_brake_performance_data_in_db(db=db,new_brake_performance_asset_data=new_bp_asset_data_df)         
            if len(existing_bp_asset_data_df)>0:
                update_brake_performance_data_in_db(db=db,existing_brake_performance_asset_data=existing_bp_asset_data_df)
            if len(missing_bp_asset_data_df) > 0:
                remove_brake_performance_asset_data_in_db(db=db,missing_brake_performance_asset_data=missing_bp_asset_data_df)

            logger.info(f"Number of new assets :{len(new_bp_asset_data_df)} has beed inserted successfully into the database") 
            logger.info(f"Number of existing assets :{len(existing_bp_asset_data_df)} has beed updated successfully into the database")
            logger.info(f"Number of deactivated assets : {len(missing_bp_asset_data_df)} has been deactivated in the database")          

            api_response = {"status":True,
                "Total BP assets to be synced": len(bp_asset_list_from_api),
                "New BP assets added": len(new_bp_asset_data_df),
                "Existing BP assets updated": len(existing_bp_asset_data_df),
                "BP Assets deactivated": len(missing_bp_asset_data_df),
                }
                
            env = os.environ['SCALAR_ENV']
            params={"environment": env, 
            "execution_time": datetime.now(),
            "total_asset": len(bp_asset_list_from_api), 
            "new_asset": len(new_bp_asset_data_df), 
            "existing_asset": len(existing_bp_asset_data_df) ,
            "deactivate_asset":len(missing_bp_asset_data_df)
        }     

            send_bp_asset_sync_report(bp_api_asset_list=bp_asset_list_from_api,new_bp_asset_list=new_bp_asset_data_df,update_bp_asset_list=existing_bp_asset_data_df,error_bp_asset_list=missing_bp_asset_data_df,params=params)  

        else:
            logger.info(f"Fetching brake performance asset from api has failed")
            api_response = {"status":False,
                            "Error": "Could not fetch brake performance data"
                            }

        return api_response
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        email=Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Brake performance asset sync report - " + env
        template_name='error_asset_email.html'
    

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return {"status":False}

# @datasync_activities_bp.activity_trigger(input_name="input")
# def SyncDbQueue(input: dict):
#     try:
#         queue_service_client = QueueServiceClient.from_connection_string(conn_str=os.environ["AzureWebJobsStorage"])
#         queue = queue_service_client.get_queue_client(queue="syncqueue-usersync")
#         try:
#             queue.create_queue()
#         except Exception:
#             pass
#         message = base64.b64encode(json.dumps(input).encode('utf-8')).decode('utf-8')
#         queue.send_message(message)
#         return {'status':True}
#     except Exception as e:
#         logging.error(f"Error occurred:{str(e)}")
#         return {'status':False}

# @datasync_activities_bp.queue_trigger(arg_name="message", queue_name="syncqueue-usersync", connection="AzureWebJobsStorage")
# def sync_queue_usersync(message: func.QueueMessage):
#     logger = logging.getLogger("sync_user_data")
#     db = Database()
#     try:
#         payload = json.loads(message.get_body().decode())
#         blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
#         container = blob_client.get_container_client("usersync-data")
#         user_data = json.loads(container.get_blob_client(payload['users']).download_blob().readall())
#         role_data = json.loads(container.get_blob_client(payload['roles']).download_blob().readall())
#         all_users_api_data = pd.DataFrame(user_data)
#         all_roles_api_data = pd.DataFrame(role_data)
#         org_count = payload['org_count']
#         all_users_db_data = get_all_users_from_db(db=db)
#         inserted_users, updated_users, deleted_users, user_role_map, failed_users_df = sync_user_db(db=db, user_api_data=all_users_api_data, user_db_data= all_users_db_data, logger=logger)
#         users_roles_mapped, failed_user_role_mapping = user_role_mapping(db=db, roles_api_data=all_roles_api_data, user_role_map=user_role_map, logger=logger)
#         usersync_response = {
#                 "total_users_to_be_synced": len(all_users_api_data),
#                 "new_users_added": len(inserted_users),
#                 "existing_users_updated": len(updated_users),
#                 "deleted_users":len(deleted_users),
#                 "users_failed_to_sync": len(failed_users_df),
#                 "organization_count": org_count,
#                 "users_error_list": ([] if failed_users_df.empty else failed_users_df.values.tolist()),
#                 "users_for_role_mapping": len(users_roles_mapped),
#                 "users_failed_to_map_roles": len(failed_user_role_mapping),
#                 "user_role_mapping_error_list": ([] if failed_user_role_mapping.empty else failed_user_role_mapping.values.tolist())
#         } 

#         if org_count > 0:
#             usersync_report = BytesIO()
#             with pd.ExcelWriter(usersync_report, engine='xlsxwriter') as writer:
#                 if len(all_users_api_data) > 0:
#                     column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
#                     all_users_api_data[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Total users from API', index=None, header=True)
#                 if len(inserted_users) > 0:
#                     inserted_users.to_excel(writer, sheet_name='New users added', index=None, header=True)
#                 if len(updated_users) > 0:
#                     updated_users.to_excel(writer, sheet_name='Existing users updated', index=None, header=True)
#                 if len(deleted_users) > 0:
#                     deleted_users.to_excel(writer, sheet_name='Deleted Users', index=None, header=True)
#                 if len(failed_users_df) > 0:
#                     failed_users_df.to_excel(writer, sheet_name='User syncing error', index=None, header=True)
#                 if len(users_roles_mapped) > 0:
#                     users_roles_mapped.to_excel(writer, sheet_name='Role Mapped for users', index=None, header=True)
#                 if len(failed_user_role_mapping) > 0:
#                     failed_user_role_mapping.to_excel(writer, sheet_name='Role mapping error', index=None, header=True)

#             send_sync_report(usersync_report=usersync_report, params=usersync_response)
#         blob = container.get_blob_client(f"usersync_status.txt")
#         blob.upload_blob("completed", overwrite=True)
#     except Exception as e:
#         blob = container.get_blob_client(f"usersync_status.txt")
#         blob.upload_blob(str(e), overwrite=True)
#         logging.error(f"Error occurred:{str(e)}")
#         status_code=getattr(e,'status_code',500)
#         env = os.environ['SCALAR_ENV']
#         email=Email()
#         receivers=["Bhowmik.Arijit@tip-group.com"]
#         subject=f"Scalar - Data Sync Error: User sync report - " + env
        
#         template_name='error_user_email.html'
#         error_params={"environment": env, 
#         "execution_time": datetime.now(),
#         "error_message": repr(e),
#         }
#         email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

# ── PHASE-1: COMPARISON ACTIVITIES ──────────────────────────────────────────
# These run the full comparison ONCE and store each result category to blob.
# SyncAssetsChunk / SyncSessionsChunk / SyncBrakePerformanceChunk then read
# those pre-computed blobs and write only their assigned slice — keeping every
# activity well under the 30-minute function timeout.

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def CompareAssets(input: dict):
    logger = logging.getLogger("compare_assets")
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("assetsync-data")

        asset_db_data  = json.loads(container.get_blob_client("assets_db_data.json").download_blob().readall())
        asset_api_data = json.loads(container.get_blob_client("assets_api_data.json").download_blob().readall())

        asset_list_from_api = pd.DataFrame(asset_api_data).replace({np.nan: None})
        asset_list_from_db  = pd.DataFrame(asset_db_data).replace({np.nan: None})

        first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df=asset_list_from_db)
        logger.info(f"Device pairing date in DB: {first_device_pairing_date}")
        asset_list_from_db["Device_Pairing_Date"] = pd.to_datetime(
            asset_list_from_db["Device_Pairing_Date"], unit="ms", errors="coerce"
        )
        asset_list_from_db = asset_list_from_db.replace({np.nan: None})

        if len(asset_list_from_db) == 0:
            asset_list_from_db["assetId"] = pd.Series(dtype="object")
            asset_list_from_db["Active"]   = pd.Series(dtype="object")

        if len(asset_list_from_api) == 0:
            return {"status": True, "counts": {}, "api_total": 0}

        (
            new_asset_data_df,
            missing_asset_data_df,
            existing_asset_api_data_df,
            existing_inactive_asset_data_df,
            existing_unpairing_asset_data_df,
            existing_new_pairing_asset_data_df,
            existing_fresh_new_pairing_asset_data_df,
        ) = get_new_existing_asset_data(asset_list_from_db, asset_list_from_api, logger)

        categories = {
            "new":           new_asset_data_df,
            "missing":       missing_asset_data_df,
            "existing":      existing_asset_api_data_df,
            "inactive":      existing_inactive_asset_data_df,
            "unpairing":     existing_unpairing_asset_data_df,
            "new_pairing":   existing_new_pairing_asset_data_df,
            "fresh_pairing": existing_fresh_new_pairing_asset_data_df,
        }
        for name, df in categories.items():
            container.get_blob_client(f"assets_cmp_{name}.json").upload_blob(
                df.to_json(orient="records"), overwrite=True
            )

        env = os.environ["SCALAR_ENV"]
        report_meta = {
            "params": {
                "environment":      env,
                "execution_time":   datetime.now().isoformat(),
                "total_asset":      len(asset_list_from_api),
                "new_asset":        len(new_asset_data_df),
                "existing_asset":   len(existing_asset_api_data_df),
                "deactivate_asset": len(missing_asset_data_df),
            },
            "api_assets":    asset_list_from_api.to_json(orient="records"),
            "new_assets":    new_asset_data_df.to_json(orient="records"),
            "update_assets": existing_asset_api_data_df.to_json(orient="records"),
            "error_assets":  missing_asset_data_df.to_json(orient="records"),
        }
        container.get_blob_client("assets_cmp_report_meta.json").upload_blob(
            json.dumps(report_meta), overwrite=True
        )

        counts = {k: len(v) for k, v in categories.items()}
        logger.info(f"Asset comparison complete: {counts}")
        return {"status": True, "counts": counts, "api_total": len(asset_list_from_api)}

    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False, "counts": {}, "api_total": 0}


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncAssetsChunk(input: dict):
    logger = logging.getLogger("sync_assets_chunk")
    db = Database()
    try:
        category = input["category"]
        offset   = input["offset"]
        limit    = input["limit"]

        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("assetsync-data")

        raw = json.loads(container.get_blob_client(f"assets_cmp_{category}.json").download_blob().readall())
        df  = pd.DataFrame(raw).replace({np.nan: None}).iloc[offset:offset + limit]

        if df.empty:
            return {"status": True}

        if category == "new":
            add_asset_data_in_db(db=db, new_asset_data=df)
        elif category == "existing":
            update_asset_data_in_db(db=db, existing_asset_data=df)
        elif category == "missing":
            delete_asset_data_in_db(db=db, missing_asset_data=df)
        elif category == "inactive":
            remove_asset_data_in_db(db=db, missing_asset_data=df)
        elif category == "unpairing":
            delete_asset_data_in_db(db=db, missing_asset_data=df)
            add_asset_data_in_history(db=db, new_asset_data=df)
        elif category == "new_pairing":
            add_asset_data_in_db(db=db, new_asset_data=df)
        elif category == "fresh_pairing":
            update_new_pairing_data_in_db(db=db, update_new_pairing_data=df)

        return {"status": True}
    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False}
    finally:
        db.get_session().close()


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SendAssetSyncReport(input: dict):
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("assetsync-data")

        meta   = json.loads(container.get_blob_client("assets_cmp_report_meta.json").download_blob().readall())
        params = meta["params"]
        params["execution_time"] = datetime.fromisoformat(params["execution_time"])

        send_asset_sync_report(
            api_asset_list=pd.DataFrame(json.loads(meta["api_assets"])),
            new_asset_list=pd.DataFrame(json.loads(meta["new_assets"])),
            update_asset_list=pd.DataFrame(json.loads(meta["update_assets"])),
            error_asset_list=pd.DataFrame(json.loads(meta["error_assets"])),
            params=params,
        )
        return {"status": True}
    except Exception as e:
        logging.error(f"SendAssetSyncReport failed: {e}", exc_info=True)
        return {"status": False}


# ── SESSIONS ──────────────────────────────────────────────────────────────────

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def CompareSessions(input: dict):
    logger = logging.getLogger("compare_sessions")
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("sessionsync-data")

        session_db_data  = json.loads(container.get_blob_client("sessions_db_data.json").download_blob().readall())
        session_api_data = json.loads(container.get_blob_client("sessions_api_data.json").download_blob().readall())

        all_sessions_data_from_api = pd.DataFrame(session_api_data).replace({np.nan: None})
        all_sessions_data_from_db  = pd.DataFrame(session_db_data).replace({np.nan: None})

        if len(all_sessions_data_from_db) == 0:
            all_sessions_data_from_db["Session_Id"] = pd.Series(dtype="object")

        if all_sessions_data_from_api.empty:
            return {"status": True, "counts": {}, "api_total": 0}

        new_sessions_to_insert, sessions_to_update, sessions_to_deactivate = \
            get_new_existing_missing_sessions_data(
                db_dataframe=all_sessions_data_from_db,
                api_dataframe=all_sessions_data_from_api,
                logger=logger,
            )

        categories = {
            "new":        new_sessions_to_insert,
            "update":     sessions_to_update,
            "deactivate": sessions_to_deactivate,
        }
        for name, df in categories.items():
            container.get_blob_client(f"sessions_cmp_{name}.json").upload_blob(
                df.to_json(orient="records"), overwrite=True
            )

        env = os.environ["SCALAR_ENV"]
        report_meta = {
            "params": {
                "environment":               env,
                "exectution_time":           datetime.now().isoformat(),
                "sessions_from_db":          len(all_sessions_data_from_db),
                "sessions_from_api":         len(all_sessions_data_from_api),
                "new_sessions_added":        len(new_sessions_to_insert),
                "existing_sessions_updated": len(sessions_to_update),
                "deactivated_sessions":      len(sessions_to_deactivate),
            }
        }
        container.get_blob_client("sessions_cmp_report_meta.json").upload_blob(
            json.dumps(report_meta), overwrite=True
        )

        counts = {k: len(v) for k, v in categories.items()}
        logger.info(f"Session comparison complete: {counts}")
        return {"status": True, "counts": counts, "api_total": len(all_sessions_data_from_api)}

    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False, "counts": {}, "api_total": 0}


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncSessionsChunk(input: dict):
    logger = logging.getLogger("sync_sessions_chunk")
    db = Database()
    try:
        category = input["category"]
        offset   = input["offset"]
        limit    = input["limit"]

        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("sessionsync-data")

        raw = json.loads(container.get_blob_client(f"sessions_cmp_{category}.json").download_blob().readall())
        df  = pd.DataFrame(raw).replace({np.nan: None}).iloc[offset:offset + limit]

        if df.empty:
            return {"status": True}

        if category == "new":
            add_new_session_data_into_db(db=db, new_sessions_to_insert=df)
        elif category == "update":
            update_existing_sessions_data_into_db(db=db, sessions_to_update=df)
        elif category == "deactivate":
            deactivate_sessions_missing_in_api(db=db, sessions_to_deactivate=df)

        return {"status": True}
    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False}
    finally:
        db.get_session().close()


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SendSessionSyncReport(input: dict):
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("sessionsync-data")

        meta   = json.loads(container.get_blob_client("sessions_cmp_report_meta.json").download_blob().readall())
        params = meta["params"]
        params["exectution_time"] = datetime.fromisoformat(params["exectution_time"])

        send_session_sync_report(
            new_sessions_to_insert=pd.DataFrame(json.loads(container.get_blob_client("sessions_cmp_new.json").download_blob().readall())),
            sessions_to_update=pd.DataFrame(json.loads(container.get_blob_client("sessions_cmp_update.json").download_blob().readall())),
            sessions_to_deactivate=pd.DataFrame(json.loads(container.get_blob_client("sessions_cmp_deactivate.json").download_blob().readall())),
            params=params,
        )
        return {"status": True}
    except Exception as e:
        logging.error(f"SendSessionSyncReport failed: {e}", exc_info=True)
        return {"status": False}


# ── BRAKE PERFORMANCE ─────────────────────────────────────────────────────────

@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def CompareBrakePerformance(input: dict):
    logger = logging.getLogger("compare_bp")
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("brakeperformancesync-data")

        bp_db_data  = json.loads(container.get_blob_client("brakeperformance_db_data.json").download_blob().readall())
        bp_api_data = json.loads(container.get_blob_client("brakeperformance_api_data.json").download_blob().readall())

        bp_asset_list_from_api = pd.DataFrame(bp_api_data).replace({np.nan: None})
        bp_asset_list_from_db  = pd.DataFrame(bp_db_data).replace({np.nan: None})

        if len(bp_asset_list_from_db) == 0:
            bp_asset_list_from_db["assetId"] = pd.Series(dtype="object")
            bp_asset_list_from_db["Active"]   = pd.Series(dtype="object")

        if bp_asset_list_from_api.empty:
            return {"status": True, "counts": {}, "api_total": 0}

        new_bp_asset_data_df, existing_bp_asset_data_df, missing_bp_asset_data_df = \
            get_new_existing_bp_asset_data(bp_asset_list_from_db, bp_asset_list_from_api)

        categories = {
            "new":      new_bp_asset_data_df,
            "existing": existing_bp_asset_data_df,
            "missing":  missing_bp_asset_data_df,
        }
        for name, df in categories.items():
            container.get_blob_client(f"bp_cmp_{name}.json").upload_blob(
                df.to_json(orient="records"), overwrite=True
            )

        env = os.environ["SCALAR_ENV"]
        report_meta = {
            "params": {
                "environment":      env,
                "execution_time":   datetime.now().isoformat(),
                "total_asset":      len(bp_asset_list_from_api),
                "new_asset":        len(new_bp_asset_data_df),
                "existing_asset":   len(existing_bp_asset_data_df),
                "deactivate_asset": len(missing_bp_asset_data_df),
            },
            "api_assets":    bp_asset_list_from_api.to_json(orient="records"),
            "new_assets":    new_bp_asset_data_df.to_json(orient="records"),
            "update_assets": existing_bp_asset_data_df.to_json(orient="records"),
            "error_assets":  missing_bp_asset_data_df.to_json(orient="records"),
        }
        container.get_blob_client("bp_cmp_report_meta.json").upload_blob(
            json.dumps(report_meta), overwrite=True
        )

        counts = {k: len(v) for k, v in categories.items()}
        logger.info(f"Brake performance comparison complete: {counts}")
        return {"status": True, "counts": counts, "api_total": len(bp_asset_list_from_api)}

    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False, "counts": {}, "api_total": 0}


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SyncBrakePerformanceChunk(input: dict):
    logger = logging.getLogger("sync_bp_chunk")
    db = Database()
    try:
        category = input["category"]
        offset   = input["offset"]
        limit    = input["limit"]

        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("brakeperformancesync-data")

        raw = json.loads(container.get_blob_client(f"bp_cmp_{category}.json").download_blob().readall())
        df  = pd.DataFrame(raw).replace({np.nan: None}).iloc[offset:offset + limit]

        if df.empty:
            return {"status": True}

        if category == "new":
            add_brake_performance_data_in_db(db=db, new_brake_performance_asset_data=df)
        elif category == "existing":
            update_brake_performance_data_in_db(db=db, existing_brake_performance_asset_data=df)
        elif category == "missing":
            remove_brake_performance_asset_data_in_db(db=db, missing_brake_performance_asset_data=df)

        return {"status": True}
    except Exception as e:
        logger.error(e, exc_info=True)
        return {"status": False}
    finally:
        db.get_session().close()


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SendBrakePerformanceSyncReport(input: dict):
    try:
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        container   = blob_client.get_container_client("brakeperformancesync-data")

        meta   = json.loads(container.get_blob_client("bp_cmp_report_meta.json").download_blob().readall())
        params = meta["params"]
        params["execution_time"] = datetime.fromisoformat(params["execution_time"])

        send_bp_asset_sync_report(
            bp_api_asset_list=pd.DataFrame(json.loads(meta["api_assets"])),
            new_bp_asset_list=pd.DataFrame(json.loads(meta["new_assets"])),
            update_bp_asset_list=pd.DataFrame(json.loads(meta["update_assets"])),
            error_bp_asset_list=pd.DataFrame(json.loads(meta["error_assets"])),
            params=params,
        )
        return {"status": True}
    except Exception as e:
        logging.error(f"SendBrakePerformanceSyncReport failed: {e}", exc_info=True)
        return {"status": False}


@datasync_activities_chunk_bp.activity_trigger(input_name="input")
def SendCallback(input: dict):
    try:
        callback_url = input['callbackUrl']
        requests.post(callback_url,json=input['status'])
        return {"status":True}
    except Exception as e:
        logging.error(msg=str(e))
        return {"status":False}