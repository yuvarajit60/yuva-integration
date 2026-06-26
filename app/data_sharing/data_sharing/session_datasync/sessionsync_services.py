import pandas as pd
import numpy as np
import os
from datetime import datetime
from app.common.database import Database
from app.common.email import Email
from io import BytesIO
from app.common.helpers.common_services import get_all_data
from app.common.scalar_api.session_api import get_all_sessions


def get_all_sessions_from_api(access_token: str, logger) -> pd.DataFrame:
    all_sessions_from_api_df = get_all_data(access_token= access_token, func=get_all_sessions)
    all_sessions_from_api_df = all_sessions_from_api_df.drop(["agreementName","parentContractId","contractId",
            "contractName","providerOrgName","consumerOrgName","vinNumber","licensePlate",
            "providerAssetName","consumerAssetName"], axis=1)
    all_sessions_from_api_df.rename(columns = {"sessionId": "Session_Id",
        "agreementId": "Agreement_Id",
        "providerOrgId": "Provider_Organization_Id",
        "consumerOrgId": "Consumer_Organization_Id",
        "status": "Status",
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

def send_session_sync_report(new_sessions_to_insert,sessions_to_update,sessions_to_deactivate, params):
    email = Email()
    env = os.environ['SCALAR_ENV']
    receivers=os.environ['REPORT_MAIL_DL']
    receivers = receivers.split(",")
    file_name = f"Session_Sync_Report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    subject = f"Scalar - Data Sync: Session sync report"
    if os.environ['SCALAR_ENV'] != 'PROD':
            subject = f"Scalar - Data Sync: Session sync report - {os.environ['SCALAR_ENV']}"
    template_name = f'session_data_sync_report.html'

    sessionsync_report = BytesIO()
    with pd.ExcelWriter(sessionsync_report, engine='xlsxwriter') as writer:
        if len(new_sessions_to_insert) > 0:
            new_sessions_to_insert.to_excel(writer, sheet_name='New sessions added', index=None, header=True)
        if len(sessions_to_update) > 0:
            sessions_to_update.to_excel(writer, sheet_name='Existing sessions updated', index=None, header=True)
        if len(sessions_to_deactivate) > 0:
            sessions_to_deactivate.to_excel(writer, sheet_name='Sessions deactivated', index=None, header=True)
            
    attachment = None
    if sessionsync_report is not None:
        sessionsync_report.seek(0)
        attachment = sessionsync_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)