import logging
import json
import os
import azure.functions as func
import requests
import uuid
from sqlalchemy import text
from datetime import datetime
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response
from app.common.database import Database
from app.common.email import Email
from app.common.scalar_api.common_api import verify
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_services import get_scalar_api_error_messages
from app.common.helpers.common_data_access import get_consumer_organization_data, get_FA_root_org_details

from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.fleetconnected_migration.common.migration_tables import SC_Customer_Migration_Process_Status_Log, SC_Migrated_SKY_Customer_To_Scalar
from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_subcontracted_tenancy_record, inform_to_fleetconnected_database

customer_end_to_end_migration_bp = func.Blueprint()

@customer_end_to_end_migration_bp.function_name(name="Customer_End_To_End_Migration")
@customer_end_to_end_migration_bp.route(route="customerendtoendmigration",  methods=[func.HttpMethod.POST])
@global_exception_handler
def customer_migration_process_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Customer_End_To_End_Migration")
    try:
        db = Database()
        fc_db = FleetConnectedDatabase()
        owner_name = req.params.get('owner_name')

        migration_successful_orgs = list()
        migration_failed_orgs = list()
        already_migrated_orgs = list()
        inactive_orgs = list()
        non_scalar_orgs = list()
        non_sky_orgs = list()

        run_id = str(uuid.uuid4())
        offset = 0
        while True:
            input_query = text(''' SELECT FA_Root_Organization_Id FROM SCALAR.SC_Migration_Process_Request
									WHERE Active = '1' AND Owner_Name = :owner_name
                                    ORDER BY FA_Root_Organization_Id
                                    OFFSET :offset ROWS FETCH NEXT 1 ROWS ONLY''')

            fa_root_org_id = db.query(statement=input_query, params={"offset": offset, "owner_name": owner_name})
            if fa_root_org_id is None or len(fa_root_org_id) == 0:
                #Reached the end of table, exit
                break

            offset += 1

            fa_root_org_id = fa_root_org_id[0][0]

            start_time = datetime.now()
            fa_root_org_name = get_FA_root_org_details(db=db, fa_root_org_id=fa_root_org_id) 
            stop_time = datetime.now()              
            if fa_root_org_name is None:
                #Update the status log table with "VALIDATION_CHECK" process name
                db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                Run_Id = run_id,
                FA_Root_Organization_Id = fa_root_org_id,
                Process_Name = "VALIDATION_CHECK",
                Start_Datetime = start_time,
                Stop_Datetime = stop_time,
                Success_Status = 'N',
                Response_Message= "Invalid (or) Inactive FA Root Organization ID"
                )
            )
                db.get_session().commit()
                continue
            
            start_time = datetime.now()
            subcontracting_tenancy_record = get_subcontracted_tenancy_record(fc_db=fc_db, root_org_id=fa_root_org_id) 
            stop_time = datetime.now()          
            if subcontracting_tenancy_record is None or len(subcontracting_tenancy_record) == 0:
                #Update the status log table with "VALIDATION_CHECK" process name
                db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                Run_Id = run_id,
                FA_Root_Organization_Id = fa_root_org_id,
                Process_Name = "VALIDATION_CHECK",
                Start_Datetime = start_time,
                Stop_Datetime = stop_time,
                Success_Status = 'N',
                Response_Message= "Non-SKY Organization (or) tenancy not populated"
                )
            )
                db.get_session().commit()
                continue

            start_time = datetime.now()
            sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
            stop_time = datetime.now()
            if sc_org_details_df is None or len(sc_org_details_df) == 0:
                #Update the status log table with "VALIDATION_CHECK" process name
                db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                Run_Id = run_id,
                FA_Root_Organization_Id = fa_root_org_id,
                Process_Name = "VALIDATION_CHECK",
                Start_Datetime = start_time,
                Stop_Datetime = stop_time,
                Success_Status = 'N',
                Response_Message= "Framework Agreement/Scalar Organization is not yet created"
                )
            )
                db.get_session().commit()
                #skip execution
                continue

            sc_org_dict = sc_org_details_df.to_dict('records')[0]

            start_time = datetime.now()
            #check if the org is already migrated or not. Proceed only if it's not migrated already
            migration_status_from_db = db.get_session().query(SC_Migrated_SKY_Customer_To_Scalar).filter(SC_Migrated_SKY_Customer_To_Scalar.FA_Root_Org_Id == fa_root_org_id).first()
            to_migrate = False

            #If details not found or migrated flag is N
            if migration_status_from_db is None:
                to_migrate = True
            elif int(migration_status_from_db.Migrated_Flag) == 0:
                to_migrate = True

            stop_time = datetime.now()

            # If already migrated, log status and skip iteration
            if to_migrate == False:
                db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                Run_Id = run_id,
                FA_Root_Organization_Id = fa_root_org_id,
                Process_Name = "VALIDATION_CHECK",
                Start_Datetime = start_time,
                Stop_Datetime = stop_time,
                Success_Status = 'N',
                Response_Message= "Organization already migrated to scalar"
                )
            )
                db.get_session().commit()
                # Skip iteration
                continue

            # All checks are passed and already not migrated, execute all the processes
            start_time = datetime.now()
            dev_url = os.environ["SCALAR_BASE_URL"]
            json_payload = {'faRootOrgIds': [fa_root_org_id]}

            flag = True
            # ASSET GROUP HIERARCHY CREATION
            start_time = datetime.now()
            asset_group_hierarchy_response = requests.post(url=dev_url+'/api/customer/assetgroup/hierarchy',
                                                            headers = {"x-functions-key": os.environ["X_FUNCTIONS_KEY"], "Content-Type": "application/json"},
                                                            json=json_payload,
                                                            verify=verify)
            stop_time = datetime.now()
            
            if asset_group_hierarchy_response.status_code == 200:
                status = 'Y'
                message = asset_group_hierarchy_response.json()["message"]
            else:
                status = 'N'
                message = get_scalar_api_error_messages(error_response=asset_group_hierarchy_response)[0]
                flag = False
                
            db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                                Run_Id = run_id,
                                FA_Root_Organization_Id = fa_root_org_id,
                                Process_Name = "ASSET GROUP HIERARCHY CREATION",
                                Company_Code = subcontracting_tenancy_record[2],
                                Start_Datetime = start_time,
                                Stop_Datetime = stop_time,
                                Response_Code = asset_group_hierarchy_response.status_code,
                                Success_Status = status,
                                Response_Message= message
                                    )
                                )
            db.get_session().commit()

            # SKY CUSTOMER SESSION SYNC
            start_time = datetime.now()
            customer_sessionsync_response = requests.post(url=dev_url+'/api/syncskycustomersessions',
                                                            headers = {"x-functions-key": os.environ["X_FUNCTIONS_KEY"], "Content-Type": "application/json"},
                                                            json=json_payload,
                                                            verify=verify)
            stop_time = datetime.now()
            if customer_sessionsync_response.status_code == 200:
                message = json.dumps(customer_sessionsync_response.json()[0])
                status = 'Y'
            else:
                message = get_scalar_api_error_messages(error_response=customer_sessionsync_response)[0]
                status = 'N'
                flag = False

            db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                                Run_Id = run_id,
                                FA_Root_Organization_Id = fa_root_org_id,
                                Process_Name = "SKY CUSTOMER SESSION SYNC",
                                Company_Code = subcontracting_tenancy_record[2],
                                Start_Datetime = start_time,
                                Stop_Datetime = stop_time,
                                Response_Code = customer_sessionsync_response.status_code,
                                Success_Status = status,
                                Response_Message = message
                                    )
                                )
            db.get_session().commit()

            # SKY CUSTOMER USER SYNC
            start_time = datetime.now()
            customer_usersync_response = requests.post(url=dev_url+'/api/syncskycustomerusers',
                                                            headers = {"x-functions-key": os.environ["X_FUNCTIONS_KEY"], "Content-Type": "application/json"},
                                                            json=json_payload,
                                                            verify=verify)
            stop_time = datetime.now()

            if customer_usersync_response.status_code == 200:
                message = json.dumps(customer_usersync_response.json()[0])
                status = 'Y'
            else:
                message = get_scalar_api_error_messages(error_response=customer_usersync_response)[0]
                status = 'N'
                flag = False

            db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                                Run_Id = run_id,
                                FA_Root_Organization_Id = fa_root_org_id,
                                Process_Name = "SKY CUSTOMER USER SYNC",
                                Company_Code = subcontracting_tenancy_record[2],
                                Start_Datetime = start_time,
                                Stop_Datetime = stop_time,
                                Response_Code = customer_usersync_response.status_code,
                                Success_Status = status,
                                Response_Message= message
                                    )
                                )
            db.get_session().commit()

            # SKY CUSTOMER USER ASSIGNMENT
            start_time = datetime.now()
            customer_user_assignment_response = requests.post(url=dev_url+'/api/customer/userassignment',
                                                            headers = {"x-functions-key": os.environ["X_FUNCTIONS_KEY"], "Content-Type": "application/json"},
                                                            json=json_payload,
                                                            verify=verify)
            stop_time = datetime.now()

            if customer_user_assignment_response.status_code == 200:
                message = json.dumps(customer_user_assignment_response.json()[0])
                status = 'Y'
            else:
                message = message = get_scalar_api_error_messages(error_response=customer_user_assignment_response)[0]
                status = 'N'
                flag = False

            db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                                Run_Id = run_id,
                                FA_Root_Organization_Id = fa_root_org_id,
                                Process_Name = "SKY CUSTOMER USER ASSIGNMENT",
                                Company_Code = subcontracting_tenancy_record[2],
                                Start_Datetime = start_time,
                                Stop_Datetime = stop_time,
                                Response_Code = customer_user_assignment_response.status_code,
                                Success_Status = status,
                                Response_Message= message
                                    )
                                )
            db.get_session().commit()

            # SKY CUSTOMER ASSET ASSIGNMENT
            start_time = datetime.now()
            customer_asset_assignment_response = requests.post(url=dev_url+'/api/customer/assetassignment',
                                                            headers = {"x-functions-key": os.environ["X_FUNCTIONS_KEY"], "Content-Type": "application/json"},
                                                            json=json_payload,
                                                            verify=verify)
            stop_time = datetime.now()

            if customer_asset_assignment_response.status_code == 200:
                message = message = json.dumps(customer_asset_assignment_response.json()[0])
                status = 'Y'
            else:
                message = get_scalar_api_error_messages(error_response=customer_asset_assignment_response)[0]
                status = 'N'
                flag = False

            db.get_session().add(SC_Customer_Migration_Process_Status_Log(
                                Run_Id = run_id,
                                FA_Root_Organization_Id = fa_root_org_id,
                                Process_Name = "SKY CUSTOMER ASSET ASSIGNMENT",
                                Company_Code = subcontracting_tenancy_record[2],
                                Response_Code = customer_asset_assignment_response.status_code,
                                Start_Datetime = start_time,
                                Stop_Datetime = stop_time,
                                Success_Status = status,
                                Response_Message= message
                                    )
                                )
            db.get_session().commit()

            #If all the above tasks are successful, update SC_Migrated_SKY_Customers_To_Scalar table
            if flag == True:
                migrated_flag = '1'
            else:
                migrated_flag = '0'
        
            migration_status_from_db = db.get_session().query(SC_Migrated_SKY_Customer_To_Scalar).filter(SC_Migrated_SKY_Customer_To_Scalar.FA_Root_Org_Id == fa_root_org_id).first()

            if migration_status_from_db is None:
                db.get_session().add(SC_Migrated_SKY_Customer_To_Scalar(
                                    SC_Organization_Id = sc_org_dict['Organization_Id'],
                                    SC_Organization_Name = sc_org_dict['Organization_Name'],
                                    SKY_Company_id = subcontracting_tenancy_record[0],
                                    SKY_Company_Code = subcontracting_tenancy_record[2],
                                    FA_Root_Org_Id = fa_root_org_id,
                                    Migrated_Flag = migrated_flag,
                                    Migrated_Date = datetime.now()
                                        )
                                    )
            else:
                migration_status_from_db.SC_Organization_Id = sc_org_dict['Organization_Id']
                migration_status_from_db.SC_Organization_Name = sc_org_dict['Organization_Name']
                migration_status_from_db.Migrated_Flag = migrated_flag
                migration_status_from_db.Migrated_Date = datetime.now()
            db.get_session().commit()

            #Inform to Fleetconnected DB about migration status.Update tenancy_populated flag value to 2 in insight DB
            env = os.environ['SCALAR_ENV']
            if env== 'PROD':
                inform_to_fleetconnected_database(fc_db= fc_db, fa_root_org_id= fa_root_org_id)

        response = Response(status=True, message="Customer End To End Migration process completed").getJsonResponse()
        return func.HttpResponse(
            response,
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)
         

    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["MIGRATION_REPORT_MAIL_DL"].split(",")
        subject=f"Customer End To End Migration process error report - " + env
        template_name='error_customer_migration_email.html'

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