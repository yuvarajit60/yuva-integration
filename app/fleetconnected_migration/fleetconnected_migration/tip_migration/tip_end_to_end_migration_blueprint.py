import os
import logging
import json
import uuid
from datetime import datetime
import azure.functions as func
import requests
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.exception_handler import global_exception_handler
from app.common.models import Response
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import insert_migration_record_in_db
from app.fleetconnected_migration.common.migration_tables import SC_Migrated_SKY_Customer_To_Scalar

tip_end_to_end_migration_bp = func.Blueprint()

@tip_end_to_end_migration_bp.function_name(name="Tip_End_To_End_Migration")
@tip_end_to_end_migration_bp.route(route="tipendtoendmigration",  methods=[func.HttpMethod.POST])
@global_exception_handler
def tip_end_to_end_migration(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Tip_End_To_End_Migration")
    db = Database()
    url = os.environ['SCALAR_BASE_URL']
    headers = {'x-functions-key':os.environ['X_FUNCTIONS_KEY']}
    try:
        run_id = uuid.uuid4()

        success = False
        # set region country asset group hierarchy in provider org
        start_datetime = datetime.now()
        hierarchy_response = requests.post(url+'/api/tip/assetgroup/hierarchy', headers=headers)
        stop_datetime = datetime.now()
        if hierarchy_response.status_code == 200:
            message = json.dumps(hierarchy_response.json())
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Hierarchy',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=hierarchy_response.status_code,
                                        success_status='Y',
                                        response_msg=message
                                        )
            success = True
        else: 
            message = hierarchy_response.json()['message']
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Hierarchy',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=hierarchy_response.status_code,
                                        success_status='N',
                                        response_msg=message
                                        )
            raise ScalarException(message='TIP Hierarchy creation failed. Exceution terminated')
        
        # sync assets in provider org
        start_datetime = datetime.now()
        assetsync_response = requests.post(url+'/api/syncskytipasset', headers=headers)
        stop_datetime = datetime.now()
        if assetsync_response.status_code == 200:
            message = json.dumps(assetsync_response.json())
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Asset Sync',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=assetsync_response.status_code,
                                        success_status='Y',
                                        response_msg=message
                                        )
            success = True
        else:
            message = assetsync_response.json()['message']
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Asset Sync',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=assetsync_response.status_code,
                                        success_status='N',
                                        response_msg=message
                                        )
            raise ScalarException(message='TIP Asset Sync failed. Exceution terminated')

        # asset assignment in provider org
        start_datetime = datetime.now()
        assetassignment_response = requests.post(url+'/api/tip/assetassignment', headers=headers)
        stop_datetime = datetime.now()
        if assetassignment_response.status_code == 200:
            message = json.dumps(assetassignment_response.json())
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Asset Assignment',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=assetassignment_response.status_code,
                                        success_status='Y',
                                        response_msg=message
                                        )
            success = True
        else:
            message = assetassignment_response.json()['message']
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP Asset Assignment',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=assetassignment_response.status_code,
                                        success_status='N',
                                        response_msg=message
                                        )
            raise ScalarException(message='TIP Asset Assignment failed. Exceution terminated')
        
        # sync users in provider org
        start_datetime = datetime.now()
        usersync_response = requests.post(url+'/api/syncskytipuser', headers=headers)
        stop_datetime = datetime.now()
        if usersync_response.status_code == 200:
            message = json.dumps(usersync_response.json())
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP User Sync',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=usersync_response.status_code,
                                        success_status='Y',
                                        response_msg=message
                                        )
            success = True
        else:
            message = usersync_response.json()['message']
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP User Sync',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=usersync_response.status_code,
                                        success_status='N',
                                        response_msg=message
                                        )
            raise ScalarException(message='TIP User Sync failed. Exceution terminated')

        # users assignment in provider org
        start_datetime = datetime.now()
        userassignment_response = requests.post(url+'/api/tip/userassignment', headers=headers)
        stop_datetime = datetime.now()
        if userassignment_response.status_code == 200:
            message = json.dumps(userassignment_response.json())
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP User Assignment',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=userassignment_response.status_code,
                                        success_status='Y',
                                        response_msg=message
                                        )
            success = True
        else:
            message = userassignment_response.json()['message']
            insert_migration_record_in_db(db=db, 
                                        run_id=run_id, 
                                        process_name='TIP User Assignment',
                                        start_datetime=start_datetime,
                                        stop_datetime=stop_datetime,
                                        response_code=userassignment_response.status_code,
                                        success_status='N',
                                        response_msg=message
                                        )
            raise ScalarException(message='TIP User Assignment failed. Exceution terminated')

        if success == True:
            migrated_flag = 1
        else:
            migrated_flag = 0

        migration_status_from_db = db.get_session().query(SC_Migrated_SKY_Customer_To_Scalar).filter(SC_Migrated_SKY_Customer_To_Scalar.SKY_Company_id == 2006).first()
        if migration_status_from_db is None:
            db.get_session().add(SC_Migrated_SKY_Customer_To_Scalar(
                                SC_Organization_Id = '02a6443e-f197-41c6-89e5-c10435cf227c',
                                SC_Organization_Name = 'TIP HQ',
                                SKY_Company_id = '2006',
                                SKY_Company_Code = 'TIP_HQEUROPE',
                                FA_Root_Org_Id = None,
                                Migrated_Flag = migrated_flag
                                    )
                                )
        else:
            migration_status_from_db.Migrated_Flag = 1
        db.get_session().commit()
        
        response = Response(status=True, message="Tip End To End Migration process completed").getJsonResponse()
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
        subject=f"Tip End To End Migration process error report - " + env
        template_name='error_tip_migration_email.html'

        error_params={"environment": env, 
        "execution_time": datetime.now(),
        "error_message": str(e),
        }

        email.send_email(receivers=receivers, subject=subject, template_name=template_name,params=error_params)
        response = Response(message=str(e), status=False).getJsonResponse()
        return func.HttpResponse(
            response,
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )