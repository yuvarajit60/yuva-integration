from io import BytesIO
import json
import logging
import pandas as pd
import azure.functions as func
import os
from datetime import datetime
from app.common.email import Email
from app.users.user_datasync.usersync_data_access import get_all_users_from_db
from app.users.user_datasync.usersync_services import get_allusers_allroles_for_allorg, send_sync_report, sync_user_db, user_role_mapping
from app.common.exception_handler import global_exception_handler
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database

usersync_bp = func.Blueprint()

@usersync_bp.function_name(name="Sync_User_Data")
@usersync_bp.route(route="syncuserdata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def usersync_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("sync_user_data")
    db = Database()
    try:
        all_users_api_data, all_roles_api_data, all_orgs_count = get_allusers_allroles_for_allorg(db=db, logger=logger)
        all_users_db_data = get_all_users_from_db(db=db)
        inserted_users, updated_users, deleted_users, user_role_map, failed_users_df = sync_user_db(db=db, user_api_data=all_users_api_data, user_db_data= all_users_db_data, logger=logger)
        users_roles_mapped, failed_user_role_mapping = user_role_mapping(db=db, roles_api_data=all_roles_api_data, user_role_map=user_role_map, logger=logger)

        usersync_response = {
                "total_users_to_be_synced": len(all_users_api_data),
                "new_users_added": len(inserted_users),
                "existing_users_updated": len(updated_users),
                "deleted_users":len(deleted_users),
                "users_failed_to_sync": len(failed_users_df),
                "organization_count": all_orgs_count,
                "users_error_list": ([] if failed_users_df.empty else failed_users_df.values.tolist()),
                "users_for_role_mapping": len(users_roles_mapped),
                "users_failed_to_map_roles": len(failed_user_role_mapping),
                "user_role_mapping_error_list": ([] if failed_user_role_mapping.empty else failed_user_role_mapping.values.tolist())
        } 
    
        if all_orgs_count > 0:
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

        return func.HttpResponse(
            json.dumps(usersync_response, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: User sync report"
        if os.environ['SCALAR_ENV'] != 'PROD':
            subject=f"{subject} - {env}"
        template_name='error_user_email.html'
        

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )