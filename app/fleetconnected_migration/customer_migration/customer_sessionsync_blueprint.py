import os
import logging
import json
import azure.functions as func
import pandas as pd
from datetime import datetime
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization, get_consumer_organization_data,\
                            get_agreement_id, get_FA_root_org_details
from app.common.helpers.session_helpers import get_new_existing_missing_sessions_data
from app.common.constants import AudienceCode

from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.fleetconnected_migration.common.tx_tango.trailer_api import TrailerApi
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_all_sessions_from_database, \
    add_new_session_data_into_db, update_existing_sessions_data_into_db, deactivate_sessions_missing_in_api,\
    get_data_sharing_details_from_scalar_db, get_subcontracted_tenancy_record
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import get_all_sessions_for_specific_org,\
     send_session_sync_report, get_subcontracting_info_from_sky

customer_sessionsync_bp = func.Blueprint() 

@customer_sessionsync_bp.function_name(name="Sync_SKY_Customer_Sessions")
@customer_sessionsync_bp.route(route="syncskycustomersessions",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customer_session_sync_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Sync_SKY_Customer_Sessions")
    db = Database()
    fc_db = FleetConnectedDatabase()
    try:
        fa_root_org_id_list = req.get_json().get('faRootOrgIds')

        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")

        env = os.environ["SCALAR_ENV"]
        app_version = os.environ["APP_VERSION"]
        tenancy_dispatcher = os.environ["TENANCY_DISPATCHER"]
        tenancy_integrator = os.environ['TENANCY_INTEGRATOR']
        tenancy_system_nr = os.environ['TENANCY_SYSTEM_NR']
        tenancy_password = os.environ['TENANCY_PASSWORD']
        trailer_api = TrailerApi(  dispatcher= tenancy_dispatcher, 
                                        integrator=tenancy_integrator,
                                        system_nr=tenancy_system_nr,
                                        password=tenancy_password,
                                        version=app_version)


        api_response = list()

        provider_organization_id = provider_organization[0]
        access_token = fetch_access_token(db=db,org_id= provider_organization_id,audience= AudienceCode.DATA_SHARING)

        for fa_root_org_id in fa_root_org_id_list:

            sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
            if sc_org_details_df is None or len(sc_org_details_df) == 0:
                continue
            sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
            
            root_org_name = get_FA_root_org_details(db=db, fa_root_org_id=fa_root_org_id)

            agreement_id = get_agreement_id(db=db, org_id=sc_org_id)
            if agreement_id is None or len(agreement_id) == 0:
                 continue
            #Session info from scalar
            all_sessions_data_from_db = get_all_sessions_from_database(db=db, sc_org_id=sc_org_id)
            logger.info(f"Total number of sessions found in the database: {len(all_sessions_data_from_db)}")
            all_sessions_for_org = get_all_sessions_for_specific_org(access_token= access_token, agreement_id=agreement_id[0], logger=logger)
            logger.info(f"Total number of sessions found in API for org id {fa_root_org_id}: {len(all_sessions_for_org)}")

            if all_sessions_for_org is not None and len(all_sessions_for_org) > 0:

                #Syncing sessions data first
                new_sessions_to_insert, sessions_to_update, sessions_to_deactivate = get_new_existing_missing_sessions_data(db_dataframe=all_sessions_data_from_db, api_dataframe=all_sessions_for_org, logger=logger)
                logger.info(f"New sessions to be inserted: {len(new_sessions_to_insert)}")
                logger.info(f"Existing sessions to be updated: {len(sessions_to_update)}")
                logger.info(f"Missing sessions to be deactivated: {len(sessions_to_deactivate)}")
                if len(new_sessions_to_insert) > 0:
                    add_new_session_data_into_db(db=db, new_sessions_to_insert=new_sessions_to_insert)
                if len(sessions_to_update) > 0:
                    update_existing_sessions_data_into_db(db=db, sessions_to_update=sessions_to_update)
                if len(sessions_to_deactivate) > 0:
                    deactivate_sessions_missing_in_api(db=db, sessions_to_deactivate= sessions_to_deactivate)

                #Retrieving and comparing data sharing between scalar and fc
                current_total_data_sharing_in_scalar = get_data_sharing_details_from_scalar_db(db=db, sc_org_id=sc_org_id)
                current_total_data_sharing_in_scalar = pd.merge(current_total_data_sharing_in_scalar, all_sessions_for_org[['Session_Id','SC_License_Plate']], on="Session_Id", how="outer")
                current_total_data_sharing_in_scalar["unit_nr"] = current_total_data_sharing_in_scalar["unit_nr"].astype(pd.Int64Dtype()).astype(str).replace('<NA>', pd.NA)
                current_active_data_sharing_in_scalar = current_total_data_sharing_in_scalar.loc[current_total_data_sharing_in_scalar['Status'].isin(['running', 'pending'])]

                #Subcontracting details from fleetconnected API
                subcontracting_tenancy_record = get_subcontracted_tenancy_record(fc_db=fc_db, root_org_id=fa_root_org_id)
                if subcontracting_tenancy_record is None or len(subcontracting_tenancy_record) == 0:
                    raise Exception(f"Subcontracted tenancy details not found.")
                company_id = subcontracting_tenancy_record[0]
                
                if subcontracting_tenancy_record[4] == 1:

                    params={"environment": env, 
                            "exectution_time": datetime.now(), 
                            "root_organization_id":fa_root_org_id,
                            "root_organization_name": root_org_name,
                            "zf_consumer_flag": 'Yes',
                            "new_sessions_added":len(new_sessions_to_insert),
                            "existing_sessions_updated":len(sessions_to_update),
                            "deactivated_sessions": len(sessions_to_deactivate),
                            "current_total_data_sharing_in_scalar": len(all_sessions_for_org),
                            "current_active_data_sharing_in_scalar": len(current_active_data_sharing_in_scalar),
                            "current_active_data_sharing_in_sky": 'NA',
                            "matched_data_sharing_in_sky_and_scalar": 'NA',
                            "missing_data_sharing_in_scalar": 'NA',
                            "missing_data_sharing_in_sky": 'NA'
                            }
                    send_session_sync_report(org_name=root_org_name,
                    current_total_data_sharing_in_scalar = current_total_data_sharing_in_scalar,
                    current_active_data_sharing_in_scalar = current_active_data_sharing_in_scalar,
                    current_active_data_sharing_in_sky=[],
                    matched_data_sharing_in_sky_and_scalar=[],
                    missing_data_sharing_in_scalar=[],
                    missing_data_sharing_in_sky=[],
                                        params=params)

                else:

                    active_subcontracting_info_from_sky=get_subcontracting_info_from_sky(trailer_api=trailer_api, company_id=company_id, logger=logger)

                    if active_subcontracting_info_from_sky is None:
                        raise Exception(f"SKY subcontracting details not found.")

                    full_data_sharing_sky_scalar_df = pd.merge(current_active_data_sharing_in_scalar, active_subcontracting_info_from_sky, on="unit_nr", how="outer")

                    matched_data_sharing_in_sky_and_scalar = full_data_sharing_sky_scalar_df.loc[\
                                    full_data_sharing_sky_scalar_df['Provider_Asset_ID'].notna() &\
                                        full_data_sharing_sky_scalar_df["unit_nr"].notna() & full_data_sharing_sky_scalar_df['transics_trailer_id'].notna()&\
                                            full_data_sharing_sky_scalar_df['Session_Id'].notna()]

                    matched_unit_nrs = matched_data_sharing_in_sky_and_scalar["unit_nr"].to_list()
                    missing_unit_nrs_in_scalar = set(active_subcontracting_info_from_sky["unit_nr"].to_list()).difference(matched_unit_nrs)
                    missing_unit_nrs_in_sky = set(current_active_data_sharing_in_scalar["unit_nr"].to_list()).difference(matched_unit_nrs)
                    
                    missing_data_sharing_in_scalar = full_data_sharing_sky_scalar_df.loc[full_data_sharing_sky_scalar_df['unit_nr'].isin(\
                                                    missing_unit_nrs_in_scalar)].drop(columns=current_active_data_sharing_in_scalar.columns.to_list())

                    missing_data_sharing_in_sky = full_data_sharing_sky_scalar_df.loc[full_data_sharing_sky_scalar_df['unit_nr'].isin(\
                                            missing_unit_nrs_in_sky)].drop(columns=active_subcontracting_info_from_sky.columns.to_list())
                    
                    params={"environment": env, 
                            "exectution_time": datetime.now(), 
                            "root_organization_id":fa_root_org_id,
                            "root_organization_name": root_org_name,
                            "zf_consumer_flag": 'No',
                            "new_sessions_added":len(new_sessions_to_insert),
                            "existing_sessions_updated":len(sessions_to_update),
                            "deactivated_sessions": len(sessions_to_deactivate),
                            "current_total_data_sharing_in_scalar": len(all_sessions_for_org),
                            "current_active_data_sharing_in_scalar": len(current_active_data_sharing_in_scalar),
                            "current_active_data_sharing_in_sky": len(active_subcontracting_info_from_sky),
                            "matched_data_sharing_in_sky_and_scalar": len(matched_data_sharing_in_sky_and_scalar),
                            "missing_data_sharing_in_scalar": abs(len(active_subcontracting_info_from_sky) - len(matched_data_sharing_in_sky_and_scalar)),
                            "missing_data_sharing_in_sky":abs(len(current_active_data_sharing_in_scalar) - len(matched_data_sharing_in_sky_and_scalar))
                            }

                    send_session_sync_report(org_name=root_org_name,
                    current_total_data_sharing_in_scalar = current_total_data_sharing_in_scalar,
                    current_active_data_sharing_in_scalar = current_active_data_sharing_in_scalar,
                    current_active_data_sharing_in_sky=active_subcontracting_info_from_sky,
                    matched_data_sharing_in_sky_and_scalar=matched_data_sharing_in_sky_and_scalar, 
                                        missing_data_sharing_in_scalar=missing_data_sharing_in_scalar, 
                                        missing_data_sharing_in_sky=missing_data_sharing_in_sky,
                                        params=params)

                api_response.append(params)
            else:
                message = f"No sessions found to sync for Root Organization {fa_root_org_id}"
                logger.info(message)
                params={"environment": env, 
                        "exectution_time": datetime.now(), 
                        "root_organization_id":fa_root_org_id,
                        "root_organization_name": root_org_name,
                        "zf_consumer_flag": 'Unknown',
                        "new_sessions_added":0,
                        "existing_sessions_updated":0,
                        "deactivated_sessions": 0,
                        "current_total_data_sharing_in_scalar": 0,
                        "current_active_data_sharing_in_scalar": 0,
                        "current_active_data_sharing_in_sky": 0,
                        "matched_data_sharing_in_sky_and_scalar": 0,
                        "missing_data_sharing_in_scalar":0,
                        "missing_data_sharing_in_sky":0
                        }

                api_response.append(params)

                email = Email()
                env = os.environ['SCALAR_ENV']
                receivers=os.environ['MIGRATION_REPORT_MAIL_DL']
                receivers = receivers.split(",")
                subject = f"Scalar Migration - Customer session sync report for {root_org_name[:36]} - "+env
                template_name = f'customer_sessionsync_report.html'

                email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=params)

        return func.HttpResponse(
        json.dumps(api_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)

    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject=f"Scalar Migration - Error report for {root_org_name[:36]} - " + env
        template_name='error_session_email.html'

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )
