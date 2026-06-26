import random
import string
import time
import pandas as pd
from app.assets.asset_upload.asset_upload_data_access import get_TIPGlobal_main_asset_group
from app.common.constants import GeneralConstant, TrailerIdentifier
from app.common.database import Database
from app.common.exceptions import ScalarException
from app.common.helpers.asset_group_helper import assign_assets_to_assetgroup_in_scalar_and_db, fetch_all_assets_and_groups_from_api
from app.common.helpers.common_services import fetch_access_token, get_all_data, get_scalar_api_error_messages, save_asset_group_in_db
from app.common.helpers.unit_helpers import add_asset_group_mapping_in_db, get_asset_api_data
from app.common.scalar_api.asset_group_api import assign_asset_to_assetgroup, create_asset_group, get_specific_asset_group, unassign_asset_from_assetgroup
from app.common.scalar_api.framework_api import get_all_framework_agreements, get_integrator
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_TIP_Global_assinged_assets_for_report, get_asset_country_group, get_child_asset_group_for_TIPGlobal_asset_group_new, get_country_assinged_assets_for_report, insert_update_db, remove_all_mapped_assets, get_group_list_for_tip_global_asset_group
from app.common.email import Email 
import os
from datetime import datetime
from io import BytesIO
from app.fleetconnected_migration.common.tx_tango.trailer_api import TrailerApi
import numpy as np

def assign_assets_to_tip_global_group_in_provider_org(db: Database, asset_ids: list, access_token: str, provider_org_id: str):

    tip_global_child_asset_groups_df = get_group_list_for_tip_global_asset_group(db=db, sc_org_id=provider_org_id)
    if len(tip_global_child_asset_groups_df)==0:
        raise ScalarException(message=f"Sub asset group missing for TIP global asset group {GeneralConstant.TIPGLOBALGROUP}")
    tip_global_child_asset_group_ids = tip_global_child_asset_groups_df['Child_Asset_Group_Id'].tolist()
    
    # Unassign assets from asset group which assigned already
    for child_asset_group_id in tip_global_child_asset_group_ids:
        attempt = GeneralConstant.RETRY_LIMIT
        response = get_specific_asset_group(access_token=access_token, asset_group_id=child_asset_group_id)
        while response.status_code == 429 and attempt != 0:
            time.sleep(GeneralConstant.RETRY_WAITTIME)
            response = get_specific_asset_group(access_token=access_token, asset_group_id=child_asset_group_id)
            attempt = attempt-1
        if response.status_code == 200:
                all_data_json = response.json()
                assets_in_asset_group = all_data_json["assetIds"]
        else:
            errors = get_scalar_api_error_messages(error_response=response)
            raise ScalarException(message=f"Error getting specific asset group {child_asset_group_id} from Scalar API-"+' '.join(map(str,errors)))

        if len(assets_in_asset_group) > 0:
            attempt = GeneralConstant.RETRY_LIMIT
            unassignment_response = unassign_asset_from_assetgroup(access_token=access_token,
                                                            asset_group_id=child_asset_group_id,
                                                            asset_ids=assets_in_asset_group)
            while unassignment_response.status_code != 200 and attempt != 0:
                if unassignment_response.status_code == 429:
                    time.sleep(GeneralConstant.RETRY_WAITTIME)
                    unassignment_response = unassign_asset_from_assetgroup(access_token=access_token,
                                                                asset_group_id=child_asset_group_id,
                                                                asset_ids=assets_in_asset_group)
                else:
                    errors = get_scalar_api_error_messages(error_response=unassignment_response)
                    if 'upstream request timeout' in errors:
                        time.sleep(GeneralConstant.RETRY_WAITTIME)
                        unassignment_response = unassign_asset_from_assetgroup(access_token=access_token,
                                                                        asset_group_id=child_asset_group_id,
                                                                        asset_ids=assets_in_asset_group)
                attempt = attempt - 1
            if unassignment_response.status_code != 200:
                raise ScalarException(message=f"Error occured during unassignment of asset from asset group {child_asset_group_id} in Scalar API "+' '.join(map(str,errors)))
        remove_all_mapped_assets(db=db, assetgroupid= child_asset_group_id)
    # Create asset group based on asset count
    asset_limit = GeneralConstant.ASSET_LIMIT
    total_assets = len(asset_ids)
    group_len= len(tip_global_child_asset_group_ids)
    flag = 0
    while (group_len * asset_limit) < total_assets:
        random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
        child_asset_group_name =tip_global_child_asset_groups_df["Child_Group_Name"][0]
        child_asset_group_name =f"{child_asset_group_name} - #Copy#{random_id}"
        child_asset_group_description = f"{child_asset_group_name} - TIP Global Asset Group copy"
        child_asset_parent_group_id = tip_global_child_asset_groups_df["Parent_Group_Id"][0]
        child_asset_root_group_id = tip_global_child_asset_groups_df["Root_Group_Id"][0]
        asset_group_response = create_asset_group(access_token= access_token, name=child_asset_group_name,description=child_asset_group_description, parent_group_id=child_asset_parent_group_id)
        if  asset_group_response.status_code == 201:
            asset_group_dict = asset_group_response.json()
            child_asset_group_id =asset_group_dict["id"] 
            save_asset_group_in_db(db=db, asset_group_id=child_asset_group_id, asset_group_name=child_asset_group_name, asset_group_description=child_asset_group_description, sc_organization_id=provider_org_id, root_group_id=child_asset_root_group_id, parent_group_id=child_asset_parent_group_id, fa_root_org_id= None)  
            group_len = group_len + 1
            flag = 1
        else:
            error_list = get_scalar_api_error_messages(error_response=asset_group_response)
            raise ScalarException(message=f"Failed to create asset group for org {provider_org_id}-"+' '.join(map(str,error_list)))
    #Assign assets to asset group
    if flag:
        tip_global_child_asset_groups_df = get_group_list_for_tip_global_asset_group(db=db, sc_org_id=provider_org_id)
        tip_global_child_asset_group_ids = tip_global_child_asset_groups_df['Child_Asset_Group_Id'].tolist()

    for child_asset_group_id in tip_global_child_asset_group_ids:
        asset_set = asset_ids[:asset_limit]
        if len(asset_set)>0:
            assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                                        asset_group_id=child_asset_group_id,
                                                                        asset_ids=asset_set)
            if  assignment_response.status_code == 200:
                add_asset_group_mapping_in_db(db=db, asset_nrs=asset_set, group_id= child_asset_group_id)
                asset_ids = list(set(asset_ids) - set(asset_set))
            else:
                error_list = get_scalar_api_error_messages(error_response=assignment_response)
                raise ScalarException(message=f"Failed to assign asset to asset group - {child_asset_group_id}-"+' '.join(map(str,error_list)))
    
    return get_scalar_api_error_messages(error_response=assignment_response)

def send_asset_assignment_report(total_asset_list,updated_asset_for_TIP_global, new_asset_for_TIP_global, assigned_asset_for_TIP_country,params):
    email = Email()
    receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
    file_name = f"TIP_Global_Asset_assignment_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar Migration - TIP Global asset assignment: Assigning assets to asset group report - " + env
    template_name = 'tip_global_asset_assignment.html'


    sub_control_report = BytesIO()
    with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
        if len(total_asset_list) > 0:
            total_asset_list.to_excel(writer, sheet_name='Assignment details for assets', index=None, header=True)
        if len(updated_asset_for_TIP_global) > 0:
            updated_asset_for_TIP_global.to_excel(writer, sheet_name="Updated assets for TIP Global", index=None, header=True)
        if len(new_asset_for_TIP_global) > 0:
            new_asset_for_TIP_global.to_excel(writer, sheet_name="New assets for TIP Global", index=None, header=True)
        if len(assigned_asset_for_TIP_country) > 0:
            assigned_asset_for_TIP_country.to_excel(writer, sheet_name="Assigned assets for TIP country", index=None, header=True)
  
    attachment = None
    file_name = f"{file_name}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)
    
def get_all_framework_agreements_api(provider_org_id: str, access_token: str, logger):
    all_frameworks_df = get_all_data(access_token=access_token,func=get_all_framework_agreements)
    if all_frameworks_df.empty:
        raise ScalarException(message=f"Could not retrieve any framework agreements with provider org: {provider_org_id} from API")
    
    all_frameworks_df['org_isSSOEnabled'] = all_frameworks_df['profileId'].apply(lambda x: 1 if pd.notna(x) and x !='' else 0)
    all_frameworks_df['org_active'] = all_frameworks_df['status'].apply(lambda x: 1 if x=='approved' else 0)
    # Extract boolean columns only then replace using numpy due to dataframe size
    bool_cols = all_frameworks_df.select_dtypes(include=["bool","boolean"]).columns
    for col in bool_cols:
        c = all_frameworks_df[col]
        all_frameworks_df[col] = np.where(c,"Y","N")
    return all_frameworks_df

def sync_frameworks_data(db:Database, access_token: str, framework_api_data: pd.DataFrame, framework_db_data: pd.DataFrame):
    errors = {}
    integrator_details_df = pd.DataFrame()
    framework_list = framework_api_data[framework_api_data['agreementId'].isin(framework_db_data['mapped_agreement_id'].tolist())]
    framework_list = framework_list[framework_list['createIntegrator']=='Y']['agreementId'].tolist()
    for framework_id in framework_list:
        response = get_integrator(access_token=access_token, agreement_id=framework_id)
        if response.status_code == 200:
            integrator_details_df = pd.concat([integrator_details_df,pd.DataFrame([response.json()])], ignore_index=True)
        elif response.status_code == 429:
            attempt = GeneralConstant.RETRY_LIMIT
            while response.status_code == 429 and attempt > 0:
                time.sleep(GeneralConstant.RETRY_WAITTIME)
                response = get_integrator(access_token=access_token, agreement_id=framework_id)
                if response.status_code == 200:
                    integrator_details_df = pd.concat([integrator_details_df,pd.DataFrame([response.json()])], ignore_index=True)
                attempt = attempt - 1
        else:
            integrator_details_df = pd.concat([integrator_details_df,pd.DataFrame(None,columns=['name','clientId','secretId','organizationId'])], ignore_index=True)
            errors[framework_id] = response.json()
    merged_df = pd.merge(framework_api_data,integrator_details_df[['name','clientId','secretId','organizationId']], 
                                 left_on='consumerOrgId', 
                                 right_on='organizationId', 
                                 how='left'
                                 ).drop(columns=['organizationId']).copy()
    framework_api_data = merged_df
    framework_api_data = framework_api_data.replace(np.nan,None)
    framework_db_data = framework_db_data.replace(np.nan,None)
    merge_df = pd.merge(framework_api_data,framework_db_data[['mapped_agreement_id','FA_Root_Organization_Id']], 
                                  left_on='agreementId', 
                                  right_on='mapped_agreement_id', 
                                  how='left'
                                  ).drop(columns=['mapped_agreement_id']).copy()
    merge_df = merge_df.astype(object).where(merge_df.notna(),None)
    # filter frameworks to insert/update based on agreement fa_org mappings 
    new_frameworks_df = merge_df[merge_df['agreementId'].isin(framework_db_data[framework_db_data['Agreement_Id'].isnull()]['mapped_agreement_id'].tolist())]
    existing_frameworks_df = merge_df[merge_df['agreementId'].isin(framework_db_data['Agreement_Id'].tolist())]
    
    # filter organizations based on agreement fa_org mappings
    new_orgs_df = merge_df[merge_df['consumerOrgId'].isin(framework_db_data[framework_db_data['SC_Organization_Id'].isnull()]['mapped_org_id'].tolist())]
    new_orgs_df['isExistingCustomer'] = new_orgs_df['isExistingCustomer'].apply(lambda x: 1 if x=='Y' else 0)
    existing_orgs_df = merge_df[merge_df['consumerOrgId'].isin(framework_db_data['SC_Organization_Id'].tolist())]
    existing_orgs_df['isExistingCustomer'] = existing_orgs_df['isExistingCustomer'].apply(lambda x: 1 if x=='Y' else 0)
    
    # filter integrator details based on agreement fa_org mappings
    new_integrator_df = merge_df[merge_df['consumerOrgId'].isin(framework_db_data[framework_db_data['Framework_Id'].isnull()]['mapped_org_id'].tolist())]
    new_integrator_df = new_integrator_df[new_integrator_df['createIntegrator']=='Y']
    existing_integrator_df = merge_df[merge_df['consumerOrgId'].isin(framework_db_data[framework_db_data['Framework_Id'].notnull()]['mapped_org_id'].tolist())]
    
    insert_update_db(db,new_frameworks_df,existing_frameworks_df,new_orgs_df,existing_orgs_df,new_integrator_df,existing_integrator_df)
    
    merge_df = merge_df[merge_df['agreementId'].isin(framework_db_data['mapped_agreement_id'].tolist())]
    return merge_df, merge_df[merge_df['org_isSSOEnabled']==0], merge_df[merge_df['createIntegrator']=='N'], errors

def TIP_get_new_existing_asset_data(asset_table_data_df, asset_api_data_df):
    asset_table_data_list = asset_table_data_df["assetId"].tolist()
    asset_api_data_list = asset_api_data_df["assetId"].tolist()

    new_asset_data = set(asset_api_data_list) - set(asset_table_data_list) 

    missing_asset_data = set(asset_table_data_list) - set(asset_api_data_list)

    new_asset_data = list(new_asset_data)
    existing_asset_data = list(set(asset_table_data_list) - set(missing_asset_data))
    asset_table_data_df = asset_table_data_df.replace({np.nan: None})
    asset_api_data_df["devices"] = asset_api_data_df['devices'].apply(lambda x: x[0] if x else None)
    asset_api_data_df["devicestype"] = asset_api_data_df["devices"].apply( lambda x: x.split(':')[0] if isinstance(x, str) and ':' in x else None )
    asset_api_data_df["devicestatus"]=asset_api_data_df['devices'].apply(lambda x: 1 if x else 0)
    asset_api_data_df["active"]=asset_api_data_df['status'].apply(lambda x: 1 if x=='active' else 0)
    asset_api_data_df["devicestatus"]=asset_api_data_df.apply(lambda x: 0 if x['status']=='inActive' else x["devicestatus"] ,axis=1)

    asset_api_data_df.loc[asset_api_data_df['internalCode'].isnull(), 'internalCode'] = None
    asset_api_data_df["unit_nr"]= None
    asset_api_data_df.loc[pd.to_numeric(asset_api_data_df['internalCode'], errors='coerce').notnull(),'unit_nr']= asset_api_data_df['internalCode']
    asset_api_data_df["fleet_id"]= None
    # asset_api_data_df.loc[asset_api_data_df['fleetId'].notna(), 'fleet_id'] = asset_api_data_df.loc[asset_api_data_df['fleetId'].notna(), 'fleetId']
    asset_api_data_df["fleet_id"] = asset_api_data_df["fleetId"].where( asset_api_data_df["fleetId"].notna(), None ).astype(object)
    asset_api_data_df = asset_api_data_df.replace({np.nan: None})
    # Check asset information between api and DB
    new_asset_data_df = asset_api_data_df.loc[asset_api_data_df["assetId"].isin(new_asset_data)]
    existing_asset_api_data_df = asset_api_data_df.loc[asset_api_data_df["assetId"].isin(existing_asset_data)]
    existing_asset_table_data_df = asset_table_data_df.loc[asset_table_data_df["assetId"].isin(existing_asset_data)]
    missing_asset_data_df = asset_table_data_df.loc[asset_table_data_df["assetId"].isin(missing_asset_data) & asset_table_data_df["Active"]==1]
    
    if len(existing_asset_api_data_df)>0:
        # Filter out paired and active table data
        existing_active_paired_asset_table_data_df = existing_asset_table_data_df.loc[(existing_asset_table_data_df["Device_Pairing_Status"]==1) & (existing_asset_table_data_df["Active"]==1)]
        #Merge API and Table data
        merge_paired_device_db_and_api_data_df = pd.merge(existing_asset_api_data_df, existing_active_paired_asset_table_data_df,on="assetId",how='left')
        merge_paired_device_db_and_api_data_df["Device_Pairing_Date"] = (merge_paired_device_db_and_api_data_df["assetId"]
                                                                        .map(asset_table_data_df.set_index("assetId")["Device_Pairing_Date"]))
        #Case 1 : Asset which is inactive from API but active in DB
        existing_inactive_asset_data_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["status"]=="inActive") & (merge_paired_device_db_and_api_data_df["Active"]==1)]
        #Case 2: New Pairing asset which not paired with any device in DB but paired in API with active status
        existing_new_pairing_asset_data_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].isna() & merge_paired_device_db_and_api_data_df["devices"].notna()) & (merge_paired_device_db_and_api_data_df["active"]==1)]
        existing_fresh_new_pairing_asset_data_df = existing_new_pairing_asset_data_df.loc[existing_new_pairing_asset_data_df["assetId"].isin(asset_table_data_df.loc[asset_table_data_df["Device_Number"].isna()]["assetId"].values)]
        existing_new_pairing_asset_data_df= existing_new_pairing_asset_data_df.loc[~existing_new_pairing_asset_data_df["assetId"].isin(existing_fresh_new_pairing_asset_data_df["assetId"].tolist())][["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id"]]
        #Case 3: Un-Pairing asset which paired already in DB but not paired in API 
        existing_unpairing_asset_data_df= merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].isna()) & (merge_paired_device_db_and_api_data_df["active"]==1)][["assetId","Device_Number","Device_Pairing_Status","Device_Pairing_Date","Device_Type","Device_Paired_By","internalCode","unit_nr","active","status","fleet_id"]]
        existing_unpairing_asset_to_insert_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].isna()) & (merge_paired_device_db_and_api_data_df["active"]==1)][["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id"]]
        existing_new_pairing_asset_data_df = pd.concat([existing_new_pairing_asset_data_df,existing_unpairing_asset_to_insert_df]).drop_duplicates()
        #Case 4: Different device between DB and API
        existing_different_pairing_asset_data_df =merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].notna()) & (merge_paired_device_db_and_api_data_df["active"]==1) &
                                                                                               (merge_paired_device_db_and_api_data_df["Device_Number"]!=merge_paired_device_db_and_api_data_df["devices"])]
        unpairing_asset_for_different_devices = existing_different_pairing_asset_data_df[["assetId","Device_Number","Device_Pairing_Status","Device_Pairing_Date","Device_Type","Device_Paired_By","internalCode","unit_nr","active","status","fleet_id"]]
        new_Pairing_asset_for_different_device = existing_different_pairing_asset_data_df[["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id"]]

        existing_unpairing_asset_data_df = pd.concat([unpairing_asset_for_different_devices,existing_unpairing_asset_data_df]).drop_duplicates()
        existing_new_pairing_asset_data_df = pd.concat([existing_new_pairing_asset_data_df,new_Pairing_asset_for_different_device]).drop_duplicates()

    else:
        existing_inactive_asset_data_df = pd.DataFrame()
        existing_unpairing_asset_data_df = pd.DataFrame()
        existing_new_pairing_asset_data_df =pd.DataFrame()
        existing_fresh_new_pairing_asset_data_df =pd.DataFrame()

    return new_asset_data_df, missing_asset_data_df, existing_asset_api_data_df, existing_inactive_asset_data_df, existing_unpairing_asset_data_df,\
                        existing_new_pairing_asset_data_df, existing_fresh_new_pairing_asset_data_df


def get_trailers_from_transics(api: TrailerApi, units = []):
    get_trailers_response = api.get_trailers(trailer_identifiers=units, trailer_identifier_type=TrailerIdentifier.ID)
    if get_trailers_response['Errors'] is not None:
        errors = get_trailers_response['Errors']['Error']
        #raise FleetConnectedException(str(errors))
        raise ScalarException(message=str(errors))
    trailers = get_trailers_response['Trailers']['TrailerResult_V6']
    transics_trailers_df = pd.DataFrame(trailers)
    return transics_trailers_df

def assign_assets_to_tip_global_country_in_provider_org(db: Database, asset_ids: list, provider_org_id: str, logger):
    assets_assigned_to_TIP_Global_group = []
    assets_not_assigned_to_TIP_Global_group = []
    access_token = fetch_access_token(db=db,org_id=provider_org_id,audience="TMAPI")
    assets_assigned_to_TIP_Global_group = get_TIP_Global_assignment_details_for_assets(db=db, org_id=provider_org_id, asset_list=asset_ids)
    assets_assigned_to_TIP_Global_group_df = assets_assigned_to_TIP_Global_group 
    assets_assigned_to_TIP_Global_group = assets_assigned_to_TIP_Global_group["assetId"].tolist()
    assets_not_assigned_to_TIP_Global_group = list(set(asset_ids) - set(assets_assigned_to_TIP_Global_group))
    assets_not_assigned_to_TIP_Global_group = list(dict.fromkeys(assets_not_assigned_to_TIP_Global_group))
    assets_assigned_to_TIP_Global_group = list(dict.fromkeys(assets_assigned_to_TIP_Global_group))
    newly_assigned_assets_for_TIP_Global = []
    if len(assets_not_assigned_to_TIP_Global_group)>0:
        asset_limit = GeneralConstant.ASSET_LIMIT
        child_group_for_global_main_group= get_child_asset_group_for_TIPGlobal_asset_group_new(db=db, asset_limit=asset_limit, sc_org_id=provider_org_id)
        # if len(child_group_for_global_main_group)==0:
        child_group_for_global_main_group = child_group_for_global_main_group[child_group_for_global_main_group["Available_Count"] >= 0].copy()
        total_available_count = int(child_group_for_global_main_group["Available_Count"].sum())
        total_unassign_assets = len(assets_not_assigned_to_TIP_Global_group)
        flag = 0
        while total_unassign_assets > total_available_count:
            new_child_asset_group_id = create_TIP_global_sub_asset_group(db=db, tip_tmapi_access_token= access_token, provider_org_id= provider_org_id, logger=logger)
            total_available_count = total_available_count + asset_limit
            flag = 1
        if flag:
            child_group_for_global_main_group= get_child_asset_group_for_TIPGlobal_asset_group_new(db=db, asset_limit=asset_limit, sc_org_id=provider_org_id)

        if len(child_group_for_global_main_group)>0:
            for _,child_group_details in child_group_for_global_main_group.iterrows():
                # Exit loop if no assets remain 
                if len(assets_not_assigned_to_TIP_Global_group) == 0: break
                child_asset_group_id = child_group_details["Asset_Group_Id"]
                child_asset_group_name = child_group_details["Asset_Group_Name"]
                asset_count = child_group_details["Asset_Count"]
                available_count = asset_limit - asset_count
                asset_set = assets_not_assigned_to_TIP_Global_group[:available_count]
                if len(asset_set)>0:
                    error_list = assign_assets_to_assetgroup_in_scalar_and_db(db=db,logger=logger,access_token=access_token,
                                        asset_group_id=child_asset_group_id,
                                        asset_id_list=asset_set,
                                        error_list=[])
                    assets_not_assigned_to_TIP_Global_group = list(set(assets_not_assigned_to_TIP_Global_group) - set(asset_set))
                    if len(error_list) > 0:
                        logger.info(error_list)
                    else:
                        newly_assigned_assets_for_TIP_Global.extend(asset_set)
                        message = f"Assets has assigned to {child_asset_group_name} Asset group successfully."
                        logger.info(message)
        logger.info("Assets has assigned with TIP Global sub asset Group successfully.")
    else:
        if not assets_assigned_to_TIP_Global_group_df.empty:
            grouped_df = (
                    assets_assigned_to_TIP_Global_group_df.groupby("groupIds", as_index=False)
                    .agg(assetIds=("assetId", lambda x: list(dict.fromkeys(x))))
            )
            for row in grouped_df.itertuples(index=False): 
                add_asset_group_mapping_in_db( db=db, asset_nrs=row.assetIds, group_id=row.groupIds )
        logger.info("All assets are assigned already with TIP Global sub asset Group.Assignment details updated in DB.")
    message = f"Assets has assigned to TIP Global group successfully."
    assiged_TIP_Global_Assets= get_TIP_Global_assinged_assets_for_report(db=db, sc_org_id= provider_org_id, asset_ids= asset_ids)
    newly_assigned_assets_for_TIP_Global_df = assiged_TIP_Global_Assets.loc[assiged_TIP_Global_Assets["Asset_Id"].isin(newly_assigned_assets_for_TIP_Global)]
    already_assigned_assets_for_TIP_Global_df = assiged_TIP_Global_Assets.loc[assiged_TIP_Global_Assets["Asset_Id"].isin(assets_assigned_to_TIP_Global_group)]
    assiged_TIP_country_Assets_df= assign_asset_to_country_group(logger=logger,db=db, tip_tmapi_access_token=access_token,
                                                                    asset_id_list=asset_ids,
                                                                    provider_org_id=provider_org_id)
    message = f"{message} Assets has assigned to country Asset group successfully."
    logger.info(message)
    return newly_assigned_assets_for_TIP_Global_df,already_assigned_assets_for_TIP_Global_df,assiged_TIP_country_Assets_df
    
def create_TIP_global_sub_asset_group(db: Database,tip_tmapi_access_token: str, provider_org_id: str,logger):
    # child_group_for_global_main_group = pd.DataFrame()
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    child_asset_group_name = GeneralConstant.TIPGLOBALCHILDGROUP
    TIPGlobal_main_asset_group= get_TIPGlobal_main_asset_group(db=db, org_id= provider_org_id)
    parent_group_details = TIPGlobal_main_asset_group.iloc[0]
    parent_group_id = parent_group_details["Asset_Group_Id"]
    child_asset_group_name = f"{child_asset_group_name} - #Copy#{random_id}"
    asset_group_response = create_asset_group(access_token= tip_tmapi_access_token, name=child_asset_group_name,description=child_asset_group_name, parent_group_id=parent_group_id)
    if  asset_group_response.status_code == 201:
        asset_group_dict = asset_group_response.json()
        child_asset_group_id =asset_group_dict["id"]
        # child_group_for_global_main_group["Asset_Group_Id"] = child_asset_group_id
        # child_group_for_global_main_group["Asset_Count"] = 0
        save_asset_group_in_db(db=db, asset_group_id=child_asset_group_id, asset_group_name=child_asset_group_name, asset_group_description=child_asset_group_name, sc_organization_id=provider_org_id, root_group_id=parent_group_id, parent_group_id=parent_group_id, fa_root_org_id=None)
        message = f"Copy TIP Global sub asset group {child_asset_group_name} has created."
        logger.info(message)
    else:
        error_list= get_scalar_api_error_messages(error_response=asset_group_response)
        raise Exception(message=f"Failed to create tip global sub asset group for provider org {provider_org_id}-"+' '.join(map(str,error_list)))
    return child_asset_group_id

def get_TIP_Global_assignment_details_for_assets(db:Database, org_id: str,asset_list: list):
    asset_list_from_api = get_asset_api_data(db=db,org_id=org_id)
    asset_list_from_api["groupIds"] = asset_list_from_api["assignees"].apply(
                                            lambda x: x.get("groupIds", []) if isinstance(x, dict) else []
                                            )
    asset_data_df = asset_list_from_api[["assetId", "groupIds"]]
    asset_data_df = asset_data_df[asset_data_df["groupIds"].map(lambda x: bool(x))]

    asset_data_df = asset_data_df.explode("groupIds").reset_index(drop=True)

    asset_data_df = asset_data_df.loc[asset_data_df["assetId"].isin(asset_list)]
    tip_global_child_asset_groups_df = get_group_list_for_tip_global_asset_group(db=db, sc_org_id=org_id)
    if len(tip_global_child_asset_groups_df)==0:
        raise ScalarException(message=f"Sub asset group missing for TIP global asset group {GeneralConstant.TIPGLOBALGROUP}")
    tip_global_child_asset_group_ids = tip_global_child_asset_groups_df['Child_Asset_Group_Id'].tolist()

    # Filter assets that are already assigned (groupIds matching TIP global child asset group IDs) 
    already_assigned_asset_df = asset_data_df[ asset_data_df['groupIds'].isin(tip_global_child_asset_group_ids) ].reset_index(drop=True)
    
    return already_assigned_asset_df

def assign_asset_to_country_group(logger,db: Database, tip_tmapi_access_token: str, asset_id_list: list,provider_org_id: str):
    # Assign to country asset group
    group_mapping_df = get_asset_country_group(db=db, asset_ids=asset_id_list, provider_org_id = provider_org_id)
    for asset_group_id, group_df in group_mapping_df.groupby("Country_Group_Id"):
        asset_group_name = group_df["Asset_Group_Name"].iloc[0]
        group_asset_ids = group_df["Asset_Id"].dropna().astype(str).unique().tolist()

        # check if the assetgroup has reached limit of 5000 assets assigned
        logger.info(f"Fetching all assets and their assetgroup details")   
        all_assets_and_groups_df = fetch_all_assets_and_groups_from_api(db=db,org_id=provider_org_id)
        assets_already_assigned_df = all_assets_and_groups_df.loc[all_assets_and_groups_df['groupIds'] == asset_group_id]
        # if the maximum limit for asset assignment already reached, return with error
        if len(assets_already_assigned_df) >= GeneralConstant.ASSET_LIMIT:
            msg = f"Maximum limit for assigning assets ({GeneralConstant.ASSET_LIMIT}) to assetgroup {asset_group_id} is already reached. \
                Cannot assign any new assets to group."
            logger.info(msg)
            continue
        
        no_of_assets_can_be_assigned = GeneralConstant.ASSET_LIMIT - len(assets_already_assigned_df)
        logger.info(f"The assetgroup has {len(assets_already_assigned_df)} assets assigned. \
                    Only {no_of_assets_can_be_assigned} more assets can be assigned until it reaches it's limit.")
        
        # filter the already assigned asset list
        already_assigned_list = assets_already_assigned_df['assetId'].to_list()

        asset_list_to_be_assigned = list(set(group_asset_ids) - set(already_assigned_list))
        asset_ids = asset_list_to_be_assigned[0:no_of_assets_can_be_assigned]
        if len(asset_ids) >0:
            error_list = assign_assets_to_assetgroup_in_scalar_and_db(db=db,logger=logger,access_token=tip_tmapi_access_token,\
                                                    asset_group_id=asset_group_id,asset_id_list=asset_ids,
                                                    error_list=[])

            if len(error_list) > 0:
                logger.info(error_list)
            else:
                message = f"Assets has assigned to {asset_group_name} Asset group successfully."
                logger.info(message)
        else:
            message = f"There is no new assets to assign in {asset_group_name} Asset group successfully."
            logger.info(message)
        if len(assets_already_assigned_df)>0:
            add_asset_group_mapping_in_db( db=db, asset_nrs=already_assigned_list, group_id=asset_group_id)
            message = f"Assignment details updated in DB for already assigned assets for asset group {asset_group_name}."
            logger.info(message)
    assiged_TIP_country_Assets = get_country_assinged_assets_for_report(db=db, sc_org_id= provider_org_id, asset_ids= asset_id_list)
    # assiged_TIP_country_Assets = get_TIP_country_assinged_assets_for_report(db=db, sc_org_id= provider_org_id, asset_ids= asset_id_list)
    return assiged_TIP_country_Assets