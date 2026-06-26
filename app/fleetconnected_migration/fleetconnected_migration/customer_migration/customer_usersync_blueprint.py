from io import BytesIO
import os
import logging
import json
import azure.functions as func
import pandas as pd
from datetime import datetime
from sqlalchemy import and_

from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User_App_Access, SC_User
from app.common.models import Response
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_consumer_organization_data

from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.fleetconnected_migration.common.tx_tango.user_api import UserApi
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_all_users_from_db_for_org,get_subcontracted_tenancy_record
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import cust_user_role_mapping, get_allusers_allroles_for_an_org, get_sky_users_for_customer, send_sky_scalar_usersync_report
from app.users.user_datasync.usersync_services import sync_user_db

customer_usersync_bp = func.Blueprint() 

@customer_usersync_bp.function_name(name="Sync_SKY_Customer_Users")
@customer_usersync_bp.route(route="syncskycustomerusers",  methods=[func.HttpMethod.POST])
@global_exception_handler
def user_datasync(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Sync_SKY_Customer_Users")
    db = Database()
    fc_db = FleetConnectedDatabase()
    try:
        fa_root_org_id_list = req.get_json().get('faRootOrgIds')

        app_version = os.environ["APP_VERSION"]
        tenancy_dispatcher = os.environ["CUST_TENANCY_DISPATCHER"]
        tenancy_integrator = os.environ['CUST_TENANCY_INTEGRATOR']
        tenancy_password = os.environ['CUST_TENANCY_PASSWORD']
        errors ={}

        usersync_response = list()

        for fa_root_org_id in fa_root_org_id_list:
            try:
                sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
                if sc_org_details_df.empty:
                    raise Exception(f'Scalar Organization details not found for FA Root Organization id {fa_root_org_id}')
                sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
                sc_org_name = sc_org_details_df.loc[0,'Organization_Name']
                ZF_customer = sc_org_details_df.loc[0,'ZF_Consumer_Org']
                if ZF_customer == 1:
                    usersync_response.append({"Message": f"No user sync for ZF/shared Customer {sc_org_name}"})
                    mail_parms = {"fa_root_org_id": fa_root_org_id,
                                "sc_organization_name": sc_org_name,
                                "new_users_added": 'NA',
                                "existing_users_updated": 'NA',
                                "deleted_users":'NA',
                                "users_failed_to_sync": 'NA',
                                "users_error_list": 'NA',
                                "users_for_role_mapping": 'NA',
                                "users_failed_to_map_roles": 'NA',
                                "user_role_mapping_error_list": 'NA',
                                "scalar_total_users": 'NA',
                                "zf_consumer_flag": 'Yes',
                                "sky_total_users": 'NA',
                                "matching_users_data_in_sky_scalar": 'NA',
                                "missing_users_data_in_sky": 'NA',
                                "missing_users_data_in_scalar": 'NA'
                            }
                    subject = f"Scalar Migration - Customer user sync report for {sc_org_name[:36]} (ZF/Shared customer) - "
                    send_sky_scalar_usersync_report(usersync_report=None, params=mail_parms, org_name=sc_org_name, subject=subject)
                    continue

                subcontracting_tenancy_record = get_subcontracted_tenancy_record(fc_db=fc_db, root_org_id=fa_root_org_id)
                if subcontracting_tenancy_record is None:
                    raise Exception(f'{sc_org_name} with FA Root Organization id {fa_root_org_id} is not a sky customer (or) tenancy not populated')
                tenancy_system_nr = subcontracting_tenancy_record[0]
                user_api = UserApi(  dispatcher=tenancy_dispatcher, 
                                        integrator=tenancy_integrator,
                                        system_nr=tenancy_system_nr,
                                        password=tenancy_password,
                                        version=app_version)

                all_users_db_data = get_all_users_from_db_for_org(db=db, sc_org_id=sc_org_id)
                all_users_api_data, all_roles_api_data = get_allusers_allroles_for_an_org(db=db, scalar_org_id=sc_org_id, scalar_org_name=sc_org_name, logger=logger)
                
                inserted_users, updated_users, deleted_users, user_role_map, failed_users_df = sync_user_db(db=db, user_api_data=all_users_api_data, user_db_data= all_users_db_data, logger=logger)
                users_to_insert_update = inserted_users['UserId'].tolist() + updated_users['UserId'].tolist()
                records = db.get_session().query(
                            SC_User.FA_User_Id,FA_User_App_Access).outerjoin(
                                FA_User_App_Access, 
                                and_(   
                                    FA_User_App_Access.User_Id == SC_User.FA_User_Id, 
                                    FA_User_App_Access.Application_Id == 4)
                                    ).filter(
                                        SC_User.User_Id.in_(users_to_insert_update)
                                        ).all()
                for fa_user_id,fa_user_app_access_record in records:
                    if fa_user_app_access_record is None and fa_user_id is not None:
                        db.get_session().add(FA_User_App_Access(
                            User_Id = fa_user_id,
                            Application_Id = 4,
                            Active = 1
                        ))
                    elif fa_user_app_access_record is not None:
                        fa_user_app_access_record.Active = 1
                db.get_session().commit()
                users_to_delete = deleted_users['UserId'].tolist()
                records = db.get_session().query(
                            SC_User.FA_User_Id,FA_User_App_Access).outerjoin(
                                FA_User_App_Access, 
                                and_(   
                                    FA_User_App_Access.User_Id == SC_User.FA_User_Id, 
                                    FA_User_App_Access.Application_Id == 4)
                                    ).filter(
                                        SC_User.User_Id.in_(users_to_delete)
                                        ).all()
                for fa_user_id,fa_user_app_access_record in records:
                    if fa_user_app_access_record is None and fa_user_id is not None:
                        db.get_session().add(FA_User_App_Access(
                            User_Id = fa_user_id,
                            Application_Id = 4,
                            Active = 0
                        ))
                    elif fa_user_app_access_record is not None:
                        fa_user_app_access_record.Active = 0
                db.get_session().commit()
                users_roles_mapped, failed_user_role_mapping = cust_user_role_mapping(db=db, roles_api_data=all_roles_api_data, user_role_map=user_role_map, logger=logger)

                mail_parms = {"fa_root_org_id": fa_root_org_id,
                                "sc_organization_name": sc_org_name,
                                "new_users_added": len(inserted_users),
                                "existing_users_updated": len(updated_users),
                                "deleted_users":len(deleted_users),
                                "users_failed_to_sync": len(failed_users_df),
                                "users_error_list": ([] if failed_users_df.empty else failed_users_df.values.tolist()),
                                "users_for_role_mapping": len(users_roles_mapped),
                                "users_failed_to_map_roles": len(failed_user_role_mapping),
                                "user_role_mapping_error_list": ([] if failed_user_role_mapping.empty else failed_user_role_mapping.values.tolist()),
                                "scalar_total_users": len(all_users_api_data)
                            }

                usersync_report = BytesIO()
                with pd.ExcelWriter(usersync_report, engine='xlsxwriter') as writer:
                    if len(all_users_api_data) > 0:
                        column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                        all_users_api_data[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Total users from SCALAR', index=None, header=True)
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

                    if subcontracting_tenancy_record[4] == 1:

                        mail_parms.update({"zf_consumer_flag": 'Yes',
                                    "sky_total_users": 'NA',
                                    "matching_users_data_in_sky_scalar": 'NA',
                                    "missing_users_data_in_sky": 'NA',
                                    "missing_users_data_in_scalar": 'NA'
                                })
                    else:
                        all_users_sky_data = get_sky_users_for_customer(txTangoApi=user_api)
                        if type(all_users_sky_data) == dict:
                            message = f'Error while fetching SKY data: {all_users_sky_data}'
                            raise Exception(message)

                        matching_users_data_in_sky_scalar = all_users_api_data[all_users_api_data['emailAddress'].isin(all_users_sky_data['Email'])]
                        missing_users_data_in_sky = all_users_api_data[~all_users_api_data['emailAddress'].isin(all_users_sky_data['Email'])]
                        missing_users_data_in_scalar = all_users_sky_data[~all_users_sky_data['Email'].isin(all_users_api_data['emailAddress'])]

                        mail_parms.update({"zf_consumer_flag": 'No',
                                    "sky_total_users": len(all_users_sky_data),
                                    "matching_users_data_in_sky_scalar": len(matching_users_data_in_sky_scalar),
                                    "missing_users_data_in_sky": len(missing_users_data_in_sky),
                                    "missing_users_data_in_scalar": len(missing_users_data_in_scalar)
                                    })

                        if len(all_users_sky_data) > 0:
                            all_users_sky_data.to_excel(writer, sheet_name='Total users in SKY', index=None, header=True)
                        if len(matching_users_data_in_sky_scalar) > 0:
                            column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                            matching_users_data_in_sky_scalar[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Matched users in SKY and Scalar', index=None, header=True)
                        if len(missing_users_data_in_sky) > 0:
                            column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                            missing_users_data_in_sky[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Missing users in SKY', index=None, header=True)
                        if len(missing_users_data_in_scalar) > 0:
                            missing_users_data_in_scalar.to_excel(writer, sheet_name='Missing users in Scalar', index=None, header=True)

                send_sky_scalar_usersync_report(usersync_report=usersync_report, params=mail_parms, org_name=sc_org_name)
                usersync_response.append(mail_parms) 
                
            except Exception as e:
                logger.error(e, exc_info=True)
                errors[fa_root_org_id] = str(e)
                env = os.environ['SCALAR_ENV']
                email=Email()
                receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
                subject=f"Data Sync Error: Customer User sync for {sc_org_name[:36]} - " + env
                template_name='error_user_email.html'

                error_params={"environment": env, 
                "execution_time": datetime.now(),
                "error_message": str(e),
                }

                email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
                status_code=getattr(e,'status_code',500)
                response = Response(message=str(e), status=False).getJsonResponse()
                return func.HttpResponse(
                    response,
                    status_code=status_code,
                    mimetype=ContentType.APPLICATION_JSON
                )

        return func.HttpResponse(
        json.dumps(usersync_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)

    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject=f"Data Sync Error: Customer User sync report - " + env
        template_name='error_user_email.html'

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        response = Response(message=str(e), status=False).getJsonResponse()
        return func.HttpResponse(
            response,
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )
