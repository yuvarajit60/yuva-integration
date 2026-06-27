import logging
import os
from datetime import datetime

import azure.functions as func
import pandas as pd
from sqlalchemy.exc import SQLAlchemyError

from app.common.constants import AudienceCode, ContentType, ErrorFields, GeneralConstant, ResponseCode, StatusCode
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_consumer_organization_data, get_last_successfull_job_execution_ts, get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token, log_errors, start_job_execution_process, update_job_execution_process, get_distinct_count
from app.common.helpers.group_helpers import get_sc_groups
from app.common.helpers.process_helpers import get_units_by_root_orgs
from app.common.helpers.asset_group_helper import remove_asset_group_mapping_from_db
from app.common.models import Response
from app.data_sharing.interchange_in_units.interchange_in_units_data_access import get_interchange_in_units
from app.data_sharing.interchange_in_units.interchange_in_units_services import generate_interchangein_unit_report, get_control_report_records, provider_asset_fleet_id_change, stop_datasharing, unassign_assets_from_group_in_provider_org


interchange_in_bp = func.Blueprint() 

@interchange_in_bp.function_name(name="Interchange_In_Units")
@interchange_in_bp.route(route="units/interchangein",  methods=[func.HttpMethod.POST])
@global_exception_handler
def interchange_in_units(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Interchange_In_Units")
    try:
        units_wout_root_org_list = []
        units_wout_pairing_info_list = []
        consumer_issues_unit_list = []
        consumer_issues_unit_set = set()
        error_list = []
        datasharing_removed_unit_list = []
        datasharing_removed_unit_set = set()
        datasharing_not_exist_unit_list = []
        datasharing_not_exist_unit_set = set()
        message = ""
        total_intch_in_units_count, units_wout_root_org_count, units_wout_pairing_info_count = 0, 0, 0
        job_exectution_time = datetime.now()
        job_id = None
        job_name = GeneralConstant.INTCH_IN_UNIT_JOB_NAME
        db = Database()
        last_successful_execution_ts = get_last_successfull_job_execution_ts(db=db, job_name=job_name)
        interchange_in_units_df = get_interchange_in_units(db=db, last_successful_execution_ts=last_successful_execution_ts)

        job_id = start_job_execution_process(db=db, job_name=job_name)
        total_intch_in_units_count = get_distinct_count(data_set=interchange_in_units_df)
        if len(interchange_in_units_df) > 0:
            logger.info(f"New units interchange in: {len(interchange_in_units_df)}")
            provider_organization = get_tip_provider_organization(db=db)
            if provider_organization is None:
                raise ScalarException(message="Provider Organization is not found")
            provider_org_id = provider_organization[0]
            provider_access_token_data_sharing = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.DATA_SHARING)

            units_wout_root_org_df = interchange_in_units_df.loc[pd.isna(interchange_in_units_df['Organization_Id'])].drop_duplicates()
            units_wout_pairing_info_df = interchange_in_units_df.loc[(pd.isna(interchange_in_units_df['Asset_Id']) & pd.notnull(interchange_in_units_df['Organization_Id']))]
            units_with_root_org_asset_id_df = interchange_in_units_df.loc[pd.notnull(interchange_in_units_df['Organization_Id'])].\
                                                                            loc[pd.notnull(interchange_in_units_df['Asset_Id'])]

            units_wout_root_org_list = get_control_report_records(unit_df=units_wout_root_org_df)
            units_wout_root_org_count = get_distinct_count(data_set=units_wout_root_org_df)
            units_wout_pairing_info_list = get_control_report_records(unit_df=units_wout_pairing_info_df)
            units_wout_pairing_info_count = get_distinct_count(data_set=units_wout_pairing_info_df)

            units_by_root_orgs: dict = get_units_by_root_orgs(units_with_root_org_asset_id_df)

            for fa_root_org_id in units_by_root_orgs.keys():

                org_dict = units_by_root_orgs[fa_root_org_id]
                org_ids = list(org_dict.keys())
                sc_groups_df = get_sc_groups(db=db, fa_organization_ids= org_ids+[fa_root_org_id])

                for org_id in org_ids:
                    units = org_dict[org_id]
                    consumer_details = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)

                    if consumer_details is not None and len(consumer_details) > 0:
                        consumer_org_id = consumer_details['Organization_Id'][0]
                        ZF_customer = consumer_details['ZF_Consumer_Org'][0]
                    else:
                        org_units_df = org_dict[org_id]
                        consumer_issues_unit_list.extend(get_control_report_records(unit_df= org_units_df))
                        consumer_issues_unit_set.update(org_units_df['UnitNr'].to_list())
                        continue
                    provider_asset_ids = units['Asset_Id'].tolist()
                    datasharing_stopped_assets = list()
                    no_datasharing_assets = list()
                    # stop unpaired units data sharing
                    datasharing_stopped_assets, no_datasharing_assets, datashare_stopping_error_list = stop_datasharing(db=db, asset_ids=provider_asset_ids, consumer_org_id=consumer_org_id, access_token=provider_access_token_data_sharing)
                    if len(datashare_stopping_error_list) > 0:
                        error_list.extend(log_errors(error_list=datashare_stopping_error_list, field=ErrorFields.ORGANIZATION_ID, value=consumer_org_id))
                        logger.error(f"Error occured while stopping datasharing units, Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {datashare_stopping_error_list}")
                    
                    change_error_list = provider_asset_fleet_id_change(db=db, 
                                                            provider_assets=provider_asset_ids, 
                                                            provider_org_id=provider_org_id
                                                            )
                        
                    if len(change_error_list) > 0:
                        error_list.extend(log_errors(error_list=change_error_list, field=ErrorFields.ORGANIZATION_ID, value=org_id))
                        logger.error(f"Error occured while making Fleet Id null for provider asset, Fleetadmin Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {error_list}")
                        continue
                    datasharing_removed_unit_df = units.loc[units["Asset_Id"].isin(datasharing_stopped_assets)]
                    datasharing_removed_unit_list.extend(get_control_report_records(unit_df=datasharing_removed_unit_df))
                    datasharing_removed_unit_set.update(set(datasharing_removed_unit_df['UnitNr'].to_list()))
                    #above set is required to get distinct count as unit may belong to mutiple organizations

                    no_datasharing_unit_df = units.loc[units["Asset_Id"].isin(no_datasharing_assets)]
                    datasharing_not_exist_unit_list.extend(get_control_report_records(unit_df=no_datasharing_unit_df))
                    datasharing_not_exist_unit_set.update(set(no_datasharing_unit_df['UnitNr'].to_list()))
                    #above set is required to get distinct count as unit may belong to mutiple organizations

                    provider_access_token_teams = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.TEAMS)
                    provider_group_id = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]['Asset_Group_Id'].values[0]
                    datasharing_stopped_assets.extend(no_datasharing_assets)
                    if len(datasharing_stopped_assets) > 0:
                        unassign_error_list = unassign_assets_from_group_in_provider_org(provider_access_token=provider_access_token_teams,
                                                        provider_group_id=provider_group_id,
                                                        provider_asset_ids=datasharing_stopped_assets,
                                                        )
                        if len(unassign_error_list) > 0:
                            error_list.extend(log_errors(error_list=unassign_error_list, field=ErrorFields.ORGANIZATION_ID, value=provider_org_id))
                            logger.error(f"Error occured while removing units from tip tenancy group, Root Org Id: {fa_root_org_id}, Org Id: {org_id} and Error: {unassign_error_list}")
                            continue
                                           
                        tip_group_df = sc_groups_df.loc[(sc_groups_df['FA_Organization_Id'] == fa_root_org_id) & (sc_groups_df['SC_Organization_Id'] == provider_org_id)]
                        if len(tip_group_df) == 0:
                            error_msg = f"No Fleetconnected group record found for organization id {org_id} of root org id {fa_root_org_id} under provider org {provider_org_id}"
                            logger.error(error_msg)
                            error_list.extend(log_errors(error_list=[error_msg], field=ErrorFields.ORGANIZATION_ID, value=provider_org_id))
                            continue

                        tip_group = tip_group_df.iloc[0]
                        datasharing_removed_units_df = units.loc[units["Asset_Id"].isin(datasharing_stopped_assets)]
                        asset_nrs = datasharing_removed_units_df['Asset_Id'].tolist()
                        remove_asset_group_mapping_from_db(db=db, asset_nrs=asset_nrs, group_id=tip_group.Asset_Group_Id)

            if len(error_list) > 0:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.FAILURE)
                message = "Insight interchange in units job failed with errors"
            elif len(units_wout_root_org_list) > 0 or len(units_wout_pairing_info_list) > 0 \
                                or len(consumer_issues_unit_list) > 0:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)
                message = "Insight interchange in units job completed successfully"
            else:
                update_job_execution_process(db=db, job_id=job_id, job_status=StatusCode.SUCCESSFUL)
                message = "Insight interchange in units job completed successfully"
        else:
            message = f"No new interchange in units found with Insight additional charges since last successful job run timestamp {last_successful_execution_ts}"
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
        interchangein_unit_report = generate_interchangein_unit_report(units_wout_root_org_list=units_wout_root_org_list, 
                                                                    units_wout_pairing_info_list=units_wout_pairing_info_list, 
                                                                    consumer_issues_unit_list=consumer_issues_unit_list,
                                                                    datasharing_removed_unit_list=datasharing_removed_unit_list,
                                                                    datasharing_not_exist_unit_list=datasharing_not_exist_unit_list,
                                                                    unknown_errors=error_list)
                            
        email = Email()
        environment = os.environ['SCALAR_ENV']
        receivers = os.environ["REPORT_MAIL_DL"].split(",")
        subject = "Scalar - Insight Interchange In Units Report"
        if len(error_list)>0:
            subject = "Scalar Job Failure - Insight Interchange In Units Report"
        if os.environ['SCALAR_ENV'] != 'PROD':
            subject = f"{subject} - {environment}"
        template_name = "insight_intch_in_units.html"
        params = {
            "environment": environment,
            "job_exectution_time": job_exectution_time,
            "job_exectution_message": message,
            "total_intch_in_units_count": total_intch_in_units_count,
            "units_wout_root_org_count":units_wout_root_org_count,
            "units_wout_pairing_info_count":units_wout_pairing_info_count,
            "consumer_issues_unit_count":len(consumer_issues_unit_set),
            "datasharing_removed_unit_count":len(datasharing_removed_unit_set),
            "datasharing_not_exist_unit_count":len(datasharing_not_exist_unit_set),
            "error_list_count":len(error_list),
            "last_successful_execution_ts": last_successful_execution_ts
            }
        attachment, file_name = None, None
        if interchangein_unit_report is not None:
            interchangein_unit_report.seek(0)
            attachment = interchangein_unit_report.read()
            file_name = "insight_intch_in_units.xlsx"
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                            attachment=attachment, filename=file_name)
        logger.info("Insight interchange in mail sent successfully")