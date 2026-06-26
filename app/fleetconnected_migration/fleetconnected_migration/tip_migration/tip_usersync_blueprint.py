from io import BytesIO
import os
import logging
import json
import pandas as pd
from datetime import datetime
import azure.functions as func
from sqlalchemy import and_
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User_App_Access, SC_User
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.models import Response
from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.common.exception_handler import global_exception_handler
from app.fleetconnected_migration.common.tx_tango.user_api import UserApi
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_all_users_from_db_for_org
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import cust_user_role_mapping, get_allusers_allroles_for_an_org, get_sky_users_for_customer
from app.users.user_datasync.usersync_services import sync_user_db

sync_SKY_TIP_User_bp = func.Blueprint()

@sync_SKY_TIP_User_bp.function_name(name="Sync_SKY_TIP_User")
@sync_SKY_TIP_User_bp.route(route="syncskytipuser",  methods=[func.HttpMethod.POST])
@global_exception_handler
def sync_SKY_TIP_user(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Sync_SKY_TIP_User")
    db = Database()
    fc_db = FleetConnectedDatabase()
    try:
        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")
        provider_organization_id = provider_organization[0]

        app_version = os.environ["APP_VERSION"]
        tenancy_dispatcher = os.environ["TENANCY_DISPATCHER"]
        tenancy_integrator = os.environ['TENANCY_INTEGRATOR']
        tenancy_system_nr = os.environ['TENANCY_SYSTEM_NR']
        tenancy_password = os.environ['TENANCY_PASSWORD']
        user_api = UserApi(  dispatcher=tenancy_dispatcher, 
                                            integrator=tenancy_integrator,
                                            system_nr=tenancy_system_nr,
                                            password=tenancy_password,
                                            version=app_version)
        all_tip_users_db_data = get_all_users_from_db_for_org(db=db, sc_org_id=provider_organization_id)
        all_tip_users_api_data, all_roles_api_data = get_allusers_allroles_for_an_org(db=db, scalar_org_id=provider_organization_id, scalar_org_name='TIP', logger=logger)
        
        inserted_users, updated_users, deleted_users, user_role_map, failed_users_df = sync_user_db(db=db, user_api_data=all_tip_users_api_data, user_db_data= all_tip_users_db_data, logger=logger)
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
        all_tip_users_sky_data = get_sky_users_for_customer(txTangoApi=user_api)
        matching_users_data_in_sky_scalar = all_tip_users_api_data[all_tip_users_api_data['emailAddress'].isin(all_tip_users_sky_data['Email'])]
        missing_users_data_in_sky = all_tip_users_api_data[~all_tip_users_api_data['emailAddress'].isin(all_tip_users_sky_data['Email'])]
        missing_users_data_in_scalar = all_tip_users_sky_data[~all_tip_users_sky_data['Email'].isin(all_tip_users_api_data['emailAddress'])]

        usersync_response = {
                "new_users_added": len(inserted_users),
                "existing_users_updated": len(updated_users),
                "deleted_users":len(deleted_users),
                "users_failed_to_sync": len(failed_users_df),
                "users_error_list": ([] if failed_users_df.empty else failed_users_df.values.tolist()),
                "users_for_role_mapping": len(users_roles_mapped),
                "users_failed_to_map_roles": len(failed_user_role_mapping),
                "user_role_mapping_error_list": ([] if failed_user_role_mapping.empty else failed_user_role_mapping.values.tolist()),
                "scalar_total_users": len(all_tip_users_api_data),
                "sky_total_users": len(all_tip_users_sky_data),
                "matching_users_data_in_sky_scalar": len(matching_users_data_in_sky_scalar),
                "missing_users_data_in_sky": len(missing_users_data_in_sky),
                "missing_users_data_in_scalar": len(missing_users_data_in_scalar)
        } 

        usersync_report = BytesIO()
        with pd.ExcelWriter(usersync_report, engine='xlsxwriter') as writer:
            if len(all_tip_users_api_data) > 0:
                column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                all_tip_users_api_data[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Total users from SCALAR', index=None, header=True)
            if len(all_tip_users_sky_data) > 0:
                all_tip_users_sky_data.to_excel(writer, sheet_name='Total users in SKY', index=None, header=True)
            if len(matching_users_data_in_sky_scalar) > 0:
                column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                matching_users_data_in_sky_scalar[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Matched users in SKY and Scalar', index=None, header=True)
            if len(missing_users_data_in_sky) > 0:
                column_order = ['userId','firstName','lastName','emailAddress','loginType','language','status','orgId','sc_orgName','roles']
                missing_users_data_in_sky[column_order].rename(columns={'orgId':'scalar_orgId','sc_orgName':'scalar_orgName'}).to_excel(writer, sheet_name='Missing users in SKY', index=None, header=True)
            if len(missing_users_data_in_scalar) > 0:
                missing_users_data_in_scalar.to_excel(writer, sheet_name='Missing users in Scalar', index=None, header=True)
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
        
        email = Email()
        receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        file_name = f"User_Sync_TIP_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        env = os.environ['SCALAR_ENV']
        subject = f"Scalar Migration - TIP user sync report - " + env
        template_name = 'TIP_usersync_report.html'
        
        usersync_response["environment"] = env
        usersync_response["exectution_time"] = datetime.now()
        attachment = None
        file_name = f"{file_name} - {datetime.now().strftime('%Y-%m-%d')}.xlsx"
        if usersync_report is not None:
            usersync_report.seek(0)
            attachment = usersync_report.read()
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=usersync_response, 
                            attachment=attachment, filename=file_name)
                            
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
        subject=f"Data Sync Error: TIP User sync report - " + env
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