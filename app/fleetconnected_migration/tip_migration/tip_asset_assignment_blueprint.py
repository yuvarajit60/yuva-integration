import logging
import azure.functions as func
import os
from datetime import datetime

from app.common.constants import ContentType, GeneralConstant, ResponseCode
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import  get_tip_provider_organization
from app.common.helpers.common_services import  fetch_access_token
from app.common.models import Response
from app.fleetconnected_migration.tip_migration.fc_tip_migration_service import assign_assets_to_tip_global_country_in_provider_org
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_all_asset, get_assinged_assets_for_report, get_country_assinged_assets_for_report
from app.fleetconnected_migration.tip_migration.fc_tip_migration_service import send_asset_assignment_report

tip_asset_assignment_bp = func.Blueprint()
@tip_asset_assignment_bp.function_name(name="Tip_Asset_Assignment")
@tip_asset_assignment_bp.route(route="tip/assetassignment",  methods=[func.HttpMethod.POST])
@global_exception_handler
def tip_asset_assignment_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Tip_asset_Assignment")
    db = Database()
    message = {}
    tip_main_asset_group = GeneralConstant.TIPGLOBALGROUP
    #Fetch all asset 
    all_asset_df = get_all_asset(db=db)
    asset_ids = all_asset_df["Asset_Id"].tolist()
    if len(asset_ids)>0:
        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")
        provider_org_id = provider_organization[0]
        newly_assigned_assets_for_TIP_Global,already_assigned_assets_for_TIP_Global,assiged_TIP_country_Assets= assign_assets_to_tip_global_country_in_provider_org(db=db, asset_ids=asset_ids, provider_org_id= provider_org_id, logger=logger)
        message = f"Assets has assigned to TIP Global Asset group successfully.Assets has assigned to country Asset group successfully."
        logger.warning(message)

        env = os.environ['SCALAR_ENV']
        params={"environment": env, 
        "execution_time": datetime.now(),
        "total_active_assigned_assets": len(all_asset_df)}
        
        asset_assignment_report = get_assinged_assets_for_report(db=db, sc_org_id= provider_org_id)
        send_asset_assignment_report(total_asset_list=asset_assignment_report,updated_asset_for_TIP_global= already_assigned_assets_for_TIP_Global, new_asset_for_TIP_global= newly_assigned_assets_for_TIP_Global,
                                                assigned_asset_for_TIP_country= assiged_TIP_country_Assets, params= params)
        
        message = f"{message} Assets assignment report sent successfully."
        logger.warning(message)
        
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON
            )
    else:
        raise ScalarException(message=f"There is no any asset to assign with TIP global asset group {tip_main_asset_group}.")