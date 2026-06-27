from datetime import datetime, time
import logging
import azure.functions as func

from app.common.helpers.common_data_access import get_last_successfull_job_execution_ts
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, GeneralConstant, ResponseCode
from app.common.database import Database
from app.common.helpers.datasharing_helper import execute_data_sharing, get_data_sharing_session
from app.common.models import Response
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_all_organizations, get_tip_provider_organization
from app.common.constants import AudienceCode
from app.common.helpers.datasharing_helper import add_or_update_subcontring_summary, send_control_report

from app.data_sharing.interchange_out_units.interchange_out_units_data_access import get_interchange_out_units

interchange_out_bp = func.Blueprint() 


@interchange_out_bp.function_name(name="Interchange_Out_Units")
@interchange_out_bp.route(route="units/interchangeout",  methods=[func.HttpMethod.POST])
@global_exception_handler
def interchange_out_units(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Interchange_Out_Units")
    db = Database()
    job_name = GeneralConstant.INTCH_OUT_UNIT_JOB_NAME
    db = Database()
    file_name = "insight_intch_out_units"
    process = "Interchange Out"
    last_successful_execution_ts = get_last_successfull_job_execution_ts(db=db, job_name=job_name)
    # get the start of the day of the last run time because some assets are interchanged out with date but no time
    last_successful_execution_ts = datetime.combine(last_successful_execution_ts, time.min)
    logger.info(f"Last successful execution date: {last_successful_execution_ts}")

    interchange_out_units_df = get_interchange_out_units(db=db, last_successful_execution_ts=last_successful_execution_ts)
    logger.info(f"Total Interchange Out units: {len(interchange_out_units_df)}")

    message, response_code = execute_data_sharing(db= db,  
                                                    total_units_df=interchange_out_units_df, 
                                                    last_successful_execution_ts=last_successful_execution_ts,
                                                    process=process,
                                                    job_name=job_name,
                                                    file_name=file_name)
    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=response_code,
            mimetype=ContentType.APPLICATION_JSON)