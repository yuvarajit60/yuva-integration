from venv import logger

import pandas as pd
from app.brake_performance.brake_performance_activate.brake_performance_activate_data_access import update_existing_bp_data_in_db
from app.common.database import Database
from app.common.scalar_api.brake_performance_api import enable_ebpms_asset, get_all_bp_assets
from app.common.helpers.common_services import  get_all_data, get_scalar_api_error_messages

def activate_bp_assets(db: Database, org_id: str, access_token: str, asset_ids: list):
    
    successfully_bp_activated_units =[]
    bp_failed_units = list()
    for asset_id in asset_ids:
        temp_bp_failed_units = list()
        asset_ids= list((asset_id,))
        activate_response = enable_ebpms_asset(access_token= access_token, asset_ids= asset_ids)
        if activate_response.status_code != 200:
            error_list = get_scalar_api_error_messages(error_response=activate_response)
            message=f"Failed to activate asset {asset_id} for provider org {org_id} "+' '.join(map(str,error_list))
            logger.warning(message)
            temp_bp_failed_units = [{"Asset_Id":asset_id,"error":"; ".join(error_list) if isinstance(error_list,list) else str(error_list)}]
        else:
            successfully_bp_activated_units.append(asset_id)
        if len(temp_bp_failed_units) > 0:
            bp_failed_units.extend(temp_bp_failed_units)
    return successfully_bp_activated_units,temp_bp_failed_units

def sync_and_check_if_really_activated(db: Database, access_token: str, activated_units: list):
    brakeplus_data = get_all_data(access_token=access_token,func=get_all_bp_assets)
    brakeplus_data_df = pd.DataFrame(brakeplus_data) if brakeplus_data is not None else None
    curr_brakeplus_data_df = brakeplus_data_df.loc[brakeplus_data_df["assetId"].isin(activated_units)]
    truly_bp_activated_units = curr_brakeplus_data_df.loc[(curr_brakeplus_data_df["ebpms"] == 'enabling') | (curr_brakeplus_data_df["ebpms"] == 'enabled')]
    falsely_bp_activated_units = curr_brakeplus_data_df.loc[curr_brakeplus_data_df["ebpms"] == 'disabled']
    
    update_existing_bp_data_in_db(db=db, existing_bp_data=curr_brakeplus_data_df)

    return truly_bp_activated_units["assetId"].to_list(), falsely_bp_activated_units["assetId"].to_list()
