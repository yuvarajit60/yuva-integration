import os
import logging
import json
import pandas as pd
from datetime import datetime
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.unit_helpers import get_asset_api_data
from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.common.exception_handler import global_exception_handler
from app.fleetconnected_migration.common.tx_tango.trailer_api import TrailerApi
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import send_TIP_asset_sync_report
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import TIP_add_asset_data_in_db, TIP_add_asset_data_in_history, TIP_delete_asset_data_in_db, TIP_inactive_asset_data, TIP_remove_asset_data_in_db, TIP_unpairing_current_device, TIP_update_asset_data_in_db, TIP_update_new_pairing_data_in_db, get_asset_data_from_db
from app.fleetconnected_migration.tip_migration.fc_tip_migration_service import TIP_get_new_existing_asset_data, get_trailers_from_transics

sync_SKY_TIP_Asset_bp = func.Blueprint()

@sync_SKY_TIP_Asset_bp.function_name(name="Sync_SKY_TIP_Asset")
@sync_SKY_TIP_Asset_bp.route(route="syncskytipasset",  methods=[func.HttpMethod.POST])
@global_exception_handler
def sync_SKY_TIP_asset(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Sync_SKY_TIP_Asset")
    db = Database()
    fc_db = FleetConnectedDatabase()

    provider_organization = get_tip_provider_organization(db=db)
    if provider_organization is None:
        raise ScalarException(message="Provider Organization is not found")
    provider_organization_id = provider_organization[0]

    asset_list_from_db = get_asset_data_from_db(db=db)
    asset_table_data_list = asset_list_from_db["assetId"].drop_duplicates().tolist()
    logger.info(f"Total number of assets found in the database: {len(asset_table_data_list)}")
    asset_list_from_api = get_asset_api_data(db=db,org_id=provider_organization_id)
    logger.info(f"Total number of assets found in API: {len(asset_list_from_api)}")
    # asset_list_from_api["unit_nr"] = asset_list_from_api["internalCode"]
    if len(asset_list_from_api) > 0:
    
        new_asset_data_df, missing_asset_data_df, existing_asset_api_data_df, existing_inactive_asset_data_df, existing_unpairing_asset_data_df,\
                    existing_new_pairing_asset_data_df, existing_fresh_new_pairing_asset_data_df = TIP_get_new_existing_asset_data(asset_list_from_db, asset_list_from_api)
        
        if len(new_asset_data_df) > 0:
            TIP_add_asset_data_in_db(db=db,new_asset_data=new_asset_data_df)         
        if len(existing_asset_api_data_df)>0:
            TIP_update_asset_data_in_db(db=db,existing_asset_data=existing_asset_api_data_df)
        if len(missing_asset_data_df) > 0:
            TIP_delete_asset_data_in_db(db=db,missing_asset_data=missing_asset_data_df)
        if len(existing_inactive_asset_data_df)>0:
            TIP_remove_asset_data_in_db(db=db,missing_asset_data=existing_inactive_asset_data_df)
        if len(existing_unpairing_asset_data_df)>0:
            TIP_delete_asset_data_in_db(db=db,missing_asset_data=existing_unpairing_asset_data_df)
            TIP_add_asset_data_in_history(db=db,new_asset_data=existing_unpairing_asset_data_df)
        if len(existing_new_pairing_asset_data_df)>0:
            TIP_add_asset_data_in_db(db=db,new_asset_data=existing_new_pairing_asset_data_df)
        if len(existing_fresh_new_pairing_asset_data_df)>0:
            TIP_update_new_pairing_data_in_db(db=db,update_new_pairing_data=existing_fresh_new_pairing_asset_data_df)

    env = os.environ["SCALAR_ENV"]
    app_version = os.environ["APP_VERSION"]
    tenancy_dispatcher = os.environ["TENANCY_DISPATCHER"]
    tenancy_integrator = os.environ['TENANCY_INTEGRATOR']
    tenancy_system_nr = os.environ['TENANCY_SYSTEM_NR']
    tenancy_password = os.environ['TENANCY_PASSWORD']
    trailer_api = TrailerApi(  dispatcher=tenancy_dispatcher, 
                                    integrator=tenancy_integrator,
                                    system_nr=tenancy_system_nr,
                                    password=tenancy_password,
                                    version=app_version)
    # Scalar and SKY asset comparision
    asset_list_from_api = asset_list_from_api.drop("assignees")

    SKY_units_api_df= get_trailers_from_transics(api=trailer_api)
    full_asset_sky_scalar_df = pd.merge(asset_list_from_api, SKY_units_api_df, left_on="internalCode", right_on="TrailerID",how="outer", suffixes=('_sc', '_sky'))
    #Get Matched asset between Scalar and SKY
    full_asset_sky_scalar_df["unit_nr"] = full_asset_sky_scalar_df["TrailerID"]
    matched_asset_in_sky_and_scalar = full_asset_sky_scalar_df.loc[\
                    full_asset_sky_scalar_df['unit_nr'].notna() &\
                        full_asset_sky_scalar_df["internalCode"].notna()]
    #Get missing assets in Scalar
    missing_asset_in_scalar = full_asset_sky_scalar_df.loc[full_asset_sky_scalar_df['internalCode'].isna() & full_asset_sky_scalar_df['assetId'].isna()]
    #Get missing assets in SKY
    missing_asset_in_sky = full_asset_sky_scalar_df.loc[full_asset_sky_scalar_df['unit_nr'].isna() & full_asset_sky_scalar_df['status']=="active"]

    #Get active assets in Scalar
    active_asset_in_scalar = asset_list_from_api.loc[asset_list_from_api['status']=="active"]

    params={"environment": env, 
        "exectution_time": datetime.now(), 
        "current_asset_in_scalar": len(asset_list_from_api),
        "current_active_asset_in_scalar" :len(active_asset_in_scalar),
        "current_active_asset_in_sky": len(SKY_units_api_df),
        "matched_asset_in_sky_and_scalar": len(matched_asset_in_sky_and_scalar),
        "missing_asset_in_scalar": len(missing_asset_in_scalar),
        "missing_asset_in_sky":len(missing_asset_in_sky)
       
        }
    
    send_TIP_asset_sync_report(
        current_asset_in_scalar = asset_list_from_api,
        current_asset_in_sky=SKY_units_api_df,
        matched_asset_in_sky_and_scalar=matched_asset_in_sky_and_scalar, 
                            missing_asset_in_scalar=missing_asset_in_scalar, 
                            missing_asset_in_sky=missing_asset_in_sky,
                            params=params)
    
    api_response = {"Total assets in Scalar": len(asset_list_from_api),
                "Current Active assets in Scalar": len(active_asset_in_scalar),
                "Total active assets in SKY": len(SKY_units_api_df),
                "Matched assets in Scalar and SKY":len(matched_asset_in_sky_and_scalar),
                "Missing assets in Scalar": len(missing_asset_in_scalar),
                "Missing assets in SKY": len(missing_asset_in_sky)
                }
                          
    return func.HttpResponse(
    json.dumps(api_response, default=str),
    status_code=ResponseCode.SUCCESS,
    mimetype=ContentType.APPLICATION_JSON)