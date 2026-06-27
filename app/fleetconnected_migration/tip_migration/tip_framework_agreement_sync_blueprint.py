from datetime import datetime
from io import BytesIO
import json
import logging
import os
import azure.functions as func
import pandas as pd

from app.common.constants import AudienceCode, ContentType, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token
from app.common.models import Response
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_all_agreements_organizations_integrators_db
from app.fleetconnected_migration.tip_migration.fc_tip_migration_service import get_all_framework_agreements_api, sync_frameworks_data


tip_frameworkagreement_sync_bp = func.Blueprint()
@tip_frameworkagreement_sync_bp.function_name(name="Sync_Framework_Agreement")
@tip_frameworkagreement_sync_bp.route(route="syncframeworkagreement", methods=[func.HttpMethod.POST])
@global_exception_handler
def framework_agreement_sync(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger = logging.getLogger("sync_framework_agreement")
        db = Database()
        errors = {}
        provider_org_id = get_tip_provider_organization(db=db)[0]
        access_token = fetch_access_token(db=db, org_id=provider_org_id, audience=AudienceCode.DATA_SHARING)
        framework_agreements_api_df = get_all_framework_agreements_api(provider_org_id=provider_org_id,access_token=access_token,logger=logger)
        framework_agreements_db_df = get_all_agreements_organizations_integrators_db(db=db)
        consolidated_frameworks_df, orgs_without_sso_df, missing_integrators_df, errors = sync_frameworks_data(db=db,
                                                                            access_token=access_token,
                                                                            framework_api_data=framework_agreements_api_df,
                                                                            framework_db_data=framework_agreements_db_df
                                                                            )
    except Exception as e:
        logger.error(e, exc_info=True)
        errors['Unknown Error'] = str(e)
        consolidated_frameworks_df=framework_agreements_db_df=orgs_without_sso_df=missing_integrators_df=pd.DataFrame()
        response = Response(message=e, status=False)
        return func.HttpResponse(
            json.dumps(response, default=str),
            status_code=ResponseCode.INTERNAL_ERROR,
            mimetype=ContentType.APPLICATION_JSON)
    finally:
        tip_framework_sync_report = BytesIO()
        with pd.ExcelWriter(tip_framework_sync_report, engine='xlsxwriter') as writer:
            if len(consolidated_frameworks_df) > 0:
                column_order = ['agreementId','agreementName','dataSharingType','description','subjectType','assetType','status','providerOrgId','providerOrgName','consumerOrgId','consumerOrgName','org_isSSOEnabled','org_active','FA_Root_Organization_Id','profileId','createIntegrator','name','clientId','secretId','ownerReceivingOrg','isExistingCustomer','payer','consumerPrimaryEmail','consumerPrimaryLastName','consumerPrimaryFirstName','allowFurtherSharing','multiShareMode','sessionContractMode','rejectedReason','stoppedOn','stoppedBy','approvedOrRejectedOn','approvedOrRejectedBy']
                consolidated_frameworks_df[column_order].to_excel(writer, sheet_name='All Frameworks', index=None, header=True)
            if len(errors) > 0:
                pd.DataFrame(errors.items(), columns=['Error Framework Id','Error Description']).to_excel(writer, sheet_name='Errors', index=None, header=True)
            
        email = Email()
        receivers = os.environ['MIGRATION_REPORT_MAIL_DL'].split(",")
        env = os.environ['SCALAR_ENV']
        file_name = f"TIP_Framework_Sync_Report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        subject = f"Scalar - Data Sync: Framework Agreement Sync Report -" + env
        template_name = "agreement_data_sync_report.html"
        
        agreementsync_response = {
            "total_framework_agreements_db":len(framework_agreements_db_df),
            "total_framework_agreements_api":len(consolidated_frameworks_df),
            "orgs_without_sso":len(orgs_without_sso_df),
            "missing_integrator_details":len(missing_integrators_df),
            "errors":len(errors)
        }
        agreementsync_response["environment"] = os.environ['SCALAR_ENV']
        agreementsync_response["exectution_time"] = datetime.now()
        attachment = None
        file_name = f"{file_name} - {datetime.now().strftime('%Y-%m-%d')}.xlsx"
        if tip_framework_sync_report is not None:
            tip_framework_sync_report.seek(0)
            attachment = tip_framework_sync_report.read()
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=agreementsync_response, 
                            attachment=attachment, filename=file_name)
        
        return func.HttpResponse(
            json.dumps(agreementsync_response, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)