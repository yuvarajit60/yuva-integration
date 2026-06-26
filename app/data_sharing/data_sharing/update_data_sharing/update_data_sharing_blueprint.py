import logging
import azure.functions as func
import pandas as pd
from datetime import datetime
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode, AudienceCode
from app.common.database import Database
from app.common.models import Response
from app.common.constants import GeneralConstant
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.datasharing_helper import get_data_sharing_session, execute_data_sharing

from app.data_sharing.update_data_sharing.update_data_sharing_data_access import get_units_to_data_share

update_data_sharing_bp = func.Blueprint() 

@update_data_sharing_bp.function_name(name="Update_DataSharing")
@update_data_sharing_bp.route(route="update/datasharing",  methods=[func.HttpMethod.POST])
@global_exception_handler
def update_data_sharing(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("update_data_sharing")
    last_successful_execution_ts = datetime.now()
    process = "Update Data Sharing"
    file_name = "update_data_sharing"
    job_name = GeneralConstant.INSIGHT_UPDATE_DATA_SHARING_JOB_NAME
    req_body = req.get_json()
    consumer_org_id = req_body.get('orgId')

    db = Database()
    provider_organization = get_tip_provider_organization(db=db)
    if provider_organization is None:
        raise ScalarException(message="Provider Organization is not found")
    provider_org_id = provider_organization[0]

    access_token = fetch_access_token(db=db,org_id= provider_org_id,audience= AudienceCode.DATA_SHARING)

    if consumer_org_id is None or len(consumer_org_id.strip()) == 0:
        logger.error("Consumer Organization ID is mandatory")
        response = Response(False, "Consumer Organization ID is mandatory")
        return func.HttpResponse(response.getJsonResponse(), 
                                status_code=ResponseCode.BAD_REQUEST,
                                mimetype=ContentType.APPLICATION_JSON)
    else:
        
        consolidated_insight_units_df = get_data_sharing_session(db=db, cust_org_id=consumer_org_id, 
                                                                access_token=access_token, logger=logger)
        
        if consolidated_insight_units_df is None:
            logger.error("Consumer Organization ID doesn't exist or data sharing details not yet populated")
            response = Response(False, "Consumer Organization ID doesn't exist or data sharing details not yet populated")
            return func.HttpResponse(response.getJsonResponse(), 
                                    status_code=ResponseCode.BAD_REQUEST,
                                    mimetype=ContentType.APPLICATION_JSON)
        
        insight_units_df = consolidated_insight_units_df.loc[(consolidated_insight_units_df["insight_unit"] == "True")]

        # Insight units with missing subcontarcting
        insight_missing_data_sharing_units_df = insight_units_df.loc[((pd.isnull(insight_units_df["data_sharing"])) & (pd.notnull(insight_units_df["CustomerCombiNr"])) & (pd.notnull(insight_units_df["Asset_Id"])))]
        logger.info(f"Total missing insight units: {len(insight_missing_data_sharing_units_df)}")
        insight_data_sharing_units_df = insight_units_df.loc[((pd.notnull(insight_units_df["data_sharing"])) & (pd.notnull(insight_units_df["Asset_Id"])) & (pd.notnull(insight_units_df["CustomerCombiNr"])))]
        logger.info(f"Total already data_shared insight units: {len(insight_data_sharing_units_df)}")
        if len(insight_missing_data_sharing_units_df) > 0 or len(insight_data_sharing_units_df) > 0:
            insight_units_to_data_share_list = insight_missing_data_sharing_units_df["UnitNr"].tolist()
            insight_units_to_data_share_list.extend(insight_data_sharing_units_df["UnitNr"].tolist())
            units_to_data_share_df = get_units_to_data_share(db=db, units=insight_units_to_data_share_list)
            logger.info(f"Total units to data_share: {len(units_to_data_share_df)}")
            customer_org_name = units_to_data_share_df['root_org_name'][0]
            process = f"{process} for {customer_org_name} "
            message, response_code = execute_data_sharing(db= db,  
                                                            total_units_df=units_to_data_share_df, 
                                                            last_successful_execution_ts=last_successful_execution_ts,
                                                            process=process,
                                                            job_name=job_name,
                                                            file_name=file_name
                                                            )
        else:
            message = "There is no insight units to update the data sharing"
            response_code = 200
    
        response = Response(status=True, message=message)
        return func.HttpResponse(
                response.getJsonResponse(),
                status_code=response_code,
                mimetype=ContentType.APPLICATION_JSON)
