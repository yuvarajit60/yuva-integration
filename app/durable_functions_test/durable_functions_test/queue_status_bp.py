import azure.functions as func
from azure.storage.blob import BlobServiceClient
import uuid,os,json

job_status_check_bp = func.Blueprint()

@job_status_check_bp.activity_trigger(input_name="jobname")
def job_status_check(jobname):
    client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    blob = client.get_blob_client(container="job-status",blob=f"{jobname}.txt")
    try:
        return blob.download_blob().readall().decode().strip()
    except Exception:
        return "pending"