

import os

from app.common.constants import ContentType, ResponseCode
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token, get_all_data
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
import logging
from datetime import datetime
from app.common.email import Email
from io import BytesIO
from app.common.models import Response
from app.common.scalar_api.framework_api import get_all_framework_agreements
import pandas as pd
from sqlalchemy import text

getallframeworkagreement_bp = func.Blueprint()

@getallframeworkagreement_bp.function_name(name="Get_All_Framework_Agreement")
@getallframeworkagreement_bp.route(route="getallframeworkagreement",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customeronboardingpostsync_api(req: func.HttpRequest) -> func.HttpResponse:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Get_All_Framework_Agreement")
    db = Database()
    provider_org_id = get_tip_provider_organization(db=db)
    provider_org_id = provider_org_id[0]    
    access_token = fetch_access_token(db=db,org_id=provider_org_id,audience="DASAPI")
    all_frameworks_df = get_all_data(access_token=access_token,func=get_all_framework_agreements)
    all_frameworks_df = all_frameworks_df[['agreementId', 'agreementName','consumerOrgId','consumerOrgName','createdOn']]
    all_frameworks_df['consumerOrgName'] = all_frameworks_df['consumerOrgName'].str.replace(r'^.*_', '', regex=True)
    select_statement = text('''
                            SELECT Organization_Name consumerOrgName,Organization_Id FA_Root_Organization_Id
                            FROM FA_Organization (NOLOCK) WHERE Active = 1  AND Root_Organization_Id IS NULL                        
                        ''')
    all_fa_organization_df = db.query(statement=select_statement, as_dataframe=True)
    # all_frameworks_df = all_frameworks_df.merge(all_fa_organization_df[['Organization_Name']], left_on='consumerOrgName', right_on='Organization_Name', how='left')
    all_frameworks_df = pd.merge(all_frameworks_df,all_fa_organization_df, on ='consumerOrgName', how='left')
    all_frameworks_df = all_frameworks_df.sort_values(by='createdOn', ascending=False)
    if len(all_frameworks_df)>0:
        email = Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject = f"Scalar - All framework Agreement Details " + env
        template_name='all_framework_agreement_details_report.html'
        params={"environment": env, 
        "execution_time": datetime.now(),
        "total_framework_agreements" : len(all_frameworks_df)
        }

        file_name = f"Framework_Agreements_Details_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        sub_control_report = BytesIO()
        with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
            if len(all_frameworks_df) > 0:
                all_frameworks_df.to_excel(writer, sheet_name="Framework_Agreements", index=None, header=True)
        attachment = None
        file_name = f"{file_name}.xlsx"
        if sub_control_report is not None:
            sub_control_report.seek(0)
            attachment = sub_control_report.read()

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,attachment=attachment,filename=file_name,params=params)
    
    response = Response(status=True, message="All Framework aggreement report sent successfully!")
    return func.HttpResponse(
        response.getJsonResponse(),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)
