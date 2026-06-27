# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Locally

```powershell
# Install dependencies
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Start the function host (activates venv automatically)
$env:VIRTUAL_ENV="${PWD}\.venv"; $env:PATH="${PWD}\.venv\Scripts;" + $env:PATH; func host start
```

Debugging is done via VS Code: run the **"Attach to Python Functions"** launch configuration, which starts the host with debugpy listening on port 9091 (enabled when `PYTHON_ENABLE_DEBUGPY=true` in `local.settings.json`).

There are no automated tests. Verification is done by calling endpoints locally with HTTP clients.

## Module Structure

Each top-level module lives directly under `app/` with a standard flat layout:

```
app/assets/asset_datasync/   ← files live directly here
app/common/scalar_api/
app/data_sharing/session_datasync/
```

Imports in `function_app.py` must include the feature subfolder level:
```python
# Correct
from app.data_sharing.assign_combinumbers.assign_combinumbers_blueprint import assign_combinumbers_bp
# Wrong (missing subfolder)
from app.data_sharing.assign_combinumbers_blueprint import assign_combinumbers_bp
```

## Feature Module Structure

Every feature follows the same 3-layer pattern:

```
*_blueprint.py    ← Azure Function endpoint, request parsing, @global_exception_handler
*_services.py     ← Business logic and orchestration
*_data_access.py  ← SQLAlchemy ORM queries and raw SQL
```

New endpoints must apply `@global_exception_handler` from `app.common.exception_handler`. This catches all exceptions (including `ScalarException`, `SQLAlchemyError`, and Marshmallow validation errors) and converts them to a structured `{"status": false, "message": "..."}` JSON response.

## Common Layer (`app/common/`)

Key utilities used across all modules:

| File | What it provides |
|---|---|
| `database.py` | `Database` class — `query()`, `insert_orm()`, `insert_orm_list()`, `insert_update_delete_raw()` |
| `constants.py` | `StatusCode`, `AudienceCode`, `ApiUrl`, `GeneralConstant` and other enums |
| `helpers/common_services.py` | `fetch_access_token()`, `get_all_data()` (paginated Scalar API fetcher), job tracking |
| `helpers/common_data_access.py` | Shared DB queries used by multiple features |
| `helpers/datasharing_helper.py` | Core data sharing engine (`execute_data_sharing()`) |
| `scalar_api/` | Thin wrappers for every Scalar REST API domain (auth, assets, sessions, groups, teams, BP) |
| `email.py` | Microsoft Graph API email sender with HTML templates and Excel attachments |

### Access Token Caching
`fetch_access_token(db, org_id, audience)` checks the DB before calling the Scalar auth API. Each `(org_id, audience)` pair has its own cached token in `SC_Integrator_Details`. Always use this function — never call `get_access_token()` directly.

### Paginated API Fetching
`get_all_data(access_token, func)` handles Scalar's cursor-based pagination, retries on HTTP 429/502/504, and returns a concatenated pandas DataFrame. Use this for any Scalar list API.

## Durable Functions Datasync (`app/logic_apps/`)

The datasync orchestrator at `datasync_orchestrator_bp.py` uses a **2-phase fan-out** pattern for all three sync types to avoid the 30-minute activity timeout:

**Phase 1 — Compare activity** (`CompareAssets` / `CompareSessions` / `CompareBrakePerformance`):
- Downloads both full blobs, runs the comparison function once (e.g., `get_new_existing_asset_data()`), stores each result category as a separate JSON blob in Azure Blob Storage. Returns a `counts` dict of rows per category.

**Phase 2 — Chunk activities** (`SyncAssetsChunk` / `SyncSessionsChunk` / `SyncBrakePerformanceChunk`):
- Reads ONE pre-computed category blob and writes a ≤1,000-row slice using the correct DA function for that category. Runs in parallel via `context.task_all()`.

**Why naive offset/limit chunking on the raw blob doesn't work:** `get_new_existing_asset_data()` needs both full datasets to correctly identify "missing" assets (in DB but not in API). Slicing the API blob before comparison produces wrong counts.

Orchestrators must not do I/O directly (no `Database()`, no blob reads/writes). All I/O goes in activities. The `UploadBlobData` activity handles blob writes from the orchestrator.

## Key Business Rules Affecting Code

- **Session creation batched in groups of 25** (Scalar API limit) — see `datasharing_helper.py`
- **Asset group max is 5,000 assets** — overflow creates a new group with a `#Copy#<random>` suffix
- **Culina Group (FA root org ID = 38) is excluded** from provider-side asset group assignment — hardcoded bypass
- **ZF Consumer customers** (`ZF_Consumer_Org = 1`) skip consumer asset renaming and group assignment
- **EBPMS activation requires a 100-second pause** after the API call before re-syncing to verify
- **Customer onboarding is idempotent** — raises `ScalarException` if org already exists before any API calls

## Environment Variables

All required variables are in `local.settings.json` (not committed with real secrets). Key ones:

| Variable | Purpose |
|---|---|
| `DB_CONN` | ODBC connection string for SQL Server |
| `AzureWebJobsStorage` | Azure Storage connection string (blob + durable functions state) |
| `AUTH_API_URL` | Scalar auth base URL |
| `SCALAR_ENV` | `LOCAL` / `DEV` / `PROD` — controls email subject prefixes |
| `SC_API_ERROR_EMAIL_ALLOWED` | `True` to auto-email on API errors |
| `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` | Azure AD credentials for Graph API email |
| `FC_EMAIL_ID` | Sender mailbox address |
