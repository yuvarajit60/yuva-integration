import logging
import requests

from app.common.scalar_api.common_api import get_header, verify, asset_group_hostname
from ..constants import ApiUrl, GeneralConstant

def create_asset_group(access_token: str, name:str, description: str, parent_group_id: str = None):               
    asset_group_url = ApiUrl.ASSET_GROUP_URL.format(hostname=asset_group_hostname)

    req_body = {
        "name":name,
        "description":description
    }
    if parent_group_id:
        req_body["parentGroupId"] = parent_group_id

    header = get_header(access_token=access_token)
    response = requests.post(asset_group_url, json=req_body, headers=header, verify=verify)        
    return response

def get_specific_asset_group(access_token: str, asset_group_id: str):                 
    specific_asset_group_url = ApiUrl.SPECIFIC_ASSET_GROUP_URL.format(hostname=asset_group_hostname, asset_group_id=asset_group_id)
    header = get_header(access_token=access_token)
    response = requests.get(specific_asset_group_url, headers=header, verify=verify)        
    return response

def get_all_asset_groups(access_token: str, limit: int=100, offset: int = 0):              
    asset_group_url = ApiUrl.ASSET_GROUP_URL.format(hostname=asset_group_hostname) 
    header = get_header(access_token=access_token)
    parameters = {"limit": limit, "offset": offset}
    response = requests.get(asset_group_url, params=parameters, headers=header, verify=verify)        
    return response

def update_asset_group(access_token: str, asset_group_id: str, name: str, description: str):                
    specific_asset_url = ApiUrl.SPECIFIC_ASSET_GROUP_URL.format(hostname=asset_group_hostname, asset_group_id=asset_group_id)
    header = get_header(access_token=access_token)
    content = {"name":name, "description":description}
    response = requests.patch(specific_asset_url, json=content, headers=header, verify=verify)        
    return response

def assign_asset_to_assetgroup(access_token: str, asset_ids: list, asset_group_id: str):
    assign_asset_group_url = ApiUrl.ASSIGN_ASSET_GROUP_URL.format(hostname=asset_group_hostname)
    header = get_header(access_token=access_token)
    for curr_index in range(0, len(asset_ids), 100): 
        content = {"assetGroupId":asset_group_id, "assetIds":asset_ids[curr_index:curr_index + 100]}
        response = requests.post(assign_asset_group_url, json=content, headers=header, verify=verify)
        logging.info(f"Assigning asset to asset group response status: {response.status_code}")
    return response

def unassign_asset_from_assetgroup(access_token: str,asset_ids: list, asset_group_id: str):
    unassign_asset_group_url = ApiUrl.UNASSIGN_ASSET_GROUP_URL.format(hostname=asset_group_hostname)
    header = get_header(access_token=access_token, content_type="application/json")
    for curr_index in range(0, len(asset_ids), 100): 
        content = {"assetGroupId":asset_group_id, "assetIds":asset_ids[curr_index:curr_index + 100]}
        response = requests.post(unassign_asset_group_url, json=content, headers=header, verify=verify)
        logging.info(f"Unassigning asset from asset group response status: {response.status_code}") 
    return response

def delete_asset_group(access_token: str, asset_group_id: str):                 
    specific_asset_url = ApiUrl.SPECIFIC_ASSET_GROUP_URL.format(hostname=asset_group_hostname, asset_group_id=asset_group_id)
    header = get_header(access_token=access_token)
    response = requests.delete(specific_asset_url, headers=header, verify=verify)        
    return response
