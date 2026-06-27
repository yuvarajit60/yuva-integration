from datetime import date
import os
import pandas as pd
from io import BytesIO
from pandas import DataFrame
from app.common.email import Email
from app.common.constants import AutoPairingEvent

def send_auto_pairing_report(auto_pairing_log: DataFrame, from_date: date, end_date: date):
    device_paired_failed,device_manual_paired_failed,device_manual_unpaired_failed, vin_not_found_failed, multi_match_found_failed,invalid_data,unknown_data = 0, 0, 0, 0, 0,0,0
    control_report = BytesIO()
    with pd.ExcelWriter(control_report, engine='xlsxwriter') as writer:
        if len(auto_pairing_log) > 0:
            df_by_event_type = auto_pairing_log.groupby(['Reason'])        
            for event_type, event_type_df in df_by_event_type:
                event_type =event_type[0]
                if event_type == AutoPairingEvent.DEVICE_SUCCESSFULLY_AUTO_PAIRED:
                    device_paired_failed = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_SUCCESSFULLY_MANUAL_PAIRED:
                    device_manual_paired_failed = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_SUCCESSFULLY_MANUAL_UNPAIRED:
                    device_manual_unpaired_failed = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_NOT_PAIRED_VIN_NOT_FOUND:
                    vin_not_found_failed = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_NOT_PAIRED_MULTIPLE_MATCH_FOUND:
                    multi_match_found_failed = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_NOT_PAIRED_INVALID_DATA:
                    invalid_data = len(event_type_df)
                if event_type == AutoPairingEvent.DEVICE_NOT_PAIRED_UNKNOWN:
                    unknown_data = len(event_type_df)
            auto_pairing_log.to_excel(writer, sheet_name='Auto pairing failure log', index = None, header=True)

    if from_date == end_date:
        message = f"on {str(from_date)}"
    else:
        message = f"between {str(from_date)} and {str(end_date)}"


    email = Email()
    receivers = os.environ["AUTO_PAIRING_REPORT_RECIPIENTS"].split(",")
    env = os.environ['SCALAR_ENV']
    subject = f"Scalar - Auto Pairing Failure Log Report" 
    if env != 'PROD':
        subject = f"Scalar - Auto Pairing Failure Log Report - "+ env
    template_name = 'auto_pairing_failure_log_report.html'

    params = {
        "environment": env,
        "message": message,
        "device_paired_failed": device_paired_failed,
        "device_manual_paired_failed": device_manual_paired_failed,
        "device_manual_unpaired_failed": device_manual_unpaired_failed,
        "vin_not_found_failed": vin_not_found_failed,
        "multi_match_found_failed": multi_match_found_failed,
        "invalid_data":invalid_data,
        "unknown_data":unknown_data
        }


    attachment, file_name = None, None
    if len(auto_pairing_log) > 0:
        if control_report is not None:
            control_report.seek(0)
            attachment = control_report.read()
            file_name = f"Auto_Pairing_Failure_Log.xlsx"
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params,
                        attachment=attachment, filename=file_name)