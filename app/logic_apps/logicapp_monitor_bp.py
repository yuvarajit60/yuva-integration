import os
import json
import logging
import datetime
import requests
import msal
import anthropic
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import azure.functions as func

logicapp_monitor_bp = func.Blueprint()

logger = logging.getLogger("logicapp_monitor")

SUBSCRIPTION_ID = "9cdd2afb-3b70-4069-808d-fe9f81f92445"
RESOURCE_GROUP = "YuvaTestGroup"
LOGIC_APP_NAME = "Yuva-Dev-DataSync"
WORKFLOW_NAME = "wf_dev_DataSync"
APP_INSIGHTS_APP_ID = "f8cc5070-01f2-43b2-86c3-8b20e5bc52e5"

MGMT_SCOPE = "https://management.azure.com/.default"
APP_INSIGHTS_SCOPE = "https://api.applicationinsights.io/.default"

ACTION_TO_FILES = {
    "HTTP_Webhook-Asset_Data_Sync": [
        "app/logic_apps/datasync_durable/datasync_orchestrator_bp.py",
        "app/logic_apps/datasync_durable/datasync_activities_bp.py",
    ],
    "HTTP_Webhook-Session_Data_Sync": [
        "app/logic_apps/datasync_durable/datasync_orchestrator_bp.py",
        "app/logic_apps/datasync_durable/datasync_activities_bp.py",
    ],
    "HTTP_Webhook-Brake_Performance_Data_Sync": [
        "app/logic_apps/datasync_durable/datasync_orchestrator_bp.py",
        "app/logic_apps/datasync_durable/datasync_activities_bp.py",
    ],
    "HTTP_Webhook_-_user_data_sync": [
        "app/logic_apps/datasync_durable/datasync_orchestrator_bp.py",
        "app/logic_apps/datasync_durable/datasync_activities_bp.py",
    ],
    "Call_an_Azure_function_Auto_Pairing_Report": [
        "app/assets/auto_pairing_report/auto_pairing_report_blueprint.py",
        "app/assets/auto_pairing_report/auto_pairing_report_services.py",
        "app/assets/auto_pairing_report/auto_pairing_report_data_access.py",
    ],
    "Call_an_Azure_function_Interchanging_In_Units": [
        "app/data_sharing/interchange_in_units/interchange_in_units_blueprint.py",
        "app/data_sharing/interchange_in_units/interchange_in_units_services.py",
        "app/data_sharing/interchange_in_units/interchange_in_units_data_access.py",
    ],
    "Call_an_Azure_function_Interchanging_Out_Units": [
        "app/data_sharing/interchange_out_units/interchange_out_units_blueprint.py",
        "app/data_sharing/interchange_out_units/interchange_out_units_services.py",
        "app/data_sharing/interchange_out_units/interchange_out_units_data_access.py",
    ],
    "Call_an_Azure_function_Copy_Move_Along_Units": [
        "app/data_sharing/copy_move_along_units/copy_move_along_blueprint.py",
        "app/data_sharing/copy_move_along_units/copy_move_along_services.py",
        "app/data_sharing/copy_move_along_units/copy_move_along_data_access.py",
    ],
    "Call_an_Azure_function_New_Pairing_Insight_Units": [
        "app/data_sharing/new_pairing_insight_units/new_pairing_blueprint.py",
        "app/data_sharing/new_pairing_insight_units/new_pairing_services.py",
        "app/data_sharing/new_pairing_insight_units/new_pairing_data_access.py",
    ],
    "Call_an_Azure_function_Activate_brake_performance": [
        "app/brake_performance/brake_performance_activate/brake_performance_activate_blueprint.py",
        "app/brake_performance/brake_performance_activate/brake_performance_activate_services.py",
        "app/brake_performance/brake_performance_activate/brake_performance_activate_data_access.py",
    ],
    "Call_an_Azure_function_deactivate_brake_performance": [
        "app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_blueprint.py",
        "app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_services.py",
        "app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_data_access.py",
    ],
}

# Resolves to the project root regardless of where the function is deployed
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_msal_token(scope: str) -> str:
    authority = f"https://login.microsoftonline.com/{os.environ['TENANT_ID']}"
    app = msal.ConfidentialClientApplication(
        os.environ["CLIENT_ID"],
        client_credential=os.environ["CLIENT_SECRET"],
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=[scope])
    if "access_token" not in result:
        raise RuntimeError(f"MSAL token acquisition failed: {result.get('error_description', result)}")
    return result["access_token"]


def _get_latest_run(mgmt_token: str) -> dict:
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Web/sites/{LOGIC_APP_NAME}"
        f"/hostruntime/runtime/webhooks/workflow/api/management/workflows/{WORKFLOW_NAME}"
        f"/runs?api-version=2022-03-01&$top=1"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {mgmt_token}"}, timeout=30)
    resp.raise_for_status()
    runs = resp.json().get("value", [])
    return runs[0] if runs else {}


def _get_run_actions(mgmt_token: str, run_name: str) -> list:
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Web/sites/{LOGIC_APP_NAME}"
        f"/hostruntime/runtime/webhooks/workflow/api/management/workflows/{WORKFLOW_NAME}"
        f"/runs/{run_name}/actions?api-version=2022-03-01"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {mgmt_token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def _query_app_insights(ai_token: str, query: str) -> list:
    url = f"https://api.applicationinsights.io/v1/apps/{APP_INSIGHTS_APP_ID}/query"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {ai_token}", "Content-Type": "application/json"},
        json={"query": query},
        timeout=30,
    )
    if not resp.ok:
        logger.warning(f"App Insights query failed ({resp.status_code}): {resp.text[:300]}")
        return []
    tables = resp.json().get("tables", [])
    if not tables:
        return []
    cols = [c["name"] for c in tables[0]["columns"]]
    return [dict(zip(cols, row)) for row in tables[0]["rows"]]


def _read_source_files(file_paths: list) -> dict:
    contents = {}
    for rel_path in file_paths:
        abs_path = os.path.join(PROJECT_ROOT, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                contents[rel_path] = f.read()
        except Exception as exc:
            contents[rel_path] = f"[Could not read: {exc}]"
    return contents


def _read_agent_instructions() -> str:
    path = os.path.join(PROJECT_ROOT, "agents", "logicapp", "CLAUDE.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _call_claude(system_prompt: str, user_message: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        message = stream.get_final_message()
    return "\n".join(
        block.text for block in message.content if hasattr(block, "text") and block.text
    )


def _build_html_email(run: dict, failed_actions: list, diagnosis: str) -> str:
    props = run.get("properties", {})
    run_name = run.get("name", "Unknown")
    status = props.get("status", "Unknown")
    start_time = props.get("startTime", "Unknown")
    end_time = props.get("endTime", "Unknown")
    failed_names = ", ".join(a["name"] for a in failed_actions) or "Unknown"
    safe_diagnosis = (
        diagnosis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;color:#333;">
  <h2 style="color:#c0392b;">Logic App Workflow Failure Report</h2>
  <h3>Summary</h3>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
    <tr><td><b>Logic App</b></td><td>{LOGIC_APP_NAME}</td></tr>
    <tr><td><b>Workflow</b></td><td>{WORKFLOW_NAME}</td></tr>
    <tr><td><b>Run ID</b></td><td>{run_name}</td></tr>
    <tr><td><b>Status</b></td><td style="color:#c0392b;"><b>{status}</b></td></tr>
    <tr><td><b>Start Time</b></td><td>{start_time}</td></tr>
    <tr><td><b>End Time</b></td><td>{end_time}</td></tr>
    <tr><td><b>Failed Actions</b></td><td>{failed_names}</td></tr>
  </table>
  <h3>Diagnosis &amp; Suggested Fix</h3>
  <pre style="background:#f4f4f4;padding:16px;border-radius:4px;white-space:pre-wrap;word-wrap:break-word;font-size:13px;">{safe_diagnosis}</pre>
  <hr/>
  <p style="font-size:11px;color:#999;">Generated by LogicApp Monitor &mdash; {generated_at}</p>
</body>
</html>"""


def _send_email(subject: str, html_body: str):
    message = Mail(
        from_email=os.environ.get("FC_EMAIL_ID", "yuvaraj-periyasamy@outlook.com"),
        to_emails=os.environ.get("REPORT_MAIL_DL", "yuvarajit60@gmail.com"),
        subject=subject,
        html_content=html_body,
    )
    SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(message)


@logicapp_monitor_bp.function_name(name="LogicApp_Monitor")
@logicapp_monitor_bp.timer_trigger(arg_name="timer", schedule="0 0 8 * * *", run_on_startup=False)
def logicapp_monitor(timer: func.TimerRequest) -> None:
    logger.info("LogicApp_Monitor triggered")

    try:
        mgmt_token = _get_msal_token(MGMT_SCOPE)
        run = _get_latest_run(mgmt_token)

        if not run:
            logger.info("No workflow runs found.")
            return

        props = run.get("properties", {})
        status = props.get("status", "")
        run_name = run.get("name", "")
        logger.info(f"Latest run: {run_name}, status: {status}")

        if status == "Succeeded":
            logger.info("Latest run succeeded — nothing to report.")
            return

        if status == "Running":
            logger.info("Run still in progress — skipping.")
            return

        # Collect failed / timed-out actions
        actions = _get_run_actions(mgmt_token, run_name)
        failed_actions = [
            a for a in actions
            if a.get("properties", {}).get("status") in ("Failed", "TimedOut")
        ]
        logger.info(f"Failed actions: {[a['name'] for a in failed_actions]}")

        # Query App Insights (best-effort — don't abort if it fails)
        exceptions, traces = [], []
        try:
            ai_token = _get_msal_token(APP_INSIGHTS_SCOPE)
            exceptions = _query_app_insights(
                ai_token,
                "exceptions | where timestamp > ago(2h) | order by timestamp desc | take 20",
            )
            traces = _query_app_insights(
                ai_token,
                "traces | where severityLevel >= 3 and timestamp > ago(2h) | order by timestamp desc | take 30",
            )
        except Exception as ai_exc:
            logger.warning(f"App Insights query error (continuing): {ai_exc}")

        # Identify and read relevant source files
        relevant_files: set = set()
        for action in failed_actions:
            relevant_files.update(ACTION_TO_FILES.get(action["name"], []))

        if not relevant_files:
            relevant_files = {
                "app/logic_apps/datasync_durable/datasync_orchestrator_bp.py",
                "app/logic_apps/datasync_durable/datasync_activities_bp.py",
            }

        source_contents = _read_source_files(list(relevant_files))

        # Build the diagnostic prompt for Claude
        failed_action_summary = json.dumps(
            [
                {
                    "name": a["name"],
                    "status": a.get("properties", {}).get("status"),
                    "error": a.get("properties", {}).get("error"),
                }
                for a in failed_actions
            ],
            indent=2,
        )

        user_message = (
            f"## Logic App Run Details\n\n"
            f"Run ID: {run_name}\n"
            f"Status: {status}\n"
            f"Start Time: {props.get('startTime', 'Unknown')}\n"
            f"End Time: {props.get('endTime', 'Unknown')}\n\n"
            f"## Failed Actions\n```json\n{failed_action_summary}\n```\n\n"
            f"## Application Insights — Exceptions (last 2h)\n"
            f"```json\n{json.dumps(exceptions[:10], indent=2, default=str)}\n```\n\n"
            f"## Application Insights — Error Traces (last 2h)\n"
            f"```json\n{json.dumps(traces[:15], indent=2, default=str)}\n```\n\n"
            f"## Relevant Source Files\n"
        )
        for path, content in source_contents.items():
            user_message += f"\n### {path}\n```python\n{content}\n```\n"

        user_message += "\nPlease diagnose the failure following Steps 3–4 from your instructions and provide a specific code fix."

        system_prompt = _read_agent_instructions()
        diagnosis = _call_claude(system_prompt, user_message)
        logger.info("Claude diagnosis complete.")

        failed_names = ", ".join(a["name"] for a in failed_actions) or status
        subject = f"[Yuva Dev] Logic App Failure: {WORKFLOW_NAME} — {failed_names}"
        html_body = _build_html_email(run, failed_actions, diagnosis)
        _send_email(subject, html_body)
        logger.info(f"Diagnostic email sent for run {run_name}.")

    except Exception as exc:
        logger.error(f"LogicApp_Monitor unhandled error: {exc}", exc_info=True)
        try:
            _send_email(
                subject="[Yuva Dev] LogicApp Monitor — Internal Error",
                html_body=f"<p>The LogicApp Monitor function encountered an error:</p><pre>{repr(exc)}</pre>",
            )
        except Exception:
            pass
