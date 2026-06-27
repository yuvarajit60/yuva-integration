import requests

from app.common.scalar_api.common_api import get_header, verify, user_hostname
from ..constants import ApiUrl


def get_all_user(access_token: str, limit: int = 100, offset: int = 0, status: str = None):               
    all_user_url = ApiUrl.ALL_USER_URL.format(hostname=user_hostname)
    header = get_header(access_token=access_token)
    parameters = {"limit": limit, "offset": offset, "status": status}
    response = requests.get(all_user_url, params=parameters, headers=header, verify=verify)        
    return response

def get_specific_user(access_token: str, user_id: str):
    specific_user_url = ApiUrl.SPECIFIC_USER_URL.format(hostname=user_hostname,user_id=user_id)
    header = get_header(access_token=access_token)
    response = requests.get(specific_user_url, headers=header, verify=verify)        
    return response

def create_user(access_token: str, user_req_body):
    create_user_url = ApiUrl.CREATE_USER_URL.format(hostname=user_hostname)
    header = get_header(access_token=access_token)
    response = requests.post(create_user_url, headers=header, json=user_req_body, verify=verify)        
    return response

def update_user(access_token: str, user_id: str, user_req_body):
    update_user_url = ApiUrl.SPECIFIC_USER_URL.format(hostname=user_hostname,user_id=user_id)
    header = get_header(access_token=access_token,content_type="application/merge-patch+json")
    response = requests.patch(update_user_url, headers=header, json=user_req_body, verify=verify)        
    return response

def delete_user(access_token: str, user_id: str):
    delete_user_url = ApiUrl.SPECIFIC_USER_URL.format(hostname=user_hostname,user_id=user_id)
    header = get_header(access_token=access_token,content_type="application/json")
    response = requests.delete(delete_user_url , headers=header, verify=verify)        
    return response


