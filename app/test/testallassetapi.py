from app.common.constants import AudienceCode
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token
from app.common.scalar_api.asset_api import get_all_assets
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response
from app.common.database import Database
import logging
import json
import pandas as pd

checkgetallassetdata_bp = func.Blueprint()

@checkgetallassetdata_bp.function_name(name="Check_Get_All_Asset_Data")
@checkgetallassetdata_bp.route(route="checkgetallassetdata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def checkgetallassetdata_api(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger = logging.getLogger("check_get_all_asset_data")
        db = Database()
        offset = 0
        limit = 250
        provider_organization = get_tip_provider_organization(db=db)
        provider_org_id = provider_organization[0]
        rows = []
        access_token = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.ASSET)
        while True:
            asset_response = get_all_assets(access_token=access_token, limit= limit, offset= offset)
            if asset_response.status_code == 200:
                asset_dict= asset_response.json()
                pagination = asset_dict.get("metadata", {}).get("pagination", {})
                total_count = pagination.get("totalCount", 0)
                dict_length = len(asset_dict["items"])
                rows.append({"offset": offset, "item_length": dict_length})
                message =f"Offset: {offset} data_length: {dict_length}"
                logger.info(message)

                offset += limit
            if offset >= total_count:
                break  
        message = "Pagination summary generated successfully"
        payload = {
                "status": True,
                "message": message,
                "meta": {
                    "limit": limit,
                    "pages": len(rows),
                    "totalCount": total_count
                },
                "data": rows  # <-- this is your row data
            }
        return func.HttpResponse(
                body=json.dumps(payload, ensure_ascii=False),
                status_code=200,
                mimetype="application/json"
                    )
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        
        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )