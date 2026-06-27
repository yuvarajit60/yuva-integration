import time
import pandas as pd
from app.common.constants import AudienceCode, GeneralConstant
from app.common.database import Database
from app.common.helpers.common_data_access import get_agreement_id
from app.common.helpers.common_services import fetch_access_token, generate_common_multi_error_report, get_combined_err_list, get_scalar_api_error_messages
from app.common.helpers.session_helpers import get_session_data_by_framework, insert_update_session_in_db
from app.common.scalar_api.asset_api import update_asset
from app.common.scalar_api.asset_group_api import unassign_asset_from_assetgroup
from app.common.scalar_api.session_api import get_specific_session, stop_session


def stop_datasharing(db: Database, asset_ids: list, access_token: str, consumer_org_id: str):
    session_stopped_assets = []
    error_list = []
    agreement_id = get_agreement_id(db=db, org_id=consumer_org_id)
    if agreement_id == None:
        error_list.append(f"organizationId: {consumer_org_id} invalid/doesn't exist. Agreement ID not found.")
    else:
        agreement_id = agreement_id[0]
        all_sessions_df = get_session_data_by_framework(access_token = access_token, agreement_id=agreement_id, status='running')
        if all_sessions_df.empty:
            no_datasharing_assets = asset_ids
        else:
            running_sessions_found = all_sessions_df.loc[all_sessions_df["providerAssetId"].isin(asset_ids)]
            no_datasharing_assets = [asset_id for asset_id in asset_ids if asset_id not in all_sessions_df["providerAssetId"].values]
            
            for session_id in running_sessions_found["sessionId"].tolist():
                stop_datasharing_response =  stop_session(session_id=session_id, access_token=access_token)
                if stop_datasharing_response.status_code == 200:
                    session_response= get_specific_session(access_token= access_token, session_id= session_id)
                    session_dict = session_response.json()
                    insert_update_session_in_db(db=db, session_dict=session_dict)
                    session_stopped_assets.append(running_sessions_found[running_sessions_found["sessionId"] == session_id]["providerAssetId"].iloc[0]) 
                else:
                    error_list.append({"Asset_Id":running_sessions_found[running_sessions_found["sessionId"] == session_id]["providerAssetId"].iloc[0], "api_error_message":get_scalar_api_error_messages(stop_datasharing_response)})

    return session_stopped_assets, no_datasharing_assets, error_list


def unassign_assets_from_group_in_provider_org(provider_access_token: str, provider_group_id: str, provider_asset_ids: list):

    assignment_response = unassign_asset_from_assetgroup(access_token=provider_access_token,
                                                            asset_group_id=provider_group_id,
                                                            asset_ids=provider_asset_ids)
    return get_scalar_api_error_messages(error_response=assignment_response)

        
def get_control_report_records(unit_df) :
    control_report_records = []
    for index, unit in unit_df.iterrows():
        control_report_record = {}
        control_report_record["Unit_Number"] = int(unit["UnitNr"])
        control_report_record["License_Plate_Number"] = unit["UnitLicenceNr"]
        control_report_record["Customer_Combi_Number"] = unit["CustomerCombiNr"]
        control_report_record["Region"] = unit["Region_Name"]
        control_report_record["Country"] = unit["Country_Name"]
        control_report_record["Customer_Name"] = unit["organization_name"]
        control_report_record["Rate_Number"] = unit["RateNr"]
        control_report_record["Master_Lease_Number"] = unit["MasterLeaseNr"]
        r_org_id = unit["Root_Organization_Id"]
        control_report_record["Root_Org_Id"] = int(r_org_id) if r_org_id is not None else r_org_id
        control_report_record["Root_Org_Name"] = unit["root_org_name"]
        org_id = unit["Organization_Id"]
        control_report_record["Org_Id"] = int(org_id) if org_id is not None else org_id
        control_report_record["Org_Name"] = unit["organization_name"]
        control_report_record["Asset_Id"] = unit["Asset_Id"]
        control_report_records.append(control_report_record)
    return control_report_records


def generate_interchangein_unit_report(units_wout_root_org_list, units_wout_pairing_info_list,
                                            consumer_issues_unit_list, datasharing_removed_unit_list,
                                            datasharing_not_exist_unit_list, unknown_errors):
    combined_err_list = get_combined_err_list(units_wout_root_org_list=units_wout_root_org_list,
                        units_wout_pairing_info_list=units_wout_pairing_info_list,
                        consumer_issues_unit_list=consumer_issues_unit_list,
                        data_sharing_removed_unit_list=datasharing_removed_unit_list,
                        data_sharing_not_exists_list=datasharing_not_exist_unit_list,
                        unknown_errors=unknown_errors)
    report_content = None
    if len(combined_err_list) > 0:
        report_content = generate_common_multi_error_report(error_list=combined_err_list)
    return report_content

def provider_asset_fleet_id_change(db:Database, provider_assets: list, provider_org_id: str):
    provider_access_token = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.ASSET)
    errors = []
    for provider_asset_id in provider_assets:
        attempts = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
        body = {"fleetId": None}
        response = update_asset(access_token=provider_access_token, assetid=provider_asset_id, json_payload=body)
        while response.status_code == 429 and attempts > 0:
            time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
            response = update_asset(access_token=provider_access_token, assetid=provider_asset_id, json_payload=body)
            attempts = attempts - 1
        errors.extend(get_scalar_api_error_messages(error_response=response))
    return errors
