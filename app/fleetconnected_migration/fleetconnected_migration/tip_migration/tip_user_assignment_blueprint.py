import logging
import azure.functions as func
import json
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

from app.common.constants import AudienceCode, ContentType, ResponseCode
from app.common.database import Database
from app.common.func_validator import CreateUser
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token
from app.common.models import Response
from app.common.email import Email
from app.common.helpers.user_helpers import user_assignment

from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_all_tip_fa_users, get_user_team_assetgroup_mapping

tip_user_assignment_bp = func.Blueprint()
@tip_user_assignment_bp.function_name(name="Tip_User_Assignment")
@tip_user_assignment_bp.route(route="tip/userassignment",  methods=[func.HttpMethod.POST])
@global_exception_handler
def tip_user_assignment(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Tip_User_Assignment")
    db = Database()
    try:
        provider_org_id = get_tip_provider_organization(db=db)[0]
        tmapi_access_token = fetch_access_token(db=db, org_id=provider_org_id, audience=AudienceCode.TEAMS)
        #Fetch all TIP users from FA_User table
        all_scalar_users_df = get_all_tip_fa_users(db=db, sc_org_id=provider_org_id)
        users_to_assign_df = all_scalar_users_df.loc[all_scalar_users_df['User_Id'].notna()]

        assignment_failed_dataframe = pd.DataFrame(columns=["FA_User_Id", "FA_Org_Id", "SC_User_Id", 
                                                     "Error_Message"])
        assignment_successful_dataframe = pd.DataFrame(columns=["FA_User_Id", "FA_Org_Id", "SC_User_Id", 
                                                    "Message"])
            
        for index, row in users_to_assign_df.iterrows():

            user = CreateUser.Schema().loads(json.dumps({"faUserId": row['User_Id']}))

            #User assignment starts here 
            message_dict = user_assignment(db=db, 
                                sc_org_id=row['SC_Organization_Id'], 
                                user=user, 
                                fa_user_dict=dict(row), 
                                tmapi_access_token=tmapi_access_token, 
                                scalar_user_id=row['SC_User_Id'], 
                                logger=logger)

            if "error" in message_dict:
                assignment_failed_dataframe = pd.concat([assignment_failed_dataframe, 
                                                         pd.DataFrame([{'FA_User_Id': row['User_Id'], 
                                                                        'FA_Org_Id': row['Organization_Id'],
                                                                        'SC_User_Id': row['SC_User_Id'], 
                                                                        'SC_User_Email': row['SC_User_Email'],
                                                                        'Error_Message': message_dict["error"]}])
                                                        ], ignore_index=True)
                
            else:
                assignment_successful_dataframe = pd.concat([assignment_successful_dataframe, 
                                                             pd.DataFrame([{'FA_User_Id': row['User_Id'], 
                                                                            'FA_Org_Id': row['Organization_Id'],
                                                                            'SC_User_Id': row['SC_User_Id'], 
                                                                            'Message': message_dict["success"]}])
                                                            ], ignore_index=True)
                                
        user_assignment_stats = { "total_scalar_users_found_in_tip":len(all_scalar_users_df),
                                    "total_users_selected_for_assignment":len(users_to_assign_df),
                                  "assignment_successful_user_count": len(assignment_successful_dataframe),
                                  "assignment_failed_user_count": len(assignment_failed_dataframe)
                            } 
                            
        user_team_assetgroup_mapping_df = get_user_team_assetgroup_mapping(db=db, sc_org_id=provider_org_id, tip_user=['Y', 'y'])
        control_report = BytesIO()
        with pd.ExcelWriter(control_report, engine='xlsxwriter') as writer:
            if len(all_scalar_users_df) > 0:
                all_scalar_users_df.to_excel(writer, sheet_name='All Scalar Users in TIP', index=None, header=True)
            if len(users_to_assign_df) > 0:
                users_to_assign_df.to_excel(writer, sheet_name='Users Selected for Assignment', index=None, header=True)
            if len(user_team_assetgroup_mapping_df) > 0:
                user_team_assetgroup_mapping_df.to_excel(writer, sheet_name='Mapping After Assignment', index=None, header=True)
            if len(assignment_failed_dataframe) > 0:
                assignment_failed_dataframe.to_excel(writer, sheet_name='User Assignment failed', index=None, header=True)
            
        email = Email()
        receivers = os.environ['MIGRATION_REPORT_MAIL_DL'].split(",")
        env = os.environ['SCALAR_ENV']
        file_name = f"TIP_User_Assignment_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        subject = f"Scalar Migration - TIP user assignment: Assigning TIP user to teams report - " + env
        template_name = "tip_user_assignment.html"
        
        mail_params = { "environment": os.environ['SCALAR_ENV'],
                            "execution_time": datetime.now(),
                            "total_distinct_scalar_users_found":len(all_scalar_users_df.drop_duplicates(subset='SC_User_Id')),
                            "total_distinct_active_fa_scalar_users_selected_for_assignment": len(users_to_assign_df.drop_duplicates(subset='SC_User_Id')),
                            "total_user_assignment_count":len(users_to_assign_df),
                            "user_assignment_successful_count": len(assignment_successful_dataframe),
                            "user_assignment_failed_count": len(assignment_failed_dataframe)
                            } 

        attachment = None
        if control_report is not None:
            control_report.seek(0)
            attachment = control_report.read()
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=mail_params, 
                            attachment=attachment, filename=file_name)

        return func.HttpResponse(
            json.dumps(user_assignment_stats, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    
    except Exception as e:
        logger.error(e)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject = f"Scalar Migration - User assignment error: Assigning TIP user to teams report - " + env
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