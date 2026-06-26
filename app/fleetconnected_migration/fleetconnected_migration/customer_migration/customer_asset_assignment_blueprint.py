import json
import logging
import azure.functions as func
import os
from datetime import datetime

import pandas as pd

from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import  get_fa_organization_details, get_tip_provider_organization, get_consumer_organization_data
from app.common.models import Response
from app.common.email import Email
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import  get_scalar_assets_for_fa_root_org, get_units_for_fa_org_id
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import asset_assignment_with_asset_group, send_customer_asset_assignment_error_report, send_customer_asset_assignment_report

customer_asset_assignment_bp = func.Blueprint()
@customer_asset_assignment_bp.function_name(name="Customer_Asset_Assignment")
@customer_asset_assignment_bp.route(route="customer/assetassignment",  methods=[func.HttpMethod.POST])
@global_exception_handler
def consumer_asset_assignment_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("consumer_asset_Assignment")
    db = Database()
    message = {}
    asset_assignment_issue = pd.DataFrame(columns=['Asset_Group_Id','Asset_Group_Name','Asset_Ids','Error_Message'])
    try:
        faRootOrgIds = req.get_json().get('faRootOrgIds')
        invalid_input = True
        for value in faRootOrgIds:
            if not str(value).isnumeric():
                invalid_input = False
        if not invalid_input:
            message = f"Please provide valid FA root organization id."
            logger.warning(message)
            response = Response(status=True, message=message).getJsonResponse()
            return func.HttpResponse(
                    response,
                    status_code=ResponseCode.BAD_REQUEST,
                    mimetype=ContentType.APPLICATION_JSON
                )
        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")
        provider_org_id = provider_organization[0]

        successful_orgs = list()
        failed_orgs = list()

        api_response = list()

        email = Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        template_name='customer_asset_assignment.html'

        for faRootOrgId in faRootOrgIds:
            fa_org_details_df= get_fa_organization_details(db= db, fa_org_id= faRootOrgId)
            if len(fa_org_details_df)==0:
                org_message=f"Organization details not found in Fleet admin for FA_Root_OrgId: {faRootOrgId}."
                logger.error(org_message)
                failed_orgs.append(faRootOrgId)
                send_customer_asset_assignment_error_report(org_name= " FA_Root_OrgId: "+ str(faRootOrgId), error= org_message,asset_assignment_issue= asset_assignment_issue)
                continue

            fa_org_details_dict = fa_org_details_df.to_dict('records')[0]
            org_name = fa_org_details_dict["Organization_Name"]

            consumer_details = get_consumer_organization_data(db=db, fa_root_org_id=faRootOrgId)
            if consumer_details is None or len(consumer_details) == 0:
                raise Exception(f'Scalar Organization details not found for FA Root Organization id {faRootOrgId}')
            
            if consumer_details is not None and len(consumer_details) > 0:
                if consumer_details['ZF_Consumer_Org'][0] == 1:
                    msg = f"ZF-Shared customer (ID: {faRootOrgId}). Asset assignment not done."
                    logger.info(msg)
                    api_response.append({"Message": msg})
                    subject = f"Scalar Migration - Customer asset assignment report for {org_name[:36]} (ZF/Shared customer) - " + env
                    
                    params={"environment": env, 
                    "execution_time": datetime.now(),
                    "root_org_id" : faRootOrgId,
                    "root_org_name": org_name,
                    "total_active_assets_in_scalar" : 'NA',
                    "total_active_assets_selected_for_assignment" : 'NA',
                    "assets_assigned_already_for_provider": 'NA',
                    "assets_assigned_already_for_customer": 'NA',
                    "newly_assigned_asset_for_provider" : 'NA',
                    "newly_assigned_asset_for_customer" : 'NA'
                    }
                    email.send_email(receivers=receivers, subject=subject, template_name=template_name,attachment=None,filename=None,params=params)
                    continue
            
            total_active_scalar_units_df = get_scalar_assets_for_fa_root_org(db=db, fa_root_org_id=faRootOrgId)
            total_units_df = get_units_for_fa_org_id(db=db, fa_root_org_id=faRootOrgId)
            if len(total_units_df)==0:
                failed_orgs.append(faRootOrgId)
                asset_message=f"Asset not found to assign to asset group for {org_name}."
                logger.error(asset_message)
                subject = f"Scalar Migration - Customer asset assignment report for {org_name[:36]} - " + env
                params={"environment": env, 
                "execution_time": datetime.now(),
                "root_org_id" : faRootOrgId,
                "root_org_name": org_name,
                "total_active_assets_in_scalar" : 0,
                "total_active_assets_selected_for_assignment" : 0,
                "assets_assigned_already_for_provider": 0,
                "assets_assigned_already_for_customer": 0,
                "newly_assigned_asset_for_provider" : 0,
                "newly_assigned_asset_for_customer" : 0
                }

                api_response.append(params)
                email.send_email(receivers=receivers, subject=subject, template_name=template_name,attachment=None,filename=None,params=params)
                continue
            logger.info(f"Fetching access token for provider")
            consumer_sc_org_id = consumer_details['Organization_Id'][0]
            logger.info(f"Access token fetch successful, proceeding to assignment")
            already_assigned_assets_for_provider,already_assigned_assets_for_customer,asset_assignment_issue =asset_assignment_with_asset_group(db=db, 
                                                total_units_df=total_units_df,provider_org_id=provider_org_id,
                                                consumer_org_id = consumer_sc_org_id,
                                                fa_root_org_id=faRootOrgId, logger=logger)               
            if len(asset_assignment_issue) >0 :
                failed_orgs.append(faRootOrgId)
                message = f"Error occured while Asset assignment with asset group for organization :{org_name}"
                send_customer_asset_assignment_error_report(org_name= org_name, error= message,asset_assignment_issue= asset_assignment_issue)
                logger.error(message)
                continue
            
            successful_orgs.append(faRootOrgId)

            updated_assets_for_provider = pd.DataFrame()
            updated_assets_for_customer = pd.DataFrame()
            new_assigned_asset_for_provider = pd.DataFrame()
            new_assigned_asset_for_customer = pd.DataFrame()

            provider_assets_list = total_units_df["Provider_Asset_Id"].tolist()
            consumer_assets_list = total_units_df["Consumer_Asset_Id"].tolist()
            newly_assigned_assets_for_provider = set(provider_assets_list) - set(already_assigned_assets_for_provider['Provider_Asset_Id'].tolist())
            newly_assigned_assets_for_customer = set(consumer_assets_list) - set(already_assigned_assets_for_customer['Consumer_Asset_Id'].tolist())
            if len(already_assigned_assets_for_provider)>0:
                updated_assets_for_provider = total_units_df.loc[total_units_df["Provider_Asset_Id"].isin(already_assigned_assets_for_provider['Provider_Asset_Id'].tolist())]
            if len(already_assigned_assets_for_customer)>0:
                updated_assets_for_customer = total_units_df.loc[total_units_df["Consumer_Asset_Id"].isin(already_assigned_assets_for_customer['Consumer_Asset_Id'].tolist())]
            if len(newly_assigned_assets_for_provider)>0:
                new_assigned_asset_for_provider = total_units_df.loc[total_units_df["Provider_Asset_Id"].isin(newly_assigned_assets_for_provider)]
            if len(newly_assigned_assets_for_customer)>0:
                new_assigned_asset_for_customer = total_units_df.loc[total_units_df["Consumer_Asset_Id"].isin(newly_assigned_assets_for_customer)]

            env = os.environ['SCALAR_ENV']
            params={"environment": env, 
            "execution_time": datetime.now(),
            "root_org_id" : faRootOrgId,
            "root_org_name": org_name,
            "total_active_assets_in_scalar" : len(total_active_scalar_units_df),
            "total_active_assets_selected_for_assignment" : len(total_units_df),
            "assets_assigned_already_for_provider": len(already_assigned_assets_for_provider),
            "assets_assigned_already_for_customer": len(already_assigned_assets_for_customer),
            "newly_assigned_asset_for_provider" : len(newly_assigned_assets_for_provider),
            "newly_assigned_asset_for_customer" : len(newly_assigned_assets_for_customer)
            }

            api_response.append(params)
            send_customer_asset_assignment_report(db=db, sc_org_id= provider_org_id, org_name= org_name, fa_root_org_id=faRootOrgId, total_active_scalar_units= total_active_scalar_units_df,
                                                updated_asset_for_provider=updated_assets_for_provider, updated_asset_for_customer= updated_assets_for_customer,
                                                new_asset_for_provider= new_assigned_asset_for_provider, new_asset_for_customer= new_assigned_asset_for_customer, params= params)

            logger.warning(f"Asset assignment completed successfully for customer : {org_name}")
            
        return func.HttpResponse(
        json.dumps(api_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)
    except Exception as e:
        send_customer_asset_assignment_error_report(error= repr(e), org_name=org_name, asset_assignment_issue=asset_assignment_issue)
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        response = Response(message=str(e), status=False).getJsonResponse()
        return func.HttpResponse(
            response,
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )