import logging
import azure.functions as func
from sqlalchemy import and_, or_
from app.common.constants import AudienceCode, ContentType, ResponseCode
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User, SC_Organization, SC_Team_User_Mapping, SC_User, SC_User_Role_Mapping
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_services import fetch_access_token, get_scalar_api_error_messages
from app.common.helpers.team_helpers import unassignuser_from_team
from app.common.models import Response
from app.common.scalar_api.user_api import delete_user

remove_user_bp = func.Blueprint()

@remove_user_bp.function_name(name="Remove_User")
@remove_user_bp.route(route="delete/user",  methods=[func.HttpMethod.POST])
@global_exception_handler
def remove_user(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("remove_user")
    db = Database()
    fa_user_id = req.get_json().get('faUserId')
    if fa_user_id is None or not fa_user_id:
        message = f"Input FleetAdmin User ID cannot be empty."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    sc_user = db.get_session().query(SC_User).join(
        FA_User, FA_User.User_Id == SC_User.FA_User_Id
    ).join(
        SC_Organization, SC_Organization.Organization_Id == SC_User.SC_Organization_Id
    ).filter(
        FA_User.User_Id == fa_user_id,
        or_(
            and_(
            FA_User.Tip_User == 'N',
            FA_User.Root_Organization_Id == SC_Organization.FA_Root_Organization_Id
            ),
            and_(
                FA_User.Tip_User == 'Y',
                SC_Organization.FA_Root_Organization_Id.is_(None)
            )
        ),
        SC_User.Status.in_(['Active', 'Pending'])
    ).first()
    if sc_user is None:
        message = f"No active scalar user found for FA user id: {fa_user_id}"
        logger.warning(message)
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.NOT_FOUND,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    access_token = fetch_access_token(db=db,org_id= sc_user.SC_Organization_Id,audience= AudienceCode.TEAMS)
    user_team_mappings = db.get_session().query(SC_Team_User_Mapping).filter_by(User_Id=sc_user.User_Id, Active='1').all()
    for user_team_map in user_team_mappings:
        error_list = unassignuser_from_team(db=db, user_ids=[user_team_map.User_Id], team_id=user_team_map.Team_Id, org_id=sc_user.SC_Organization_Id, access_token=access_token)
        logger.warning(error_list)
        
    db.get_session().query(SC_User_Role_Mapping).filter_by(User_Id=sc_user.User_Id).delete()

    access_token = fetch_access_token(db=db,org_id= sc_user.SC_Organization_Id,audience= AudienceCode.USER)
    delete_user_response = get_scalar_api_error_messages(delete_user(access_token=access_token,user_id=sc_user.User_Id))
    if len(delete_user_response) > 0:
        raise ScalarException(message=f"Error occured while deleting user {sc_user.User_Id}-"+' '.join(map(str,delete_user_response)), response_code=ResponseCode.INTERNAL_ERROR)
    sc_user.Status = "Inactive"
    db.get_session().commit()

    message = f"Scalar user {sc_user.User_Id} for FA_user_id {fa_user_id} has been removed successfully."
    response = Response(status=True, message=message).getJsonResponse()
    return func.HttpResponse(
        response,
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)