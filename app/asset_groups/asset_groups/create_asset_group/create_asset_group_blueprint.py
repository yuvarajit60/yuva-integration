import json
import logging
import os
import azure.functions as func

from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.constants import ContentType, ResponseCode
from app.common.helpers.common_services import fetch_access_token
from app.common.helpers.common_data_access import get_fa_organization_details, get_tip_provider_organization, \
                                            get_consumer_organization_data, get_asset_group_data
from app.common.helpers.asset_group_helper import create_consumer_asset_group_in_api_db, create_consumer_org_asset_group_in_provider

create_asset_group_bp = func.Blueprint()

@create_asset_group_bp.function_name(name="Create_Asset_Group")
@create_asset_group_bp.route(route="create/assetgroup",  methods=[func.HttpMethod.POST])
@global_exception_handler
def create_asset_group_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Create_Asset_Group")
    db = Database()
    fa_org_id = req.get_json().get('faOrganizationId')
    
    if fa_org_id is None or not str(fa_org_id).isnumeric():
        message = f"Please provide valid FA organization id."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    fa_org_details_df = get_fa_organization_details(db=db, fa_org_id=fa_org_id)

    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        message = f"The organization is not an active FA organization or there is no existing DB record for the organization (ID: {fa_org_id})"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.NOT_FOUND,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    fa_org_details_dict = fa_org_details_df.to_dict('records')[0]
    if fa_org_details_dict['Root_Organization_Id'] is None:
        message = f"Child Asset Group could not be created since the FA organization (ID:{fa_org_id}) is a root organization"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_org_details_dict['Root_Organization_Id'])
    
    if sc_org_details_df is not None and len(sc_org_details_df) > 0:
        sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
    else:
        message = f"Scalar Organization is not created (or) Onboarded for the given FA Organization (ID: {fa_org_id})"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.INTERNAL_ERROR,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    scalar_parent_group_details = get_asset_group_data(db=db, 
                                                        FA_Organization_Id=fa_org_details_dict['Parent_Organization_Id'], 
                                                        sc_organization_id=sc_org_id)
    if scalar_parent_group_details is None or len(scalar_parent_group_details) == 0:
        message = f"Scalar parent group details not found, please check if parent group is created."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.INTERNAL_ERROR,
                mimetype=ContentType.APPLICATION_JSON
            )

    if sc_org_details_df.loc[0,'ZF_Consumer_Org'] == 0:
        consumer_access_token = fetch_access_token(db=db,org_id=sc_org_id,audience="TMAPI")  
        scalar_parent_group_details = scalar_parent_group_details[0]
        if scalar_parent_group_details[3] is None and scalar_parent_group_details[4] is None:
            root_group_id = scalar_parent_group_details[0]
        else:
            root_group_id = scalar_parent_group_details[3]
            
        create_consumer_asset_group_in_api_db(db=db,access_token=consumer_access_token,
                                            child_asset_group_name=fa_org_details_dict["Organization_Name"],
                                            root_asset_group_id=root_group_id,
                                            parent_asset_group_id=scalar_parent_group_details[0],
                                            sc_organization_id=sc_org_id,
                                            FA_Organization_Id=fa_org_id)

        message = "Child asset group created for the given FA Organization in consumer scalar organization"
    else:
        message = f"The organization (ID: {fa_org_id}) is a ZF consumer organization. Scalar group is not created."

    provider_org = get_tip_provider_organization(db=db)
    if provider_org is None:
        message += ", but consumer asset group in TIP is not found as provider org details are not found."
        logger.warning(message)

    provider_org_id = provider_org[0]
    provider_access_token = fetch_access_token(db=db, org_id=provider_org_id, audience='TMAPI')
    create_consumer_org_asset_group_in_provider(db=db, provider_org_id=provider_org_id, 
                                                fa_root_org_id=fa_org_details_dict['Root_Organization_Id'], 
                                                access_token=provider_access_token)

    logger.info(message)

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)