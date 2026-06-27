import os

verify = bool(os.environ["SSL_VERIFICATION"])
data_sharing_hostname = os.environ["DATA_SHARING_API_URL"]
user_hostname = os.environ["USER_API_URL"]
asset_hostname = os.environ["ASSET_API_URL"]
teams_hostname = os.environ["TEAM_API_URL"] 
asset_group_hostname = os.environ["ASSET_GROUP_API_URL"]
brake_performance_hostname = os.environ["BRAKE_PERFORMANCE_URL"]


def get_header(access_token: str, content_type="application/json"):
    header = {"Authorization": "Bearer "+ access_token, "Content-Type": content_type}
    return header

