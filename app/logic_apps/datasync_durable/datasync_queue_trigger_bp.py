
import azure.functions as func
import azure.durable_functions as df
import json

datasync_queue_start_bp = func.Blueprint()

@datasync_queue_start_bp.function_name(name="Durable_Datasync_Queue")
@datasync_queue_start_bp.queue_trigger(
    arg_name="msg",
    queue_name="datasync-queue",   # ✅ your queue name
    connection="AzureWebJobsStorage"
)
@datasync_queue_start_bp.durable_client_input(client_name="client")
async def synctrigger(msg: func.QueueMessage, client: df.DurableOrchestrationClient):
    try:
        # ✅ Read queue message
        msg_body = msg.get_body().decode('utf-8')
        
        try:
            body = json.loads(msg_body)
        except Exception:
            body = {"raw_message": msg_body}

        # ✅ Start orchestration
        instance_id = await client.start_new("datasync_orc_func", None, body)

        # ✅ Logging (no HTTP response in queue trigger)
        print(f"Started orchestration with ID = '{instance_id}' for message: {body}")
    
    except Exception as e:
        print(f"Queue processing failed: {repr(e)}")
        raise e  # ensures retry

