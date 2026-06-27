import json
import logging
import os
import azure.functions as func

from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_consumer_organization_data,get_fa_organization_details,get_asset_group_data,get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token,save_asset_group_in_db,get_scalar_api_error_messages
from app.common.helpers.asset_group_helper import create_consumer_asset_group_in_api_db,create_consumer_org_asset_group_in_provider
from app.common.constants import ContentType, ResponseCode
from app.common.scalar_api.asset_group_api import update_asset_group

update_asset_group_bp = func.Blueprint()

@update_asset_group_bp.function_name(name="Update_Asset_Group")
@update_asset_group_bp.route(route="update/assetgroup",  methods=[func.HttpMethod.PUT])
@global_exception_handler
def update_asset_group_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Update_Asset_Group")
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
        root_org_id = fa_org_id
        parent_org_id = fa_org_id
    else:
        root_org_id = fa_org_details_dict['Root_Organization_Id']
        parent_org_id = fa_org_details_dict['Parent_Organization_Id']

    sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=root_org_id)
    
    if sc_org_details_df is not None and len(sc_org_details_df) > 0:
        sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
    else:
        message=f"Scalar organization is not created (or) Onboarded for the given FA Organization (ID: {fa_org_id})"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.INTERNAL_ERROR,
                mimetype=ContentType.APPLICATION_JSON
            )

    ZF_Consumer_Org = sc_org_details_df.loc[0,'ZF_Consumer_Org']
    if ZF_Consumer_Org == 0:
        consumer_access_token = fetch_access_token(db=db,org_id=sc_org_id,audience="TMAPI")
        asset_group_data = get_asset_group_data(db=db,FA_Organization_Id = fa_org_id, sc_organization_id = sc_org_id)
        if asset_group_data is None or len(asset_group_data) == 0:
            logger.info("Asset Group not found, creating the asset group")
            if fa_org_details_dict['Root_Organization_Id'] is None:
                message = f"Child asset group could not be created since the input FA organization (ID:{fa_org_id}) is a root organization"
                logger.warning(message)
                response = Response(status=False, message=message).getJsonResponse()
                return func.HttpResponse(
                        response,
                        status_code=ResponseCode.BAD_REQUEST,
                        mimetype=ContentType.APPLICATION_JSON
                    )

            scalar_parent_group = get_asset_group_data(db=db,FA_Organization_Id = parent_org_id,sc_organization_id = sc_org_id)
            if scalar_parent_group is None or len(scalar_parent_group) == 0:
                message = "Scalar parent group details not found, please check if parent group is created"
                logger.warning(message)
                response = Response(status=False, message=message).getJsonResponse()
                return func.HttpResponse(
                        response,
                        status_code=ResponseCode.INTERNAL_ERROR,
                        mimetype=ContentType.APPLICATION_JSON
                    )

            if  scalar_parent_group[0][4] is None:
                root_asset_group_id = scalar_parent_group[0][0]
            else:
                root_asset_group_id = scalar_parent_group[0][3]

            create_consumer_asset_group_in_api_db(db=db,access_token=consumer_access_token,
                                        child_asset_group_name=fa_org_details_dict["Organization_Name"],
                                        root_asset_group_id=root_asset_group_id,
                                        parent_asset_group_id=scalar_parent_group[0][0],
                                        sc_organization_id=sc_org_id,
                                        FA_Organization_Id=fa_org_id)
            message = "Scalar asset group with updated details for the given FA organization is created successfully"
        else:
            updated_asset_group_response = update_asset_group(access_token = consumer_access_token, 
                                    asset_group_id = asset_group_data[0][0], name= fa_org_details_dict['Organization_Name'],
                                    description=fa_org_details_dict['Organization_Name'])

            if updated_asset_group_response.status_code == 200 :
                save_asset_group_in_db(db=db, asset_group_id=asset_group_data[0][0], 
                                        asset_group_name=fa_org_details_dict['Organization_Name'],
                                        asset_group_description=fa_org_details_dict['Organization_Name'],
                                        sc_organization_id=sc_org_id,
                                        root_group_id=asset_group_data[0][3],
                                        parent_group_id=asset_group_data[0][4], 
                                        fa_root_org_id=fa_org_id)

                message = f"Asset group updated for the given FA organization(ID: {fa_org_id}) in scalar"
            else:  
                error_str  = get_scalar_api_error_messages(error_response=updated_asset_group_response)[0].split("-")
                message = error_str[0] + "Update Failed."
                if "not found" in message:
                    message = "Update failed. Asset group deleted (or) not found"
                raise ScalarException(message=message, response_code=ResponseCode.INTERNAL_ERROR)
    
    # Consumer asset group check for FA Root org in TIP
    provider_org = get_tip_provider_organization(db=db)
    if provider_org is None:
        message += ",  Root organization Asset group in TIP not verified in TIP as provider org details are not found"
        logger.warning(message)    

    provider_org_id = provider_org[0]
    provider_access_token = fetch_access_token(db=db, org_id=provider_org_id, audience='TMAPI')
    create_consumer_org_asset_group_in_provider(db=db, provider_org_id=provider_org_id, 
                                                fa_root_org_id=root_org_id, 
                                                access_token=provider_access_token)

    response = Response(status=True, message=message)
    return func.HttpResponse(response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    