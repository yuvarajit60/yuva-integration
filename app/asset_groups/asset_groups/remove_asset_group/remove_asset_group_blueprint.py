import json
import logging
import os
import azure.functions as func
from sqlalchemy import update

from app.common.database_model.scalar_tables import SC_Asset_Group, SC_Asset_Group_Team_Mapping
from app.common.helpers.unit_helpers import is_combi_number_removal_allowed
from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.constants import ContentType, ResponseCode
from app.common.helpers.common_services import fetch_access_token, get_scalar_api_error_messages
from app.common.helpers.common_data_access import get_consumer_organization_data, get_asset_group_data
from app.common.scalar_api.asset_group_api import delete_asset_group, get_specific_asset_group, unassign_asset_from_assetgroup
from app.common.helpers.asset_group_helper import remove_asset_group_mapping_from_db
from app.asset_groups.remove_asset_group.remove_asset_group_data_access import get_cust_combi_numbers, get_fa_users_by_fa_org_id, get_fa_organization

remove_asset_group_bp = func.Blueprint()

@remove_asset_group_bp.function_name(name="Remove_Asset_Group")
@remove_asset_group_bp.route(route="delete/assetgroup",  methods=[func.HttpMethod.POST])
@global_exception_handler
def remove_asset_group_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Remove_Asset_Group")
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

    fa_org_details_df = get_fa_organization(db=db, fa_org_id=fa_org_id)

    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        message = f"There is no existing DB record for the organization (ID: {fa_org_id})"
        logger.warning(message)
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.NOT_FOUND,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    fa_org_details_dict = fa_org_details_df.to_dict('records')[0]
    if fa_org_details_dict['Root_Organization_Id'] is None:
        message = f"The FA organization (ID:{fa_org_id}) is a root organization hence cannot be deleted."
        logger.warning(message)
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    if not get_fa_users_by_fa_org_id(db=db, fa_org_id=fa_org_id).empty:
        raise ScalarException(message=f"Can not remove scalar asset group for FA Organization with active fa_user(s)", 
                                response_code=ResponseCode.INTERNAL_ERROR)
    
    sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_org_details_dict['Root_Organization_Id'])
    if sc_org_details_df is not None and len(sc_org_details_df) > 0:
        root_org_id = fa_org_details_dict['Root_Organization_Id']
        sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
    else:
        raise ScalarException(message="Corresponding Scalar Organization ID not found/Root organization is not created in scalar", 
                                response_code=ResponseCode.INTERNAL_ERROR)
    
    cust_combi_numbers = get_cust_combi_numbers(db=db, organization_id=fa_org_id)
    combi_number_removal_allowed, tip_asset_deassignment_allowed = is_combi_number_removal_allowed(db=db, cust_combi_numbers=cust_combi_numbers, root_org_id=root_org_id, org_id=fa_org_id)
    if not combi_number_removal_allowed:
        raise ScalarException(message=f"One or more combinumbers of FA organization {fa_org_id} has Insight active units. Hence, organization can't be removed.", 
                                response_code=ResponseCode.INTERNAL_ERROR, display_reqd=True)
    
    asset_group_details = get_asset_group_data(db=db, FA_Organization_Id=fa_org_id, sc_organization_id=sc_org_id)
    if asset_group_details is None or len(asset_group_details) == 0:
        raise ScalarException(message="Asset group details for FA organization id not found in DB", 
                                response_code=ResponseCode.INTERNAL_ERROR)
    
    asset_group_id = asset_group_details[0][0]
    consumer_access_token = fetch_access_token(db=db,org_id=sc_org_id,audience="TMAPI")

    response = get_specific_asset_group(access_token=consumer_access_token, asset_group_id=asset_group_id)
    if response.status_code == 200:
            all_data_json = response.json()
            if len(all_data_json["subGroups"]) > 0:
                raise ScalarException(message=f"Can not delete asset group {asset_group_id} with subgroup(s) in it", response_code=ResponseCode.INTERNAL_ERROR)
            assets_in_asset_group = all_data_json["assetIds"]
            teams_in_asset_group = all_data_json["teamIds"]
    else:
        errors = get_scalar_api_error_messages(error_response=response)
        raise ScalarException(message=f"Error getting specific asset group {asset_group_id} from Scalar API-"+' '.join(map(str,errors)), 
                            response_code=ResponseCode.INTERNAL_ERROR)

    if len(assets_in_asset_group) > 0:
        errors = get_scalar_api_error_messages(unassign_asset_from_assetgroup(access_token=consumer_access_token,
                                                        asset_group_id=asset_group_id,
                                                        asset_ids=assets_in_asset_group))
        if len(errors) > 0:
            raise ScalarException(message=f"Error occured during unassignment of asset from asset group {asset_group_id} in Scalar API "+' '.join(map(str,errors)),
                            response_code=ResponseCode.INTERNAL_ERROR)
        remove_asset_group_mapping_from_db(db=db, asset_nrs=assets_in_asset_group, group_id=asset_group_id)

    errors = get_scalar_api_error_messages(delete_asset_group(access_token=consumer_access_token, asset_group_id=asset_group_id))
    if len(errors) > 0:
        raise ScalarException(message=f"Error occured during deletion of asset group {asset_group_id} in Scalar API "+' '.join(map(str,errors)),
                        response_code=ResponseCode.INTERNAL_ERROR)
    
    db.get_session().execute(update(SC_Asset_Group).where(SC_Asset_Group.Asset_Group_Id == asset_group_id, SC_Asset_Group.SC_Organization_Id == sc_org_id).values(Active="0"))
    db.get_session().execute(update(SC_Asset_Group_Team_Mapping).where(SC_Asset_Group_Team_Mapping.Asset_Group_Id == asset_group_id, SC_Asset_Group_Team_Mapping.Team_Id.in_(teams_in_asset_group)).values(Active="0"))
    db.get_session().commit()
    message = f"Asset group {asset_group_id} deleted for the FA Organization {fa_org_id} in scalar"
 
    logger.info(message)

    response = Response(status=True, message=message).getJsonResponse()
    return func.HttpResponse(
            response,
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)