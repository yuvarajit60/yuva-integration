import os
import json
import logging
import datetime
import requests
import anthropic
from azure.identity import DefaultAzureCredential
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


_credential = DefaultAzureCredential()

def _get_azure_token(scope: str) -> str:
    return _credential.get_token(scope).token


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


def _build_html_email(run: dict, failed_actions: list, diagnosis: str, logicapp_failed: bool = True) -> str:
    props = run.get("properties", {})
    run_name = run.get("name", "Unknown")
    status = props.get("status", "Unknown")
    start_time = props.get("startTime", "Unknown")
    end_time = props.get("endTime", "Unknown")
    failed_names = ", ".join(a["name"] for a in failed_actions) or "—"
    safe_diagnosis = (
        diagnosis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if logicapp_failed:
        header_color = "#c0392b"
        title = "Logic App Workflow Failure Report"
        banner = (
            f'<div style="background:#c0392b;color:white;padding:10px 16px;border-radius:4px;margin-bottom:16px;">'
            f'<b>ALERT: Logic App Workflow Failed</b> — {failed_names}</div>'
        )
        status_color = "#c0392b"
    else:
        header_color = "#e67e22"
        title = "Function Internal Errors Report (Logic App Succeeded)"
        banner = (
            '<div style="background:#e67e22;color:white;padding:10px 16px;border-radius:4px;margin-bottom:16px;">'
            '<b>ALERT: Internal Function Errors Detected</b> — The Logic App workflow returned HTTP 200 '
            '(Succeeded) but Application Insights contains exceptions from the function invocations. '
            'These are errors caught inside the business logic that did not cause the HTTP response to fail.</div>'
        )
        status_color = "#e67e22"

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;color:#333;">
  <h2 style="color:{header_color};">{title}</h2>
  {banner}
  <h3>Summary</h3>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
    <tr><td><b>Logic App</b></td><td>{LOGIC_APP_NAME}</td></tr>
    <tr><td><b>Workflow</b></td><td>{WORKFLOW_NAME}</td></tr>
    <tr><td><b>Run ID</b></td><td>{run_name}</td></tr>
    <tr><td><b>Logic App Status</b></td><td style="color:{status_color};"><b>{status}</b></td></tr>
    <tr><td><b>Start Time</b></td><td>{start_time}</td></tr>
    <tr><td><b>End Time</b></td><td>{end_time}</td></tr>
    <tr><td><b>Failed Logic App Actions</b></td><td>{failed_names}</td></tr>
    <tr><td><b>Error Source</b></td><td>{"Logic App action failure" if logicapp_failed else "Internal function exception (caught, logged to App Insights)"}</td></tr>
  </table>
  <h3>Diagnosis &amp; Suggested Fix</h3>
  <pre style="background:#f4f4f4;padding:16px;border-radius:4px;white-space:pre-wrap;word-wrap:break-word;font-size:13px;">{safe_diagnosis}</pre>
  <hr/>
  <p style="font-size:11px;color:#999;">Generated by LogicApp Monitor &mdash; {generated_at}</p>
</body>
</html>"""


def _send_email(subject: str, html_body: str):
    api_key = os.environ["SENDGRID_API_KEY"]
    from_email = os.environ.get("FC_EMAIL_ID", "yuvaraj-periyasamy@outlook.com")
    to_email = os.environ.get("REPORT_MAIL_DL", "yuvarajit60@gmail.com")
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid {resp.status_code}: {resp.text}")


@logicapp_monitor_bp.function_name(name="LogicApp_Monitor")
@logicapp_monitor_bp.timer_trigger(arg_name="timer", schedule="0 0 8 * * *", run_on_startup=False)
def logicapp_monitor(timer: func.TimerRequest) -> None:
    logger.info("LogicApp_Monitor triggered")

    try:
        mgmt_token = _get_azure_token(MGMT_SCOPE)
        run = _get_latest_run(mgmt_token)

        if not run:
            logger.info("No workflow runs found.")
            return

        props = run.get("properties", {})
        status = props.get("status", "")
        run_name = run.get("name", "")
        logger.info(f"Latest run: {run_name}, status: {status}")

        if status == "Running":
            logger.info("Run still in progress — skipping.")
            return

        # Always fetch all actions regardless of Logic App status
        actions = _get_run_actions(mgmt_token, run_name)
        failed_actions = [
            a for a in actions
            if a.get("properties", {}).get("status") in ("Failed", "TimedOut")
        ]
        logicapp_failed = status in ("Failed", "TimedOut", "Cancelled")
        logger.info(f"Logic App status: {status}, failed actions: {[a['name'] for a in failed_actions]}")

        # Always query App Insights — functions may return HTTP 200 but log internal errors
        exceptions, traces = [], []
        try:
            ai_token = _get_azure_token(APP_INSIGHTS_SCOPE)
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

        has_function_errors = len(exceptions) > 0 or len(traces) > 0
        logger.info(f"App Insights: {len(exceptions)} exceptions, {len(traces)} error traces")

        # Only skip if Logic App succeeded AND no internal function errors in App Insights
        if not logicapp_failed and not has_function_errors:
            logger.info("Latest run succeeded with no internal function errors — nothing to report.")
            return

        # Determine relevant source files
        # For Logic App failures: map from failed actions; for internal errors: map from all actions
        relevant_files: set = set()
        source_actions = failed_actions if failed_actions else actions
        for action in source_actions:
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

        if logicapp_failed:
            run_context = (
                f"## Failed Logic App Actions\n```json\n{failed_action_summary}\n```\n\n"
            )
            diagnosis_instruction = (
                "\nPlease diagnose the failure following Steps 3–4 from your instructions and provide a specific code fix."
            )
        else:
            run_context = (
                "## Important: Logic App Status = Succeeded (HTTP 200)\n"
                "The Logic App workflow completed successfully — all function calls returned HTTP 200. "
                "However, Application Insights contains exceptions or error-level traces from the function "
                "invocations. These are INTERNAL ERRORS that were caught inside the business logic "
                "(e.g. inside execute_data_sharing or start_data_sharing) and did not propagate to the "
                "HTTP response. They appear as unknown_errors in the report email or as caught exceptions "
                "logged via logger.error. Diagnose the internal error from the App Insights data below.\n\n"
            )
            diagnosis_instruction = (
                "\nThe Logic App succeeded but the function had internal errors logged to App Insights. "
                "Cross-reference the exception stack trace with the source files provided. "
                "Check the Known Error Patterns section of your instructions first — this may already be a documented pattern."
            )

        user_message = (
            f"## Logic App Run Details\n\n"
            f"Run ID: {run_name}\n"
            f"Logic App Status: {status}\n"
            f"Start Time: {props.get('startTime', 'Unknown')}\n"
            f"End Time: {props.get('endTime', 'Unknown')}\n\n"
            f"{run_context}"
            f"## Application Insights — Exceptions (last 2h)\n"
            f"```json\n{json.dumps(exceptions[:10], indent=2, default=str)}\n```\n\n"
            f"## Application Insights — Error Traces (last 2h)\n"
            f"```json\n{json.dumps(traces[:15], indent=2, default=str)}\n```\n\n"
            f"## Relevant Source Files\n"
        )
        for path, content in source_contents.items():
            user_message += f"\n### {path}\n```python\n{content}\n```\n"

        user_message += diagnosis_instruction

        system_prompt = _read_agent_instructions()
        diagnosis = _call_claude(system_prompt, user_message)
        logger.info("Claude diagnosis complete.")

        if logicapp_failed:
            failed_names = ", ".join(a["name"] for a in failed_actions) or status
            subject = f"[Yuva Dev] Logic App Failure: {WORKFLOW_NAME} — {failed_names}"
        else:
            subject = f"[Yuva Dev] Function Internal Errors Detected: {WORKFLOW_NAME} (Logic App Succeeded)"

        html_body = _build_html_email(run, failed_actions, diagnosis, logicapp_failed)
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
