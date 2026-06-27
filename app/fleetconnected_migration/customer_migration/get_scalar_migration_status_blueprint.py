import logging
import json
import azure.functions as func

from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.models import Response
from app.common.helpers.common_data_access import get_fa_organization_details, get_consumer_organization_data
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import  get_scalar_migration_status, \
    get_scalar_region_migration_status

consumer_migration_status_bp = func.Blueprint()

@consumer_migration_status_bp.function_name(name="Get_SKY_Customer_Migration_Status")
@consumer_migration_status_bp.route(route="skycustomer/migrationstatus",  methods=[func.HttpMethod.GET])
@global_exception_handler
def consumer_migration_status(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Get_SKY_Customer_Migration_Status")
    db = Database()
    fa_root_org_id = req.params.get('faRootOrgId')
    migration_status = True

    if fa_root_org_id is None or not str(fa_root_org_id).isnumeric():
        message = f"Please provide valid FA Root Organization Id."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    # Check FA Organization table and get region id
    fa_org_details_df = get_fa_organization_details(db=db, fa_org_id=fa_root_org_id)

    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        message = f"The FA Root Organization ID doesn't exist or is inactive"
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    region_id = fa_org_details_df.loc[0, 'Region_Id']

    # Check region migration table
    region_migration_df = get_scalar_region_migration_status(db=db, region_id=str(region_id))
    region_migration_status = region_migration_df.loc[0, 'Migrated_Flag']

    if int(region_migration_status) == 1:
        scalar_migration_details_df = get_scalar_migration_status(db=db, fa_root_org_id=fa_root_org_id)

        if scalar_migration_details_df is None or len(scalar_migration_details_df) == 0:
            migration_status = True

            sc_org_id = None
            sc_org_name = None

            sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
            if sc_org_details_df is not None and len(sc_org_details_df) > 0:
                sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
                sc_org_name = sc_org_details_df.loc[0, 'Organization_Name']

            api_response = {"faRootOrganizationId": fa_root_org_id,
                            "scalarOrganizationId":sc_org_id,
                            "scalarOrganizationName":sc_org_name,
                            "migrationStatus": migration_status}
            return func.HttpResponse(
                    json.dumps(api_response, default=str),
                    status_code=ResponseCode.SUCCESS,
                    mimetype=ContentType.APPLICATION_JSON
                )

    else:
        scalar_migration_details_df = get_scalar_migration_status(db=db, fa_root_org_id=fa_root_org_id)
        if scalar_migration_details_df is None or len(scalar_migration_details_df) == 0:
            migration_status = False

            api_response = {"faRootOrganizationId": fa_root_org_id,
                            "migrationStatus": migration_status}
            return func.HttpResponse(
                    json.dumps(api_response, default=str),
                    status_code=ResponseCode.SUCCESS,
                    mimetype=ContentType.APPLICATION_JSON
                )

    scalar_migration_details_dict = scalar_migration_details_df.to_dict('records')[0]

    if int(scalar_migration_details_dict['Migrated_Flag']) == 1:
        migration_status = True
    else:
        migration_status = False

    api_response = {"faRootOrganizationId": fa_root_org_id,
                    "migrationStatus": migration_status,
                    "scalarOrganizationId": scalar_migration_details_dict['SC_Organization_Id'],
                    "scalarOrganizationName":scalar_migration_details_dict['SC_Organization_Name'],
                    "skyCompanyId":scalar_migration_details_dict['SKY_Company_id'],
                    "skyCompanyName":scalar_migration_details_dict['SKY_Company_code'],
                }

    return func.HttpResponse(
        json.dumps(api_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON
        )