import logging
import json
import azure.functions as func

from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import  get_tip_migration_status

tip_migration_status_bp = func.Blueprint()

@tip_migration_status_bp.function_name(name="Get_TIP_Migration_Status")
@tip_migration_status_bp.route(route="tip/migrationstatus",  methods=[func.HttpMethod.GET])
@global_exception_handler
def tip_migration_status(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Get_TIP_Migration_Status")
    db = Database()
    migration_status = False

    tip_migration_details_df = get_tip_migration_status(db=db)

    if tip_migration_details_df is None or len(tip_migration_details_df) == 0:
        api_response = {"migrationStatus": migration_status}
        return func.HttpResponse(
                json.dumps(api_response, default=str),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    tip_migration_details_dict = tip_migration_details_df.to_dict('records')[0]

    if int(tip_migration_details_dict['Migrated_Flag']) == 1:
        migration_status = True

    api_response = { "migrationStatus": migration_status,
                    "scalarOrganizationId": tip_migration_details_dict['SC_Organization_Id'],
                    "scalarOrganizationName":tip_migration_details_dict['SC_Organization_Name'],
                    "skyCompanyId":tip_migration_details_dict['SKY_Company_id'],
                    "skyCompanyName":tip_migration_details_dict['SKY_Company_code']
                }

    return func.HttpResponse(
        json.dumps(api_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON
        )