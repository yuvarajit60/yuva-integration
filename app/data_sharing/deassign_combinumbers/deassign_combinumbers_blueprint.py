import json
import logging
import azure.functions as func
from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.constants import ContentType, ResponseCode, AudienceCode
from app.common.helpers.common_services import fetch_access_token, get_scalar_api_error_messages
from app.common.scalar_api.asset_group_api import unassign_asset_from_assetgroup
from app.common.helpers.common_data_access import get_consumer_organization_data,get_tip_provider_organization,get_fa_organization_details
from app.common.func_validator import CombinumbersPayloadSchema
from app.common.helpers.unit_helpers import is_combi_number_removal_allowed
from app.data_sharing.deassign_combinumbers.deassign_combinumbers_data_access import get_asset_groups,get_fc_unit_from_cust_combi_nrs,inactivate_asset_from_asset_group_mapping
deassign_combi_bp = func.Blueprint()

@deassign_combi_bp.function_name(name="Deassign_Combinumbers")
@deassign_combi_bp.route(route="deassign/combinumbers",  methods=[func.HttpMethod.POST])
@global_exception_handler
def deassign_combinum_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Deassign_Combinumbers")
    db = Database()
    req_body = req.get_json()
    combinumber_details = CombinumbersPayloadSchema.Schema().loads(json.dumps(req_body))

    fa_organization_id = combinumber_details.faOrganizationId
    fa_root_organization_id = combinumber_details.faRootOrganizationId
    combi_numbers = combinumber_details.combiNumbers

    fa_org_details_df = get_fa_organization_details(db=db, fa_org_id=fa_organization_id)

    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        message = f"The organization is not an active FA organization or there is no existing DB record for the organization (ID: {fa_organization_id})"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )
    scalar_ind = fa_org_details_df.iloc[0]['Fleetconnected_Ind'] =='Y'
    if scalar_ind:
        provider_org = get_tip_provider_organization(db=db)
        if provider_org is None or len(provider_org) == 0:
            raise ScalarException(message="Provider organization details not found", response_code=ResponseCode.INTERNAL_ERROR)
        provider_org_id = provider_org[0]
        
        sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_organization_id)
    
        if sc_org_details_df is not None and len(sc_org_details_df) > 0:
            sc_consumer_org_id = sc_org_details_df.loc[0,'Organization_Id']
        else:
            raise ScalarException(message="Corresponding Scalar Organization ID not found/Root organization is not created in scalar", 
                                response_code=ResponseCode.INTERNAL_ERROR)

        combi_number_removal_allowed, tip_asset_deassignment_allowed = is_combi_number_removal_allowed(
            db=db,
            cust_combi_numbers= combi_numbers,
            root_org_id=fa_root_organization_id,
            org_id=fa_organization_id
        )
        logger.info(f"Is combi number allowed to be removed: {combi_number_removal_allowed}")
        if combi_number_removal_allowed :
            if tip_asset_deassignment_allowed:
                asset_groups = get_asset_groups(db=db, sc_provider_org_id=provider_org_id, fa_root_org_id=fa_root_organization_id, sc_consumer_org_id=sc_consumer_org_id, fa_org_id=fa_organization_id)
                if len(asset_groups) > 0:
                    units = get_fc_unit_from_cust_combi_nrs(db=db,cust_combi_numbers=combi_numbers)
                    logger.info(f"{len(units)} assets found in combinubers {combi_numbers}")
                    if len(units) > 0:

                        tip_asset_group = asset_groups.loc[(asset_groups['SC_Organization_Id'] == provider_org_id)].iloc[0]
                        provider_access_token = fetch_access_token(db=db, org_id=provider_org_id, audience=AudienceCode.TEAMS)

                        asset_id_list = [unit[2] for unit in units if unit[2] is not None]
        
                        if len(asset_id_list) > 0:
                            tip_remove_resources_response = unassign_asset_from_assetgroup(access_token=provider_access_token,
                                                                                asset_ids= asset_id_list,
                                                                                asset_group_id=tip_asset_group['Asset_Group_Id'])
                            
                            if tip_remove_resources_response.status_code ==200:
                                inactivate_asset_from_asset_group_mapping(db=db, units=asset_id_list, group_id=tip_asset_group['Asset_Group_Id'])
                                message="Combinumbers deassigned from TIP Scalar organization successfully"
                            else:
                                errors = get_scalar_api_error_messages(error_response=tip_remove_resources_response)
                                logger.info(errors)
                        else:
                            message="No assets found to deassig from TIP Scalar organization"  
                        
                    else:
                       message=f"Combinumbers deassigned from organization successfully, but no units found linked to the group code {fa_organization_id}"
                else:
                    message = f"Groups missing in SCALAR, Combinumbers deassignment failed from organization {fa_organization_id}"
                    raise ScalarException(message=message, display_reqd=True)
            else:
                message=f"Combinumbers deassigned from organization successfully."
        else:
            message = f"You can't unlink the combinumbers from this organization yet. They still have insight active units"
            raise ScalarException(message=message, display_reqd=True)
                    
    else:
        message = "Combinumbers deassigned from a non FC organization successfully"

    logger.info(message)

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
                    
            


                