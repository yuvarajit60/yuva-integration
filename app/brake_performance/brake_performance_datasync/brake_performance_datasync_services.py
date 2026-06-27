import os
import pandas as pd
from io import BytesIO
from app.common.database import Database
from app.common.constants import AudienceCode
from app.common.helpers.common_services import fetch_access_token, get_all_data
from app.common.scalar_api.brake_performance_api import get_all_bp_assets
from asyncio.log import logger
from app.common.email import Email
from datetime import datetime


def get_bp_api_data(db:Database, org_id: str):
    access_token = fetch_access_token(db=db, org_id=org_id, audience=AudienceCode.BRAKE_PERFORMANCE)
    asset_data = get_all_data(access_token=access_token,func=get_all_bp_assets)
    if asset_data is not None:
        asset_data_df = pd.DataFrame(asset_data)  
    return asset_data_df

def get_new_existing_bp_asset_data(bp_asset_table_data_df, bp_asset_api_data_df):
    bp_asset_table_data_list = bp_asset_table_data_df["assetId"].tolist()
    bp_asset_api_data_list = bp_asset_api_data_df["assetId"].tolist()

    new_bp_asset_data = set(bp_asset_api_data_list) - set(bp_asset_table_data_list) 
    existing_bp_asset_data = set(bp_asset_api_data_list) - new_bp_asset_data
    missing_bp_asset_data = set(bp_asset_table_data_list) - set(bp_asset_api_data_list)

    new_bp_asset_data = list(new_bp_asset_data)
    existing_bp_asset_data = list(existing_bp_asset_data)
    missing_bp_asset_data = list(missing_bp_asset_data)

    logger.info(f"Total new bp assets: {len(new_bp_asset_data)}")
    logger.info(f"Total existing bp assets: {len(existing_bp_asset_data)}")
    logger.info(f"Total Missing bp assets: {len(missing_bp_asset_data)}")

    new_bp_asset_data_df = bp_asset_api_data_df.loc[bp_asset_api_data_df["assetId"].isin(new_bp_asset_data)]
    existing_asset_bp_data_df = bp_asset_api_data_df.loc[bp_asset_api_data_df["assetId"].isin(existing_bp_asset_data)]
    missing_bp_asset_data_df = bp_asset_table_data_df.loc[(bp_asset_table_data_df["assetId"].isin(missing_bp_asset_data)) & bp_asset_table_data_df["Active"]==1]

    return new_bp_asset_data_df, existing_asset_bp_data_df, missing_bp_asset_data_df, 


def send_bp_asset_sync_report(bp_api_asset_list,new_bp_asset_list,update_bp_asset_list,error_bp_asset_list,params):
    email = Email()
    receivers = os.environ["REPORT_MAIL_DL"].split(",")
    file_name = f"Brake_Performance_Asset_Sync_Report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar - Data Sync: Brake performance asset sync Report"
    if env != "PROD":
        subject = f"Scalar - Data Sync: Brake performance asset sync Report - " + env
    template_name = 'bp_asset_data_sync_email.html'


    sub_control_report = BytesIO()
    with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
        if len(bp_api_asset_list) > 0:
            bp_api_asset_list.to_excel(writer, sheet_name='Total bp assets from API', index=None, header=True)
        if len(new_bp_asset_list) > 0:
            new_bp_asset_list.to_excel(writer, sheet_name='New bp assets added', index=None, header=True)
        if len(update_bp_asset_list) > 0:
            update_bp_asset_list.to_excel(writer, sheet_name='Exisiting bp assets updated', index=None, header=True)
        if len(error_bp_asset_list) > 0:
            error_bp_asset_list.to_excel(writer, sheet_name='BP assets deactivated', index=None, header=True)
            
    attachment = None
    file_name = f"{file_name}.xlsx"
    if sub_control_report is not None:
        sub_control_report.seek(0)
        attachment = sub_control_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)