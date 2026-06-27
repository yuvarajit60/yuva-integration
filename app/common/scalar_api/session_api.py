import requests
from .common_api import get_header, verify, data_sharing_hostname
from ..constants import ApiUrl
from datetime import datetime

def get_all_sessions(access_token : str, limit : int = 1000, offset : int = 0, status: str = "all"):
    url = ApiUrl.SESSIONS_URL.format(hostname=data_sharing_hostname)
    header = get_header(access_token=access_token)
    params = {'limit': limit, "offset": offset, "status": status}
    response = requests.get(url, headers=header, params=params, verify=verify)        
    return response

def get_all_sessions_for_a_framework(access_token: str, agreement_id : str, limit : int = 1000, offset : int = 0, status:str = 'all'):
    url = ApiUrl.SESSIONS_FOR_A_FRAMEWORK_URL.format(hostname=data_sharing_hostname, agreement_id = agreement_id)
    header = get_header(access_token=access_token)
    params = {'limit': limit, "offset": offset, "status": status}
    response = requests.get(url, headers=header, params=params, verify=verify)        
    return response

def get_specific_session(access_token: str, session_id : str):   
    url = ApiUrl.SPECIFIC_SESSION_URL.format(hostname=data_sharing_hostname, session_id = session_id)
    header = get_header(access_token=access_token)
    response = requests.get(url, headers=header, verify=verify)        
    return response

def create_session(access_token: str, assets, agreement_id: str, contract_id: str = None, 
                    desired_start: datetime = None, desired_stop: datetime = None):
    url = ApiUrl.SESSIONS_URL.format(hostname=data_sharing_hostname)
    req_body = {"agreementId": agreement_id,
                "contractId": contract_id,
                "desiredStart": desired_start,
                "desiredStop": desired_stop,
                "providerAssetIds": assets}
    header = get_header(access_token=access_token)
    response = requests.post(url, json=req_body, headers= header, verify=verify)        
    return response

def stop_session(access_token: str, session_id : str):
    url = ApiUrl.STOP_SESSION_URL.format(hostname=data_sharing_hostname)
    header = get_header(access_token=access_token)
    content = {"sessionId":session_id}
    response = requests.post(url, json=content, headers= header, verify=verify)        
    return response