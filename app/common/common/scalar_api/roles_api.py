import requests

from app.common.scalar_api.common_api import get_header, verify, user_hostname
from ..constants import ApiUrl


def get_all_role(access_token: str, limit: int = 249, offset: int = 0, status: str = None):               
    all_user_url = ApiUrl.ALL_ROLE_URL.format(hostname=user_hostname)
    header = get_header(access_token=access_token)
    parameters = {"limit": limit, "offset": offset, "status": status}
    response = requests.get(all_user_url, params=parameters, headers=header, verify=verify)        
    return response