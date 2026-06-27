from datetime import datetime

import pandas as pd
from app.brake_performance.brake_performance_activate.brake_performance_activate_data_access import get_disabled_brake_plus_units
from app.brake_performance.brake_performance_activate.brake_performance_activate_service import activate_bp_assets, sync_and_check_if_really_activated
from app.common.constants import ContentType, GeneralConstant, ResponseCode, StatusCode
from app.common.exception_handler import global_exception_handler
import azure.functions as func
import logging
import os
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token,log_errors, start_job_execution_process, update_job_execution_process
from app.common.models import Response
from app.common.database import Database
from app.common.email import Email
from io import BytesIO
from sqlalchemy.exc import SQLAlchemyError

brakeperformanceactivate_bp = func.Blueprint()

@brakeperformanceactivate_bp.function_name(name="Activate_Brake_Performance")
@brakeperformanceactivate_bp.route(route="activate/brakeperformance",  methods=[func.HttpMethod.POST])
@global_exception_handler
def bpactivation_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Activate_Brake_Performance")

    try:        
        db = Database()
        error_list = []
        message = ""
        job_exectution_time = datetime.now()
        job_id = None
        job_name = GeneralConstant.BRAKE_PLUS_ACTIVATE_UNIT_JOB_NAME

        report_columns = ["Unit_Nr", "License_Nr", "Asset_Id", "SC_Organization_Id", "SC_Organization_Name", "FA_Root_Org_Id"]
        appeared_to_be_activated_bp_units_df = pd.DataFrame(columns=report_columns)
        failed_activated_bp_units_df = pd.DataFrame(columns=report_columns)
        truly_activated_bp_units_df = pd.DataFrame(columns=report_columns)
        falsely_activated_bp_units_df = pd.DataFrame(columns=report_columns)
    

        to_be_activated_bp_units_df = get_disabled_brake_plus_units(db=db)
        total_units_to_be_activated = len(to_be_activated_bp_units_df)
        message = f"Total number of units to be activated: {total_units_to_be_activated}"
        logger.info(message)
        job_id = start_job_execution_process(db=db, job_name=job_name)
        if len(to_be_activated_bp_units_df)== 0:
            message=f"No new units found to be activated with EBPMS feature. All required assets already have the EBPMS feature ON."
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)
            logger.warning(message)
            response = Response(status=True, message=message).getJsonResponse()
            return func.HttpResponse(
                    response,
                    status_code=ResponseCode.SUCCESS,
                    mimetype=ContentType.APPLICATION_JSON
                )
        
        organization_id = get_tip_provider_organization(db=db)
        if organization_id is None:
            raise ScalarException(message="There is no provider organization data in database.")
        else:
            org_id=organization_id[0]
        access_token = fetch_access_token(db=db,org_id=org_id,audience="BPAPI")
        
        distinct_cust_org_ids = set(to_be_activated_bp_units_df['SC_Organization_Id'].to_list())
        logger.info(f"Total distinct Organization: {len(distinct_cust_org_ids)}")
        for cust_org_id in distinct_cust_org_ids:
            to_be_activated_bp_units = to_be_activated_bp_units_df.loc[(to_be_activated_bp_units_df["SC_Organization_Id"] == cust_org_id)]
            asset_ids = to_be_activated_bp_units["Asset_Id"].tolist()
            newly_bp_activated_units,bp_failed_units = activate_bp_assets(db= db, org_id= org_id, access_token= access_token, asset_ids=asset_ids)
            temp_truly_bp_activated_units = []
            temp_falsely_bp_activated_units = []
            if len(newly_bp_activated_units) > 0:
                temp_activated_bp_units_df = to_be_activated_bp_units_df.loc[to_be_activated_bp_units_df["Asset_Id"].isin(newly_bp_activated_units)][report_columns]
                temp_truly_bp_activated_units, temp_falsely_bp_activated_units = sync_and_check_if_really_activated(db=db, access_token=access_token, activated_units=newly_bp_activated_units)
                appeared_to_be_activated_bp_units_df = pd.concat([appeared_to_be_activated_bp_units_df, temp_activated_bp_units_df])
                if len(temp_truly_bp_activated_units) > 0:
                    temp_truly_bp_activated_units = to_be_activated_bp_units.loc[to_be_activated_bp_units["Asset_Id"].isin(temp_truly_bp_activated_units)][report_columns]
                    truly_activated_bp_units_df = pd.concat([truly_activated_bp_units_df, temp_truly_bp_activated_units])
                if len(temp_falsely_bp_activated_units) > 0:
                    temp_falsely_bp_activated_units = to_be_activated_bp_units.loc[to_be_activated_bp_units["Asset_Id"].isin(temp_falsely_bp_activated_units)][report_columns]
                    falsely_activated_bp_units_df = pd.concat([falsely_activated_bp_units_df, temp_falsely_bp_activated_units])
            if len(bp_failed_units) > 0:
                #bp_failed_units = bp_failed_units["assetId"].tolist()
                bp_failed_units = pd.DataFrame(bp_failed_units)
                temp_failed_actived_bp_units_df = to_be_activated_bp_units.loc[to_be_activated_bp_units["Asset_Id"].isin(bp_failed_units["Asset_Id"].tolist())][report_columns]
                temp_failed_actived_bp_units_df = pd.merge(temp_failed_actived_bp_units_df,bp_failed_units, on="Asset_Id", how="right")
                failed_activated_bp_units_df = pd.concat([failed_activated_bp_units_df, temp_failed_actived_bp_units_df])

            logger.info(f"Appear to be activated on {len(newly_bp_activated_units)} units, \
                        Truly activated on {len(temp_truly_bp_activated_units)} units, \
                        Falsely activated on {len(temp_falsely_bp_activated_units)} units, \
                        failed to activate on {len(bp_failed_units)} for customer {cust_org_id}")
        
        message = "EBPMS activation on brake plus units have been processed successfully"
        if len(failed_activated_bp_units_df)>0:
            message = f"{message} with some errors. Please refer to the attached excelsheet"

        update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)

        logger.info(message)            
        response = Response(status=True, message=message)
        return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    
    except SQLAlchemyError as sae:
        message = GeneralConstant.DB_EXCP_MESSAGE
        error_list.extend(log_errors([str(sae)], "DB Exception", None))
        logger.error(sae, exc_info=True)
        if job_id is not None:
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
        response = Response(status=False, message=message)
        return func.HttpResponse(
                response.getJsonResponse(),
                status_code=ResponseCode.INTERNAL_ERROR,
                mimetype=ContentType.APPLICATION_JSON)
    
    except Exception as e:
        message = str(e)
        error_list.extend(log_errors([str(e)], "Application Exception", None))
        logger.error(message, exc_info=True)
        if job_id is not None:
            update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
        response = Response(status=False, message=message)
        return func.HttpResponse(
             response.getJsonResponse(),
             status_code=ResponseCode.INTERNAL_ERROR,
             mimetype=ContentType.APPLICATION_JSON)      
    finally:
        brake_plus_report = BytesIO()
        with pd.ExcelWriter(brake_plus_report, engine='xlsxwriter') as writer:
            if len(appeared_to_be_activated_bp_units_df) > 0:
                appeared_to_be_activated_bp_units_df.to_excel(writer, sheet_name='BP_activated_units', index=None, header=True)
            if len(truly_activated_bp_units_df) > 0:
                truly_activated_bp_units_df.to_excel(writer, sheet_name='Truly_BP_activated_units', index=None, header=True)
            if len(falsely_activated_bp_units_df) > 0:
                falsely_activated_bp_units_df.to_excel(writer, sheet_name='Falsely_BP_activated_units', index=None, header=True)
            if len(failed_activated_bp_units_df) > 0:
                failed_activated_bp_units_df.to_excel(writer, sheet_name='BP_activation_failed_units', index=None, header=True)
            
        email = Email()
        env = os.environ['SCALAR_ENV']
        receivers = os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject = "Scalar - Scalar Brake Plus Activated Units Report"
        if len(error_list)>0:
            subject = "Scalar Job Failure - Scalar Brake Plus Activated Units Report"
        if env != "PROD":
            subject = f"{subject} - {env}"
        template_name = "scalar_brake_plus_activated_units.html"
        params = {
            "environment": env,
            "job_execution_time": job_exectution_time,
            "job_exectution_message": message,
            "bp_activated_unit_count":len(appeared_to_be_activated_bp_units_df),
            "truly_bp_activated_unit_count":len(truly_activated_bp_units_df),
            "falsely_bp_activated_unit_count":len(falsely_activated_bp_units_df),
            "bp_activation_failed_unit_count":len(failed_activated_bp_units_df)
            }
        attachment, file_name = None, None
        if brake_plus_report is not None:
            brake_plus_report.seek(0)
            attachment = brake_plus_report.read()
            file_name = "scalar_brake_plus_activated_units.xlsx"
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                            attachment=attachment, filename=file_name)
        logger.info("Scalar brake plus activation mail sent successfully")

        