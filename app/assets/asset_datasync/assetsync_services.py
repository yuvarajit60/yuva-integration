import os
import pandas as pd
from io import BytesIO
from datetime import datetime
from app.common.database import Database
from app.common.email import Email
import numpy as np

def get_new_existing_asset_data(asset_table_data_df, asset_api_data_df,logger):
    asset_table_data_list = asset_table_data_df["assetId"].tolist()
    asset_api_data_list = asset_api_data_df["assetId"].tolist()

    new_asset_data = set(asset_api_data_list) - set(asset_table_data_list) 

    missing_asset_data = set(asset_table_data_list) - set(asset_api_data_list)

    new_asset_data = list(new_asset_data)
    existing_asset_data = list(set(asset_table_data_list) - set(missing_asset_data))
    asset_table_data_df = asset_table_data_df.replace({np.nan: None})
    first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df= asset_table_data_df)
    logger.info(f"Device pairing date format in DB Dataframe:{first_device_pairing_date}")
    asset_api_data_df["devices"] = asset_api_data_df['devices'].apply(lambda x: x[0] if x else None)
    asset_api_data_df["devicestype"] = asset_api_data_df["devices"].apply( lambda x: x.split(':')[0] if isinstance(x, str) and ':' in x else None )
    asset_api_data_df["devicestatus"]=asset_api_data_df['devices'].apply(lambda x: 1 if x else 0)
    asset_api_data_df["active"]=asset_api_data_df['status'].apply(lambda x: 1 if x=='active' else 0)
    asset_api_data_df["devicestatus"]=asset_api_data_df.apply(lambda x: 0 if x['status']=='inActive' else x["devicestatus"] ,axis=1)

    asset_api_data_df.loc[asset_api_data_df['internalCode'].isnull(), 'internalCode'] = None
    asset_api_data_df["unit_nr"]= None
    asset_api_data_df.loc[pd.to_numeric(asset_api_data_df['internalCode'], errors='coerce').notnull(),'unit_nr']= asset_api_data_df['internalCode']
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
        first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df= merge_paired_device_db_and_api_data_df)
        logger.info(f"Device pairing date format in merged dataframe:{first_device_pairing_date}")
        # merge_paired_device_db_and_api_data_df["Device_Pairing_Date"] = (merge_paired_device_db_and_api_data_df["assetId"]
        #                                                                 .map(asset_table_data_df.set_index("assetId")["Device_Pairing_Date"]))
        #Case 1 : Asset which is inactive from API but active in DB
        existing_inactive_asset_data_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["status"]=="inActive") & (merge_paired_device_db_and_api_data_df["Active"]==1)]
        #Case 2: New Pairing asset which not paired with any device in DB but paired in API with active status
        existing_new_pairing_asset_data_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].isna() & merge_paired_device_db_and_api_data_df["devices"].notna()) & (merge_paired_device_db_and_api_data_df["active"]==1)]
        existing_fresh_new_pairing_asset_data_df = existing_new_pairing_asset_data_df.loc[existing_new_pairing_asset_data_df["assetId"].isin(asset_table_data_df.loc[asset_table_data_df["Device_Number"].isna()]["assetId"].values)]
        existing_new_pairing_asset_data_df= existing_new_pairing_asset_data_df.loc[~existing_new_pairing_asset_data_df["assetId"].isin(existing_fresh_new_pairing_asset_data_df["assetId"].tolist())][["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id","vin","licensePlate"]]
        #Case 3: Un-Pairing asset which paired already in DB but not paired in API 
        existing_unpairing_asset_data_df= merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].isna()) & (merge_paired_device_db_and_api_data_df["active"]==1)][["assetId","Device_Number","Device_Pairing_Status","Device_Pairing_Date","Device_Type","Device_Paired_By","internalCode","unit_nr","active","status","fleet_id","vin","licensePlate"]]
        existing_unpairing_asset_to_insert_df = merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].isna()) & (merge_paired_device_db_and_api_data_df["active"]==1)][["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id","vin","licensePlate"]]
        existing_new_pairing_asset_data_df = pd.concat([existing_new_pairing_asset_data_df,existing_unpairing_asset_to_insert_df]).drop_duplicates()
        #Case 4: Different device between DB and API
        existing_different_pairing_asset_data_df =merge_paired_device_db_and_api_data_df.loc[(merge_paired_device_db_and_api_data_df["Device_Number"].notna() & merge_paired_device_db_and_api_data_df["devices"].notna()) & (merge_paired_device_db_and_api_data_df["active"]==1) &
                                                                                               (merge_paired_device_db_and_api_data_df["Device_Number"]!=merge_paired_device_db_and_api_data_df["devices"])]
        unpairing_asset_for_different_devices = existing_different_pairing_asset_data_df[["assetId","Device_Number","Device_Pairing_Status","Device_Pairing_Date","Device_Type","Device_Paired_By","internalCode","unit_nr","active","status","fleet_id","vin","licensePlate"]]
        new_Pairing_asset_for_different_device = existing_different_pairing_asset_data_df[["assetId","internalCode","unit_nr","devices","devicestatus","devicestype","active","status","fleet_id","vin","licensePlate"]]

        existing_unpairing_asset_data_df = pd.concat([unpairing_asset_for_different_devices,existing_unpairing_asset_data_df]).drop_duplicates()
        existing_new_pairing_asset_data_df = pd.concat([existing_new_pairing_asset_data_df,new_Pairing_asset_for_different_device]).drop_duplicates()
    
    else:
        existing_inactive_asset_data_df = pd.DataFrame()
        existing_unpairing_asset_data_df = pd.DataFrame()
        existing_new_pairing_asset_data_df =pd.DataFrame()
        existing_fresh_new_pairing_asset_data_df =pd.DataFrame()
    
    first_device_pairing_date = print_device_pairing_date_from_df(device_pairing_date_df= existing_unpairing_asset_data_df)
    logger.info(f"Device pairing date format in final Dataframe:{first_device_pairing_date}")
    return new_asset_data_df, missing_asset_data_df, existing_asset_api_data_df, existing_inactive_asset_data_df, existing_unpairing_asset_data_df,\
                        existing_new_pairing_asset_data_df, existing_fresh_new_pairing_asset_data_df

def send_asset_sync_report(api_asset_list,new_asset_list,update_asset_list,error_asset_list,params):
    email = Email()
    receivers = os.environ["REPORT_MAIL_DL"].split(",")
    file_name = f"Asset_Sync_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar - Data Sync: Asset sync Report"
    template_name = 'asset_data_sync_email.html'
    if os.environ['SCALAR_ENV'] != 'PROD':
        subject = f"Scalar - Data Sync: Asset sync report - {os.environ['SCALAR_ENV']}"

    sub_control_report = BytesIO()
    with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
        if len(api_asset_list) > 0:
            api_asset_list.to_excel(writer, sheet_name='Total number of assets from API', index=None, header=True)
        if len(new_asset_list) > 0:
            new_asset_list.to_excel(writer, sheet_name='New assets added', index=None, header=True)
        if len(update_asset_list) > 0:
            update_asset_list.to_excel(writer, sheet_name='Exisiting assets updated', index=None, header=True)
        if len(error_asset_list) > 0:
            error_asset_list.to_excel(writer, sheet_name='Assets deactivated', index=None, header=True)
            
    attachment = None
    file_name = f"{file_name}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)
    
def print_device_pairing_date_from_df(device_pairing_date_df):
    device_pairing_date_df = device_pairing_date_df[device_pairing_date_df["Device_Pairing_Date"].notna()]
    if not device_pairing_date_df.empty:
        first_device_pairing_date = device_pairing_date_df.iloc[0]["Device_Pairing_Date"]
    else:
        first_device_pairing_date = "No Record"
    return first_device_pairing_date