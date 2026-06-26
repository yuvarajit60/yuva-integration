import os
import logging
import json
import azure.functions as func
from datetime import datetime
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.data_sharing.session_datasync.sessionsync_data_access import get_all_sessions_from_database, add_new_session_data_into_db, update_existing_sessions_data_into_db, deactivate_sessions_missing_in_api
from app.data_sharing.session_datasync.sessionsync_services import get_all_sessions_from_api, send_session_sync_report
from app.common.helpers.session_helpers import get_new_existing_missing_sessions_data
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.constants import AudienceCode

sessionsync_bp = func.Blueprint() 


@sessionsync_bp.function_name(name="Sync_Session_Data")
@sessionsync_bp.route(route="syncsessiondata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def session_datasync(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("sync_session_data")
    db = Database()
    try:
        provider_organization = get_tip_provider_organization(db=db)
        if provider_organization is None:
            raise ScalarException(message="Provider Organization is not found")

        provider_organization_id = provider_organization[0]
        access_token = fetch_access_token(db=db,org_id= provider_organization_id,audience= AudienceCode.DATA_SHARING)

        all_sessions_data_from_db = get_all_sessions_from_database(db=db)
        logger.info(f"Total number of sessions found in the database: {len(all_sessions_data_from_db)}")
        all_sessions_data_from_api = get_all_sessions_from_api(access_token= access_token, logger=logger)
        logger.info(f"Total number of sessions from the API: {len(all_sessions_data_from_api)}")

    # all_sessions_data_from_api = None

        if all_sessions_data_from_api is not None and len(all_sessions_data_from_api) > 0:

            new_sessions_to_insert, sessions_to_update, sessions_to_deactivate = get_new_existing_missing_sessions_data(db_dataframe=all_sessions_data_from_db, api_dataframe=all_sessions_data_from_api, logger=logger)
            logger.info(f"New sessions to be inserted: {len(new_sessions_to_insert)}")
            logger.info(f"Existing sessions to be updated: {len(sessions_to_update)}")
            logger.info(f"Missing sessions to be deactivated: {len(sessions_to_deactivate)}")
            if len(new_sessions_to_insert) > 0:
                add_new_session_data_into_db(db=db, new_sessions_to_insert=new_sessions_to_insert)
            if len(sessions_to_update) > 0:
                update_existing_sessions_data_into_db(db=db, sessions_to_update=sessions_to_update)
            if len(sessions_to_deactivate) > 0:
                deactivate_sessions_missing_in_api(db=db, sessions_to_deactivate= sessions_to_deactivate)

            api_response = {"Total session to be synced": len(all_sessions_data_from_api),
                        "New Sessions added": len(new_sessions_to_insert),
                        "Existing sessions updated": len(sessions_to_update),
                        "Deactivated sessions": len(sessions_to_deactivate),
                        }
            env = os.environ["SCALAR_ENV"]
            params={"environment": env, 
            "exectution_time": datetime.now(), 
            "sessions_from_db": len(all_sessions_data_from_db), 
            "sessions_from_api": len(all_sessions_data_from_api),
            "new_sessions_added":len(new_sessions_to_insert),
            "existing_sessions_updated":len(sessions_to_update),
            "deactivated_sessions": len(sessions_to_deactivate)
            }
            send_session_sync_report(new_sessions_to_insert=new_sessions_to_insert, 
                                sessions_to_update=sessions_to_update, 
                                sessions_to_deactivate=sessions_to_deactivate, params=params)

        else:
            logger.error(f"Fetching Sessions data has failed")
            api_response = {"Error": "Could not fetch sessions data"}
        
        return func.HttpResponse(
        json.dumps(api_response, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)

    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        env = os.environ['SCALAR_ENV']
        email=Email()
        receivers=os.environ["REPORT_MAIL_DL"].split(",")
        subject=f"Scalar - Data Sync Error: Session sync report"
        if os.environ['SCALAR_ENV'] != 'PROD':
            subject=f"{subject} - {env}"
        template_name='error_session_email.html'

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
