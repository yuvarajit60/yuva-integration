import logging
import azure.functions as func
import os
from datetime import datetime
from app.common.constants import  ContentType, ResponseCode
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.helpers.asset_group_helper import create_consumer_org_asset_group_in_provider
from app.common.helpers.common_data_access import get_consumer_organization_data, get_fa_organization_details, get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token
from app.common.models import Response
from app.common.exceptions import ScalarException
from app.common.database_model.scalar_tables import FA_Org_Application_Mapping
from app.fleetconnected_migration.customer_migration.fc_customer_migration_services import consumer_asset_group_hierarchy_migration, send_customer_asset_group_hierarchy_report

customer_asset_group_hierarchy_bp = func.Blueprint()
@customer_asset_group_hierarchy_bp.function_name(name="Customer_Asset_Group_Hierarchy")
@customer_asset_group_hierarchy_bp.route(route="customer/assetgroup/hierarchy",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customer_asset_group_hierarchy_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Customer_Asset_Group_Hierarchy")
    db = Database()
    message = {}
    faRootOrgIds = req.get_json().get('faRootOrgIds')
    invalid_input = True
    for value in faRootOrgIds:
        if not str(value).isnumeric():
            invalid_input = False
    if not invalid_input:
        message = f"Please provide valid FA root organization id."
        logger.warning(message)
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )
    
    provider_org_id = get_tip_provider_organization(db=db)
    access_token = fetch_access_token(db=db,org_id=provider_org_id[0],audience="TMAPI")

    for faRootOrgId in faRootOrgIds:
        consumer_details = get_consumer_organization_data(db=db, fa_root_org_id=faRootOrgId)
        if consumer_details is not None and len(consumer_details) > 0:
            consumer_org_id = consumer_details['Organization_Id'][0]
            if consumer_details['ZF_Consumer_Org'][0] == 0:
                asset_group_access_token = fetch_access_token(db=db,org_id=consumer_org_id,audience="TMAPI")
                consumer_asset_group_hierarchy_migration(logger=logger,db=db, access_token= asset_group_access_token, sc_organization_id= consumer_org_id, fa_root_org_id=faRootOrgId)
        else:
            raise ScalarException(message="Consumer Organization is not found in Scalar.")
        create_consumer_org_asset_group_in_provider(db=db,provider_org_id=provider_org_id[0],fa_root_org_id=faRootOrgId,access_token=access_token)

        root_org_application_mapping = db.get_session().query(FA_Org_Application_Mapping).filter(\
                                                FA_Org_Application_Mapping.Organization_Id == faRootOrgId, \
                                                    FA_Org_Application_Mapping.Application_Id==4).first()
        if root_org_application_mapping is None:
            db.get_session().add(FA_Org_Application_Mapping(
                Organization_Id = int(faRootOrgId),
                Application_Id = 4,
                Active = 1
            ))
        else:
            root_org_application_mapping.Active = 1
        db.get_session().commit()
        
        fa_org_details_df= get_fa_organization_details(db= db, fa_org_id= faRootOrgId)
        fa_org_details_dict = fa_org_details_df.to_dict('records')[0]
        org_name = fa_org_details_dict["Organization_Name"]

        env = os.environ['SCALAR_ENV']
        params={"environment": env, 
        "execution_time": datetime.now(),
        "root_org_id" : faRootOrgId,
        "root_org_name": org_name
        }
        send_customer_asset_group_hierarchy_report(db= db, fa_root_org_id=faRootOrgId, org_name=org_name, params= params)

    message = f"Created customer asset group hierarchy Successfully!"
    logger.warning(message)
    response = Response(status=True, message=message).getJsonResponse()
    return func.HttpResponse(
            response,
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON
        )