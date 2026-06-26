# Scalar Integration — Project Document

---

## 1. Project Overview

**Scalar Integration** is a Python-based **Azure Functions** application that acts as an integration middleware between TIP's internal fleet management system (**FleetAdmin / FA**) and the **Scalar platform** — a REST API-driven fleet data-sharing and telematics management system.

TIP (a trailer fleet provider) uses this system to automate the full lifecycle of trailer fleet operations:

- Onboarding new customers into the Scalar platform
- Sharing trailer telematics data between TIP (provider) and customers (consumers)
- Tracking device pairing/unpairing events on trailers
- Managing organizational asset groups and team access
- Activating and deactivating brake performance monitoring (EBPMS)
- Synchronizing data between internal databases and the Scalar API

---

## 2. Technology Stack

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime |
| Azure Functions | Latest | Serverless HTTP trigger hosting |
| Azure Durable Functions | Latest | Orchestrator/activity function support |
| Azure Blob Storage | Latest | Error log and file storage |
| SQLAlchemy | 2.0.46 | ORM for Microsoft SQL Server |
| PyODBC | 5.3.0 | ODBC driver for SQL Server connection |
| Pandas | 3.0.0 | Data processing and DataFrame operations |
| Marshmallow / marshmallow_dataclass | Latest | Request payload validation and deserialization |
| XlsxWriter | 3.2.9 | Excel report generation |
| Requests | Latest | HTTP calls to Scalar REST API |
| MSAL | Latest | Microsoft identity platform authentication (for email) |
| NumPy | 2.2.4 | Numerical utilities (NaN handling) |
| Zeep | 3.4.0 | SOAP client (for FleetConnected/Transics integration) |
| OpenPyXL | Latest | Excel file reading |
| Cryptography | 43.0.3 | SSL/TLS support |

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Azure Functions App                     │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Customer    │  │   Assets /   │  │  Data Sharing   │ │
│  │ Onboarding  │  │ Auto-Pairing │  │   / Sessions    │ │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘ │
│         │                │                    │           │
│  ┌──────▼────────────────▼────────────────────▼────────┐ │
│  │              Common Layer (app/common)               │ │
│  │  Database │ Exception Handler │ Email │ Scalar API   │ │
│  └──────┬────────────────────────────────────┬─────────┘ │
└─────────┼────────────────────────────────────┼───────────┘
          │                                    │
          ▼                                    ▼
  ┌───────────────┐                  ┌──────────────────┐
  │ SQL Server DB │                  │  Scalar REST API │
  │ (SCALAR schema│                  │  (external)      │
  │  + FA tables) │                  └──────────────────┘
  └───────────────┘
```

### Layer Pattern (every feature follows this)

```
HTTP Request
    │
    ▼
*_blueprint.py      ← Azure Function endpoint, request parsing, response shaping
    │
    ▼
*_services.py       ← Business logic, orchestration, decisions
    │
    ▼
*_data_access.py    ← Raw SQL queries and ORM database operations
```

---

## 4. Project Structure

```
scalar_integration/
├── requirements.txt
├── app/
│   ├── common/                          # Shared infrastructure
│   │   └── common/
│   │       ├── database.py              # SQLAlchemy DB wrapper
│   │       ├── constants.py             # All constant classes
│   │       ├── models.py                # Response model
│   │       ├── exceptions.py            # Custom exception classes
│   │       ├── exception_handler.py     # Global exception handler decorator
│   │       ├── email.py                 # Microsoft Graph API email sender
│   │       ├── func_validator.py        # Input validation utilities
│   │       ├── database_model/
│   │       │   └── scalar_tables.py     # All SQLAlchemy ORM table models
│   │       ├── helpers/
│   │       │   ├── common_services.py   # fetch_access_token, get_all_data, job tracking, Excel reports
│   │       │   ├── common_data_access.py# Shared DB query functions
│   │       │   ├── datasharing_helper.py# Core data sharing engine
│   │       │   ├── session_helpers.py   # Session create/update logic
│   │       │   ├── asset_group_helper.py# Asset group creation helpers
│   │       │   ├── group_helpers.py     # SC group query helpers
│   │       │   ├── unit_helpers.py      # Unit/asset group assignment helpers
│   │       │   ├── framework_agreement_helpers.py  # Framework agreement creation
│   │       │   ├── process_helpers.py   # Process control report generation
│   │       │   ├── database_helpers.py  # SQLAlchemy base, mixins
│   │       │   ├── team_helpers.py      # Team management helpers
│   │       │   ├── user_helpers.py      # User management helpers
│   │       │   └── session_helpers.py   # Session management helpers
│   │       └── scalar_api/
│   │           ├── authentication.py    # Token generation API
│   │           ├── asset_api.py         # Asset CRUD API wrappers
│   │           ├── asset_group_api.py   # Asset group API wrappers
│   │           ├── session_api.py       # Session create/fetch API wrappers
│   │           ├── framework_api.py     # Framework agreement API wrappers
│   │           ├── teams_api.py         # Teams API wrappers
│   │           ├── user_api.py          # User API wrappers
│   │           ├── roles_api.py         # Roles API wrappers
│   │           ├── brake_performance_api.py  # EBPMS API wrappers
│   │           └── common_api.py        # Shared API settings (SSL verify flag)
│   │
│   ├── customer_onboarding/             # Customer onboarding workflow
│   ├── assets/                          # Asset management and auto-pairing
│   ├── asset_groups/                    # Asset group lifecycle management
│   ├── data_sharing/                    # Data sharing session management
│   ├── brake_performance/               # Brake performance (EBPMS) management
│   ├── fleetconnected_migration/        # Legacy migration utilities
│   └── durable_functions_test/          # Durable functions prototyping
```

---

## 5. Common Layer — Shared Infrastructure

### 5.1 Database (`database.py`)

Wraps SQLAlchemy with a MSSQL connection via pyodbc. Connection string is read from the `DB_CONN` environment variable.

| Method | Purpose |
|---|---|
| `query(statement, params, as_dataframe)` | SELECT queries; returns rows or a pandas DataFrame |
| `insert_orm(orm_item)` | Insert a single ORM model instance |
| `insert_orm_list(orm_list)` | Bulk insert a list of ORM model instances |
| `insert_update_delete_raw(statement, params)` | Execute raw INSERT/UPDATE/DELETE SQL |
| `get_session()` | Returns the SQLAlchemy session for advanced operations |

### 5.2 Constants (`constants.py`)

| Class | Purpose |
|---|---|
| `StatusCode` | Job status codes: `N` (not yet running), `R` (running), `S` (successful), `F` (failure) |
| `AudienceCode` | Scalar API audience identifiers: UMAPI, AMAPI, TMAPI, DASAPI, BPAPI |
| `ResponseCode` | HTTP response codes: 200, 202, 400, 404, 500 |
| `ApiUrl` | All Scalar REST API URL templates (parameterized with hostname) |
| `GeneralConstant` | Retry limits, wait times, job names, asset limits (5000), pauses |
| `ErrorFields` | Standard field names used in error reports |
| `TrailerIdentifier` | Trailer lookup identifier types (ID, CODE, LICENSE_PLATE, TRANSICS_ID) |
| `AutoPairingEvent` | Pairing event reason codes (AutoPair, ManualPair, ManualUnpair, etc.) |
| `AutoPairingEventType` | Scalar event types: `unit.paired`, `unit.unpaired` |
| `ExcelSheetName` | Sheet names in Excel reports |
| `AdditionalChargeType` | Insight product charge codes for trailer subscriptions |
| `BPAdditionalChargeType` | Brake performance specific charge codes |
| `VehicleCategory` | Vehicle types: GeneralCargo, RefrigeratedTransport |
| `Connection` | Connection types: TIP, CUSTOMER |

### 5.3 Exception Handler (`exception_handler.py`)

The `@global_exception_handler` decorator is applied to every Azure Function endpoint. It catches all exceptions and converts them to a standardized HTTP response.

| Exception Type | Handling |
|---|---|
| `ScalarException` | Returns error message with optional display message and configurable HTTP status code |
| `AutoPairingException` | Logs failure event in `SC_Auto_Pairing_Log` table, returns 500 |
| `SQLAlchemyError` | Returns generic DB error message, logs full trace |
| `MarshmallowValidationError` | Returns validation error as 400 Bad Request |
| `Exception` (generic) | Returns error string, logs full trace |

If the environment variable `SC_API_ERROR_EMAIL_ALLOWED` is set to `True`, an error email is automatically sent with request details (URL, method, payload) to the configured recipients.

### 5.4 Access Token Management (`common_services.py`)

`fetch_access_token(db, org_id, audience)` implements a 3-path token caching strategy:

```
1. Token in DB and valid   → return cached token
2. Token in DB but expired → call Scalar Auth API, update DB record, return new token
3. No token in DB          → call Scalar Auth API, insert new DB record, return token
```

Token generation calls `get_access_token(client_id, client_secret, audience)` in `authentication.py`, which POSTs to the Scalar `/integrators/token` endpoint.

### 5.5 Email System (`email.py`)

Uses **Microsoft Graph API** with MSAL `ConfidentialClientApplication` to send emails from a shared mailbox. Supports:
- HTML body templated with Python's `string.Template` (templates stored in `app/resources/email_templates/`)
- Excel file attachments (base64 encoded)
- Multiple recipients

### 5.6 Paginated API Fetching (`common_services.py`)

`get_all_data(access_token, func)` fetches all pages from any Scalar API that supports pagination:
- Calls the provided function in a loop
- Handles HTTP 429 (rate limit), 502, 504 with retry and backoff
- Stops when `nextOffset` is null and `currentPage == pageCount`

### 5.7 Job Execution Tracking

Long-running batch jobs are tracked in the `SC_Job_Execution_Details` table:

```
start_job_execution_process(db, job_name)   → inserts row with status R, returns job_id
update_job_execution_process(db, job_id, status) → updates status to S or F, sets end timestamp
```

---

## 6. Database Models (SCALAR Schema)

### ORM Base Classes (`database_helpers.py`)

| Mixin | Columns Added |
|---|---|
| `IdMixin` | `id` (BigInteger, auto primary key) |
| `CreationModificationLoggingMixin` | `Created_By`, `Created_Date`, `Modified_By`, `Modified_Date` |

### Tables

| Table | Key Columns | Purpose |
|---|---|---|
| `SC_Asset` | Asset_Id, Unit_Nr, Device_Number, Device_Pairing_Status, VIN_Number | Current asset/trailer records with device pairing state |
| `SC_Asset_Pairing_History` | Asset_Id, Device_Number, Device_Pairing_Date, Device_Unpairing_Date | Full history of device pairings and unpairings |
| `SC_User` | User_Id, Login_Type, FA_User_Id, SC_Organization_Id, User_Email | Scalar users mapped to Scalar organizations |
| `SC_User_Role_Mapping` | User_Id, Role_Id, Role_Name | User-to-role assignments |
| `SC_Team` | Team_Id, Team_Name, SC_Organization_Id | Teams within organizations |
| `SC_Team_User_Mapping` | User_Id, Team_Id, Active | User membership in teams |
| `SC_Organization` | Organization_Id, FA_Root_Organization_Id, Is_Provider, ZF_Consumer_Org | Scalar orgs (TIP = provider, customers = consumers) |
| `SC_Framework_Agreement` | Agreement_Id, Consumer_Org_Id, Provider_Org_Id, Agreement_Status | Data sharing agreements between provider and consumer |
| `SC_Integrator_Details` | Organization_Id, Framework_Id, Client_Id, Client_Secret | API credentials for each organization |
| `SC_Session` | Session_Id, Agreement_Id, Provider_Asset_Id, Consumer_Asset_Id, Status | Active/historical data sharing sessions |
| `SC_Job_Execution_Details` | Job_Name, Status_Cd, Execution_Start_Date, Execution_End_Date | Batch job run tracking |
| `SC_Asset_Group` | Asset_Group_Id, Asset_Group_Name, SC_Organization_Id, FA_Organization_Id, Root_Group_Id, Parent_Group_Id | Asset group hierarchy |
| `SC_Asset_Group_Asset_Mapping` | Asset_Group_Id, Asset_Id | Assets assigned to groups |
| `SC_Asset_Group_Team_Mapping` | Asset_Group_Id, Team_Id | Teams assigned to groups |
| `SC_Auto_Pairing_Log` | Event_Batch_Id, Event_Type, Device_Number, Asset_Id, Status, Reason | Log of all auto-pairing webhook events |
| `FA_Org_Application_Mapping` | Organization_Id, Application_Id | FleetAdmin org to application mapping |
| `FA_User_App_Access` | User_Id, Application_Id | FleetAdmin user application access |

---

## 7. Feature Modules

### 7.1 Customer Onboarding

**Endpoint:** `POST /customeronboarding`

**Input:** `{ "faOrganizationId": <int> }`

**Flow:**

```
1. Validate FA root org ID (must be numeric and exist in FA DB)
2. Call Scalar API → create Framework Agreement
   - This creates: consumer organization, primary contact, integrator credentials
3. Save to DB: SC_Organization, SC_Framework_Agreement, SC_Integrator_Details
4. Return HTTP 200 immediately with created org and agreement details
5. Background thread starts:
   a. Create asset group hierarchy in consumer org (mirroring FA org structure)
   b. Create a consumer-named asset group in provider (TIP) org
   c. Notify FleetAdmin about tenancy creation
   d. Update FleetConnected flag in FA_Organization table
   e. Insert FA_Org_Application_Mapping record
   f. Send success email to regional super users
   g. If active+paired units exist → run data sharing for all those units
```

**Error handling:** Background errors saved to Azure Blob Storage (`customer-onboarding` container) and emailed to super users.

---

### 7.2 Auto-Pairing

**Endpoint:** `POST /tip/asset/autopairing`

Receives webhook events from Scalar when a telematics device is paired or unpaired from a trailer.

**Request schema (Marshmallow):**

```
AutoPairingBatchRequest
  eventBatchId: str
  eventSubscriptionId: str
  eventBatchTime: datetime
  eventsData: List[AutoPairingEventRequest]
    eventType: str           # "unit.paired" or "unit.unpaired"
    eventVersion: int
    eventData: EventData
      unitId: str            # device IMEI / identifier
      assetId: str           # Scalar asset ID
      reason: str            # AutoPair, ManualPair, ManualUnpair, etc.
      registeredOn: datetime
      assetVIN: str
      sensorVIN: str
      location: Location { lat, lon }
```

**Processing per event:**

```
unit.paired (AutoPair or ManualPair):
  1. Look up asset in SC_Asset by assetId → get Unit_Nr
  2. If new pairing → insert into SC_Asset (active device)
  3. If already paired → log as already paired (no change)

unit.unpaired:
  1. Look up current pairing in SC_Asset
  2. Delete current SC_Asset record
  3. Insert SC_Asset with null device fields (unpaired state)
  4. Insert history record into SC_Asset_Pairing_History
```

Every event is logged in `SC_Auto_Pairing_Log` regardless of outcome. Failures within individual events do not stop the batch — processing continues and errors are collected.

---

### 7.3 Data Sharing

**Core engine:** `execute_data_sharing()` in `helpers/datasharing_helper.py`

This is the largest and most complex module. It handles sharing trailer telematics data from TIP (provider) to customer organizations (consumers).

**Data Sharing Flow:**

```
1. Fetch all units to process (from DB, filtered by Insight charge codes)
2. Group units by FA root org → then by FA child org
3. For each root org:
   a. Get consumer Scalar org (SC_Organization record)
   b. Call Scalar API → create sessions (batched in groups of 25)
      - Returns: new sessions, already-existing sessions, sessions in different org
   c. Assign provider assets to customer asset group in TIP org
   d. Rename consumer assets (displayName = Fleet_Id or UnitNr + license plate)
   e. Assign consumer assets to customer asset groups in consumer org
   f. Update SC_Session records in DB
4. Track units without pairing info in SC_Missing_Pairing table
5. Generate multi-sheet Excel control report
6. Email report to distribution list
```

**Session creation:**
- Assets batched in chunks of 25 (Scalar API limit)
- HTTP 429 handled with exponential wait (`RETRY_WAITTIME = 12s`, up to `RETRY_LIMIT = 5` attempts)
- Three outcomes per asset: new session created, already exists in same org, exists in different org

**`execute_data_sharing_wo_mail()`** is the same logic but without email — used during customer onboarding background processing.

---

### 7.4 Asset Group Management

Manages the hierarchy of asset groups within Scalar organizations.

| Endpoint | Method | Function |
|---|---|---|
| Create Asset Group | POST | Creates a new group in Scalar API and saves to SC_Asset_Group |
| Activate Asset Group | POST | Sets group Active = 1 in DB and Scalar |
| Deactivate Asset Group | POST | Sets group Active = 0 in DB and Scalar |
| Remove Asset Group | POST | Deletes group from Scalar API and marks inactive in DB |
| Update Asset Group | POST | Updates group name/description in Scalar API and DB |

**Asset Group Overflow Handling:**
When a group reaches 5,000 assets (Scalar's limit), the system automatically creates a new group named `<original_name> - #Copy#<random_5_char>` and continues assigning assets there.

---

### 7.5 Brake Performance (EBPMS)

Manages Electronic Brake Performance Monitoring System activation on trailers.

**Activate Endpoint:** `POST /activate/brakeperformance`

```
1. Fetch all trailers eligible for EBPMS but not yet activated (from DB)
2. Log job start in SC_Job_Execution_Details
3. For each customer org:
   a. Call Scalar API → enable EBPMS on eligible asset IDs
   b. Wait 100 seconds (BP_ACTIVATION_PAUSE_TIME_IN_SECS) for Scalar to process
   c. Re-sync from Scalar API to verify actual activation status
   d. Classify units as: truly activated / falsely activated / failed
4. Generate 4-sheet Excel report:
   - BP_activated_units, Truly_BP_activated_units,
     Falsely_BP_activated_units, BP_activation_failed_units
5. Email report to migration distribution list
6. Update job status in DB
```

**Deactivate Endpoint:** `POST /deactivate/brakeperformance` — reverse flow, calls Scalar EBPMS disable API.

**Datasync Endpoint:** Synchronizes EBPMS state from Scalar API back into the local database.

---

### 7.6 Data Sharing Sub-Operations

| Feature | Endpoint | Description |
|---|---|---|
| Assign Combinumbers | POST | Link internal combinumbers to Scalar assets |
| Deassign Combinumbers | POST | Unlink combinumbers from assets |
| Interchange Out Units | POST | Move units out from one organization's sharing |
| Interchange In Units | POST | Bring units into an organization's sharing |
| Copy/Move Along Units | POST | Copy or move units between organizations |
| New Pairing Insight Units | POST | Start data sharing for newly paired units |
| Update Data Sharing | POST | Update session parameters for existing data sharing |
| Session Datasync | POST | Reconcile DB session records with Scalar API state |
| Control Report | POST | Generate a data sharing control report for an org |

---

### 7.7 Asset Upload & Datasync

- **Asset Upload:** Bulk creates or updates asset records in the DB from an uploaded source
- **Asset Datasync:** Pulls current asset state from Scalar API and reconciles with `SC_Asset` table (inserts new, updates changed, flags inactive)

---

### 7.8 Auto-Pairing Report

Generates a report of all auto-pairing events, success rates, unmatched devices, and pairing errors from `SC_Auto_Pairing_Log`.

---

### 7.9 FleetConnected Migration

One-time utilities for migrating data from the legacy **FleetConnected** (Transics) system:

- `customer_migration/` — Migrate customer asset assignments and asset group hierarchies
- `common/fleetconnected_database.py` — Separate DB connection to FleetConnected database
- `common/tx_tango/` — Transics Tango API wrappers (trailer and user APIs)

---

## 8. API Endpoints Summary

| Endpoint | Method | Module | Description |
|---|---|---|---|
| `/customeronboarding` | POST | customer_onboarding | Onboard a new customer into Scalar |
| `/tip/asset/autopairing` | POST | assets/auto_pairing | Webhook for device pairing/unpairing events |
| `/activate/brakeperformance` | POST | brake_performance | Activate EBPMS on eligible trailers |
| `/deactivate/brakeperformance` | POST | brake_performance | Deactivate EBPMS on trailers |
| `/brakeperformance/datasync` | POST | brake_performance | Sync EBPMS state from Scalar API |
| `/asset/datasync` | POST | assets/asset_datasync | Sync asset state from Scalar API |
| `/asset/upload` | POST | assets/asset_upload | Bulk asset upload |
| `/autopairing/report` | POST | assets/auto_pairing_report | Generate auto-pairing report |
| `/datasharing/assign` | POST | data_sharing | Assign combinumbers |
| `/datasharing/deassign` | POST | data_sharing | Deassign combinumbers |
| `/datasharing/interchange/out` | POST | data_sharing | Interchange units out |
| `/datasharing/interchange/in` | POST | data_sharing | Interchange units in |
| `/datasharing/copy-move` | POST | data_sharing | Copy/move units along orgs |
| `/datasharing/new-pairing` | POST | data_sharing | Data share newly paired units |
| `/datasharing/update` | POST | data_sharing | Update data sharing parameters |
| `/session/datasync` | POST | data_sharing | Sync sessions with Scalar API |
| `/assetgroup/create` | POST | asset_groups | Create an asset group |
| `/assetgroup/activate` | POST | asset_groups | Activate an asset group |
| `/assetgroup/deactivate` | POST | asset_groups | Deactivate an asset group |
| `/assetgroup/remove` | POST | asset_groups | Remove an asset group |
| `/assetgroup/update` | POST | asset_groups | Update an asset group |

---

## 9. Key Design Patterns

### 9.1 Global Exception Handler

```python
@global_exception_handler          # applied to every endpoint
def my_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    ...
```

All exceptions are caught and converted to a structured JSON response:
```json
{ "status": false, "message": "...", "displayMessage": null }
```

### 9.2 Access Token Caching

Tokens are stored in the database with expiry metadata. `fetch_access_token` checks the cache before making a network call. Each organization and audience combination has its own token entry.

### 9.3 Background Threading (Customer Onboarding)

The customer onboarding endpoint returns `200 OK` immediately after creating the Framework Agreement, then spawns a background thread for:
- Asset group hierarchy creation (can take minutes due to Scalar API rate limits)
- Data sharing initialization (can process thousands of units)

Errors in the background thread are written to Azure Blob Storage and emailed to super users.

### 9.4 Batch Processing with Retry

Scalar API rate limits (HTTP 429) are handled with configurable retries:

| Constant | Value | Used For |
|---|---|---|
| `RETRY_LIMIT` | 5 | General API retry limit |
| `RETRY_WAITTIME` | 12 sec | General API retry wait |
| `ASSET_GROUP_RETRY_LIMIT` | 4 | Asset group operations |
| `ASSET_GROUP_RETRY_WAITTIME` | 15 sec | Asset group retry wait |

### 9.5 Excel Reporting via Email

Every batch job generates a multi-sheet Excel report using `xlsxwriter` in memory (`BytesIO`) and emails it via Microsoft Graph API. Sheet structure varies by job type (data sharing, brake performance, etc.).

### 9.6 Pagination

All Scalar list APIs (assets, sessions, framework agreements, etc.) use cursor-based pagination. `get_all_data()` fetches all pages and concatenates results into a single pandas DataFrame.

---

## 10. Environment Variables

| Variable | Description |
|---|---|
| `DB_CONN` | ODBC connection string for SQL Server |
| `AUTH_API_URL` | Scalar authentication API base URL |
| `SCALAR_ENV` | Environment name (`DEV` / `PROD`) — controls email subjects |
| `SC_API_ERROR_EMAIL_ALLOWED` | `True/False` — enable error emails on API failures |
| `SC_API_ERROR_EMAIL_RECIPIENTS` | Comma-separated error email recipients |
| `REPORT_MAIL_DL` | Distribution list for batch job reports |
| `MIGRATION_REPORT_MAIL_DL` | Distribution list for migration/brake performance reports |
| `TENANT_ID` | Azure AD tenant ID for email authentication |
| `CLIENT_ID` | Azure AD app client ID for email authentication |
| `CLIENT_SECRET` | Azure AD app client secret for email authentication |
| `FC_EMAIL_ID` | Shared mailbox email address (sender) |
| `AzureWebJobsStorage` | Azure Storage connection string (for blob error logs) |
| `FLEETCONNECTED_ENV` | FleetConnected environment (`DEV` / `PROD`) |
| `TEST_COMPANY_ID` | DEV override for FleetConnected company ID |
| `TEST_COMPANY_CODE` | DEV override for FleetConnected company code |
| `TEST_CUSTOMER_ID` | DEV override for FleetConnected customer ID |
| `consumerPrimaryEmail` | Default consumer contact email for onboarding |
| `consumerPrimaryFirstName` | Default consumer contact first name |
| `consumerPrimaryLastName` | Default consumer contact last name |

---

## 11. Error Reporting Structure

### Excel Report Sheets (Data Sharing Jobs)

| Sheet Name | Content |
|---|---|
| `Already DataShared units` | Units already in a running session with same consumer org |
| `DataShared in Different Org` | Units already shared to a different consumer org |
| `DataShared successfully` | Units successfully shared in this run |
| `Unknown errors` | API or application errors |
| `Units without pairing info` | Units with no device paired |
| `Units without FA Scalar Org` | Units where customer is not linked to any Scalar org |
| `Units without Scalar onboarding` | Units where customer has not been onboarded to Scalar |
| `Datasharing stopped units` | Units whose sessions were stopped |
| `Datasharing not found units` | Units with no session found |
| `Brake plus activated units` | EBPMS-activated units |
| `BrakeplusAlreadyActivatedUnits` | EBPMS already active (no change needed) |
| `Brake plus failed units` | Units where EBPMS activation failed |

---

## 12. Scalar API Integration

All Scalar API calls are wrapped in thin functions under `app/common/common/scalar_api/`. Each module corresponds to one API domain.

### Authentication
- `POST /integrators/token` — Obtain an access token using client credentials

### Assets
- `GET /assets` — Fetch all assets (paginated)
- `GET /assets/{assetId}` — Fetch a specific asset
- `PUT /assets/{assetId}` — Update asset display name, license plate, VIN, fleet ID

### Sessions (Data Sharing)
- `POST /sessions` — Create data sharing sessions (batches of 25 assets)
- `GET /sessions?frameworkAgreementId=...` — Fetch sessions for a framework agreement

### Asset Groups
- `GET /asset-groups` — List all asset groups
- `GET /asset-groups/{id}` — Get specific asset group with current asset IDs
- `POST /asset-groups` — Create a new asset group
- `POST /actions/assign-assets` — Assign assets to a group
- `POST /actions/unassign-assets` — Unassign assets from a group

### Teams
- `POST /actions/assign-asset-groups` — Assign asset groups to a team
- `POST /actions/assign-users` — Assign users to a team

### Brake Performance
- `POST /actions/enable-ebpms` — Enable EBPMS on a list of assets
- `POST /actions/disable-ebpms` — Disable EBPMS on a list of assets

### Framework Agreements
- `GET /framework-agreements` — List all framework agreements
- `POST /framework-agreements` — Create a new framework agreement
- `GET /framework-agreements/{id}/integrator` — Get integrator credentials

---

## 13. Key Business Rules

1. **Asset limit per group is 5,000.** When a group is full, a new overflow group is auto-created with a random suffix.

2. **Culina Group (FA root org ID = 38) is excluded** from asset group assignment in the provider org — hardcoded bypass due to an existing 5k asset limit constraint.

3. **ZF Consumer customers** (`ZF_Consumer_Org = 1`) do not have their consumer assets renamed or assigned to consumer org groups — only TIP-owned tenancies go through that flow.

4. **Session creation is batched in groups of 25** due to Scalar API limitations.

5. **EBPMS activation requires a 100-second pause** after the API call before re-syncing to verify the activation was actually applied.

6. **Access tokens are cached per (org_id, audience) pair** in the database. Tokens are only refreshed when the cache record shows they are expired.

7. **Every auto-pairing event is logged** in `SC_Auto_Pairing_Log` regardless of success or failure. Individual event failures do not abort the batch.

8. **Customer onboarding is idempotent** — if the org is already onboarded (exists in SC_Organization), a `ScalarException` is raised before any Scalar API calls are made.

---

## 14. Dependencies Between Modules

```
customer_onboarding
    └── framework_agreement_helpers   (create FA in Scalar)
    └── asset_group_helper            (create asset group hierarchy)
    └── datasharing_helper            (trigger data sharing for existing units)
    └── session_helpers               (create sessions per asset)

data_sharing
    └── datasharing_helper            (core engine)
    └── session_helpers               (session create/update)
    └── unit_helpers                  (asset group assignment)
    └── group_helpers                 (fetch SC asset groups)
    └── process_helpers               (generate control report records)

assets/auto_pairing
    └── auto_pairing_data_access      (SC_Asset CRUD)
    └── auto_pairing_service          (save pairing logic)
    └── auto_pairing_validator        (Marshmallow schema)

brake_performance/activate
    └── brake_performance_activate_data_access  (fetch eligible units)
    └── brake_performance_activate_service      (call enable-ebpms API, verify)

All modules
    └── common/database               (DB connection)
    └── common/exception_handler      (error handling)
    └── common/email                  (notifications)
    └── common/helpers/common_services (token, pagination, job tracking, Excel)
    └── common/scalar_api/*           (Scalar REST API calls)
```
