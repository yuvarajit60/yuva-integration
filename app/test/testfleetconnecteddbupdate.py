from sqlalchemy import text
from app.common.database import Database
from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response
import logging
import json

from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import inform_to_fleetconnected_database

updatefleetconnecteddbdata_bp = func.Blueprint()

@updatefleetconnecteddbdata_bp.function_name(name="Update_Fleetconnected_DB_Data")
@updatefleetconnecteddbdata_bp.route(route="updatefleetconnecteddbdata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def updatefleetconnecteddbdata_api(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger = logging.getLogger("update_fleetconnected_db_data")
        db = Database()
        fc_db = FleetConnectedDatabase()
        offset = 0
        while True:
            input_query = text(''' SELECT FA_Root_Organization_Id FROM SCALAR.SC_Migration_Process_Request
                                    ORDER BY FA_Root_Organization_Id
                                    OFFSET :offset ROWS FETCH NEXT 1 ROWS ONLY''')

            fa_root_org_id = db.query(statement=input_query, params={"offset": offset})
            if fa_root_org_id is None or len(fa_root_org_id) == 0:
                #Reached the end of table, exit
                break

            offset += 1

            fa_root_org_id = fa_root_org_id[0][0]
            inform_to_fleetconnected_database(fc_db= fc_db, fa_root_org_id= fa_root_org_id)
        message = "Fleetconnected_DB_Record_Updated!"
        logger.info(message)
        response = Response(status=True, message=message)
        return func.HttpResponse(
                response.getJsonResponse(),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON)
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        
        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )