import logging
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.models import Response
from app.common.constants import GeneralConstant
from app.common.exception_handler import global_exception_handler
from app.common.helpers.datasharing_helper import execute_data_sharing

from app.data_sharing.new_pairing_insight_units.new_pairing_data_access import get_new_pairing_insight_units

new_pairing_bp = func.Blueprint() 

@new_pairing_bp.function_name(name="New_Pairing_Insight_Units")
@new_pairing_bp.route(route="units/newpairing",  methods=[func.HttpMethod.POST])
@global_exception_handler
def new_pairing_insight_units(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("New_Pairing_Insight_Units")
    job_name = GeneralConstant.NEW_PAIRING_UNIT_JOB_NAME
    db = Database()
    file_name = "new_pairing_insight_units"
    process = "New pairing"
    response_code = ResponseCode.SUCCESS
        
    new_pairing_units_df = get_new_pairing_insight_units(db=db)
    message = f"Total new pairing insight units: {len(new_pairing_units_df)}"
    logger.info(message)

    if len(new_pairing_units_df) > 0:
        message, response_code = execute_data_sharing(db=db,
                                                       total_units_df= new_pairing_units_df, 
                                                       last_successful_execution_ts=None, process= process, 
                                                        job_name= job_name, file_name=file_name)

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=response_code,
            mimetype=ContentType.APPLICATION_JSON)
