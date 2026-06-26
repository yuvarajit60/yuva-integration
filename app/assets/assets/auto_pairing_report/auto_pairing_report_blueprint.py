from datetime import datetime, timedelta, date
import json
import os
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.assets.auto_pairing_report.auto_pairing_report_services import send_auto_pairing_report
from app.assets.auto_pairing_report.auto_pairing_report_data_access import get_auto_pairing_log
from app.common.models import Response
import logging

auto_pairing_report_bp = func.Blueprint()

@auto_pairing_report_bp.function_name(name="Auto_Pairing_Report")
@auto_pairing_report_bp.route(route="tip/asset/autopairing/report",  methods=[func.HttpMethod.GET])
@global_exception_handler
def autopairingreport_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Auto_Pairing_Report")
    db = Database()
    from_date = req.params.get('from')
    end_date = req.params.get('end')
    date_format_str = "%Y-%m-%d"

    if from_date is not None and end_date is not None:
        from_date = datetime.strptime(from_date, date_format_str).date()
        end_date = datetime.strptime(end_date, date_format_str).date()
    elif from_date is not None:
        from_date = datetime.strptime(from_date, date_format_str).date()
        end_date = date.today()
    else:
        from_date = date.today() - timedelta(days=1)
        end_date = date.today()

    auto_pairing_log = get_auto_pairing_log(db=db, from_date=from_date, end_date=end_date)
    send_auto_pairing_report(auto_pairing_log, from_date, end_date)
    if from_date == end_date:
        message = f"on {str(from_date)}"
    else:
        message = f"between {str(from_date)} and {str(end_date)}"
    message = f"The report of auto pairing failure log collected {message} sent successfully"

    logger.info(message)

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)