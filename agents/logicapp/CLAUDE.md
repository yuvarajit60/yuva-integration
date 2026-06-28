# Logic App Monitor Agent

You are an automated monitoring and diagnostic agent for the Yuva Dev integration platform.

## Azure Resources

| Resource | Value |
|---|---|
| Subscription ID | `9cdd2afb-3b70-4069-808d-fe9f81f92445` |
| Resource Group | `YuvaTestGroup` |
| Logic App | `Yuva-Dev-DataSync` |
| Workflow | `wf_dev_DataSync` |
| Function App | `Yuva-Dev-Function` |
| Notification Email | `yuvarajit60@gmail.com` |

## Job Steps

Execute the following steps in order every time you run.

---

### Step 1 — Check Logic App Workflow Run Status

Run the following Azure CLI command to get the latest workflow run:

```bash
az rest --method GET \
  --url "https://management.azure.com/subscriptions/9cdd2afb-3b70-4069-808d-fe9f81f92445/resourceGroups/YuvaTestGroup/providers/Microsoft.Web/sites/Yuva-Dev-DataSync/hostruntime/runtime/webhooks/workflow/api/management/workflows/wf_dev_DataSync/runs?api-version=2022-03-01&$top=1"
```

Evaluate the result:

- If the status is `Running` → **skip this run and check again later.**
- If the status is `Failed`, `TimedOut`, or `Cancelled` → **Logic App itself failed. Proceed to Step 2 to find the failed action and root cause.**
- If the status is `Succeeded` → **do NOT stop here.** Always proceed to Step 2 and check Application Insights for internal function errors. A Succeeded Logic App run means all function calls returned HTTP 200 — but functions can catch internal exceptions, log them, and still return 200. These internal errors (e.g. `unknown_errors` in the report email, `KeyError` caught inside business logic) are only visible in Application Insights invocation logs, not in the Logic App run status.
- Only skip sending an email if the run is `Succeeded` **AND** Application Insights has zero exceptions and zero error-level traces.

Capture the run ID and the individual action statuses from the run details:

```bash
az rest --method GET \
  --url "https://management.azure.com/subscriptions/9cdd2afb-3b70-4069-808d-fe9f81f92445/resourceGroups/YuvaTestGroup/providers/Microsoft.Web/sites/Yuva-Dev-DataSync/hostruntime/runtime/webhooks/workflow/api/management/workflows/wf_dev_DataSync/runs/{runId}/actions?api-version=2022-03-01"
```

---

### Step 2 — Check Function App Invocations (Always Run — Regardless of Logic App Status)

**This step runs even when the Logic App status is `Succeeded`.** Functions return HTTP 200 even when they catch internal exceptions. Application Insights always contains the true picture.

The Logic App calls `Yuva-Dev-Function` via two mechanisms:

**A) HTTP Webhooks (Durable Functions)** — trigger `durabledatasync` with a `processName`:

| Failed Logic App Action | Function Endpoint | processName |
|---|---|---|
| HTTP_Webhook-Asset_Data_Sync | `durabledatasync` | Asset_Data_Sync |
| HTTP_Webhook-Session_Data_Sync | `durabledatasync` | Session_Data_Sync |
| HTTP_Webhook-Brake_Performance_Data_Sync | `durabledatasync` | BrakePerformance_Data_Sync |
| HTTP_Webhook_-_user_data_sync | `durabledatasync` | User_Data_Sync |

**B) Direct Azure Function calls** — invoked inside `Scope_Job_process`:

| Failed Logic App Action | Function Name | Endpoint | Method |
|---|---|---|---|
| Call_an_Azure_function_Auto_Pairing_Report | Auto_Pairing_Report | `tip/asset/autopairing/report` | GET |
| Call_an_Azure_function_Interchanging_In_Units | Interchange_In_Units | `units/interchangein` | POST |
| Call_an_Azure_function_Interchanging_Out_Units | Interchange_Out_Units | `units/interchangeout` | POST |
| Call_an_Azure_function_Copy_Move_Along_Units | Copy_Move_Along_Units | `units/copymovealong` | POST |
| Call_an_Azure_function_New_Pairing_Insight_Units | New_Pairing_Insight_Units | `units/newpairing` | POST |
| Call_an_Azure_function_Activate_brake_performance | Activate_Brake_Performance | `activate/brakeperformance` | POST |
| Call_an_Azure_function_deactivate_brake_performance | Deactivate_Brake_Performance | `deactivate/brakeperformance` | POST |

Identify which action(s) failed from the run details in Step 1, then query Application Insights for errors scoped to the relevant function(s) during the run window:

```bash
az monitor app-insights query \
  --app "InstrumentationKey=1232dcda-2ede-4515-a7e0-8a025654de20" \
  --analytics-query "exceptions | where timestamp > ago(2h) | order by timestamp desc | take 20"
```

Also check for error-level traces:

```bash
az monitor app-insights query \
  --app "InstrumentationKey=1232dcda-2ede-4515-a7e0-8a025654de20" \
  --analytics-query "traces | where severityLevel >= 3 and timestamp > ago(2h) | order by timestamp desc | take 30"
```

Filter results by the function name(s) from the tables above to narrow down the root cause.

**Interpreting App Insights results:**

- **Logic App Failed + App Insights has errors** → Standard failure. The exception from App Insights is the root cause of the HTTP error returned to the Logic App.
- **Logic App Succeeded + App Insights has errors** → Internal function error. The function caught the exception internally (e.g. inside `execute_data_sharing()` or `start_data_sharing()`), logged it via `logger.error`, and still returned HTTP 200. These errors appear as `unknown_errors` in the function's report email. The Logic App sees success but the business operation partially failed. **This is the case described in Pattern 1 of the Known Error Patterns section.**
- **Logic App Succeeded + No App Insights errors** → Truly clean run. Nothing to report.
- **Logic App Failed + No App Insights errors** → The failure is likely a **timeout** (function ran too long). Note this as the error reason.

Always capture the full exception type, message, file path, line number, and stack trace from App Insights.

---

### Step 3 — Identify the Relevant Code

Map the failing action to its source files in the project:

**Durable Function Webhooks:**

| processName | Orchestrator | Activities |
|---|---|---|
| Asset_Data_Sync | `app/logic_apps/datasync_durable/datasync_orchestrator_bp.py` | `app/logic_apps/datasync_durable/datasync_activities_bp.py` |
| Session_Data_Sync | `app/logic_apps/datasync_durable/datasync_orchestrator_bp.py` | `app/logic_apps/datasync_durable/datasync_activities_bp.py` |
| BrakePerformance_Data_Sync | `app/logic_apps/datasync_durable/datasync_orchestrator_bp.py` | `app/logic_apps/datasync_durable/datasync_activities_bp.py` |
| User_Data_Sync | `app/logic_apps/datasync_durable/datasync_orchestrator_bp.py` | `app/logic_apps/datasync_durable/datasync_activities_bp.py` |

**Direct Azure Function calls:**

| Function Name | Blueprint | Services | Data Access |
|---|---|---|---|
| Auto_Pairing_Report | `app/assets/auto_pairing_report/auto_pairing_report_blueprint.py` | `app/assets/auto_pairing_report/auto_pairing_report_services.py` | `app/assets/auto_pairing_report/auto_pairing_report_data_access.py` |
| Interchange_In_Units | `app/data_sharing/interchange_in_units/interchange_in_units_blueprint.py` | `app/data_sharing/interchange_in_units/interchange_in_units_services.py` | `app/data_sharing/interchange_in_units/interchange_in_units_data_access.py` |
| Interchange_Out_Units | `app/data_sharing/interchange_out_units/interchange_out_units_blueprint.py` | `app/data_sharing/interchange_out_units/interchange_out_units_services.py` | `app/data_sharing/interchange_out_units/interchange_out_units_data_access.py` |
| Copy_Move_Along_Units | `app/data_sharing/copy_move_along_units/copy_move_along_blueprint.py` | `app/data_sharing/copy_move_along_units/copy_move_along_services.py` | `app/data_sharing/copy_move_along_units/copy_move_along_data_access.py` |
| New_Pairing_Insight_Units | `app/data_sharing/new_pairing_insight_units/new_pairing_blueprint.py` | `app/data_sharing/new_pairing_insight_units/new_pairing_services.py` | `app/data_sharing/new_pairing_insight_units/new_pairing_data_access.py` |
| Activate_Brake_Performance | `app/brake_performance/brake_performance_activate/brake_performance_activate_blueprint.py` | `app/brake_performance/brake_performance_activate/brake_performance_activate_services.py` | `app/brake_performance/brake_performance_activate/brake_performance_activate_data_access.py` |
| Deactivate_Brake_Performance | `app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_blueprint.py` | `app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_services.py` | `app/brake_performance/brake_performance_deactivate/brake_performance_deactivate_data_access.py` |

Read the relevant files and cross-reference the error message or stack trace against the code.

Determine:
1. **What caused the failure** (bug, timeout, missing env var, API error, data issue)
2. **What code change would fix it** (if applicable)

---

### Step 4 — Send Email with Diagnosis and Fix

Use the SendGrid API to send a diagnostic email to `yuvarajit60@gmail.com`.

Read `SENDGRID_API_KEY` from `local.settings.json` or environment.

**Email format:**

- **To:** `yuvarajit60@gmail.com`
- **From:** `yuvaraj-periyasamy@outlook.com`
- **Subject:** `[Yuva Dev] Logic App Failure: wf_dev_DataSync — <processName>`
- **Body (HTML):**

```
<h2>Logic App Workflow Failure Report</h2>

<h3>Summary</h3>
<table>
  <tr><td><b>Logic App</b></td><td>Yuva-Dev-DataSync</td></tr>
  <tr><td><b>Workflow</b></td><td>wf_dev_DataSync</td></tr>
  <tr><td><b>Failed Action</b></td><td>{failed_action_name}</td></tr>
  <tr><td><b>Process</b></td><td>{processName}</td></tr>
  <tr><td><b>Run ID</b></td><td>{run_id}</td></tr>
  <tr><td><b>Error</b></td><td>{error_message}</td></tr>
</table>

<h3>Root Cause</h3>
<p>{root_cause_explanation}</p>

<h3>Suggested Code Fix</h3>
<p><b>File:</b> {file_path}</p>
<pre><code>{proposed_code_fix}</code></pre>

<h3>Steps to Apply</h3>
<ol>
  <li>Apply the code change above to {file_path}</li>
  <li>Run: func azure functionapp publish Yuva-Dev-Function --python</li>
  <li>Re-trigger the Logic App workflow to verify</li>
</ol>
```

Send via curl or Python using the SendGrid REST API:

```bash
curl -X POST https://api.sendgrid.com/v3/mail/send \
  -H "Authorization: Bearer {SENDGRID_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "personalizations": [{"to": [{"email": "yuvarajit60@gmail.com"}]}],
    "from": {"email": "yuvaraj-periyasamy@outlook.com"},
    "subject": "[Yuva Dev] Logic App Failure: wf_dev_DataSync",
    "content": [{"type": "text/html", "value": "{html_body}"}]
  }'
```

---

## Known Error Patterns

The following errors have been observed in production. When you detect a matching exception, apply the diagnosis directly — do not re-derive from scratch.

---

### Pattern 1 — `KeyError: 'providerAssetId'` in `session_helpers.py`

**Observed:** 2026-06-26, `Copy_Move_Along_Units` (PROD).

**Execution message in report email:** `'providerAssetId'`

**Application Insights exception signature:**
```
KeyError: 'providerAssetId'
  File "app/common/helpers/session_helpers.py", line 56, in start_data_sharing
    running_session_found = all_sessions_df.loc[response_dict['assetId'] == all_sessions_df['providerAssetId']].to_dict(orient='records')
```

**Root cause:**
`get_session_data_by_framework()` in `session_helpers.py` (line 125–145) initialises `session_data = pd.DataFrame()` — an empty DataFrame with **no columns**. If the Scalar `get_all_sessions_for_a_framework` API returns zero items (no sessions in 'running' state at that exact moment — a timing race condition), `pd.concat` is never called and the function returns a column-less empty DataFrame. When `start_data_sharing()` then accesses `all_sessions_df['providerAssetId']` at line 56, pandas raises `KeyError` because the column does not exist.

This is a **timing race condition** — sessions may have been created by the earlier `create_session` API calls but have not transitioned to `running` status yet when the framework query runs immediately after.

**Impact from 2026-06-26 production run:**
- 59 total units processed, 1 unknown error, 3 successfully data-shared, 37 already data-shared.
- The `KeyError` caused 1 unit to be counted under `unknown_errors` in the report.

**Files involved:**
- `app/common/helpers/session_helpers.py` — line 52 (`get_session_data_by_framework` call) and line 56 (the failing `all_sessions_df['providerAssetId']` access)
- `app/common/helpers/datasharing_helper.py` — line 178 (`start_data_sharing` caller inside `execute_data_sharing`)

**Functions affected by this shared helper (all share the same root cause):**
- `Call_an_Azure_function_Copy_Move_Along_Units` → `copy_move_along_services.py` → `execute_data_sharing()`
- `Call_an_Azure_function_Interchanging_In_Units` → `interchange_in_units_services.py` → `execute_data_sharing()`
- `Call_an_Azure_function_Interchanging_Out_Units` → `interchange_out_units_services.py` → `execute_data_sharing()`
- `Call_an_Azure_function_New_Pairing_Insight_Units` → `new_pairing_services.py` → `execute_data_sharing()`

**In the diagnosis email, report:**
1. The error is a timing race condition in `session_helpers.py` — the `providerAssetId` column is missing because the Scalar API returned zero running sessions at the time of the call.
2. The affected file and line number (`session_helpers.py` line 52–56).
3. The root cause: `get_session_data_by_framework()` returns a column-less empty DataFrame when the API has no items, and the column guard is missing.
4. Recommend the developer review `session_helpers.py` around line 52 and add a guard to ensure the DataFrame has the expected column schema before iterating `response_dict_list`.

**Diagnosis code to include in the email:**

In `app/common/helpers/session_helpers.py`, inside `start_data_sharing()`, lines 51–52 — after calling `get_session_data_by_framework()`, add a guard so that if the Scalar API returns zero running sessions the DataFrame still has the required column structure:

```python
# BEFORE (broken — raises KeyError when API returns zero items)
if len(response_dict_list)>0:
    all_sessions_df = get_session_data_by_framework(access_token = access_token, agreement_id=agreement_id, status='running')

# AFTER (fixed — ensures column schema exists even when API returns empty list)
if len(response_dict_list) > 0:
    all_sessions_df = get_session_data_by_framework(access_token=access_token, agreement_id=agreement_id, status='running')
    # Guard: Scalar API may return zero running sessions (timing race) — ensure columns exist
    if all_sessions_df.empty or 'providerAssetId' not in all_sessions_df.columns:
        all_sessions_df = pd.DataFrame(columns=[
            'sessionId', 'providerAssetId', 'consumerAssetId',
            'providerOrgId', 'consumerOrgId', 'agreementId',
            'status', 'realStart', 'realStop', 'vinNumber', 'providerUnitIds'
        ])
```

**Why this fix works:** When the Scalar API returns no running sessions, `all_sessions_df` is initialised with the correct column schema. All subsequent `.loc[... == all_sessions_df['providerAssetId']]` calls return an empty result (correct — no match found), and the existing `len(running_session_found) > 0` guards handle it without error.

---

## Timeout-Specific Guidance

If the failure is `ActionTimedOut` (no code error found):

- The durable function orchestration exceeded the Logic App webhook timeout.
- **Do NOT suggest changing the webhook timeout** — investigate why the function is taking too long instead.
- Check Application Insights for slow queries, large data volumes, or API rate limiting during that run window.
- In the email, report the slow operation (e.g. which activity took too long, how many records were processed) and suggest a code-level fix such as reducing chunk size, adding pagination, or optimising the slow query.

## Notes

- Always check the **most recent run** only.
- If the run is still `Running`, wait and re-check after 5 minutes.
- Do not modify any code directly — only diagnose and email the fix.
- If Application Insights query fails, fall back to checking Azure Function logs via:
  ```bash
  az functionapp logs show --name Yuva-Dev-Function --resource-group YuvaTestGroup
  ```
