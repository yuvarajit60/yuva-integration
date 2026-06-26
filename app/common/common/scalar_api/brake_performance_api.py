import requests

from app.common.scalar_api.common_api import get_header, verify, brake_performance_hostname
from ..constants import ApiUrl


def get_all_bp_assets(access_token: str, limit: int=250, offset: int = 0, asset_ids: list =[]):              
    brake_performance_url = ApiUrl.BRAKE_PERFORMANCE_URL.format(hostname=brake_performance_hostname)
    header = get_header(access_token=access_token)
    if len(asset_ids)>0:
        parameters = {"limit": limit, "offset": offset, "assetIds": ','.join(asset_ids)}
    else:
        parameters = {"limit": limit, "offset": offset}
    response = requests.get(brake_performance_url, params=parameters, headers=header, verify=verify)        
    return response

def get_specific_bp_asset(access_token: str, assetid: str):                 
    specific_bp_asset_url = ApiUrl.SPECIFIC_BRAKE_PERFORMANCE_URL.format(hostname=brake_performance_hostname, assetid=assetid)
    header = get_header(access_token=access_token)
    response = requests.get(specific_bp_asset_url, headers=header, verify=verify)        
    return response

def enable_ebpms_asset(access_token: str, asset_ids:list):
    enable_ebpms_asset_url = ApiUrl.BRAKE_EBPMS_ENABLE_URL.format(hostname=brake_performance_hostname)
    header = get_header(access_token=access_token)
    content = {"assetIds":asset_ids}
    response = requests.post(enable_ebpms_asset_url, headers=header, json= content, verify=verify)        
    return response

def disable_ebpms_asset(access_token: str, asset_ids:list):
    disable_ebpms_asset_url = ApiUrl.BRAKE_EBPMS_DISABLE_URL.format(hostname=brake_performance_hostname)
    header = get_header(access_token=access_token)
    content = {"assetIds":asset_ids}
    response = requests.post(disable_ebpms_asset_url, headers=header, json= content, verify=verify)        
    return response