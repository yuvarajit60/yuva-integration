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
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_consumer_organization_data
from app.common.helpers.common_services import fetch_access_token
from app.common.models import Response
from app.common.email import Email
from app.common.helpers.user_helpers import user_assignment

from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_all_fa_users_in_a_scalar_organization
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_user_team_assetgroup_mapping

from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import send_customer_user_assignment_error_report

customer_user_assignment_bp = func.Blueprint()
@customer_user_assignment_bp.function_name(name="Customer_User_Assignment")
@customer_user_assignment_bp.route(route="customer/userassignment",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customer_user_assignment_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Customer_User_Assignment")
    db = Database()
    message = ""
    try:
        fa_root_org_id_list = req.get_json().get('faRootOrgIds')
        if len(fa_root_org_id_list) == 0:
            message = f"No FA Root Organizations specified for user assignment"
            logger.warning(message)
            raise ScalarException(message=message, response_code=ResponseCode.BAD_REQUEST)

        invalid_org_ids = set()
        assignment_successful_orgs = set()
        assignment_failed_orgs = set()

        api_response = list()
        email = Email()
        receivers = os.environ['MIGRATION_REPORT_MAIL_DL'].split(",")
        env = os.environ['SCALAR_ENV']

        for fa_root_org_id in fa_root_org_id_list:
            if fa_root_org_id is None or not str(fa_root_org_id).isnumeric():
                invalid_org_ids.add(fa_root_org_id)
                api_response.append({"User Assignment Error": f"Invalid Organization ID ({fa_root_org_id})"})
                continue

            scalar_org_df = get_consumer_organization_data(db=db,fa_root_org_id=fa_root_org_id)
            if scalar_org_df is None or len(scalar_org_df) == 0:
                assignment_failed_orgs.add(fa_root_org_id)
                message = f"Scalar organization details not found for Root Organization ID ({fa_root_org_id})"
                send_customer_user_assignment_error_report(error_message=message, org_name="Unknown Org")
                api_response.append({"User Assignment Error": message})
                continue
                
            sc_org_id = scalar_org_df.loc[0,'Organization_Id']
            org_name = scalar_org_df.loc[0, 'Organization_Name']

            if scalar_org_df.loc[0,'ZF_Consumer_Org'] == 1:
                msg = f"ZF-Shared customer(ID: {fa_root_org_id}). User assignment not done."
                logger.info(msg)
                api_response.append({"User Assignment": msg})
                subject = f"Scalar Migration - Customer user assignment report for {org_name[:36]} (ZF/Shared customer) - " + env
                template_name = "customer_user_assignment.html"
                
                mail_params = {"environment": env,
                            "execution_time": datetime.now(),
                            "root_org_id":fa_root_org_id,
                            "root_org_name": org_name,
                            "total_distinct_scalar_users_found_in_the_org":'NA',
                            "total_distinct_active_fa_customer_scalar_users_selected_for_assignment": 'NA',
                            "total_user_assignment_count":'NA',
                            "assignment_successful_user_count": 'NA',
                            "assignment_failed_user_count": 'NA'
                            }

                email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=mail_params, 
                                    attachment=None, filename=None)
                continue

            tmapi_access_token = fetch_access_token(db=db, org_id=sc_org_id, audience=AudienceCode.TEAMS)
            #Fetch all TIP users from FA_User table
            all_scalar_users_df = get_all_fa_users_in_a_scalar_organization(db=db, sc_org_id=sc_org_id)

            if all_scalar_users_df is None or len(all_scalar_users_df) == 0:
                message = f"No Users found in Root org ID ({fa_root_org_id})"
                logger.error(message)
                send_customer_user_assignment_error_report(error_message = message, org_name=org_name)
                api_response.append({"User Assignment Failed": message})
                assignment_failed_orgs.add(fa_root_org_id)
                continue

            # Filter out empty FA user id rows
            all_scalar_users_df = all_scalar_users_df.replace('<NA>', pd.NA)
            users_to_assign_df = all_scalar_users_df.loc[all_scalar_users_df['FA_User_Id'].notna()]

            # If no FA-Scalar users found in org to assign, stop execution and send mail with found users
            if users_to_assign_df is None or len(users_to_assign_df) == 0:
                message = f"FleetAdmin users not migrated to Scalar for Root org ID ({fa_root_org_id}). Mapping not found for user assignment."
                logger.error(message)
                assignment_failed_orgs.add(fa_root_org_id)

                control_report = BytesIO()
                with pd.ExcelWriter(control_report, engine='xlsxwriter') as writer:
                    if len(all_scalar_users_df) > 0:
                        all_scalar_users_df.to_excel(writer, sheet_name='All Scalar Users in Org', index=None, header=True)
                                        
                file_name = f"{org_name}_User_Assignment_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
                subject = f"Scalar Migration - Customer user assignment report for {org_name[:36]} - " + env
                template_name = "customer_user_assignment_error_report.html"
                
                mail_params = { "environment": os.environ['SCALAR_ENV'],
                                "execution_time": datetime.now(),
                                "root_org_id":fa_root_org_id,
                                "root_org_name": org_name,
                                "total_users_found_in_the_org":len(all_scalar_users_df)
                                } 

                attachment = None
                if control_report is not None:
                    control_report.seek(0)
                    attachment = control_report.read()
                email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=mail_params, 
                                    attachment=attachment, filename=file_name)
                api_response.append({"User Assignment": f"No FleetAdmin to Scalar migrated users found in Root organization {fa_root_org_id}"})
                continue

            assignment_failed_dataframe = pd.DataFrame(columns=["FA_User_Id", "FA_Org_Id", "SC_User_Id", 
                                                        "Error_Message"])

            assignment_successful_dataframe = pd.DataFrame(columns=["FA_User_Id", "FA_Org_Id", "SC_User_Id", 
                                                        "Message"])
                
            for index, row in users_to_assign_df.iterrows():

                user = CreateUser.Schema().loads(json.dumps({"faUserId": row['FA_User_Id']}))

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
                                                             pd.DataFrame([{'FA_User_Id': row['FA_User_Id'], 'FA_Org_Id': row['FA_Organization_Id'],
                                                                            'SC_User_Id': row['SC_User_Id'], 'SC_User_Email': row['SC_User_Email'],
                                                                            'Error_Message': message_dict["error"]}])
                                                            ], ignore_index=True)
                    
                else:
                    assignment_successful_orgs.add(fa_root_org_id)
                    assignment_successful_dataframe = pd.concat([assignment_successful_dataframe, 
                                                                 pd.DataFrame([{'FA_User_Id': row['FA_User_Id'], 'FA_Org_Id': row['FA_Organization_Id'],
                                                                                'SC_User_Id': row['SC_User_Id'], 'Message': message_dict["success"]}])
                                                                ], ignore_index=True)

            user_team_assetgroup_mapping_df = get_user_team_assetgroup_mapping(db=db, sc_org_id=sc_org_id, tip_user=['N', 'n'])
            user_unassigned_team_assetgroup_df = user_team_assetgroup_mapping_df.loc[\
                pd.isnull(user_team_assetgroup_mapping_df['Team_Id']) | pd.isnull(user_team_assetgroup_mapping_df['Asset_Group_Id'])]

            control_report = BytesIO()
            with pd.ExcelWriter(control_report, engine='xlsxwriter') as writer:
                if len(all_scalar_users_df) > 0:
                    all_scalar_users_df.to_excel(writer, sheet_name='All Scalar Users in Org', index=None, header=True)
                if len(users_to_assign_df) > 0:
                    users_to_assign_df.to_excel(writer, sheet_name='Users Selected for Assignment', index=None, header=True)
                if len(user_team_assetgroup_mapping_df) > 0:
                    user_team_assetgroup_mapping_df.to_excel(writer, sheet_name='Mapping After Assignment', index=None, header=True)
                if len(assignment_failed_dataframe) > 0:
                    assignment_failed_dataframe.to_excel(writer, sheet_name='User Assignment failed', index=None, header=True)
                if len(user_unassigned_team_assetgroup_df) > 0:
                    user_unassigned_team_assetgroup_df.to_excel(writer, sheet_name='User not assigned', index=None, header=True)        
            
            file_name = f"{org_name}_User_Assignment_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
            subject = f"Scalar Migration - Customer user assignment report for {org_name[:36]} - "+env
            template_name = "customer_user_assignment.html"
            
            mail_params = { "environment": os.environ['SCALAR_ENV'],
                            "execution_time": datetime.now(),
                            "root_org_id":fa_root_org_id,
                            "root_org_name": org_name,
                            "total_distinct_scalar_users_found_in_the_org":len(all_scalar_users_df.drop_duplicates(subset='SC_User_Id')),
                            "total_distinct_active_fa_customer_scalar_users_selected_for_assignment": len(users_to_assign_df.drop_duplicates(subset='SC_User_Id')),
                            "total_user_assignment_count":len(users_to_assign_df),
                            "assignment_successful_user_count": len(assignment_successful_dataframe),
                            "assignment_failed_user_count": len(assignment_failed_dataframe)
                            } 

            api_response.append(mail_params)

            attachment = None
            if control_report is not None:
                control_report.seek(0)
                attachment = control_report.read()
            email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=mail_params, 
                                attachment=attachment, filename=file_name)
                                    
        return func.HttpResponse(
            json.dumps(api_response, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        send_customer_user_assignment_error_report(error_message = repr(e), org_name=org_name)
        response = Response(message=str(e), status=False).getJsonResponse()
        return func.HttpResponse(
            response,
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )