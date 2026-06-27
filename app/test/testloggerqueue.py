import azure.functions as func
import logging
import time

logger_queue_bp = func.Blueprint()

@logger_queue_bp.function_name(name="Logger_Queue")
@logger_queue_bp.queue_trigger(
    arg_name="msg",
    queue_name="customeronboarding-queue",
    connection="AzureWebJobsStorage"
)
def queueloggertrigger(msg: func.QueueMessage) -> None:
    logger = logging.getLogger("Logger_Queue")
    try:
        logger.info("Background process started")
        time.sleep(5)
        logger.warning("Warning log after 5 seconds")
        time.sleep(5)
        logger.error("Error log after 10 seconds")
        time.sleep(5)
        logger.info("Background process completed successfully")
    except Exception as e:
        logger.error(f"Queue processing failed: {repr(e)}", exc_info=True)
