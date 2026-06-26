import pandas as pd
import os
from datetime import datetime
import numpy as np
import random
import string
from asyncio.log import logger
from app.assets.asset_upload.asset_upload_data_access import get_TIPGlobal_main_asset_group
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_User_Role_Mapping
from app.common.email import Email
from io import BytesIO
from app.common.helpers.datasharing_helper import consumer_asset_name_change
from app.common.helpers.session_helpers import get_session_data_by_framework
from pandas import DataFrame
from app.common.constants import AudienceCode, ErrorFields, GeneralConstant
from app.common.helpers.common_data_access import get_consumer_organization_data,get_FA_organization_hierarchy, \
    get_asset_group_data
from app.common.helpers.common_services import assign_assets_to_consumer_group_in_provider_org, fetch_access_token, get_all_data, get_distinct_count, get_scalar_api_error_messages, log_errors
from app.common.helpers.group_helpers import get_asset_groups_for_root_org
from app.common.helpers.process_helpers import get_units_by_root_orgs
from app.common.helpers.unit_helpers import add_asset_group_mapping_in_db, assign_asset_to_groups_in_consumer_org, get_asset_api_data
from app.common.exceptions import ScalarException
from app.common.helpers.asset_group_helper import create_consumer_asset_group_in_api_db, save_asset_group_in_db, fetch_all_assets_and_groups_from_api

from app.common.helpers.common_services import has_transic_errors
from app.common.scalar_api.asset_api import get_all_assets
from app.common.scalar_api.asset_group_api import  get_all_asset_groups
from app.common.scalar_api.roles_api import get_all_role
from app.common.scalar_api.user_api import get_all_user
from app.fleetconnected_migration.common.tx_tango.trailer_api import TrailerApi
from app.fleetconnected_migration.common.tx_tango.user_api import UserApi
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import cust_sync_user_role_mapping_in_db,  get_assinged_assets_for_report, get_customer_asset_group_for_report


def get_all_sessions_for_specific_org(access_token: str, agreement_id:str, logger) -> pd.DataFrame:
    all_sessions_from_api_df = get_session_data_by_framework(access_token= access_token, agreement_id=agreement_id, status='all')
    if all_sessions_from_api_df is None or len(all_sessions_from_api_df) == 0:
        return all_sessions_from_api_df
    all_sessions_from_api_df = all_sessions_from_api_df.drop(["agreementName","parentContractId","contractId",
            "contractName","providerOrgName","consumerOrgName","vinNumber",
            "providerAssetName","consumerAssetName"], axis=1)
    all_sessions_from_api_df.rename(columns = {"sessionId": "Session_Id",
        "agreementId": "Agreement_Id",
        "providerOrgId": "Provider_Organization_Id",
        "consumerOrgId": "Consumer_Organization_Id",
        "status": "Status",
        "licensePlate": "SC_License_Plate",
        "realStart": "Real_Start",
        "realStop": "Real_Stop",
        "desiredStart": "Desired_Start",
        "desiredStop": "Desired_Stop",
        "providerUnitIds": "Provider_Unit_Nr",
        "providerAssetId": "Provider_Asset_Id",
        "consumerAssetId": "Consumer_Asset_Id",
        "createdBy": "Created_By",
        "createdOn": "Created_Date"}, inplace=True)
    all_sessions_from_api_df['Provider_Unit_Nr'] = all_sessions_from_api_df['Provider_Unit_Nr'].apply(lambda x: ''.join(map(str, x)) if len(x)>0 else None)
    all_sessions_from_api_df = all_sessions_from_api_df.replace({np.nan:None})
    return all_sessions_from_api_df

def send_session_sync_report(org_name,current_total_data_sharing_in_scalar,
                        current_active_data_sharing_in_scalar, current_active_data_sharing_in_sky,
        matched_data_sharing_in_sky_and_scalar,  missing_data_sharing_in_scalar, missing_data_sharing_in_sky, params):
    email = Email()
    env = os.environ['SCALAR_ENV']
    receivers=os.environ['MIGRATION_REPORT_MAIL_DL']
    receivers = receivers.split(",")
    file_name = f"Session_Sync_{org_name[:36]}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    subject = f"Scalar Migration - Customer session sync report for {org_name[:36]} - "+env
    template_name = f'customer_sessionsync_report.html'

    sessionsync_report = BytesIO()
    with pd.ExcelWriter(sessionsync_report, engine='xlsxwriter') as writer:
        if len(current_total_data_sharing_in_scalar) > 0:
            current_total_data_sharing_in_scalar.to_excel(writer, sheet_name = "Total Data Sharing in SCALAR", index=None, header=True)
        if len(current_active_data_sharing_in_scalar) > 0:
            current_active_data_sharing_in_scalar.to_excel(writer, sheet_name = "Active Data Sharing SCALAR", index=None, header=True)
        if len(current_active_data_sharing_in_sky) > 0:
            current_active_data_sharing_in_sky.to_excel(writer, sheet_name = "Active Data Sharing in SKY", index=None, header=True)
        if len(matched_data_sharing_in_sky_and_scalar) > 0:
            matched_data_sharing_in_sky_and_scalar.to_excel(writer, sheet_name='Matched in SKY and SCALAR', index=None, header=True)
        if len(missing_data_sharing_in_scalar) > 0:
            missing_data_sharing_in_scalar.to_excel(writer, sheet_name='SCALAR - Missing Data Sharing', index=None, header=True)
        if len(missing_data_sharing_in_sky) > 0:
            missing_data_sharing_in_sky.to_excel(writer, sheet_name='SKY - Missing Data Sharing', index=None, header=True)
            
    attachment = None
    if sessionsync_report is not None:
        sessionsync_report.seek(0)
        attachment = sessionsync_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)
    
def asset_assignment_with_asset_group(db:Database, total_units_df: DataFrame, provider_org_id: str , consumer_org_id: str,fa_root_org_id: str, logger):
    logger.info(f"Starting asset assignment")
    total_distinct_units_count = 0, 0, 0
    already_assigned_assets_for_provider =pd.DataFrame()
    already_assigned_assets_for_customer=pd.DataFrame()
    total_distinct_units_count = get_distinct_count(data_set=total_units_df)
    logger.info(f"Total units: {len(total_units_df)}, New distinct units to processed: {total_distinct_units_count}")
    asset_assignment_issue = pd.DataFrame(columns=['Asset_Group_Id','Asset_Group_Name','Asset_Ids','Error_Message'])
    if total_distinct_units_count > 0:

        units_by_root_orgs: dict = get_units_by_root_orgs(total_units_df)
        
        org_dict = units_by_root_orgs[fa_root_org_id]
        org_ids = list(org_dict.keys())

        units = pd.DataFrame()
        for org_id in org_ids:
            units = pd.concat([units, org_dict[org_id]], ignore_index=True)

        all_assets_and_groups_in_provider_df = fetch_all_assets_and_groups_from_api(db=db,org_id=provider_org_id)
        already_assigned_assets_for_provider = units.loc[units['Provider_Asset_Id'].isin(all_assets_and_groups_in_provider_df['assetId'].to_list())]
        asset_ids_to_assign_in_provider = units.loc[~units["Provider_Asset_Id"].isin(already_assigned_assets_for_provider['Provider_Asset_Id'].to_list())]
        asset_ids_to_assign_in_provider = asset_ids_to_assign_in_provider['Provider_Asset_Id'].to_list()

        provider_teams_access_token = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.TEAMS)
        logger.info("Assigning assets to assetgroup in Provider org")
        if len(asset_ids_to_assign_in_provider) > 0:
            assign_error_list = assign_assets_to_consumer_group_in_provider_org(db=db,access_token=provider_teams_access_token,
                                                fa_root_org_id=fa_root_org_id,
                                                asset_ids=asset_ids_to_assign_in_provider,
                                                provider_org_id=provider_org_id
                                                )
            sc_groups_df = get_asset_groups_for_root_org(db=db, FA_Root_Org_Id=fa_root_org_id)
            tip_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]
            tip_group = tip_group_df.iloc[0]

            if len(tip_group_df) == 0:
                error_msg = f"No group record found for org id {org_id} of fleetadmin root org id {fa_root_org_id} under provider org id {provider_org_id}"
                logger.error(error_msg)
                raise Exception(error_msg)

            if len(assign_error_list) > 0:
                error_msg = f"Error occured while assigning assets to provider asset group, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Errors: {assign_error_list}"
                logger.error(error_msg)
                asset_assignment_issue = pd.concat([asset_assignment_issue, 
                                                    pd.DataFrame([{'Asset_Group_Id': tip_group.Asset_Group_Id, 
                                                                    'Asset_Group_Name': tip_group.Asset_Group_Name,
                                                                    'Asset_Ids': asset_ids_to_assign_in_provider, 
                                                                    'Error_Message': error_msg}])
                                                    ], ignore_index=True)
            else:
                asset_nrs = units['Provider_Asset_Id'].tolist()
                add_asset_group_mapping_in_db(db=db, asset_nrs=asset_nrs, group_id=tip_group.Asset_Group_Id)
                logger.info("Asset and assetgroup mapping successful")
                
            if len(already_assigned_assets_for_provider)>0:
                asset_nrs = already_assigned_assets_for_provider['Provider_Asset_Id'].tolist()
                add_asset_group_mapping_in_db(db=db, asset_nrs=asset_nrs, group_id=tip_group.Asset_Group_Id)
                logger.info("Asset and assetgroup mapping data updated for assigned assets in DB successfully.")
        else:
            logger.info(f"No new assets to assign in Provider Org")

        sc_groups_df = get_asset_groups_for_root_org(db=db, FA_Root_Org_Id=fa_root_org_id)

        all_consumer_assets = units.loc[(units["Organization_Id"]== org_id) & (units["SC_Organization_Id"]==consumer_org_id)]
        units_to_edit = all_consumer_assets[["Consumer_Asset_Id","UnitLicenceNr","Fleet_Id","UnitNr","VIN_Number"]]
        units_to_edit = units_to_edit.rename(columns={'Consumer_Asset_Id': 'consumerAssetId'})
        change_error_list = consumer_asset_name_change(db=db, 
                                            consumer_assets_df=units_to_edit, 
                                            consumer_org_id=consumer_org_id
                                            )
        
        if len(change_error_list) > 0:
            logger.error(f"Error occured while changing asset name for customer organization, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Errors: {assign_error_list}")

        # Asset assignment in consumer org
        all_assets_and_groups_in_consumer_df = fetch_all_assets_and_groups_from_api(db=db,org_id=consumer_org_id)
        already_assigned_assets_for_customer = units.loc[units['Consumer_Asset_Id'].isin(all_assets_and_groups_in_consumer_df['assetId'].to_list())]
        logger.info(f"Assigning assets to assetgroups in root org {fa_root_org_id}")
        consumer_teams_access_token = fetch_access_token(db=db,org_id=consumer_org_id,audience= AudienceCode.TEAMS)

        for org_id in org_ids:

            consumer_group = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == org_id) & (sc_groups_df['SC_Organization_Id'] == consumer_org_id)]
            if len(consumer_group) == 0:
                error_msg = f"No asset group record found in db for organization id {org_id} of root org id {fa_root_org_id} under scalar organization system number {consumer_org_id}"
                logger.error(error_msg)
                continue
            consumer_group = consumer_group.iloc[0]
            consumer_group_id = consumer_group.Asset_Group_Id
            consumer_group_name =consumer_group.Asset_Group_Name

            # all the units of the child org
            units_to_assign = org_dict[org_id]
            # find already assigned assets related to this child group and exclude from to_be_assigned df
            already_assigned_df = all_assets_and_groups_in_consumer_df.loc[all_assets_and_groups_in_consumer_df['groupIds']==consumer_group.Asset_Group_Id]
            assets_to_assign_in_child_org_df = units_to_assign.loc[~units_to_assign['Consumer_Asset_Id'].isin(already_assigned_df['assetId'].to_list())]
            assets_to_assign_in_child_org_list = assets_to_assign_in_child_org_df['Consumer_Asset_Id'].to_list()
            if len(assets_to_assign_in_child_org_list) == 0:
                logger.info(f"No new assets to assign to child org {org_id}")
                continue

            logger.info(f"Assigning assets to groups in consumer org in child org {org_id}")
            assign_error_list = assign_asset_to_groups_in_consumer_org(consumer_access_token=consumer_teams_access_token,
                                                consumer_group_id=consumer_group_id,
                                                consumer_asset_ids=assets_to_assign_in_child_org_list
                                                )
            
            if len(assign_error_list)>0:
                error_msg =f"Error occured while assingning assets to customer asset group, Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Errors: {assign_error_list}"
                
                asset_assignment_issue = pd.concat([asset_assignment_issue, 
                                                    pd.DataFrame([{'Asset_Group_Id': consumer_group_id, 
                                                                    'Asset_Group_Name': consumer_group_name,
                                                                    'Asset_Ids': assets_to_assign_in_child_org_list, 
                                                                    'Error_Message': error_msg}])
                                                    ], ignore_index=True)
                        
                logger.error(error_msg)
                continue

            add_asset_group_mapping_in_db(db=db, asset_nrs=assets_to_assign_in_child_org_list, group_id=consumer_group_id)

    return  already_assigned_assets_for_provider,already_assigned_assets_for_customer,asset_assignment_issue


def get_assignment_details_for_assets(db:Database, org_id: str,asset_list: list):
    already_assigned_asset = list()
    offset = 0
    limit = 250
    while True:
        access_token = fetch_access_token(db=db,org_id= org_id,audience= AudienceCode.ASSET)
        asset_response = get_all_assets(access_token=access_token, limit= limit, offset= offset)
        if asset_response.status_code == 200:
            asset_dict= asset_response.json()
            pagination = asset_dict.get("metadata", {}).get("pagination", {})
            total_count = pagination.get("totalCount", 0)
            asset_ids_with_group_ids = [
                item["assetId"]
                for item in asset_dict["items"]
                if item.get("assignees", {}).get("groupIds")
                ]  
            asset_data_df= pd.DataFrame(asset_ids_with_group_ids, columns=['assetId'])  
            for asset_dict in asset_list:
                assigned_assets = asset_data_df.loc[asset_data_df["assetId"]==asset_dict].to_dict(orient='records')
                if len(assigned_assets) > 0:
                    already_assigned_asset.append({"assetId": asset_dict})
        offset += limit
        if offset >= total_count:
            break   
    already_assigned_asset = pd.DataFrame(already_assigned_asset, columns=['assetId'])
    return already_assigned_asset

def send_customer_asset_assignment_report(db:Database, sc_org_id: str, org_name: str, fa_root_org_id, total_active_scalar_units, updated_asset_for_provider,updated_asset_for_customer,
                                           new_asset_for_provider, new_asset_for_customer, params):
    
    email = Email()
    receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
    file_name = f"Customer_asset_assignment_{org_name[:36]}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar Migration - Customer asset assignment report for {org_name[:36]} - " + env
    template_name = 'customer_asset_assignment.html'
    
    sub_control_report = BytesIO()
    with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
        asset_list= get_assinged_assets_for_report(db= db, sc_org_id= sc_org_id, fa_root_org_id= fa_root_org_id)
        if len(total_active_scalar_units) > 0:
            total_active_scalar_units.to_excel(writer, sheet_name="Total active assets in Scalar", index=None, header=True)
        if len(asset_list) > 0:
            asset_list.to_excel(writer, sheet_name="Assigning assets to asset group", index=None, header=True)
        if len(updated_asset_for_provider) > 0:
            updated_asset_for_provider.to_excel(writer, sheet_name="Updated assets for provider", index=None, header=True)
        if len(updated_asset_for_customer) > 0:
            updated_asset_for_provider.to_excel(writer, sheet_name="Updated assets for customer", index=None, header=True)
        if len(new_asset_for_provider) > 0:
            new_asset_for_provider.to_excel(writer, sheet_name="New assets for provider", index=None, header=True)
        if len(new_asset_for_customer) > 0:
            new_asset_for_customer.to_excel(writer, sheet_name="New assets for customer", index=None, header=True)

    attachment = None
    file_name = f"{file_name}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)

def send_customer_asset_assignment_error_report(asset_assignment_issue: DataFrame, org_name: str= None, error: str =None):
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject = f"Scalar Migration - Customer asset assignment error report for {org_name[:36]} " + env
        template_name='error_asset_assignment_email.html'
        
        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": error,
        }

        file_name = f"Error_Asset_Assignment_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        sub_control_report = BytesIO()
        with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
            if len(asset_assignment_issue) > 0:
                asset_assignment_issue.to_excel(writer, sheet_name="Error_Asset_Assignment", index=None, header=True)
        attachment = None
        file_name = f"{file_name}.xlsx"
        if sub_control_report is not None:
            sub_control_report.seek(0)
            attachment = sub_control_report.read()

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,attachment=attachment,filename=file_name,params=error_params)

                                          
def get_subcontracting_info_from_sky(trailer_api: TrailerApi, company_id, logger):
    subcontracted_units = pd.DataFrame(columns=["unit_nr", "license_plate_nr_sky", "subscription_id", "company_id", "company_code",
                                                "transics_trailer_id", "from_datetime", "end_datetime", "active"])
    
    subcontracted_response = trailer_api.get_subcontacted_vehicles(transics_id=None, company_id=company_id)
    error_list = has_transic_errors(response=subcontracted_response)
    logger.error(str(error_list))

    if subcontracted_response["SubcontractedVehicleResult"]["VehicleSubscription"] is not None:
        SubcontractedResultStrategyList = subcontracted_response["SubcontractedVehicleResult"]["VehicleSubscription"]["SubcontractedResultStrategy"]
        for subcontracted_result in SubcontractedResultStrategyList:
            subcontracted_unit = {}
            unit_nr = subcontracted_result["VehicleStrategy"]["ID"]
            if not unit_nr.isnumeric():
                continue
            subcontracted_unit["unit_nr"] = unit_nr
            subcontracted_unit["license_plate_nr_sky"] = subcontracted_result["VehicleStrategy"]["LicensePlate"]
            subcontracted_unit["subscription_id"] = subcontracted_result["SubscriptionId"]
            subcontracted_unit["company_id"] = subcontracted_result["Company"]["Id"]
            subcontracted_unit["company_code"] = subcontracted_result["Company"]["Code"]
            subcontracted_unit["transics_trailer_id"] = subcontracted_result["VehicleStrategy"]["TransicsVehicleID"]
            subcontracted_unit["from_datetime"] = subcontracted_result["Period"]["From"]
            subcontracted_unit["end_datetime"] = subcontracted_result["Period"]["Until"]
            subcontracted_unit["active"] = 1 if subcontracted_result["IsActive"] == True else 0
            subcontracted_units = pd.concat([subcontracted_units,pd.DataFrame([subcontracted_unit])], ignore_index=True)

    if len(error_list) > 0:
        raise ScalarException(message=str(error_list))
            
    return subcontracted_units

def consumer_asset_group_hierarchy_migration(logger,db: Database,access_token: str, sc_organization_id: str,fa_root_org_id: str):
    
    logger.info("Starting to fetch FA Organization Hierarchy")
    fa_organization_hierachy = get_FA_organization_hierarchy(db=db,fa_root_org_id=fa_root_org_id)
    logger.info(f"FA Organization Hierarchy: {len(fa_organization_hierachy)} Asset Groups to be created in total")
    logger.info(f"Starting to fetch Scalar Asset Group hierarchy from API")
    scalar_hierarchy_df = get_all_data(access_token=access_token, func=get_all_asset_groups)
    logger.info(f"Scalar Asset Group Hierarchy: {len(scalar_hierarchy_df)} Asset Groups found")

    if len(fa_organization_hierachy)>0:
        root_asset_group_id=None
        for index,org_hierachy in fa_organization_hierachy.iterrows():

            child_asset_group_name = org_hierachy['Organization_Name']

            if root_asset_group_id==None:
                root_asset_group_id = get_asset_group_data(db=db,FA_Organization_Id=fa_root_org_id,sc_organization_id=sc_organization_id)
                if len(root_asset_group_id)>0:
                    root_asset_group_id=root_asset_group_id[0][0]
                else:
                    root_asset_group_id=None

            parent_asset_group_details =get_asset_group_data(db=db,FA_Organization_Id=org_hierachy['Parent_Organization_Id'],sc_organization_id=sc_organization_id)
            if len(parent_asset_group_details)>0:
                parent_asset_group_id=parent_asset_group_details[0][0]
            else:
                parent_asset_group_id=None

            if scalar_hierarchy_df is not None and len(scalar_hierarchy_df) > 0:
                asset_group_rec = scalar_hierarchy_df.loc[scalar_hierarchy_df['name'] == child_asset_group_name]
                if len(asset_group_rec) > 0:
                    logger.info(f"Asset Group {child_asset_group_name} (ID: {org_hierachy['FA_Organization_Id']}) already exists. Updating in DB")
                    save_asset_group_in_db(db=db, asset_group_id=asset_group_rec.iloc[0]['id'],
                                    asset_group_name=child_asset_group_name, 
                                    asset_group_description=child_asset_group_name, 
                                    sc_organization_id=sc_organization_id, 
                                    root_group_id=root_asset_group_id, 
                                    parent_group_id=parent_asset_group_id, 
                                    fa_root_org_id=org_hierachy['FA_Organization_Id'])
                    logger.info(f"Updated asset Group {child_asset_group_name} (ID: {org_hierachy['FA_Organization_Id']}) in DB")
                    continue

            logger.info(f"Creating Asset Group: {org_hierachy['Organization_Name']} (ID: {org_hierachy['FA_Organization_Id']})")
            create_consumer_asset_group_in_api_db(db=db,access_token= access_token, 
                                                child_asset_group_name=child_asset_group_name,
                                                root_asset_group_id=root_asset_group_id,
                                                parent_asset_group_id=parent_asset_group_id,
                                                sc_organization_id=sc_organization_id,
                                                FA_Organization_Id=org_hierachy['FA_Organization_Id'])
    else:
        raise ScalarException(message=f"There is no child organization for root org {fa_root_org_id}")
    
def send_customer_asset_group_hierarchy_report(db: Database,params, org_name: str, fa_root_org_id):
    
    email = Email()
    receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
    file_name = f"Customer_Asset_Group_Hierarchy_{org_name[:36]}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar Migration - Customer asset group hierarchy report for {org_name[:36]} - " + env
    template_name = 'customer_asset_group_hierarchy.html'


    sub_control_report = BytesIO()
    with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
        asset_group_list= get_customer_asset_group_for_report(db= db, fa_root_org_id= fa_root_org_id)
        if len(asset_group_list) > 0:
            asset_group_list.to_excel(writer, sheet_name="Customer asset group hierarchy", index=None, header=True)

    attachment = None
    file_name = f"{file_name}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)
    
def get_allusers_allroles_for_an_org(db: Database, scalar_org_id: str, scalar_org_name: str, logger):
    all_users_df = pd.DataFrame()
    all_roles_df = pd.DataFrame()
    access_token = fetch_access_token(db=db, org_id=scalar_org_id, audience=AudienceCode.USER)
    logger.info(msg=f"Getting users and roles from api for org {scalar_org_id}")
    
    single_org_user_df = get_all_data(access_token=access_token,func=get_all_user)
    single_org_user_df = single_org_user_df[single_org_user_df['status'].isin(['Active','Pending'])]
    if single_org_user_df.empty:
        raise ScalarException(message=f"Could not retrieve any user for org: {scalar_org_id} from API")
    single_org_user_df['orgId'] = scalar_org_id
    single_org_user_df['sc_orgName'] = scalar_org_name
    all_users_df = pd.concat([all_users_df,single_org_user_df], ignore_index=True)

    single_org_role_df = get_all_data(access_token=access_token,func=get_all_role)
    if single_org_role_df.empty:
        raise ScalarException(message=f"Could not retrieve any role for org: {scalar_org_id} from API")
    all_roles_df = pd.concat([all_roles_df,single_org_role_df], ignore_index=True)
    return all_users_df, all_roles_df

def cust_user_role_mapping(db: Database, roles_api_data, user_role_map, logger):
    user_role_to_map = []
    inserted_user_role_mappings = {}
    failed_user_role_mapping =[]
    for userid, roleids in user_role_map.items():
        for roleid in roleids:
            try:
                role_name = roles_api_data.loc[roles_api_data['roleId']==roleid]['roleName'].values[0]
                user_role_mapping = SC_User_Role_Mapping(User_Id = userid,
                                                                Role_Id = roleid,
                                                                Role_Name = role_name)
                user_role_to_map.append(user_role_mapping)
                inserted_user_role_mappings[userid] = role_name
            except Exception as e:
                logger.info(msg=f"Failed to insert role mapping for user {userid}: {e}")
                failed_user_role_mapping.append({'userId' : userid, 'RoleId' : roleid, 'error' : str(e)})
    
    cust_sync_user_role_mapping_in_db(db=db, user_role_to_map=user_role_to_map, batch_size=100, logger=logger)
    
    inserted_user_role_mappings_df = pd.DataFrame(inserted_user_role_mappings.items(), columns=['UserId','RoleName'])
    failed_user_role_mapping_df = pd.DataFrame(failed_user_role_mapping)

    return inserted_user_role_mappings_df, failed_user_role_mapping_df

def get_sky_users_for_customer(txTangoApi: UserApi):
    users_df =[]
    response = txTangoApi.get_users()
    if response['Errors'] is not None:
        return response['Errors']
    else:
        users_df = pd.DataFrame(response['MyTransicsUsers']['GetUserDetailsResult'])
        # users_df['Emails'] = users_df['Emails'].apply(lambda x: x['string'][0] if x and 'string' in x and x['string'] else None)
        dispatcher_df = [item if item is not None else {} for item in users_df['TxConnectDispatcherDetails']]
        normalized_df = pd.json_normalize(dispatcher_df)
        if normalized_df.empty:
            return pd.DataFrame(columns=['Email'])
        normalized_df.index = users_df.index
        users_df = users_df.drop(columns=['Inactive','Language','TxConnectDispatcherDetails']).join(normalized_df)
        users_df = users_df[users_df["Email"].notna()]
        if not users_df.empty:
            users_df = users_df[(users_df["Email"].str.strip()!="")]
            users_df['Email'] = users_df['Email'].str.lower()
    return users_df

def send_sky_scalar_usersync_report(usersync_report, params, org_name, subject=None):
    email = Email()
    receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
    file_name = f"User_Sync_{org_name[:36]}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    env = os.environ['SCALAR_ENV']
    if subject:
        subject = subject + env
    else:
        subject = f"Scalar Migration - Customer user sync report for {org_name[:36]} - " + env
        
    template_name = 'customer_usersync_report.html'
    
    params["environment"] = env
    params["exectution_time"] = datetime.now()
    attachment = None
    file_name = f"{file_name} - {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    if usersync_report is not None:
        usersync_report.seek(0)
        attachment = usersync_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                        attachment=attachment, filename=file_name)
def send_TIP_asset_sync_report(current_asset_in_scalar,current_asset_in_sky,
        matched_asset_in_sky_and_scalar,  missing_asset_in_scalar, missing_asset_in_sky, params):
    email = Email()
    env = os.environ['SCALAR_ENV']
    receivers=os.environ['MIGRATION_REPORT_MAIL_DL']
    receivers = receivers.split(",")
    file_name = f"TIP_Asset_Sync_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    subject = f"Scalar Migration - TIP asset sync report - " + env
    template_name = f'TIP_assetsync_report.html'

    sessionsync_report = BytesIO()
    with pd.ExcelWriter(sessionsync_report, engine='xlsxwriter') as writer:
        if len(current_asset_in_scalar) > 0:
            current_asset_in_scalar.dropna(axis=1, how='all').to_excel(writer, sheet_name = "Current Asset in SCALAR", index=None, header=True)
        if len(current_asset_in_sky) > 0:
            current_asset_in_sky.dropna(axis=1, how='all').to_excel(writer, sheet_name = "Current Asset in SKY", index=None, header=True)
        if len(matched_asset_in_sky_and_scalar) > 0:
            matched_asset_in_sky_and_scalar.dropna(axis=1, how='all').to_excel(writer, sheet_name='Matched Asset in SKY and SCALAR', index=None, header=True)
        if len(missing_asset_in_scalar) > 0:
            missing_asset_in_scalar.dropna(axis=1, how='all').to_excel(writer, sheet_name='SCALAR - Missing Asset', index=None, header=True)
        if len(missing_asset_in_sky) > 0:
            missing_asset_in_sky.dropna(axis=1, how='all').to_excel(writer, sheet_name='SKY - Missing Asset', index=None, header=True)
            
    attachment = None
    if sessionsync_report is not None:
        sessionsync_report.seek(0)
        attachment = sessionsync_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)

def send_customer_user_assignment_error_report(error_message:str, org_name):
    env = os.environ['SCALAR_ENV']
    email=Email()
    receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
    subject = f"Scalar Migration - Customer user assignment error report for {org_name[:36]} - " + env
    template_name='error_user_email.html'
    
    error_params={"environment": env, 
    "execution_time": datetime.now(),
    "error_message": error_message,
    }

    email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

