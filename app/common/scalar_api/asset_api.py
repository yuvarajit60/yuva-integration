import requests

from app.common.scalar_api.common_api import get_header, verify, asset_hostname
from ..constants import ApiUrl


def get_all_assets(access_token: str, limit: int=250, offset: int = 0):              
    asset_url = ApiUrl.ASSET_URL.format(hostname=asset_hostname)
    header = get_header(access_token=access_token)
    parameters = {"limit": limit, "offset": offset}
    response = requests.get(asset_url, params=parameters, headers=header, verify=verify)        
    return response

def get_specific_asset(access_token: str, assetid: str):                 
    specific_asset_url = ApiUrl.SPECIFIC_ASSET_URL.format(hostname=asset_hostname, assetid=assetid)
    header = get_header(access_token=access_token)
    response = requests.get(specific_asset_url, headers=header, verify=verify)        
    return response

def create_asset(access_token: str, asset_category: str, license_plate: str, tip_unit_nr: str, customer_ref_no: str, vin: str, group_ids: list, devices: list):               
    asset_url = ApiUrl.ASSET_URL.format(hostname=asset_hostname)
    header = get_header(access_token=access_token)
    asset = create_asset_request_body(asset_category=asset_category, license_plate=license_plate, internal_code=tip_unit_nr, fleet_id=customer_ref_no, vin=vin, group_ids=group_ids, devices=devices)
    response = requests.post(asset_url, json=asset, headers=header, verify=verify)        
    return response

def update_asset(access_token: str, assetid: str, json_payload: dict):                
    get_specific_asset_url = ApiUrl.SPECIFIC_ASSET_URL.format(hostname=asset_hostname, assetid=assetid)
    header = get_header(access_token=access_token, content_type="application/merge-patch+json")
    response = requests.patch(get_specific_asset_url, json=json_payload, headers=header, verify=verify)        
    return response

def delete_asset(access_token: str, assetid: str):                 
    get_specific_asset_url = ApiUrl.SPECIFIC_ASSET_URL.format(hostname=asset_hostname, assetid=assetid)
    header = get_header(access_token=access_token)
    response = requests.delete(get_specific_asset_url, headers=header, verify=verify)        
    return response

def pairing_asset_with_device(access_token: str, assetid: str, device_id: str):                 
    get_specific_asset_url = ApiUrl.SPECIFIC_ASSET_URL.format(hostname=asset_hostname, assetid=assetid)
    header = get_header(access_token=access_token, content_type="application/merge-patch+json")
    content = {"devices":[device_id]}
    response = requests.patch(get_specific_asset_url, json=content, headers=header, verify=verify)        
    return response

def create_asset_request_body(asset_category: str, license_plate: str, internal_code: str, fleet_id: str, vin: str, group_ids: list, devices: list):

    asset_request_json={"assetType": "Trailer",
        "mileage": 0,
        "assetCategory": asset_category, 
        "displayName": f"{str(internal_code)} ({license_plate})",
        "licensePlate": license_plate,
        "internalCode": str(internal_code),
        "externalCode": None, 
        "fleetId": fleet_id, 
        "vin": vin, 
        "assignees": {"all": False,"groupIds": group_ids if group_ids is not None else None},
        "devices": devices if devices is not None else None
    }
    return asset_request_json