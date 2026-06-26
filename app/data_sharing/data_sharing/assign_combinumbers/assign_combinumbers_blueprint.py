import logging
import json
import azure.functions as func
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode, AudienceCode
from app.common.database import Database
from app.common.models import Response
from app.common.func_validator import CombinumbersPayloadSchema
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.database_model.scalar_tables import SC_Asset_Group, SC_Organization
from app.common.helpers.common_data_access import get_tip_provider_organization, get_fa_organization_details
from app.common.helpers.datasharing_helper import execute_data_sharing_wo_mail
from app.data_sharing.assign_combinumbers.assign_combinumbers_data_access import \
                                                                get_insight_units_linked_to_combinumbers


assign_combinumbers_bp = func.Blueprint() 

@assign_combinumbers_bp.function_name(name="Assign_Combinumbers")
@assign_combinumbers_bp.route(route="assign/combinumbers",  methods=[func.HttpMethod.POST])
@global_exception_handler
def assign_combinumbers(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Assign_Combinumbers")

    req_body = req.get_json()
    combinumber_details = CombinumbersPayloadSchema.Schema().loads(json.dumps(req_body))

    fa_org_id = combinumber_details.faOrganizationId
    fa_root_org_id = combinumber_details.faRootOrganizationId
    combi_nrs = combinumber_details.combiNumbers
    db = Database()
    response_code = ResponseCode.BAD_REQUEST

    fa_org_details_df = get_fa_organization_details(db=db, fa_org_id=fa_org_id)

    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        message = f"The organization is not an active FA organization or there is no existing DB record for the organization (ID: {fa_org_id})"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    fa_org_details_dict = fa_org_details_df.to_dict('records')[0]

    if fa_org_details_dict['Fleetconnected_Ind'] in ('Y', 'y'):
        asset_group = db.get_session().query(SC_Asset_Group).join(\
            SC_Organization, SC_Organization.FA_Root_Organization_Id == fa_root_org_id).filter(\
                SC_Asset_Group.FA_Organization_Id == fa_org_id, SC_Asset_Group.Active == '1').first()

        if asset_group is None:
            message = f"No active asset group found for organization: {fa_org_id}"
            logger.warning(message)
            raise ScalarException(message=message, response_code=ResponseCode.INTERNAL_ERROR)
        
        units_to_data_share = get_insight_units_linked_to_combinumbers(db=db, combi_nrs=combi_nrs)
        total_units_to_data_share = len(units_to_data_share)
        message = f"Total Units linked to the given combinumbers: {total_units_to_data_share}"
        logger.info(message)

        if total_units_to_data_share != 0:

            provider_org_id = get_tip_provider_organization(db=db)
            if provider_org_id is None or len(provider_org_id) == 0:
                raise ScalarException(message="Provider organization details not found", response_code=ResponseCode.INTERNAL_ERROR)

            provider_access_token = fetch_access_token(db=db, org_id=provider_org_id[0], audience=AudienceCode.DATA_SHARING)

            units_to_data_share["Organization_Id"] = fa_org_id
            units_to_data_share["Root_Organization_Id"] = fa_root_org_id
            message, response_code = execute_data_sharing_wo_mail(db=db, total_units_df=units_to_data_share, provider_org_id=provider_org_id[0],
                                        fa_root_org_id=fa_root_org_id, logger=logger)
        
        else:
            message = f"There are no units linked to the given combinumbers."
            response_code = ResponseCode.SUCCESS

    else:
        message = f"The given Organization is a Non-Scalar Organization. ID: ({fa_org_id})"
        response_code = ResponseCode.SUCCESS

    response = Response(status=True, message=message)
    return func.HttpResponse(
        response.getJsonResponse(),
        status_code=response_code,
        mimetype=ContentType.APPLICATION_JSON)