from app.common.constants import AudienceCode, ResponseCode
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Team_User_Mapping, SC_User, SC_User_Role_Mapping
from app.common.exceptions import ScalarException
from app.common.func_validator import User
from app.common.helpers.common_services import fetch_access_token, get_scalar_api_error_messages
from app.common.helpers.team_helpers import unassignuser_from_team
from app.common.helpers.user_helpers import create_update_scalar_user, user_assignment
from app.common.scalar_api.user_api import delete_user


def create_scalar_user_for_fa_user(db: Database, user: User, scalar_org_id: str, fa_user_dict: dict, logger):
    access_token = fetch_access_token(db=db,org_id= scalar_org_id,audience= AudienceCode.USER)
    create_scalar_user_response = create_update_scalar_user(db=db, user=user, scalar_org_id=scalar_org_id, 
                                                                access_token=access_token,
                                                                fa_user_id = user.faUserId)
    tmapi_access_token = fetch_access_token(db=db, org_id=scalar_org_id, audience=AudienceCode.TEAMS)
    message_dict = user_assignment(db=db, 
                              sc_org_id=scalar_org_id, 
                              user=user, 
                              fa_user_dict=fa_user_dict, 
                              tmapi_access_token=tmapi_access_token, 
                              scalar_user_id=create_scalar_user_response['userId'], 
                              logger=logger)
    if "error" in message_dict:
        logger.error(message_dict["error"])
    else:
        logger.info(message_dict)
        db.get_session().commit()
    return

def update_scalar_user_for_fa_user(db: Database, user: User, scalar_org_id: str, fa_user_dict: str, logger):
    access_token = fetch_access_token(db=db,org_id= scalar_org_id,audience= AudienceCode.USER)
    update_scalar_user_response = create_update_scalar_user(db=db, user=user, scalar_org_id=scalar_org_id, 
                                                                access_token=access_token,
                                                                fa_user_id = user.faUserId)
    teams_from_user = db.get_session().query(SC_Team_User_Mapping.Team_Id
                                                       ).filter(
                                                           SC_Team_User_Mapping.User_Id == update_scalar_user_response['userId'],
                                                           SC_Team_User_Mapping.Active == '1'
                                                       ).all()
    tmapi_access_token = fetch_access_token(db=db, org_id=scalar_org_id, audience=AudienceCode.TEAMS)
    for team in teams_from_user:
        if team is not None:
            error_list = unassignuser_from_team(db=db, user_ids=[update_scalar_user_response['userId']], team_id=team.Team_Id, org_id=scalar_org_id, access_token=tmapi_access_token)
            logger.warning(error_list)
    message_dict = user_assignment(db=db, 
                              sc_org_id=scalar_org_id, 
                              user=user, 
                              fa_user_dict=fa_user_dict, 
                              tmapi_access_token=tmapi_access_token, 
                              scalar_user_id=update_scalar_user_response['userId'], 
                              logger=logger)
    if "error" in message_dict:
        logger.error(message_dict["error"])
    else:
        logger.info(message_dict)
        db.get_session().commit()
    return

def remove_scalar_user_for_fa_user(db: Database, scalar_org_id: str, scalar_user_id: str, logger):
    access_token = fetch_access_token(db=db,org_id= scalar_org_id,audience= AudienceCode.TEAMS)
    user_team_mappings = db.get_session().query(SC_Team_User_Mapping).filter_by(User_Id=scalar_user_id, Active='1').all()
    for user_team_map in user_team_mappings:
        error_list = unassignuser_from_team(db=db, user_ids=[user_team_map.User_Id], team_id=user_team_map.Team_Id, org_id=scalar_org_id, access_token=access_token)
        logger.warning(error_list)
        
    db.get_session().query(SC_User_Role_Mapping).filter_by(User_Id=scalar_user_id).delete()

    access_token = fetch_access_token(db=db,org_id= scalar_org_id,audience= AudienceCode.USER)
    delete_user_response = get_scalar_api_error_messages(delete_user(access_token=access_token,user_id=scalar_user_id))
    if len(delete_user_response) > 0:
        raise ScalarException(message=f"Error occured while deleting user {scalar_user_id}-"+' '.join(map(str,delete_user_response)), response_code=ResponseCode.INTERNAL_ERROR)
    db.get_session().query(SC_User).filter_by(User_Id=scalar_user_id).update({"Status":"Inactive"})
    db.get_session().commit()
    return