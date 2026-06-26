from asyncio.log import logger
import json
import time

from app.common.constants import GeneralConstant
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Team, SC_Team_User_Mapping
from app.common.exceptions import ScalarException
from app.common.helpers.common_services import get_all_data, get_scalar_api_error_messages, pagination_check
from app.common.scalar_api.teams_api import assign_user_to_team, create_team, get_all_team, unassign_user_from_team

def assignuser_to_team(db: Database, user_ids: list, team_id: str, team_name: str, org_id: str, access_token: str):
    attempt = GeneralConstant.ASSIGNMENT_LOOKUP_LIMIT
    team_response = assign_user_to_team(access_token=access_token, team_id=team_id, user_ids=user_ids)
    while team_response.status_code != 200 and attempt > 0:
        # retry user assignemt 5 times
        error_list = get_scalar_api_error_messages(error_response=team_response)
        if "Users not found in organization. -" in error_list or "Team {0} does not exist. -" in error_list:
            logger.warning(f"Reattempting user to team assignment, remaining attempts: {attempt-1}")
            time.sleep(GeneralConstant.ASSIGNMENT_LOOKUP_WAITTIME)
            team_response = assign_user_to_team(access_token=access_token, team_id=team_id, user_ids=user_ids)
            attempt = attempt - 1
        else:
            break
    # if all attempts exhausted and no successful response return error msg
    if team_response.status_code != 200:
        return f"Failed to assign user to team for org {org_id} "+' '.join(map(str,error_list))
    
    db_team_detail = db.get_session().query(SC_Team).filter(SC_Team.Team_Id == team_id).first()
    if db_team_detail is None:
            db.get_session().add(SC_Team(
                Team_Id = team_id,
                Team_Name = team_name,
                Active = "1",
                Description = team_name,
                SC_Organization_Id = org_id
                )
            )
    else:
        db_team_detail.Team_Id = team_id
        db_team_detail.Team_Name = team_name
        db_team_detail.Active = "1"
        db_team_detail.Description = team_name
        db_team_detail.SC_Organization_Id = org_id
    assignusers_for_scalar_team_db(db=db, user_ids_to_assign=user_ids, team_id=team_id)
    db.get_session().commit()

    return team_response

def unassignuser_from_team(db: Database, user_ids: list, team_id: str, org_id: str, access_token: str):

    team_response = unassign_user_from_team(access_token=access_token, team_id=team_id, user_ids=user_ids)
    if team_response.status_code != 200:
        error_list = get_scalar_api_error_messages(error_response=team_response)
        return error_list
    
    unassignusers_for_scalar_team_db(db=db, team_id=team_id, user_ids_to_unassign=user_ids)
    db.get_session().commit()

    return []

def assignusers_for_scalar_team_db(db: Database, team_id: str, user_ids_to_assign: list):
    for user in user_ids_to_assign:
        team_user_mapping = db.get_session().query(SC_Team_User_Mapping).filter(SC_Team_User_Mapping.Team_Id == team_id, SC_Team_User_Mapping.User_Id == user).first()
        if team_user_mapping is None:
            db.get_session().add(SC_Team_User_Mapping(
                User_Id = user,
                Team_Id = team_id,
                Active = "1"
            ))
        elif team_user_mapping.Active == '0':
            team_user_mapping.Active = '1'

def unassignusers_for_scalar_team_db(db: Database, team_id: str, user_ids_to_unassign: list):
    for user in user_ids_to_unassign:
        team_user_mapping = db.get_session().query(SC_Team_User_Mapping).filter(SC_Team_User_Mapping.Team_Id == team_id, SC_Team_User_Mapping.User_Id == user, SC_Team_User_Mapping.Active == "1").first()
        if team_user_mapping is not None:
            team_user_mapping.Active = "0"


def create_team_into_db_api(db: Database, team_name: str, org_id: str, access_token: str):
    teamname= check_team_in_api(db=db,teamName=team_name,access_token=access_token)
    if teamname is None:
        team_response = create_team(access_token=access_token,teamName=team_name , description = team_name )
        if team_response.status_code != 201:
            # to-do if exception needed to raise
            error_list = get_scalar_api_error_messages(error_response=team_response)
            return error_list
        else:
            team_response_json = team_response.json()
            team_response_json["teamName"]= team_name
            team_response_json["description"]= team_name     

    else:
            team_response_json={"id":teamname,"teamName": team_name,
            "description": team_name}          

    db_team_detail = db.get_session().query(SC_Team).filter(SC_Team.Team_Id == team_response_json['id']).first()
    if db_team_detail is None:
            db.get_session().add(SC_Team(
                Team_Id = team_response_json['id'],
                Team_Name = team_response_json['teamName'],
                Active = "1",
                Description = team_response_json['description'],
                SC_Organization_Id = org_id
                )
            )
    else:
        db_team_detail.Team_Id = team_response_json['id']
        db_team_detail.Team_Name = team_response_json['teamName']
        db_team_detail.Active = "1"
        db_team_detail.Description = team_response_json['description']
        db_team_detail.SC_Organization_Id = org_id
    db.get_session().commit()

    return team_response_json

def check_team_in_api(db: Database,teamName: str,access_token: str):
    team_df =get_all_data(access_token=access_token,func=get_all_team)
    if len(team_df) > 0 and len(team_df.loc[team_df['name'] == teamName]):
        team_response =team_df.loc[team_df['name'] == teamName, 'id'].values[0]
    else:
        team_response =None
    return team_response

def get_team_info_by_name(tmapi_access_token:str, team_name: str):
    all_teams_dict_list = []
    team_info = None
    offset = 0
    while offset is not None:
        response = get_all_team(access_token=tmapi_access_token, offset=offset)
        attempt = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
        while response.status_code == 429 and attempt > 0:
            logger.info("Too many requests. Waiting 15 seconds before attempting to fetch team details by name.")
            time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
            response = get_all_team(access_token=tmapi_access_token, offset=offset)
            attempt = attempt - 1
            logger.info(f"get all teams api attempts left: {attempt}")
        while response.status_code == 500 and attempt > 0:
            error_text = get_scalar_api_error_messages(error_response=response)
            if 'HTTPSConnectionPool' in error_text:
                logger.info("Too many requests. Waiting 15 seconds before attempting to fetch team details by name.")
                time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
                response = get_all_team(access_token=tmapi_access_token, offset=offset)
                attempt = attempt - 1
                logger.info(f"get all teams api attempts left: {attempt}")
            else:
                logger.error(f"{error_text}")
                break
        if response.status_code == 429:
            message = f"Unable to fetch team details by name for {team_name} \
            Too many requests. Retry attempts exhausted."
            logger.error(message)
            raise ScalarException(message=message)
        if response.status_code == 200:
            all_teams_json = json.loads(response.content)
            offset = pagination_check(content=all_teams_json)
            all_teams_dict_list.extend(all_teams_json["items"])
        else:
            error_text = get_scalar_api_error_messages(error_response=response)
            logger.error(f"{error_text}")
            break
    if len(all_teams_dict_list) > 0:
        for team_dict in all_teams_dict_list:
            if team_dict['name'] == team_name:
                team_info = team_dict
    return team_info