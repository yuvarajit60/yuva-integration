import azure.functions as func
import logging
from app.common.exception_handler import global_exception_handler
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response

test_logger_bp = func.Blueprint()

@test_logger_bp.function_name(name="test_logger")
@test_logger_bp.route(route="testlogger", methods=[func.HttpMethod.POST])
@test_logger_bp.queue_output(
    arg_name="msg",
    queue_name="customeronboarding-queue",
    connection="AzureWebJobsStorage"
)
@global_exception_handler
def test_logger_api(req: func.HttpRequest, msg: func.Out[str]) -> func.HttpResponse:
    logger = logging.getLogger("test_logger")
    logger.info("HTTP trigger received — queuing background work")
    msg.set("start queue")
    logger.info("Message queued successfully — returning response")
    response = Response(status=True, message="Background process queued successfully")
    return func.HttpResponse(
        response.getJsonResponse(),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON
    )
