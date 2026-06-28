import json
import logging
import os
import azure.durable_functions as df
from azure.storage.blob import BlobServiceClient
import pandas as pd
from sqlalchemy import text
from datetime import datetime, timedelta

from app.common.database import Database
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_all_organizations

datasync_orc_bp = df.Blueprint()

@datasync_orc_bp.orchestration_trigger(context_name="context")
def test_orc_func(context: df.DurableOrchestrationContext):
    job_name = yield context.call_activity("test_activity", None)
    return job_name

@datasync_orc_bp.orchestration_trigger(context_name="context")
def datasync_orc_func(context: df.DurableOrchestrationContext):
    data = context.get_input()
    process_name = data.get("processName")
    callback_url = data.get("callbackUrl")
    message = "Invalid process name"
    db = Database()
    if process_name == "User_Data_Sync":
        orgs_data = yield context.call_activity("GetAllOrgs",None)
        org_list=pd.DataFrame(orgs_data['org_list'])
        org_count = orgs_data['org_count']
        batch_size = 5
        all_users = []
        all_roles = []
        errors = []
        for i in range(0, org_count, batch_size):
            batch = org_list[i:i+batch_size].to_dict(orient='records')
            tasks = [context.call_activity("GetCustomerUsers", customer) for customer in batch]
            results = yield context.task_all(tasks)
            for r in results:
                if r.get("status"):
                    all_users.extend(r['users'])
                    all_roles.extend(r['roles'])
                else:
                    errors.append(r)
            context.set_custom_status({"fetched_orgs": i+len(batch),
                                       "success_count":len(all_users),
                                       "failure_count":len(errors)
                                       })
            if i+batch_size < org_count:
                yield context.create_timer(context.current_utc_datetime+timedelta(seconds=10))
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        if len(errors) > 0:
            container = blob_client.get_container_client("job-status")
            try: 
                container.create_container()
            except:
                pass
            blob = container.get_blob_client(f"{process_name}.txt")
            blob.upload_blob(json.dumps(errors, indent=4), overwrite=True)
            message = "User data collection failed"
        else:
            container = blob_client.get_container_client("usersync-data")
            try: 
                container.create_container()
            except:
                pass
            user_blob = container.get_blob_client(f"user_details.json")
            user_blob.upload_blob(json.dumps(all_users, indent=4), overwrite=True)
            role_blob = container.get_blob_client(f"role_details.json")
            role_blob.upload_blob(json.dumps(all_roles, indent=4), overwrite=True)
            usersync_status = yield context.call_activity("SyncUsers", {"users": "user_details.json","roles": "role_details.json","org_count": org_count})
            if usersync_status.get("status")==True:
                message = "User sync successful"
            else:
                message = "User sync failed"
    
    elif process_name == "Asset_Data_Sync":
        assets_data = yield context.call_activity("GetAllAssets",None)
        if assets_data.get("status"):
            assetsync_status = yield context.call_activity("SyncAssets", {"asset_list_from_db": "assets_db_data.json","asset_list_from_api": "assets_api_data.json"})
            if assetsync_status.get("status")==True:
                message = "Asset sync successful"
                context.set_custom_status(assetsync_status)
            else:
                message = "Asset sync failed"
        else:
            message = "Asset data collection failed"
    
    elif process_name == "Session_Data_Sync":
        sessions_data = yield context.call_activity("GetAllSessions",None)
        if sessions_data.get("status"):
            sessionsync_status = yield context.call_activity("SyncSessions", {"all_sessions_data_from_db": "sessions_db_data.json","all_sessions_data_from_api": "sessions_api_data.json"})
            if sessionsync_status.get("status")==True:
                message = "Session sync successful"
                context.set_custom_status(sessionsync_status)
            else:
                message = "Session sync failed"
        else:
            message = "Session data collection failed"

    elif process_name == "BrakePerformance_Data_Sync":
        assets_data = yield context.call_activity("GetAllBpAssets",None)
        if assets_data.get("status"):
            assetsync_status = yield context.call_activity("SyncBrakePerformance", {"bp_asset_list_from_db": "brakeperformance_db_data.json","bp_asset_list_from_api": "brakeperformance_api_data.json"})
            if assetsync_status.get("status")==True:
                message = "Brake Performance sync successful"
                context.set_custom_status(assetsync_status)
            else:
                message = "Brake Performance sync failed"
        else:
            message = "Brake Performance data collection failed"

    elif process_name == "User_Sync_Queue":
        orgs_data = yield context.call_activity("GetAllOrgs",None)
        org_list=pd.DataFrame(orgs_data['org_list'])
        org_count = orgs_data['org_count']
        batch_size = 5
        all_users = []
        all_roles = []
        errors = []
        for i in range(0, org_count, batch_size):
            batch = org_list[i:i+batch_size].to_dict(orient='records')
            tasks = [context.call_activity("GetCustomerUsers", customer) for customer in batch]
            results = yield context.task_all(tasks)
            for r in results:
                if r.get("status"):
                    all_users.extend(r['users'])
                    all_roles.extend(r['roles'])
                else:
                    errors.append(r)
            context.set_custom_status({"fetched_orgs": i+len(batch),
                                       "success_count":len(all_users),
                                       "failure_count":len(errors)
                                       })
            if i+batch_size < org_count:
                yield context.create_timer(context.current_utc_datetime+timedelta(seconds=10))
        blob_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
        if len(errors) > 0:
            container = blob_client.get_container_client("job-status")
            try: 
                container.create_container()
            except:
                pass
            error_blob = container.get_blob_client(f"{process_name}.txt")
            error_blob.upload_blob(json.dumps(errors, indent=4), overwrite=True)
            message = "User sync failed"
        else:
            container = blob_client.get_container_client("usersync-data")
            try: 
                container.create_container()
            except:
                pass
            user_blob = container.get_blob_client(f"user_details.json")
            user_blob.upload_blob(json.dumps(all_users, indent=4), overwrite=True)
            role_blob = container.get_blob_client(f"role_details.json")
            role_blob.upload_blob(json.dumps(all_roles, indent=4), overwrite=True)
            usersync_status = yield context.call_activity("SyncDbQueue", {"users": "user_details.json","roles": "role_details.json","org_count": org_count})
            if usersync_status.get("status")==True:
                message = "User sync process queued"
            else:
                message = "User sync failed"

    callback_status = yield context.call_activity("SendCallback", {"callbackUrl":callback_url,"status":message})
    if callback_status.get("status")==False:
        message += ", Sending callback failed."
    else:
        message += ", Callback sent succesfully."
    return message