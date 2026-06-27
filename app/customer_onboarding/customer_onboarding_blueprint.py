import json
import os
import sys
from app.common.helpers.asset_group_helper import create_consumer_org_asset_group_in_provider
from app.common.helpers.common_data_access import  get_organization_profile, get_tip_provider_organization
from app.common.helpers.common_services import save_error_details_in_blob, fetch_access_token
from app.common.helpers.framework_agreement_helpers import customer_onboarding
from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
import logging
from app.common.constants import ContentType, GeneralConstant, ResponseCode
from app.customer_onboarding.customer_onboarding_data_access import  get_FA_root_org, get_insight_units, get_sc_application_id, save_fa_org_application_mapping, update_faorg_fcflag_in_db
from app.common.helpers.datasharing_helper import execute_data_sharing_wo_mail
from app.customer_onboarding.customer_onboarding_services import  create_consumer_asset_group_hierarchy, fetch_asset_group_access_token, inform_fleetadmin_about_tenancy_creation, send_data_sharing_error_email_to_super_users, send_success_email_to_regional_super_users, send_error_email_to_super_users
import threading
from sqlalchemy.exc import SQLAlchemyError

customeronboarding_bp = func.Blueprint()

@customeronboarding_bp.function_name(name="Customer_Onboarding")
@customeronboarding_bp.route(route="customeronboarding",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customeronboarding_api(req: func.HttpRequest) -> func.HttpResponse:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Customer_Onboarding")
    db = Database()
    faRootOrgId = req.get_json().get('faOrganizationId')
    #Validate input FA root organization id
    if faRootOrgId is None or not str(faRootOrgId).isnumeric():
        message = f"Please provide valid FA root organization id."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )
    #Validate active record in FA organization table
    consumer_organization_name= get_FA_root_org(db=db,fa_root_org_id=faRootOrgId)
    if consumer_organization_name is None :
        message = f"The organization is not an active FA root organization or there is no existing DB record for the root organization (ID: {faRootOrgId})."
        logger.warning(message)
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )
    req_body = {"consumerPrimaryEmail":os.environ["consumerPrimaryEmail"],
                "consumerPrimaryLastName":os.environ["consumerPrimaryLastName"],
                "consumerPrimaryFirstName":os.environ["consumerPrimaryFirstName"] }
    req_body["faRootOrgId"]= faRootOrgId
    
    provider_org_id = get_tip_provider_organization(db=db)
    provider_org_id = provider_org_id[0]    
    access_token = fetch_access_token(db=db,org_id=provider_org_id,audience="DASAPI")
    profile_id = get_organization_profile(db=db)
    
    # Customer onboarding into scalar 
    customer_onboarding_response = customer_onboarding(db=db,access_token= access_token, orgName=consumer_organization_name,primaryEmail=req_body["consumerPrimaryEmail"],primaryLastName=req_body["consumerPrimaryLastName"],primaryFirstName=req_body["consumerPrimaryFirstName"],fa_root_org_id=faRootOrgId,profile_id=profile_id)
    framework_agreement_id  = customer_onboarding_response["agreementId"]
    consumer_org_id = customer_onboarding_response["consumerOrgId"]
    consumer_org_name = customer_onboarding_response["consumerOrgName"]
    logger.info(f"Created framework agreement details: agreement id: {framework_agreement_id} customer id: {consumer_org_id} customer name: {consumer_org_name}. Background process going to start.")
    threading.Thread(
            target=background_process,
            args=(db, consumer_org_id, consumer_org_name, provider_org_id, faRootOrgId, logger)
            ).start()
    customer_onboarding_response["status"] = True
    customer_onboarding_response["message"] = f"Customer is onboarded successfully with Scalar Org Id as {consumer_org_id} and Scalar Org name as {consumer_org_name}"
    customer_onboarding_response["displayMessage"] = None

    return func.HttpResponse(
        json.dumps(customer_onboarding_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)

def _make_background_logger(fa_root_org_id) -> logging.Logger:
    """
    Background threads can't write to the invocation log (invocation closes
    when the HTTP response returns). This logger writes to stdout so the
    Azure Functions worker forwards output to Application Insights traces
    and the portal Log Stream instead.
    """
    name = f"Customer_Onboarding.Background.{fa_root_org_id}"
    bg_logger = logging.getLogger(name)
    bg_logger.setLevel(logging.INFO)
    if not bg_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("[BG %(asctime)s] %(levelname)s %(name)s: %(message)s")
        )
        bg_logger.addHandler(handler)
    return bg_logger


def background_process(db: Database, consumer_org_id: str, consumer_org_name: str, provider_org_id: str, faRootOrgId: int, logger):
    logger = _make_background_logger(faRootOrgId)
    try:
        logger.info(f"Background process started....")
        process_name = 'Customer assetgroup hierarchy creation'
        logger.info(f"Customer asset group hierarchy creation has been initiated.")
        asset_group_access_token = fetch_asset_group_access_token(db=db,org_id=consumer_org_id,audience="TMAPI")          
        create_consumer_asset_group_hierarchy(db=db,access_token=asset_group_access_token,sc_organization_id=consumer_org_id,fa_root_org_id=faRootOrgId)
        logger.info(f"Customer asset group hierarchy creation completed.")
        process_name = 'Customer assetgroup hierarchy creation in provider'
        logger.info(f"Provider main asset group creation has been initiated.")
        asset_group_access_token = fetch_access_token(db=db,org_id=provider_org_id,audience="TMAPI")
        # Create asset group for root organization in provider organization
        create_consumer_org_asset_group_in_provider(db=db,provider_org_id=provider_org_id,fa_root_org_id=faRootOrgId,access_token=asset_group_access_token)
        logger.info(f"Provider main asset group creation completed.")
        # Update record in FleetAdmin table -[TIPinsight].[dbo].[FA_Root_Org_Tenancy]
        process_name = 'Inform fleet admin about organization creation'
        logger.info(f"Inform fleet admin about organization creation process has been started.")
        inform_fleetadmin_about_tenancy_creation(db=db, root_org_id=faRootOrgId)
        # Update FleetConnected_Ind flag to 'Y' in FA Org Table
        # process = 'Update fleetconnected flag in FA_Organization table.'
        update_faorg_fcflag_in_db(db=db, farootorgid=faRootOrgId)
        # Insert record into FA_Org_Application_Mapping
        # process = 'Update fleetconnected flag in FA_Organization table.'
        app_id = get_sc_application_id(db=db) 
        save_fa_org_application_mapping(db=db, organization_id=faRootOrgId, application_id=app_id)
        # Send email to customer primary contach email about customer onboading into scalar.
        logger.info(f"Inform fleet admin about organization creation process ended.")
        logger.info(f"Sending customer onboarding success email to super user.")
        send_success_email_to_regional_super_users(db=db, root_org_id=faRootOrgId, consumer_org_name=consumer_org_name)
        logger.info(f"Customer onboarding success email sent to super user.")
    except SQLAlchemyError as sae:
        # error_message = GeneralConstant.DB_EXCP_MESSAGE
        error_message = f"DB Exception: {str(sae)}"
        logger.error(error_message, exc_info=True)
        consumer_org_name= (consumer_org_name.lower()).replace("/", " ")
        save_error_details_in_blob(container_name= 'customer-onboarding',folder_name= consumer_org_name, process_name= process_name, error_message= error_message)
        send_error_email_to_super_users(db=db, root_org_id=faRootOrgId, consumer_org_name=consumer_org_name, error_message= error_message, process_name= process_name)
    except Exception as e:
        # logger.error(f"Error occurred:{str(e)}")
        error_message =f"Application Exception: {str(e)}"
        logger.error(error_message, exc_info=True)
        consumer_org_name= (consumer_org_name.lower()).replace("/", " ")
        save_error_details_in_blob(container_name= 'customer-onboarding',folder_name= consumer_org_name, process_name= process_name, error_message= error_message)
        send_error_email_to_super_users(db=db, root_org_id=faRootOrgId, consumer_org_name=consumer_org_name, error_message= error_message, process_name= process_name)

    # Start data sharing with TIP
    total_units_df = get_insight_units(db=db, fa_root_org_id=faRootOrgId)
    if len(total_units_df)>0:
        logger.info(f"Datasharing has been started for active & paired assets.")
        msg, response_code= execute_data_sharing_wo_mail(db=db, total_units_df=total_units_df, provider_org_id=provider_org_id,
                                            fa_root_org_id=faRootOrgId, logger=logger)
        if response_code == ResponseCode.INTERNAL_ERROR:
            send_data_sharing_error_email_to_super_users(db=db, root_org_id=faRootOrgId, consumer_org_name=consumer_org_name, error_message= msg)
        logger.info(f"Datasharing completed for active & paired assets.")
        logger.info(f"Background process completed successfully.")
