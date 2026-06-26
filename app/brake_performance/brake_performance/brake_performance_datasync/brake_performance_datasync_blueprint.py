from datetime import datetime
import json
import os
from app.brake_performance.brake_performance_datasync.brake_performance_datasync_data_access import add_brake_performance_data_in_db, get_brake_performance_db_data, remove_brake_performance_asset_data_in_db, update_brake_performance_data_in_db
from app.brake_performance.brake_performance_datasync.brake_performance_datasync_services import get_bp_api_data, get_new_existing_bp_asset_data, send_bp_asset_sync_report
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
import logging

brakeperformancesync_bp = func.Blueprint()

@brakeperformancesync_bp.function_name(name="Sync_Brake_Performance_Data")
@brakeperformancesync_bp.route(route="syncbrakeperformancedata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def bpassetsync_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("sync_brake_performance_data")
    db = Database()
    try:
        bp_asset_list_from_db = get_brake_performance_db_data(db=db)
        organization_id = get_tip_provider_organization(db=db)
        if organization_id is None:
            raise ScalarException(message="There is no provider Organization data in database")
        else:
            org_id=organization_id[0]

        bp_asset_list_from_api = get_bp_api_data(db=db,org_id=org_id)
    
        if len(bp_asset_list_from_api) > 0:
            new_bp_asset_data_df, existing_bp_asset_data_df, missing_bp_asset_data_df = get_new_existing_bp_asset_data(bp_asset_list_from_db, bp_asset_list_from_api)
            
            if len(new_bp_asset_data_df) > 0:
                add_brake_performance_data_in_db(db=db,new_brake_performance_asset_data=new_bp_asset_data_df)         
            if len(existing_bp_asset_data_df)>0:
                update_brake_performance_data_in_db(db=db,existing_brake_performance_asset_data=existing_bp_asset_data_df)
            if len(missing_bp_asset_data_df) > 0:
                remove_brake_performance_asset_data_in_db(db=db,missing_brake_performance_asset_data=missing_bp_asset_data_df)

            logger.info(f"Number of new assets :{len(new_bp_asset_data_df)} has beed inserted successfully into the database") 
            logger.info(f"Number of existing assets :{len(existing_bp_asset_data_df)} has beed updated successfully into the database")
            logger.info(f"Number of deactivated assets : {len(missing_bp_asset_data_df)} has been deactivated in the database")          

            asset_response = {"Total BP assets to be synced": len(bp_asset_list_from_api),
                "New BP assets added": len(new_bp_asset_data_df),
                "Existing BP assets updated": len(existing_bp_asset_data_df),
                "BP Assets deactivated": len(missing_bp_asset_data_df),
                }
                
            env = os.environ['SCALAR_ENV']
            params={"environment": env, 
            "execution_time": datetime.now(),
            "total_asset": len(bp_asset_list_from_api), 
            "new_asset": len(new_bp_asset_data_df), 
            "existing_asset": len(existing_bp_asset_data_df) ,
            "deactivate_asset":len(missing_bp_asset_data_df)
            }     

            send_bp_asset_sync_report(bp_api_asset_list=bp_asset_list_from_api,new_bp_asset_list=new_bp_asset_data_df,update_bp_asset_list=existing_bp_asset_data_df,error_bp_asset_list=missing_bp_asset_data_df,params=params)  

        else:
            logger.info(f"Fetching brake performance asset from api has failed")

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
        subject=f"Scalar - Data Sync Error: Brake performance asset sync report"
        if os.environ['SCALAR_ENV'] != 'PROD':
            subject=f"{subject} - {env}"
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