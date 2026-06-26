import logging
import os
from datetime import datetime
import time

import pandas as pd
import numpy as np
from pandas import DataFrame
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_agreement_id, get_consumer_organization_data, get_cust_org_detail, \
    get_tip_provider_organization, get_sc_org_info_by_list_of_root_orgs
from app.common.helpers.session_helpers import get_session_data_by_framework, start_data_sharing
from app.common.helpers.unit_helpers import add_asset_group_mapping_in_db, assign_asset_to_groups_in_consumer_org,\
    get_insight_org_units_by_cust_org_id, get_insight_units_by_root_org, get_non_insight_units_by_root_org, add_missing_pairing_insight_unit,\
        update_missing_pairing_insight_unit_as_treated       
from app.common.helpers.process_helpers import get_units_by_root_orgs, generate_process_control_report, get_control_report_records
from app.common.helpers.common_services import assign_assets_to_consumer_group_in_provider_org, get_all_data, get_scalar_api_error_messages, start_job_execution_process, \
    update_job_execution_process, log_errors, get_distinct_count
from app.common.helpers.group_helpers import get_sc_groups
from app.common.helpers.common_services import fetch_access_token
from app.common.scalar_api.asset_api import get_all_assets, update_asset
from ..constants import ErrorFields, GeneralConstant, ResponseCode, StatusCode, AudienceCode
from ..database import Database
from ..email import Email
from ..models import Response

from app.common.helpers.group_helpers import get_asset_groups_for_root_org

def get_data_sharing_session(db: Database, cust_org_id: str, access_token: str, logger):
    org_detail = get_cust_org_detail(db=db, consumer_org_id=cust_org_id)
    consolidated_insight_units_df = None
    if len(org_detail) > 0:
        logger.info(f"FA Root org Id: {org_detail['FA_Root_Organization_Id'][0]} - FA Root org name:{org_detail['Organization_Name'][0]}")
        insight_fa_org_units_df = get_insight_org_units_by_cust_org_id(db=db, cust_org_id=cust_org_id)
        logger.info(f"Total Insight units linked to FA orgs: {len(insight_fa_org_units_df)}")
        insight_units_df = get_insight_units_by_root_org(db=db, root_org_id=int(org_detail['FA_Root_Organization_Id'][0]))
        logger.info(f"Total Insight units: {len(insight_units_df)}")
        subcontracted_response_df = get_session_info_from_api(db=db, access_token=access_token, cust_org_id=cust_org_id, logger=logger)
        logger.info(f"Total data shared units: {len(subcontracted_response_df)}")
        consolidated_insight_units_df = pd.merge(insight_units_df, insight_fa_org_units_df, on=["UnitNr", "UnitLicenceNr", "CustomerCombiNr"], how="outer")
        consolidated_insight_units_df = pd.merge(consolidated_insight_units_df, subcontracted_response_df, on=["Asset_Id"], how="outer")
        non_insight_units_df = consolidated_insight_units_df.loc[(pd.isnull(consolidated_insight_units_df["insight_unit"]))]
        if len(non_insight_units_df) > 0:
            asset_ids = non_insight_units_df["Asset_Id"].to_list()
            logger.info(f"Total non insight assets: {len(asset_ids)}")
            non_insight_unit_nrs = get_non_insight_units_by_root_org(db=db, root_org_id=int(org_detail['FA_Root_Organization_Id'][0]), asset_ids=asset_ids)
            unitNr_map = non_insight_unit_nrs.set_index("Asset_Id")["UnitNr"]
            consolidated_insight_units_df["UnitNr"] = consolidated_insight_units_df["UnitNr"].fillna(consolidated_insight_units_df["Asset_Id"].map(unitNr_map))
            non_insight_unit_nrs = non_insight_unit_nrs["UnitNr"].to_list()
            consolidated_insight_units_df.loc[consolidated_insight_units_df["UnitNr"].isin(non_insight_unit_nrs), "insight_unit"] = "False"
        consolidated_insight_units_df.loc[consolidated_insight_units_df['Device_Pairing_Status'] == "0", "Asset_Id"] = pd.NA
        logger.info(f"Total Consolidated Insight units: {len(consolidated_insight_units_df)}")

    return consolidated_insight_units_df



def get_session_info_from_api(db: Database, access_token: str, cust_org_id: str, logger):
    subcontracted_units_df = pd.DataFrame()
    agreement_id = get_agreement_id(db=db, org_id=cust_org_id)    
    if agreement_id is None:
        raise ScalarException(message=f"Agreement Id not found for org Id: {cust_org_id}")
    
    response_df = get_session_data_by_framework(access_token=access_token, agreement_id=agreement_id[0], status='running')

    if len(response_df) > 0:
        subcontracted_units_df["Asset_Id"] = response_df["providerAssetId"]
        subcontracted_units_df["consumer_org_id"] = response_df["consumerOrgId"]
        subcontracted_units_df["vin_number"] = response_df["vinNumber"]
        subcontracted_units_df["from_datetime"] = response_df["realStart"]
        subcontracted_units_df["to_datetime"] = response_df["realStop"]
        subcontracted_units_df["active"] = [1 if row in ["pending", "running"] else 0
                                            for row in response_df["status"]]
        subcontracted_units_df["data_sharing"] = "True"

    if len(subcontracted_units_df) == 0:
        return pd.DataFrame({'Asset_Id': pd.Series(dtype='str'),
                   'data_sharing': pd.Series(dtype='str')
                })
    else:
        return subcontracted_units_df.replace({np.nan: None})

def consumer_asset_name_change(db:Database, consumer_assets_df: DataFrame, consumer_org_id: str):
    consumer_access_token = fetch_access_token(db=db,org_id= consumer_org_id,audience= AudienceCode.ASSET)
    errors = []
    for index, consumer_asset in consumer_assets_df.iterrows():
        consumer_asset_id = consumer_asset['consumerAssetId']
        fleet_id = consumer_asset['Fleet_Id']
        vin_number = consumer_asset['VIN_Number']
        unit_nr = consumer_asset['UnitNr']
        fleet_id = None if pd.isna(fleet_id) else fleet_id
                    
        license_plate = (
            consumer_asset['UnitLicenceNr']
            if pd.notna(consumer_asset['UnitLicenceNr']) and str(consumer_asset['UnitLicenceNr']).strip()
            else str(consumer_asset['UnitNr'])
        )
        attempts = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
        if fleet_id is not None and len(fleet_id) > 0:
            body = {"displayName": fleet_id + " (" + license_plate + ")", "fleetId": fleet_id, "licensePlate": license_plate, "vin": vin_number}
        else:
            body = {"displayName": str(unit_nr) + " (" + license_plate + ")", "licensePlate": license_plate, "vin": vin_number}
        response = update_asset(access_token=consumer_access_token, assetid=consumer_asset_id, json_payload=body)
        while response.status_code == 429 and attempts > 0:
            time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
            response = update_asset(access_token=consumer_access_token, assetid=consumer_asset_id, json_payload=body)
            attempts = attempts - 1
        errors.extend(get_scalar_api_error_messages(error_response=response))
    return errors

def execute_data_sharing(db: Database, total_units_df: DataFrame, last_successful_execution_ts, process: str, 
                                                                        job_name: str, file_name: str) :
    logger = logging.getLogger("execute_data_sharing")

    try:
        message = ""
        exectution_time = datetime.now()
        error_list = []
        job_id = None 
        units_wout_fa_scalar_org_list = []
        units_wout_pairing_info_list = []
        missing_scalar_cust_onboarding_list = list()
        missing_scalar_cust_onboarding_set = set()
        data_shared_unit_list = []
        already_data_shared_unit_list = []
        diff_org_already_data_shared_unit_list = []
        # data_sharing_issues_unit_set = set()
        data_shared_unit_set = set()
        already_data_shared_unit_set = set()
        diff_org_already_data_shared_unit_set = set()
        unwanted_error_list = []
        total_distinct_units_count, units_wout_fa_scalar_org_count, units_wout_pairing_info_count = 0, 0, 0

        total_distinct_units_count = get_distinct_count(data_set=total_units_df)
        logger.info(f"Total units: {len(total_units_df)}, New distinct units to processed: {total_distinct_units_count}")
        job_id = start_job_execution_process(db=db, job_name=job_name)

        if total_distinct_units_count > 0:
            provider_organization = get_tip_provider_organization(db=db)
            if provider_organization is None:
                raise ScalarException(message="Provider Organization is not found")
            provider_org_id = provider_organization[0]

            provider_access_token_data_sharing = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.DATA_SHARING)
            provider_access_token_teams = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.TEAMS)

            units_wout_fa_scalar_org_df = total_units_df.loc[pd.isna(total_units_df['Organization_Id'])].drop_duplicates()
            units_wout_pairing_info_df = total_units_df.loc[(pd.isna(total_units_df['Asset_Id']) & pd.notnull(total_units_df['Organization_Id']))]
            units_wout_pairing_info_set = set(units_wout_pairing_info_df['UnitNr'].tolist())
            units_with_root_org_asset_id_df = total_units_df.loc[pd.notnull(total_units_df['Organization_Id'])].\
                                                                            loc[pd.notnull(total_units_df['Asset_Id'])]
            
            units_by_root_orgs: dict = get_units_by_root_orgs(units_with_root_org_asset_id_df)

            for fa_root_org_id in units_by_root_orgs.keys():
                org_dict = units_by_root_orgs[fa_root_org_id]
                org_ids = list(org_dict.keys())
                
                # units dataframe combines all units of all child orgs into one
                units = pd.DataFrame()
                for org_id in org_ids:
                    units = pd.concat([units, org_dict[org_id]], ignore_index=True)

                # Fetch SC_Organization detail since total_units_df contains FA_Organization_Id
                consumer_details = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
                if consumer_details is not None and len(consumer_details) > 0:
                    consumer_org_id = consumer_details['Organization_Id'][0]
                    ZF_customer = consumer_details['ZF_Consumer_Org'][0]
                else:
                    missing_scalar_cust_onboarding_list.extend(get_control_report_records(unit_df=units))
                    missing_scalar_cust_onboarding_set.update(units['UnitNr'].to_list())
                    continue

                new_sessions_list, existing_sessions_in_same_org, existing_sessions_in_different_org, \
                    unwanted_error_list = start_data_sharing(db=db, access_token=provider_access_token_data_sharing,
                                                            provider_org_id=provider_org_id,
                                                            consumer_org_id=consumer_org_id, 
                                                        asset_list=units['Asset_Id'].to_list(), logger=logger)

                new_ds_asset_list = [val['providerAssetId'] for val in new_sessions_list]
                new_ds_df = units.loc[units['Asset_Id'].isin(new_ds_asset_list)]
                data_shared_unit_list.extend(get_control_report_records(unit_df=new_ds_df))
                data_shared_unit_set.update(set(new_ds_df['UnitNr'].to_list()))

                already_ds_asset_list = [val['providerAssetId'] for val in existing_sessions_in_same_org]
                already_ds_df = units.loc[units['Asset_Id'].isin(already_ds_asset_list)]
                already_data_shared_unit_list.extend(get_control_report_records(unit_df=already_ds_df))
                already_data_shared_unit_set.update(set(already_ds_df['UnitNr'].to_list()))

                #Prepare similar list and set of existing_sessions_in_different_org
                already_ds_diff_org_asset_list = [val['providerAssetId'] for val in existing_sessions_in_different_org]
                already_ds_diff_org_df = units.loc[units['Asset_Id'].isin(already_ds_diff_org_asset_list)]
                diff_org_already_data_shared_unit_list.extend(get_control_report_records(unit_df=already_ds_diff_org_df))
                diff_org_already_data_shared_unit_set.update(set(already_ds_diff_org_df['UnitNr'].to_list()))

                if len(unwanted_error_list) > 0:
                    logger.error(f"Error occured while data sharing units, Root Org Id: {fa_root_org_id} and Error: {unwanted_error_list}")
                    error_list.extend(log_errors(error_list=unwanted_error_list, field=ErrorFields.ORGANIZATION_ID, value=consumer_org_id))

                # consumer_group_name_in_provider = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]['Asset_Group_Name'].values[0]
                logger.info(f"Assigning assets in provider org for root org {fa_root_org_id}")
                # Skipping the Asset Assignment for Culina Group in TIP Scalar as the customer asset group has already got 5k assets
                # Need to remove this condition once the restriction has removed.
                if fa_root_org_id != 38:
                    assign_error_list = assign_assets_to_consumer_group_in_provider_org(db=db,access_token=provider_access_token_teams,
                                                        fa_root_org_id=fa_root_org_id,
                                                        asset_ids=units['Asset_Id'].to_list(),
                                                        provider_org_id=provider_org_id
                                                        )
                    if len(assign_error_list) > 0:
                        error_list.extend(log_errors(error_list=assign_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                        logger.error(f"Error occured while assigning datashared units to provider group, FLeetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                        continue
                else:
                    logger.warning("Skipping the Asset Assignment for Culina Group in TIP Scalar as the customer asset group has already got 5k assets")

                # fetching all asset groups of the root org, under both provider and consumer orgs
                sc_groups_df = get_sc_groups(db=db, fa_organization_ids= org_ids+[fa_root_org_id])

                # Consumer group under provider org
                tip_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]
                if len(tip_group_df) == 0:
                    error_msg = f"No group record found for org id {org_id} of fleetadmin root org id {fa_root_org_id} under provider org id {provider_org_id}"
                    logger.error(error_msg)
                    error_list.extend(log_errors(error_list=[error_msg], field=ErrorFields.ORGANIZATION_ID, value=org_id))
                    continue
                
                tip_group = tip_group_df.iloc[0]
                asset_nrs = units['Asset_Id'].tolist()
                add_asset_group_mapping_in_db(db=db, asset_nrs=asset_nrs, group_id=tip_group.Asset_Group_Id)

                new_data_shared_unit_df=pd.DataFrame(new_sessions_list, columns=['providerAssetId','consumerAssetId'])
                already_data_shared_unit_df=pd.DataFrame(existing_sessions_in_same_org, columns=['providerAssetId','consumerAssetId'])
                units = units.loc[(units["UnitNr"].isin(data_shared_unit_set)) | (units["UnitNr"].isin(already_data_shared_unit_set))]
                combined_assets_df = pd.concat([already_data_shared_unit_df,new_data_shared_unit_df], ignore_index=True).drop_duplicates()

                # units assign to groups in consumer org will only happen to TIP owned customer tenancies
                if len(combined_assets_df) > 0 and ZF_customer == 0:

                    consumer_access_token = fetch_access_token(db=db,org_id= consumer_org_id,audience= AudienceCode.TEAMS)
                    units_to_edit = units.merge(combined_assets_df,
                                            left_on='Asset_Id',
                                            right_on='providerAssetId',
                                            how='inner')[['UnitNr','consumerAssetId','UnitLicenceNr','Fleet_Id','VIN_Number']]
                    change_error_list = consumer_asset_name_change(db=db, 
                                                        consumer_assets_df=units_to_edit, 
                                                        consumer_org_id=consumer_org_id
                                                        )
                    if len(change_error_list) > 0:
                        # error_list.extend(log_errors(error_list=change_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                        logger.error(f"Error occured while changing asset name for customer organization, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                        continue
                    logger.info(f"Assets name update for root org {fa_root_org_id} successful.")

                    logger.info(f"Assigning assets to consumer orgs in root org {fa_root_org_id}")
                    for org_id in org_ids:

                        units_to_assign = org_dict[org_id] # units by each child org
                        consumer_asset_ids_list = combined_assets_df.merge(units_to_assign,
                                                                        left_on= 'providerAssetId',
                                                                        right_on='Asset_Id',
                                                                        how='inner')['consumerAssetId'].to_list()
                        
                        consumer_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == org_id) & (sc_groups_df['SC_Organization_Id'] == consumer_org_id)]
                        if len(consumer_group_df) == 0:
                            error_msg = f"No Scalar group record found for organization id {org_id} of root org id {fa_root_org_id} under scalar consumer org {consumer_org_id}"
                            logger.error(error_msg)
                            error_list.extend(log_errors(error_list=[error_msg], field=ErrorFields.ORGANIZATION_ID, value=org_id))
                            continue
                        consumer_group = consumer_group_df.iloc[0]

                        logger.info(f"Assigning assets {len(consumer_asset_ids_list)} for child org {org_id}")
                        if len(consumer_asset_ids_list):
                            assign_error_list = assign_asset_to_groups_in_consumer_org(consumer_access_token=consumer_access_token,
                                                                consumer_group_id=consumer_group.Asset_Group_Id,
                                                                consumer_asset_ids=consumer_asset_ids_list,
                                                                )

                            if len(assign_error_list) > 0:
                                error_list.extend(log_errors(error_list=assign_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                                logger.error(f"Error occured while assigning datashared units to customer group, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                                continue
                            
                            add_asset_group_mapping_in_db(db=db, asset_nrs=consumer_asset_ids_list, group_id=consumer_group.Asset_Group_Id)

            logger.info(f"Datasharing and assetgroup assignment done. Updating missing pairing units details")            
            units_wout_fa_scalar_org_df = units_wout_fa_scalar_org_df.loc[~units_wout_fa_scalar_org_df['UnitNr'].isin(data_shared_unit_set)]
            units_wout_fa_scalar_org_df = units_wout_fa_scalar_org_df.loc[~units_wout_fa_scalar_org_df['UnitNr'].isin(already_data_shared_unit_set)]
            units_wout_fa_scalar_org_df = units_wout_fa_scalar_org_df.loc[~units_wout_fa_scalar_org_df['UnitNr'].isin(missing_scalar_cust_onboarding_set)]
            units_wout_fa_scalar_org_df = units_wout_fa_scalar_org_df.loc[~units_wout_fa_scalar_org_df['UnitNr'].isin(units_wout_pairing_info_set)]
            units_wout_fa_scalar_org_list = get_control_report_records(unit_df=units_wout_fa_scalar_org_df)
            units_wout_fa_scalar_org_count = get_distinct_count(data_set=units_wout_fa_scalar_org_df)
            units_wout_pairing_info_list = get_control_report_records(unit_df=units_wout_pairing_info_df)
            units_wout_pairing_info_count = get_distinct_count(data_set=units_wout_pairing_info_df)
            treated_units = set()
            treated_units.update(data_shared_unit_set)
            treated_units.update(already_data_shared_unit_set)
            update_missing_pairing_insight_unit_as_treated(db=db, treated_units=list(treated_units))
            # Filter out non-scalar org related units
            if len(units_wout_pairing_info_df) > 0:
                # Find if the units in wout_pairing_df are linked to scalar orgs
                fa_root_org_id_list = set(units_wout_pairing_info_df['Root_Organization_Id'].to_list())
                scalar_orgs_df = get_sc_org_info_by_list_of_root_orgs(db=db, 
                                                    fa_root_org_list=list(fa_root_org_id_list))
                if len(scalar_orgs_df) > 0:
                    # update only the units of scalar orgs from the wout_pairing_df
                    units_wout_pairing_info_df = units_wout_pairing_info_df.loc[units_wout_pairing_info_df['Root_Organization_Id'].isin(\
                        scalar_orgs_df['FA_Root_Organization_Id'])]
                    add_missing_pairing_insight_unit(db=db, missing_pairing_units_df=units_wout_pairing_info_df, process_name=process)

            #job will be marked as failure only if there is any error or pairing is missing
            #job will be marked as successful even if there is missing organization details or tenancies not yet created/populated
            if len(error_list) > 0:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
                message = f"Insight {process} units have been processed with some errors."
                message += " Please refer to the attached excelsheet"
            elif units_wout_fa_scalar_org_count > 0 or units_wout_pairing_info_count > 0 or len(missing_scalar_cust_onboarding_list) > 0:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)
                message = f"Insight {process} units have been processed successfully."
                message += " Though there are some units which are not linked to any FA Scalar organization or their customer is not yet onboarded to Scalar."
                message += " Please refer to the attached excelsheet"
            else:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)
                message = f"Insight {process} units have been processed successfully"

        else:
            message = f"No new {process} units found with Insight additional charges since last successful job run timestamp {last_successful_execution_ts}"
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)

        logger.info(message)

        response = Response(status=True, message=message)
        return message, ResponseCode.SUCCESS

    except SQLAlchemyError as sae:
        message = GeneralConstant.DB_EXCP_MESSAGE
        error_list.extend(log_errors([str(sae)], "DB Exception", None))
        logger.error(sae, exc_info=True)
        if job_id is not None:
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
        return message, ResponseCode.INTERNAL_ERROR
    except Exception as e:
        message = str(e)
        error_list.extend(log_errors([message], "Application Exception", None))
        logger.error(message, exc_info=True)
        if job_id is not None:
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
        response = Response(status=False, message=message)
        return message, ResponseCode.INTERNAL_ERROR
    finally:
        process_control_report = generate_process_control_report(units_wout_root_org_list= units_wout_fa_scalar_org_list, 
                                                units_wout_pairing_info_list=units_wout_pairing_info_list,
                                            consumer_issues_unit_list = missing_scalar_cust_onboarding_list,
                                             data_shared_unit_list=data_shared_unit_list,
                                            already_data_shared_unit_list=already_data_shared_unit_list,
                                            diff_org_already_data_shared_unit_list = diff_org_already_data_shared_unit_list,
                                             unknown_errors= error_list)
                            
        email = Email()
        receivers = os.environ["REPORT_MAIL_DL"].split(",")
        
        subject = f"Scalar - Insight {process} Units Report"
        template_name = f"{file_name}.html"
        environment = os.environ['SCALAR_ENV']

        if environment != 'PROD':
            subject = f"{subject} - {environment}"
        params = {
            "environment": environment,
            "exectution_time": exectution_time,
            "exectution_message": message,
            "process": process,
            "total_units_count": total_distinct_units_count,
            "units_wout_root_org_count":units_wout_fa_scalar_org_count,
            "units_wout_pairing_info_count":units_wout_pairing_info_count,
            "consumer_issues_unit_count": len(missing_scalar_cust_onboarding_set),
            "data_shared_unit_count":len(data_shared_unit_set),
            "already_data_shared_unit_count":len(already_data_shared_unit_set),
            "already_data_shared_in_diff_org_count": len(diff_org_already_data_shared_unit_set),
            "error_list_count":len(error_list),
            "last_successful_execution_ts": last_successful_execution_ts
            }
        attachment = None
        file_name = f"{file_name}.xlsx"
        if process_control_report is not None:
            process_control_report.seek(0)
            attachment = process_control_report.read()
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                            attachment=attachment, filename=file_name)
        logger.info(f"Insight {process} control report mail sent successfully")


def execute_data_sharing_wo_mail(db:Database, total_units_df: DataFrame, provider_org_id: str,fa_root_org_id: str, logger):
    try:
        message = ""
        error_list = []
        consumer_issues_unit_set = set()

        data_shared_unit_set = set()
        already_data_shared_unit_set = set()
        unwanted_error_list = []
        total_distinct_units_count = 0, 0, 0

        total_distinct_units_count = get_distinct_count(data_set=total_units_df)
        logger.info(f"Total units: {len(total_units_df)}, New distinct units to processed: {total_distinct_units_count}")

        if total_distinct_units_count > 0:

            provider_access_token_data_sharing = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.DATA_SHARING)
            provider_access_token_teams = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.TEAMS)
            units_wout_pairing_info_df = total_units_df.loc[(pd.isna(total_units_df['Asset_Id']) & pd.notnull(total_units_df['Organization_Id']))]
            units_wout_pairing_info_set = set(units_wout_pairing_info_df['UnitNr'].tolist())
            units_with_root_org_asset_id_df = total_units_df.loc[pd.notnull(total_units_df['Organization_Id'])].\
                                                                            loc[pd.notnull(total_units_df['Asset_Id'])]
            
            units_by_root_orgs: dict = get_units_by_root_orgs(units_with_root_org_asset_id_df)

            for fa_root_org_id in units_by_root_orgs.keys():
                org_dict = units_by_root_orgs[fa_root_org_id]
                org_ids = list(org_dict.keys())
                
                # units dataframe combines all units of all child orgs into one
                units = pd.DataFrame()
                for org_id in org_ids:
                    units = pd.concat([units, org_dict[org_id]], ignore_index=True)
                    # Fetch SC_Organization detail since total_units_df contains FA_Organization_Id
                consumer_details = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)

                if consumer_details is not None and len(consumer_details) > 0:
                    consumer_org_id = consumer_details['Organization_Id'][0]
                    ZF_customer = consumer_details['ZF_Consumer_Org'][0]
                else:
                    consumer_issues_unit_set.update(units['UnitNr'].to_list())
                    continue

                new_sessions_list, existing_sessions_in_same_org, existing_sessions_in_different_org, \
                    unwanted_error_list = start_data_sharing(db=db, access_token=provider_access_token_data_sharing,
                                                            provider_org_id=provider_org_id,
                                                            consumer_org_id=consumer_org_id, 
                                                        asset_list=units['Asset_Id'].to_list(), logger=logger)

                new_ds_asset_list = [val['providerAssetId'] for val in new_sessions_list]
                new_ds_df = units.loc[units['Asset_Id'].isin(new_ds_asset_list)]
                data_shared_unit_set.update(set(new_ds_df['UnitNr'].to_list()))

                already_ds_asset_list = [val['providerAssetId'] for val in existing_sessions_in_same_org]
                already_ds_df = units.loc[units['Asset_Id'].isin(already_ds_asset_list)]
                already_data_shared_unit_set.update(set(already_ds_df['UnitNr'].to_list()))

                # unwanted_error_list.extend(existing_sessions_in_different_org)
                if len(unwanted_error_list) > 0:
                    logger.error(f"Error occured while data sharing units, Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {unwanted_error_list}")
                    error_list.extend(log_errors(error_list=unwanted_error_list, field=ErrorFields.ORGANIZATION_ID, value=consumer_org_id))
                # Skipping the Asset Assignment for Culina Group in TIP Scalar as the customer asset group has already got 5k assets
                # Need to remove this condition once the restriction has removed.
                if fa_root_org_id != 38:
                    assign_error_list = assign_assets_to_consumer_group_in_provider_org(db=db,access_token=provider_access_token_teams,
                                                        fa_root_org_id=fa_root_org_id,
                                                        asset_ids=units['Asset_Id'].to_list(),
                                                        provider_org_id=provider_org_id
                                                        )
                    if len(assign_error_list) > 0:
                        error_list.extend(log_errors(error_list=assign_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                        logger.error(f"Error occured while assigning datashared units to provider group, FLeetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                        continue
                else:
                    logger.warning("Skipping the Asset Assignment for Culina Group in TIP Scalar as the customer asset group has already got 5k assets")
                # fetching all asset groups of the root org, under both provider and consumer orgs
                sc_groups_df = get_sc_groups(db=db, fa_organization_ids= org_ids+[fa_root_org_id])

                # Consumer group under provider org
                tip_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]
                if len(tip_group_df) == 0:
                    error_msg = f"No group record found for org id {org_id} of fleetadmin root org id {fa_root_org_id} under provider org id {provider_org_id}"
                    logger.error(error_msg)
                    error_list.extend(log_errors(error_list=[error_msg], field=ErrorFields.ORGANIZATION_ID, value=org_id))
                    continue
                
                tip_group = tip_group_df.iloc[0]
                asset_nrs = units['Asset_Id'].tolist()
                add_asset_group_mapping_in_db(db=db, asset_nrs=asset_nrs, group_id=tip_group.Asset_Group_Id)

                new_data_shared_unit_df=pd.DataFrame(new_sessions_list, columns=['providerAssetId','consumerAssetId'])
                already_data_shared_unit_df=pd.DataFrame(existing_sessions_in_same_org, columns=['providerAssetId','consumerAssetId'])
                units = units.loc[(units["UnitNr"].isin(data_shared_unit_set)) | (units["UnitNr"].isin(already_data_shared_unit_set))]
                combined_assets_df = pd.concat([already_data_shared_unit_df,new_data_shared_unit_df], ignore_index=True).drop_duplicates()

                # units assign to groups in consumer org will only happen to TIP owned customer tenancies
                if len(combined_assets_df) > 0 and ZF_customer == 0:

                    consumer_access_token = fetch_access_token(db=db,org_id= consumer_org_id,audience= AudienceCode.TEAMS)
                    units_to_edit = units.merge(combined_assets_df,
                                            left_on='Asset_Id',
                                            right_on='providerAssetId',
                                            how='inner')[['UnitNr','consumerAssetId','UnitLicenceNr','Fleet_Id','VIN_Number']]
                    change_error_list = consumer_asset_name_change(db=db, 
                                                        consumer_assets_df=units_to_edit, 
                                                        consumer_org_id=consumer_org_id
                                                        )
                    if len(change_error_list) > 0:
                        # error_list.extend(log_errors(error_list=change_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                        logger.error(f"Error occured while changing asset name for customer organization, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                        continue
                    logger.info(f"Assets name update for root org {fa_root_org_id} successful.")

                    logger.info(f"Assigning assets to consumer orgs in root org {fa_root_org_id}")
                    for org_id in org_ids:

                        units_to_assign = org_dict[org_id] # units by each child org
                        consumer_asset_ids_list = combined_assets_df.merge(units_to_assign,
                                                                        left_on= 'providerAssetId',
                                                                        right_on='Asset_Id',
                                                                        how='inner')['consumerAssetId'].to_list()
                        
                        consumer_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == org_id) & (sc_groups_df['SC_Organization_Id'] == consumer_org_id)]
                        if len(consumer_group_df) == 0:
                            error_msg = f"No Scalar group record found for organization id {org_id} of root org id {fa_root_org_id} under scalar consumer org {consumer_org_id}"
                            logger.error(error_msg)
                            error_list.extend(log_errors(error_list=[error_msg], field=ErrorFields.ORGANIZATION_ID, value=org_id))
                            continue
                        consumer_group = consumer_group_df.iloc[0]

                        logger.info(f"Assigning assets for child org {org_id}:")
                        assign_error_list = assign_asset_to_groups_in_consumer_org(consumer_access_token=consumer_access_token,
                                                            consumer_group_id=consumer_group.Asset_Group_Id,
                                                            consumer_asset_ids=consumer_asset_ids_list,
                                                            )

                        if len(assign_error_list) > 0:
                            error_list.extend(log_errors(error_list=assign_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                            logger.error(f"Error occured while assigning datashared units to customer group, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                            continue
                        
                        add_asset_group_mapping_in_db(db=db, asset_nrs=consumer_asset_ids_list, group_id=consumer_group.Asset_Group_Id)
            
            logger.info(f"Datasharing and assetgroup assignment done. Updating missing pairing units details")
            treated_units = set()
            treated_units.update(data_shared_unit_set)
            treated_units.update(already_data_shared_unit_set)
            update_missing_pairing_insight_unit_as_treated(db=db, treated_units=list(treated_units))
            # Filter out non-scalar org related units
            if len(units_wout_pairing_info_df) > 0:
                # Find if the units in wout_pairing_df are linked to scalar orgs
                fa_root_org_id_list = set(units_wout_pairing_info_df['Root_Organization_Id'].to_list())
                scalar_orgs_df = get_sc_org_info_by_list_of_root_orgs(db=db, 
                                                    fa_root_org_list=list(fa_root_org_id_list))
                if len(scalar_orgs_df) > 0:
                    # update only the units of scalar orgs from the wout_pairing_df
                    units_wout_pairing_info_df = units_wout_pairing_info_df.loc[units_wout_pairing_info_df['Root_Organization_Id'].isin(\
                        scalar_orgs_df['FA_Root_Organization_Id'])]
                    add_missing_pairing_insight_unit(db=db, missing_pairing_units_df=units_wout_pairing_info_df, process_name='Data Sharing')

            message = f"Data sharing and Asset assignment to the asset group has completed Successfully!"
        else:
            message = "There are no insight units for data sharing!"

        logger.info(message)
        response = Response(status=True, message=message)
        return message, ResponseCode.SUCCESS

    except SQLAlchemyError as sae:
        message = GeneralConstant.DB_EXCP_MESSAGE
        error_list.extend(log_errors([str(sae)], "DB Exception", None))
        logger.error(sae, exc_info=True)
        return message, ResponseCode.INTERNAL_ERROR
    except Exception as e:
        message = str(e)
        error_list.extend(log_errors([message], "Application Exception", None))
        logger.error(message, exc_info=True)
        response = Response(status=False, message=message)
        return message, ResponseCode.INTERNAL_ERROR

def add_or_update_subcontring_summary(db, params):
    result = get_subcontring_summary(db=db, organization_id=params["organization_id"])
    if len(result) > 0:
        update_subcontring_summary(db=db, params=params)
    else:
        add_subcontring_summary(db=db, params=params)


def send_control_report(sub_control_report, params):
    organization_name = params['organization_name']
    email = Email()
    receivers = params['recipient'].split(",")
    file_name = "datasharing_session_control_report"
    subject = f"Data sharing Control Report for organization {organization_name}"
    template_name = f"{file_name}.html"
    
    params["environment"] = os.environ['SCALAR_ENV']
    if os.environ['SCALAR_ENV'] != 'PROD':
        subject = f"Data sharing Control Report for organization {organization_name} - {os.environ['SCALAR_ENV']}"
    params["exectution_time"] = datetime.now()
    attachment = None
    file_name = f"{file_name} - {organization_name[:30]}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                        attachment=attachment, filename=file_name)

def get_subcontring_summary(db: Database, organization_id: str):
    query = text('''SELECT SC_Organization_Id
                FROM SCALAR.SC_Insight_Unit_Datasharing_Control_Report (NOLOCK)
                WHERE SC_Organization_Id = :organization_id
            ''')
    params = {"organization_id": organization_id}
    return db.query(statement=query, params=params)


def add_subcontring_summary(db: Database, params):
    query = text('''INSERT INTO SCALAR.SC_Insight_Unit_Datasharing_Control_Report
                    (SC_Organization_Id, Insight_Unit_Count, Insight_Datashared_Unit_Count, Insight_Non_Paired_Unit_Count,
                    Insight_Non_Fc_Org_Unit_Count, Insight_Manual_Session_Unit_Count, Insight_Missing_Session_Unit_Count,
                    Non_Insight_Datashared_Unit_Count, Wrong_Datashared_Unit_Count, 
                    Created_By, Created_Date, Modified_By, Modified_Date
                    ) VALUES 
                    (:organization_id, :insight_units_count, :insight_datashared_units_count, :insight_non_paired_units_count,
                    :insight_non_fc_org_units_count, :insight_manual_session_units_count, :insight_missing_session_units_count,
                    :non_insight_datashared_units_count, :wrong_datashared_units_count,
                    'Scalar', getdate(), 'Scalar', getdate() 
                    )
            ''')

    db.insert_update_delete_raw(statement=query, params=params)


def update_subcontring_summary(db: Database, params):
    query = text('''UPDATE SCALAR.SC_Insight_Unit_Datasharing_Control_Report WITH(ROWLOCK)
                    SET Insight_Unit_Count = :insight_units_count,
                    Insight_Datashared_Unit_Count = :insight_datashared_units_count,
                    Insight_Non_Paired_Unit_Count = :insight_non_paired_units_count,
                    Insight_Non_Fc_Org_Unit_Count = :insight_non_fc_org_units_count,
                    Insight_Manual_Session_Unit_Count = :insight_manual_session_units_count,
                    Insight_Missing_Session_Unit_Count = :insight_missing_session_units_count,
                    Non_Insight_Datashared_Unit_Count = :non_insight_datashared_units_count,
                    Wrong_Datashared_Unit_Count = :wrong_datashared_units_count,
                    Modified_By = 'Scalar',
                    Modified_Date = getdate()
                    WHERE SC_Organization_Id = :organization_id
                ''')

    db.insert_update_delete_raw(statement=query, params=params)
