import requests

from app.common.scalar_api.common_api import get_header, teams_hostname, verify
from ..constants import ApiUrl

def get_all_team(access_token: str, limit: int=100, offset: int = 0):               
    get_all_team_url = ApiUrl.TEAM_URL.format(hostname=teams_hostname)
    header = get_header(access_token=access_token)
    parameters = {"limit": limit, "offset": offset}
    response = requests.get(get_all_team_url, params=parameters, headers=header, verify=verify)        
    return response

def get_users_in_team(access_token: str, team_id: str):               
    get_user_in_team_url = ApiUrl.USER_IN_TEAM_URL.format(hostname=teams_hostname,team_id=team_id)
    header = get_header(access_token=access_token)
    response = requests.get(get_user_in_team_url, headers=header, verify=verify)        
    return response

def assign_user_to_team(access_token: str, team_id:str, user_ids:list):
    assign_user_url = ApiUrl.ASSIGN_USER_TO_TEAM_URL.format(hostname=teams_hostname)
    header = get_header(access_token=access_token)
    content = {"teamId":team_id, "userIds":user_ids}
    response = requests.post(assign_user_url, headers=header, json= content, verify=verify)        
    return response

def unassign_user_from_team(access_token: str, team_id:str, user_ids:list):
    unassign_user_url = ApiUrl.UNASSIGN_USER_TO_TEAM_URL.format(hostname=teams_hostname)
    header = get_header(access_token=access_token)
    content = {"teamId":team_id, "userIds":user_ids}
    response = requests.post(unassign_user_url, headers=header, json=content, verify=verify)        
    return response

def create_team(access_token: str, teamName: str, description: str):
    create_team_url = ApiUrl.TEAM_URL.format(hostname=teams_hostname)
    req_body = {
        "teamName" : teamName,
        "description":description
    }
    header = get_header(access_token=access_token)
    response = requests.post(create_team_url, headers=header, json=req_body, verify=verify)        
    return response

def edit_team(access_token: str, team_id: str, teamName:str, description:str):
    edit_team_url = ApiUrl.SPECIFIC_TEAM_URL.format(hostname=teams_hostname, team_id=team_id)
    header = get_header(access_token=access_token, content_type="application/merge-patch+json")
    content = {"teamName":teamName, "description":description}
    response = requests.patch(edit_team_url, headers=header, json=content, verify=verify)        
    return response

def delete_team(access_token: str, team_id: str):
    delete_team_url = ApiUrl.SPECIFIC_TEAM_URL.format(hostname=teams_hostname,team_id=team_id)
    header = get_header(access_token=access_token)
    response = requests.delete(delete_team_url, headers=header, verify=verify)        
    return response


def assign_asset_groups_to_team(access_token: str, team_id:str, asset_group_ids:list):
    assign_asset_group_url = ApiUrl.ASSIGN_ASSET_GROUP_TO_TEAM_URL.format(hostname=teams_hostname)
    header = get_header(access_token=access_token)
    content = {"teamId":team_id, "assetGroupIds":asset_group_ids}
    response = requests.post(assign_asset_group_url, headers=header, json= content, verify=verify)        
    return response

def unassign_asset_groups_from_team(access_token: str, team_id:str, asset_group_ids:list):
    unassign_asset_group_url = ApiUrl.UNASSIGN_ASSET_GROUP_TO_TEAM_URL.format(hostname=teams_hostname)
    header = get_header(access_token=access_token)
    content = {"teamId":team_id, "assetGroupIds":asset_group_ids}
    response = requests.post(unassign_asset_group_url, headers=header, json= content, verify=verify)        
    return response 