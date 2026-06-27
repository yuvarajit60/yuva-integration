import os
from sqlalchemy import text
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.helpers.asset_group_helper import fetch_all_assets_and_groups_from_api
from app.common.models import Response
import logging
import pandas as pd
import io
from datetime import datetime

from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_assinged_assets_for_report

fetchassetsfromassetgroup_bp = func.Blueprint()

@fetchassetsfromassetgroup_bp.function_name(name="Fetch_Assets_From_Asset_Group")
@fetchassetsfromassetgroup_bp.route(route="fetchassetsfromassetgroup", methods=[func.HttpMethod.POST])
@global_exception_handler
def fetchassetsfromassetgroup_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("fetch_assets_from_asset_group")
    db = Database()

    try:
        # Get all active organizations that have a FA root org mapping
        org_query = text('''
            SELECT Organization_Id, Organization_Name, FA_Root_Organization_Id
            FROM SCALAR.SC_Organization (NOLOCK)
            WHERE FA_Root_Organization_Id IS NOT NULL AND Active = 1
        ''')
        sc_org_df = db.query(statement=org_query, as_dataframe=True)

        if sc_org_df.empty:
            response = Response(status=False, message="No organizations found.")
            return func.HttpResponse(
                response.getJsonResponse(),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON
            )

        all_report_rows = []

        for _, sc_org in sc_org_df.iterrows():
            consumer_org_id = sc_org["Organization_Id"]
            org_name = sc_org["Organization_Name"]
            fa_root_org_id = sc_org["FA_Root_Organization_Id"]

            logger.info(f"Processing organization: {org_name} ({consumer_org_id})")

            # Fetch API asset-group data
            try:
                api_df = fetch_all_assets_and_groups_from_api(db=db, org_id=consumer_org_id)
            except Exception as e:
                logger.warning(f"API fetch failed for org {org_name}: {e}")
                api_df = pd.DataFrame(columns=["assetId", "groupIds"])

            # Fetch DB asset-group data
            try:
                db_df = get_assinged_assets_for_report(db=db, sc_org_id=consumer_org_id, fa_root_org_id=fa_root_org_id)
            except Exception as e:
                logger.warning(f"DB fetch failed for org {org_name}: {e}")
                db_df = pd.DataFrame()

            # Summarise API: count distinct assets per asset group
            if not api_df.empty:
                api_summary = (
                    api_df.groupby("groupIds")["assetId"]
                    .nunique()
                    .reset_index()
                    .rename(columns={"groupIds": "Asset_Group_Id", "assetId": "API_Asset_Count"})
                )
            else:
                api_summary = pd.DataFrame(columns=["Asset_Group_Id", "API_Asset_Count"])

            # Summarise DB: count distinct assets per asset group, keep name and org name
            if not db_df.empty:
                db_summary = (
                    db_df.groupby(["Asset_Group_Id", "Asset_Group_Name", "Scalar_Organization_Name"])["Scalar_Asset_Id"]
                    .nunique()
                    .reset_index()
                    .rename(columns={"Scalar_Organization_Name": "Organization_Name", "Scalar_Asset_Id": "DB_Asset_Count"})
                )
            else:
                db_summary = pd.DataFrame(columns=["Asset_Group_Id", "Asset_Group_Name", "Organization_Name", "DB_Asset_Count"])

            # Merge API and DB on Asset_Group_Id (outer join captures groups missing from either side)
            merged = pd.merge(api_summary, db_summary, on="Asset_Group_Id", how="outer")
            merged["Organization_Name"] = merged["Organization_Name"].fillna(org_name)
            merged["API_Asset_Count"] = merged["API_Asset_Count"].fillna(0).astype(int)
            merged["DB_Asset_Count"] = merged["DB_Asset_Count"].fillna(0).astype(int)
            merged["Asset_Group_Name"] = merged["Asset_Group_Name"].fillna("Unknown")

            all_report_rows.append(merged[["Organization_Name", "Asset_Group_Id", "Asset_Group_Name", "API_Asset_Count", "DB_Asset_Count"]])

        if not all_report_rows:
            response = Response(status=False, message="No asset group data found across all organizations.")
            return func.HttpResponse(
                response.getJsonResponse(),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON
            )

        # Combine all organizations and sort
        report_df = pd.concat(all_report_rows, ignore_index=True)
        report_df = report_df.sort_values(["Organization_Name", "Asset_Group_Name"]).reset_index(drop=True)

        # Build Excel report
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            worksheet = workbook.add_worksheet("Asset Group Report")

            # Formats
            header_fmt = workbook.add_format({
                "bold": True, "bg_color": "#1F4E79", "font_color": "#FFFFFF",
                "border": 1, "align": "center", "valign": "vcenter"
            })
            match_fmt = workbook.add_format({"bg_color": "#C6EFCE", "border": 1, "align": "center"})
            mismatch_fmt = workbook.add_format({"bg_color": "#FFC7CE", "border": 1, "align": "center"})
            text_fmt = workbook.add_format({"border": 1})

            # Column widths
            worksheet.set_column(0, 0, 35)
            worksheet.set_column(1, 1, 38)
            worksheet.set_column(2, 2, 30)
            worksheet.set_column(3, 3, 30)
            worksheet.set_row(0, 20)

            # Headers
            headers = [
                "Organization Name",
                "Asset Group Name",
                "Total Assigned Assets (API)",
                "Total Assigned Assets (DB)"
            ]
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_fmt)

            # Data rows
            for row_idx, row in report_df.iterrows():
                excel_row = row_idx + 1
                api_count = int(row["API_Asset_Count"])
                db_count = int(row["DB_Asset_Count"])
                count_fmt = match_fmt if api_count == db_count else mismatch_fmt

                worksheet.write(excel_row, 0, row["Organization_Name"], text_fmt)
                worksheet.write(excel_row, 1, row["Asset_Group_Name"], text_fmt)
                worksheet.write(excel_row, 2, api_count, count_fmt)
                worksheet.write(excel_row, 3, db_count, count_fmt)

            worksheet.freeze_panes(1, 0)

        excel_bytes = output.getvalue()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Asset_Group_Report_{timestamp}.xlsx"

        logger.info(f"Report generated: {len(report_df)} rows, {len(sc_org_df)} organizations")

        # Send success email with Excel report attached
        env = os.environ['SCALAR_ENV']
        receivers = os.environ["REPORT_MAIL_DL"].split(",")
        subject = f"Scalar - Asset Group vs API Comparison Report"
        if env != 'PROD':
            subject = f"{subject} - {env}"

        email_params = {
            "environment": env,
            "execution_time": datetime.now(),
            "total_organizations": len(sc_org_df),
            "total_rows": len(report_df)
        }
        email = Email()
        email.send_email(
            receivers=receivers,
            subject=subject,
            template_name="fetch_assets_group_report_email.html",
            params=email_params,
            attachment=excel_bytes,
            filename=filename
        )
        logger.info("Report email sent successfully.")

        response = Response(status=True, message=f"Report generated for {len(sc_org_df)} organization(s) with {len(report_df)} row(s). Email sent to {', '.join(receivers)}.")
        return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        status_code = getattr(e, 'status_code', 500)

        env = os.environ['SCALAR_ENV']
        receivers = os.environ["REPORT_MAIL_DL"].split(",")
        subject = f"Scalar - Asset Group Report Error"
        if env != 'PROD':
            subject = f"{subject} - {env}"

        error_params = {
            "environment": env,
            "execution_time": datetime.now(),
            "error_message": repr(e)
        }
        try:
            email = Email()
            email.send_email(
                receivers=receivers,
                subject=subject,
                template_name="fetch_assets_group_report_error_email.html",
                params=error_params
            )
        except Exception as email_err:
            logger.error(f"Failed to send error email: {email_err}")

        return func.HttpResponse(
            body=repr(e),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )
