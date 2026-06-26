import json
import logging

import azure.functions as func
from app.common.exception_handler import global_exception_handler
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.users.get_scalar_org_details.get_scalar_org_details_services import user_scalar_org

user_org_bp = func.Blueprint() 

@user_org_bp.function_name(name="Get_Scalar_Org_Details")
@user_org_bp.route(route="scalarorgdetails",  methods=[func.HttpMethod.GET])
@global_exception_handler

def main(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Get_Scalar_Org_Details") 
    db = Database()
    user_id = req.params.get('userId')
    user_response = user_scalar_org(db=db,fa_user_id=user_id)  

    return func.HttpResponse(
        json.dumps(user_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)