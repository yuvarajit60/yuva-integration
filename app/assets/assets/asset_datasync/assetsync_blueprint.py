from datetime import datetime
import json
import os
from app.assets.asset_datasync.assetsync_services import get_new_existing_asset_data, send_asset_sync_report
from app.assets.asset_datasync.assetsync_data_access import add_asset_data_in_history, delete_asset_data_in_db, get_asset_table_data, inactive_asset_data, remove_asset_data_in_db, add_asset_data_in_db, unpairing_current_device, update_asset_data_in_db, update_new_pairing_data_in_db
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.unit_helpers import get_asset_api_data, get_asset_data
from app.common.models import Response
import logging


assetsync_bp = func.Blueprint()

@assetsync_bp.function_name(name="Sync_Asset_Data")
@assetsync_bp.route(route="syncassetdata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def assetsync_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("sync_asset_data")
    db = Database()
    try:
        asset_list_from_db = get_asset_table_data(db=db)
        organization_id = get_tip_provider_organization(db=db)
        if organization_id is None:
            raise ScalarException(message="There is no provider Organization data in database")
        else:
            org_id=organization_id[0]

        asset_list_from_api = get_asset_api_data(db=db,org_id=org_id)
    
        if len(asset_list_from_api) > 0:
            
            new_asset_data_df, missing_asset_data_df, existing_asset_api_data_df, existing_inactive_asset_data_df, existing_unpairing_asset_data_df,\
                existing_new_pairing_asset_data_df, existing_fresh_new_pairing_asset_data_df = get_new_existing_asset_data(asset_list_from_db, asset_list_from_api, logger)
            
            if len(new_asset_data_df) > 0:
                add_asset_data_in_db(db=db,new_asset_data=new_asset_data_df)         
            if len(existing_asset_api_data_df)>0:
                update_asset_data_in_db(db=db,existing_asset_data=existing_asset_api_data_df)
            if len(missing_asset_data_df) > 0: # Asset not found in Scalar system
                delete_asset_data_in_db(db=db,missing_asset_data=missing_asset_data_df)
            if len(existing_inactive_asset_data_df)>0:# Asset made Inactive in Scalar system
                remove_asset_data_in_db(db=db,missing_asset_data=existing_inactive_asset_data_df)
            if len(existing_unpairing_asset_data_df)>0: # Pairied asset becoming Unpairing asset
                delete_asset_data_in_db(db=db,missing_asset_data=existing_unpairing_asset_data_df)
                add_asset_data_in_history(db=db,new_asset_data=existing_unpairing_asset_data_df)
            if len(existing_new_pairing_asset_data_df)>0:# Change of pairing from old device to new device
                add_asset_data_in_db(db=db,new_asset_data=existing_new_pairing_asset_data_df)
            if len(existing_fresh_new_pairing_asset_data_df)>0:# Fresh pairing with Un-Pairied assets
                update_new_pairing_data_in_db(db=db,update_new_pairing_data=existing_fresh_new_pairing_asset_data_df)

            logger.info(f"Number of new assets :{len(new_asset_data_df)} has beed inserted successfully into the database") 
            logger.info(f"Number of existing assets :{len(existing_asset_api_data_df)} has beed updated successfully into the database")
            logger.info(f"Number of deactivated assets : {len(missing_asset_data_df)} has been deactivated in the database")          

            asset_response = {"Total assets to be synced": len(asset_list_from_api),
                "New assets added": len(new_asset_data_df),
                "Existing assets updated": len(existing_asset_api_data_df),
                "Assets deactivated": len(missing_asset_data_df),
                }
                
            env = os.environ['SCALAR_ENV']
            params={"environment": env, 
            "execution_time": datetime.now(),
            "total_asset": len(asset_list_from_api), 
            "new_asset": len(new_asset_data_df), 
            "existing_asset": len(existing_asset_api_data_df) ,
            "deactivate_asset":len(missing_asset_data_df)
        }     

            send_asset_sync_report(api_asset_list=asset_list_from_api,new_asset_list=new_asset_data_df,update_asset_list=existing_asset_api_data_df,error_asset_list=missing_asset_data_df,params=params)  

        else:
            logger.info(f"Fetching asset from api has failed")

        return func.HttpResponse(
            json.dumps(asset_response, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
    
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        email=Email()
        env = os.environ['SCALAR_ENV']
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Asset sync report"
        if os.environ['SCALAR_ENV'] != 'PROD':
            subject= f"{subject} - {env}"
        template_name='error_asset_email.html'
    
        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": repr(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)

        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )
