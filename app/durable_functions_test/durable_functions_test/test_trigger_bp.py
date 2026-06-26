import azure.functions as func
import azure.durable_functions as df

chain_start_bp = func.Blueprint()

@chain_start_bp.function_name(name="Durable_Test")
@chain_start_bp.route(route="testdurable", methods=[func.HttpMethod.POST])
@chain_start_bp.durable_client_input(client_name="client")
async def chaining(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    instance_id = await client.start_new("test_orc_func", None, None)
    result = await client.wait_for_completion_or_create_check_status_response(
        req,
        instance_id,
        timeout_in_milliseconds=60000
    )
    return result