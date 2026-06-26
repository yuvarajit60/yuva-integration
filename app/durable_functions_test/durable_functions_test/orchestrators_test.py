import azure.durable_functions as df
from sqlalchemy import text
from datetime import timedelta


from app.common.database import Database

orc_bp = df.Blueprint()

@orc_bp.orchestration_trigger(context_name="context")
def orc_func(context: df.DurableOrchestrationContext):
    job_name = yield context.call_activity("test_activity", None)
    attempt = 40
    while attempt > 0:
        status = yield context.call_activity("job_status_check", job_name)
        if status == "completed":
            break
        yield context.create_timer(context.current_utc_datetime+timedelta(seconds=30))
        attempt = attempt - 1
    if status != "completed":
        return f"Could not complete job {job_name}"
    
    return "Completed all TIP migration jobs"
