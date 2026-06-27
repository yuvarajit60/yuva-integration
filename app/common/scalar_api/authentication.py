import os
import requests

from ..constants import ApiUrl
from app.common.scalar_api.common_api import verify
 
 
def get_access_token( client_id: str, client_secret: str, audience: str):              
    hostname = os.environ["AUTH_API_URL"]    
    authenitcation_uri = ApiUrl.AUTHENTICATION_URL.format(hostname=hostname)
    access_token = None
    access_token_type = None
    expires_in = None
    errors = None
    body = {"clientId": client_id, "clientSecret": client_secret,"audience": audience}
    response = requests.post(authenitcation_uri, json=body, verify=verify)        
    if response.status_code == 200:
        response_json = response.json()
        access_token = response_json.get("accessToken")
        access_token_type = response_json.get("tokenType")
        expires_in = response_json.get("expiresIn")
    elif response.status_code == 401:
        errors = response.json()['message']
    return access_token,access_token_type,expires_in,errors