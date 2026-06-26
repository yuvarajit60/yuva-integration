import azure.functions as func
import azure.durable_functions as df
import json

datasync_start_bp = func.Blueprint()

@datasync_start_bp.function_name(name="Durable_Datasync")
@datasync_start_bp.route(route="durabledatasync", methods=[func.HttpMethod.POST])
@datasync_start_bp.durable_client_input(client_name="client")
async def synctrigger(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    body = req.get_json()
    instance_id = await client.start_new("datasync_orc_func", None, body)
    result = await client.wait_for_completion_or_create_check_status_response(
        req,
        instance_id,
        timeout_in_milliseconds=60000
    )
    return result
