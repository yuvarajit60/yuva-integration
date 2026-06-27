from io import BytesIO
import logging
import json
import azure.functions as func
import pandas as pd
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.helpers.datasharing_helper import get_data_sharing_session
from app.common.models import Response
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_all_organizations, get_cust_org_detail, get_tip_provider_organization
from app.common.constants import AudienceCode
from app.common.helpers.datasharing_helper import add_or_update_subcontring_summary, send_control_report

session_control_bp = func.Blueprint() 


@session_control_bp.function_name(name="Get_DataSharing_Control_Reports")
@session_control_bp.route(route="units/datasharing/controlreport",  methods=[func.HttpMethod.GET])
@global_exception_handler
def datasharing_session_control_report(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Get_DataSharing_Control_Reports")
    db = Database()
    org_id = req.params.get('orgId')
    logger.info(f"Organization Id: {org_id}")

    excel_report_mail_id = req.params.get('excelReportMailId')
    logger.info(f"Excel Report: {excel_report_mail_id}")

    if org_id is not None and len(org_id.strip()) == 0:
        logger.error("Organization Id is mandatory")
        response = Response(False, "Organization Id is mandatory")
        return func.HttpResponse(response.getJsonResponse(), 
                                status_code=ResponseCode.BAD_REQUEST,
                                mimetype=ContentType.APPLICATION_JSON)
    elif org_id is not None:
        scalar_org_name = get_cust_org_detail(db=db,consumer_org_id=org_id)['Organization_Name'][0]
        organizations = [{"Organization_Id": org_id, "Organization_Name": scalar_org_name}]
    else:
        organizations = get_all_organizations(db=db)

    for organization in organizations:
        single_org_id = organization["Organization_Id"]
        provider_org_id = get_tip_provider_organization(db=db)
        access_token = fetch_access_token(db=db, org_id=provider_org_id[0], audience=AudienceCode.DATA_SHARING)
        consolidated_insight_units_df = get_data_sharing_session(db=db, access_token= access_token, cust_org_id=single_org_id, logger=logger)

        if consolidated_insight_units_df is None:
            logger.error("Organization doesn't exists")
            response = Response(False, "Organization doesn't exists")
            return func.HttpResponse(response.getJsonResponse(), 
                                    status_code=ResponseCode.BAD_REQUEST,
                                    mimetype=ContentType.APPLICATION_JSON)

        # Non Insight units
        non_insight_units_df = consolidated_insight_units_df.loc[consolidated_insight_units_df["insight_unit"] != "True"]
        # Non insight units but data shared
        non_insight_datashared_units_df = non_insight_units_df.loc[((non_insight_units_df["insight_unit"] == "False") & (non_insight_units_df["data_sharing"] == "True"))]
        # Wrong unit data shared (units which don't belong to customer but still data sharing)
        wrong_datashared_units_df = non_insight_units_df.loc[((pd.isnull(non_insight_units_df["insight_unit"])) & (non_insight_units_df["data_sharing"] == "True"))]
        
        insight_units_df = consolidated_insight_units_df.loc[(consolidated_insight_units_df["insight_unit"] == "True")]
        # Insight units non paired
        insight_non_paired_units_df = insight_units_df.loc[pd.isnull(insight_units_df["Asset_Id"])]
        # Insight units non linked combi
        insight_non_fc_org_units_df = insight_units_df.loc[pd.isnull(insight_units_df["linked_customer_combi_number"])]
        # Insight units with manually started data sharing (either non paired or non linked combi)
        insight_manual_session_units_df = insight_units_df.loc[((insight_units_df["data_sharing"] == "True") & ((pd.isnull(insight_units_df["linked_customer_combi_number"])) | (pd.isnull(insight_units_df["Asset_Id"]))))]
        # Insight units with missing data sharing session
        insight_missing_session_units_df = insight_units_df.loc[((pd.isnull(insight_units_df["data_sharing"])) & (pd.notnull(insight_units_df["linked_customer_combi_number"])) & (pd.notnull(insight_units_df["Asset_Id"])))]
        # Inisght units with paired, linked combi and data shared session
        insight_datashared_units_df = insight_units_df.loc[((pd.notnull(insight_units_df["data_sharing"])) & (pd.notnull(insight_units_df["Asset_Id"])) & (pd.notnull(insight_units_df["linked_customer_combi_number"])))]

        params = {
            "recipient": excel_report_mail_id,
            "organization_id": single_org_id,
            "organization_name": organization["Organization_Name"],
            "insight_units_count": len(insight_units_df),
            "insight_datashared_units_count": len(insight_datashared_units_df),
            "insight_non_paired_units_count": len(insight_non_paired_units_df),
            "insight_non_fc_org_units_count": len(insight_non_fc_org_units_df),
            "insight_manual_session_units_count": len(insight_manual_session_units_df),
            "insight_missing_session_units_count": len(insight_missing_session_units_df),
            "non_insight_units_count": len(non_insight_units_df),
            "non_insight_datashared_units_count": len(non_insight_datashared_units_df),
            "wrong_datashared_units_count": len(wrong_datashared_units_df)
        }

        add_or_update_subcontring_summary(db=db, params=params)

    if org_id is not None and excel_report_mail_id is not None:
        sub_control_report = BytesIO()
        with pd.ExcelWriter(sub_control_report, engine='xlsxwriter') as writer:
            if len(consolidated_insight_units_df) > 0:
                consolidated_insight_units_df.to_excel(writer, sheet_name='Full Control Report', index=None, header=True)
            if len(insight_units_df) > 0:
                insight_units_df.to_excel(writer, sheet_name='Insight Units', index=None, header=True)
            if len(insight_datashared_units_df) > 0:
                insight_datashared_units_df.to_excel(writer, sheet_name='Insight Datashared Units', index=None, header=True)
            if len(insight_non_paired_units_df) > 0:
                insight_non_paired_units_df.to_excel(writer, sheet_name='Insight Non Paired Units', index=None, header=True)
            if len(insight_non_fc_org_units_df) > 0:
                insight_non_fc_org_units_df.to_excel(writer, sheet_name='Insight Non-FC Org Units', index=None, header=True)
            if len(insight_manual_session_units_df) > 0:
                insight_manual_session_units_df.to_excel(writer, sheet_name='Insight Manual Session Units', index=None, header=True)
            if len(insight_missing_session_units_df) > 0:
                insight_missing_session_units_df.to_excel(writer, sheet_name='Insight Missing Session Units', index=None, header=True)
            if len(non_insight_units_df) > 0:
                non_insight_units_df.to_excel(writer, sheet_name='Non Insight Units', index=None, header=True)
            if len(non_insight_datashared_units_df) > 0:
                non_insight_datashared_units_df.to_excel(writer, sheet_name='Non Insight Datashared Units', index=None, header=True)
            if len(wrong_datashared_units_df) > 0:
                wrong_datashared_units_df.to_excel(writer, sheet_name='Wrong Datashared Units', index=None, header=True)
        
        send_control_report(sub_control_report=sub_control_report, params=params)
        
    return func.HttpResponse(
        json.dumps(params, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)