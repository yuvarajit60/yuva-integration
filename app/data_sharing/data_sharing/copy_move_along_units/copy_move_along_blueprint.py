import logging
import azure.functions as func
from app.common.constants import ContentType
from app.common.database import Database
from app.common.models import Response
from app.common.constants import GeneralConstant
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_last_successfull_job_execution_ts
from app.common.helpers.datasharing_helper import execute_data_sharing

from app.data_sharing.copy_move_along_units.copy_move_along_data_access import get_copy_move_along_units

copy_move_along_bp = func.Blueprint() 

@copy_move_along_bp.function_name(name="Copy_Move_Along_Units")
@copy_move_along_bp.route(route="units/copymovealong",  methods=[func.HttpMethod.POST])
@global_exception_handler
def copy_move_along_units(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Copy_Move_Along_Units")
    db = Database()
    job_name = GeneralConstant.COPY_MOVE_ALONG_UNIT_JOB_NAME
    process = "Copy Move Along Units"
    file_name = "insight_copy_move_along_units"

    last_successful_execution_ts = get_last_successfull_job_execution_ts(db=db, job_name=job_name)
        
    copy_move_along_units_df = get_copy_move_along_units(db=db, last_successful_execution_ts=last_successful_execution_ts)
    logger.info(f"Total Copy Move Along units: {len(copy_move_along_units_df)}")

    message, response_code = execute_data_sharing(db= db,  
                                                    total_units_df=copy_move_along_units_df, 
                                                    last_successful_execution_ts=last_successful_execution_ts,
                                                    process=process,
                                                    job_name=job_name,
                                                    file_name=file_name
                                                    )

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=response_code,
            mimetype=ContentType.APPLICATION_JSON)