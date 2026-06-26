import json
import logging
import azure.functions as func
from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.constants import ContentType, ResponseCode, AudienceCode
from app.common.helpers.common_services import fetch_access_token
from app.common.func_validator import CreateUser
from app.common.helpers.common_data_access import get_tip_provider_organization, get_consumer_organization_data, get_fa_user_details_by_id
from app.common.helpers.user_helpers import create_update_scalar_user, user_assignment

create_user_bp = func.Blueprint()

@create_user_bp.function_name(name="Create_User")
@create_user_bp.route(route="create/user",  methods=[func.HttpMethod.POST])
@global_exception_handler
def create_user_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Create_User")
    db = Database()

    user = CreateUser.Schema().loads(json.dumps(req.get_json()))

    fa_user_details_df = get_fa_user_details_by_id(db=db, fa_user_id=user.faUserId)
    if fa_user_details_df is None or len(fa_user_details_df) == 0:
        message = f"No Active FleetAdmin User found with the given ID."
        logger.warning(message)
        raise ScalarException(message=message, response_code=ResponseCode.NOT_FOUND)

    fa_user_dict = fa_user_details_df.to_dict('records')[0]

    if fa_user_dict['Fleet_Connected_Ind'] in ('Y', 'y'):
        if fa_user_dict['Tip_User'] in ('Y', 'y'):
            tip_org_id = get_tip_provider_organization(db=db)
            if tip_org_id is None or len(tip_org_id) == 0:
                message = f"TIP Provider organization details not found."
                logger.warning(message)
                raise ScalarException(message=message, response_code=ResponseCode.INTERNAL_ERROR)
            sc_org_id = tip_org_id[0]
            user_access_token = fetch_access_token(db=db, org_id=sc_org_id, audience=AudienceCode.USER)
            user.loginType = "SSO"

        else:
            consumer_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_user_dict['Root_Organization_Id'])
            consumer_org_dict = consumer_org_details_df.to_dict('records')[0]

            if consumer_org_details_df is None or len(consumer_org_details_df) == 0:
                message = f"Consumer Organization details not found."
                logger.warning(message)
                raise ScalarException(message=message, response_code=ResponseCode.BAD_REQUEST)
            if consumer_org_dict['ZF_Consumer_Org'] == 1:
                message = f"The user belongs to ZF consumer organization. Scalar user creation not allowed."
                logger.warning(message)
                raise ScalarException(message=message, response_code=ResponseCode.BAD_REQUEST)
            sc_org_id = consumer_org_dict['Organization_Id']
            user_access_token = fetch_access_token(db=db, org_id=sc_org_id, audience=AudienceCode.USER)
            user.loginType = "SSO" if int(consumer_org_dict['Is_SSO_Enabled']) else "Password"

        user.emailAddress = fa_user_dict['User_Email']
        user.firstName = fa_user_dict['User_First_Name']
        user.lastName = fa_user_dict['User_Last_Name']
        user.roles = [user.scalarRoleId] if user.scalarRoleId is not None else None
        user.role_names = [user.scalarRoleName] if user.scalarRoleName is not None else None
        user.language = "en" if user.language is None or not user.language else user.language
        user.language = "nb" if user.language == "no" else user.language

        logger.info("Invoking create_user or update_user api for scalar user creation")
        create_scalar_user_response = create_update_scalar_user(db=db, user=user, scalar_org_id=sc_org_id, 
                                                                access_token=user_access_token,
                                                                fa_user_id = user.faUserId)
        message = "User created (or) updated successfully in Scalar. "

        logger.info("User created successfully now invoking user assignment")
        tmapi_access_token = fetch_access_token(db=db, org_id=sc_org_id, audience=AudienceCode.TEAMS)
        #User assignment starts here 
        message_dict = user_assignment(db=db, 
                              sc_org_id=sc_org_id, 
                              user=user, 
                              fa_user_dict=fa_user_dict, 
                              tmapi_access_token=tmapi_access_token, 
                              scalar_user_id=create_scalar_user_response['userId'], 
                              logger=logger)
        if "error" in message_dict:
            message += message_dict["error"]
            response_code=ResponseCode.SUCCESS # Only user assignment failure is considered success scenario
        else:
            message += message_dict["success"]
            response_code = ResponseCode.SUCCESS
    else:
        message = f"User cannot be created in Scalar since FA User (ID: {user.faUserId}) is a Non-Scalar user"
        response_code = ResponseCode.SUCCESS

    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=response_code,
            mimetype=ContentType.APPLICATION_JSON)