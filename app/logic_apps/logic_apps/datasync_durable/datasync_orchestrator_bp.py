import json
import azure.durable_functions as df
from azure.storage.blob import BlobServiceClient
import pandas as pd
import os
from datetime import datetime, timedelta

datasync_orc_bp = df.Blueprint()

# Max users processed per parallel SyncUsers activity call.
# Keeps each activity well under the 30-min function timeout.
_USER_CHUNK_SIZE = 2000


@datasync_orc_bp.orchestration_trigger(context_name="context")
def test_orc_func(context: df.DurableOrchestrationContext):
    job_name = yield context.call_activity("test_activity", None)
    return job_name


@datasync_orc_bp.orchestration_trigger(context_name="context")
def datasync_orc_func(context: df.DurableOrchestrationContext):
    data = context.get_input()
    process_name = data.get("processName")
    callback_url = data.get("callbackUrl")
    message = "Invalid process name"

    # ── USER DATA SYNC ────────────────────────────────────────────────
    if process_name in ("User_Data_Sync", "User_Sync_Queue"):
        orgs_data = yield context.call_activity("GetAllOrgs", None)
        org_list  = pd.DataFrame(orgs_data["org_list"])
        org_count = orgs_data["org_count"]

        batch_size = 5
        all_users: list = []
        all_roles: list = []
        errors:    list = []

        for i in range(0, org_count, batch_size):
            batch   = org_list[i:i + batch_size].to_dict(orient="records")
            tasks   = [context.call_activity("GetCustomerUsers", c) for c in batch]
            results = yield context.task_all(tasks)
            for r in results:
                if r.get("status"):
                    all_users.extend(r["users"])
                    all_roles.extend(r["roles"])
                else:
                    errors.append(r)
            context.set_custom_status({
                "fetched_orgs":   i + len(batch),
                "success_count":  len(all_users),
                "failure_count":  len(errors),
            })
            if i + batch_size < org_count:
                yield context.create_timer(
                    context.current_utc_datetime + timedelta(seconds=10)
                )

        if errors:
            # Store error log via activity — no I/O in orchestrator
            yield context.call_activity("UploadBlobData", {
                "container": "job-status",
                "blob_name": f"{process_name}.txt",
                "data":      json.dumps(errors, indent=4),
            })
            message = "User data collection failed"

        elif process_name == "User_Sync_Queue":
            usersync_status = yield context.call_activity("SyncDbQueue", {
                "users":     all_users,
                "roles":     all_roles,
                "org_count": org_count,
            })
            message = (
                "User sync process queued"
                if usersync_status.get("status")
                else "User sync failed"
            )

        else:
            # Fan-out: split users into chunks and sync in parallel.
            # Each chunk runs as an independent SyncUsers activity, so no
            # single call processes the entire dataset — avoiding the 30-min timeout.
            # Only the last chunk generates and sends the summary email report.
            total_users = len(all_users)
            user_chunks = [
                all_users[i:i + _USER_CHUNK_SIZE]
                for i in range(0, max(total_users, 1), _USER_CHUNK_SIZE)
            ]
            last_idx = len(user_chunks) - 1
            chunk_tasks = [
                context.call_activity("SyncUsers", {
                    "users":       chunk,
                    "roles":       all_roles,
                    "org_count":   org_count,
                    "send_report": (idx == last_idx),
                })
                for idx, chunk in enumerate(user_chunks)
            ]
            chunk_results = yield context.task_all(chunk_tasks)
            all_ok  = all(r.get("status") for r in chunk_results)
            message = "User sync successful" if all_ok else "User sync partial failure"

    # ── ASSET DATA SYNC ───────────────────────────────────────────────
    # 2-phase fan-out:
    #   Phase 1 – CompareAssets runs the full comparison once and stores each
    #             result category (new/missing/existing/…) as a separate blob.
    #   Phase 2 – SyncAssetsChunk activities run in parallel; each reads only
    #             its category blob and writes a 1 000-row slice to the DB.
    #   Report  – SendAssetSyncReport emails the summary after all writes finish.
    elif process_name == "Asset_Data_Sync":
        assets_data = yield context.call_activity("GetAllAssets", None)
        if assets_data.get("status"):
            compare_result = yield context.call_activity("CompareAssets", None)
            if compare_result.get("status"):
                chunk_size  = 1000
                write_tasks = [
                    context.call_activity("SyncAssetsChunk", {
                        "category": category,
                        "offset":   offset,
                        "limit":    chunk_size,
                    })
                    for category, count in compare_result["counts"].items()
                    if count > 0
                    for offset in range(0, count, chunk_size)
                ]
                if write_tasks:
                    write_results = yield context.task_all(write_tasks)
                    all_ok = all(r.get("status") for r in write_results)
                else:
                    all_ok = True
                yield context.call_activity("SendAssetSyncReport", None)
                message = "Asset sync successful" if all_ok else "Asset sync partial failure"
                context.set_custom_status(compare_result["counts"])
            else:
                message = "Asset comparison failed"
        else:
            message = "Asset data collection failed"

    # ── SESSION DATA SYNC ─────────────────────────────────────────────
    # Same 2-phase fan-out: CompareSessions → SyncSessionsChunk (parallel) → SendSessionSyncReport
    elif process_name == "Session_Data_Sync":
        sessions_data = yield context.call_activity("GetAllSessions", None)
        if sessions_data.get("status"):
            compare_result = yield context.call_activity("CompareSessions", None)
            if compare_result.get("status"):
                chunk_size  = 1000
                write_tasks = [
                    context.call_activity("SyncSessionsChunk", {
                        "category": category,
                        "offset":   offset,
                        "limit":    chunk_size,
                    })
                    for category, count in compare_result["counts"].items()
                    if count > 0
                    for offset in range(0, count, chunk_size)
                ]
                if write_tasks:
                    write_results = yield context.task_all(write_tasks)
                    all_ok = all(r.get("status") for r in write_results)
                else:
                    all_ok = True
                yield context.call_activity("SendSessionSyncReport", None)
                message = "Session sync successful" if all_ok else "Session sync partial failure"
                context.set_custom_status(compare_result["counts"])
            else:
                message = "Session comparison failed"
        else:
            message = "Session data collection failed"

    # ── BRAKE PERFORMANCE DATA SYNC ───────────────────────────────────
    # Same 2-phase fan-out: CompareBrakePerformance → SyncBrakePerformanceChunk → SendBrakePerformanceSyncReport
    elif process_name == "BrakePerformance_Data_Sync":
        assets_data = yield context.call_activity("GetAllBpAssets", None)
        if assets_data.get("status"):
            compare_result = yield context.call_activity("CompareBrakePerformance", None)
            if compare_result.get("status"):
                chunk_size  = 1000
                write_tasks = [
                    context.call_activity("SyncBrakePerformanceChunk", {
                        "category": category,
                        "offset":   offset,
                        "limit":    chunk_size,
                    })
                    for category, count in compare_result["counts"].items()
                    if count > 0
                    for offset in range(0, count, chunk_size)
                ]
                if write_tasks:
                    write_results = yield context.task_all(write_tasks)
                    all_ok = all(r.get("status") for r in write_results)
                else:
                    all_ok = True
                yield context.call_activity("SendBrakePerformanceSyncReport", None)
                message = "Brake Performance sync successful" if all_ok else "Brake Performance sync partial failure"
                context.set_custom_status(compare_result["counts"])
            else:
                message = "Brake Performance comparison failed"
        else:
            message = "Brake Performance data collection failed"

    # ── CALLBACK ──────────────────────────────────────────────────────
    callback_status = yield context.call_activity(
        "SendCallback", {"callbackUrl": callback_url, "status": message}
    )
    message += (
        ", Callback sent successfully."
        if callback_status.get("status")
        else ", Sending callback failed."
    )
    return message
