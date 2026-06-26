from asyncio.log import logger
import json
from app.common.database import Database
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime
from app.common.models import Response
from app.common.constants import GeneralConstant
from app.common.helpers.common_services import pagination_check
from app.common.helpers.common_data_access import get_agreement_id
from app.common.helpers.common_services import get_scalar_api_error_messages
from app.common.scalar_api.session_api import get_all_sessions, create_session, get_all_sessions_for_a_framework
from app.common.database_model.scalar_tables import SC_Session

def start_data_sharing(db: Database, access_token:str, consumer_org_id: str, asset_list: list, provider_org_id: str, logger):
    new_sessions_details = list()
    existing_sessions_in_same_org = list()
    existing_sessions_in_different_org = list()
    combined_error_list = list()
    agreement_id = get_agreement_id(db=db, org_id=consumer_org_id)
    if agreement_id == None:
        combined_error_list.append(f"Agreement ID for organization (ID: {consumer_org_id}) doesn't exist (or) is inactive")
    else:
        agreement_id = agreement_id[0]
        # splitting list of Asset IDs into chunks of 25 to adjust for max limit of create_session api
        asset_list = [asset_list[i:i + 25] for i in range(0, len(asset_list), 25)]
    
        response_dict_list = []
        for i in range(len(asset_list)):
            session_api_response = create_session(access_token=access_token, assets=asset_list[i], agreement_id=agreement_id)
            attempt = GeneralConstant.RETRY_LIMIT
            while session_api_response.status_code == 429 and attempt > 0:
                logger.error("Too many requests. Waiting 12 seconds before attempting to create sessions")
                time.sleep(GeneralConstant.RETRY_WAITTIME)
                session_api_response = create_session(access_token=access_token, assets=asset_list[i], agreement_id=agreement_id)
                attempt = attempt - 1
                logger.info(f"Create session api attempts left: {attempt}")
            if session_api_response.status_code == 200 or session_api_response.status_code == 201:
                logger.info(f"Create sessions successful. Collecting responses")
                response_dict_list.extend(session_api_response.json())
            elif session_api_response.status_code == 400:
                logger.error(f"Create session api status code: 400, logging errors")
                combined_error_list.extend(handle_400_response(response=session_api_response))
            else:
                logger.error(f"Create session api status code: {session_api_response.status_code}, logging errors")
                combined_error_list.extend(get_scalar_api_error_messages(session_api_response))
                
        # Call get_all_sessions_for_framework API to fetch all the sessions details
        if len(response_dict_list)>0:
            all_sessions_df = get_session_data_by_framework(access_token = access_token, agreement_id=agreement_id, status='running')

        for response_dict in response_dict_list:
            error_set = set()
            running_session_found = all_sessions_df.loc[response_dict['assetId'] == all_sessions_df['providerAssetId']].to_dict(orient='records')

            if response_dict['statusCode'] == 400:
                if 'unexpected error' in response_dict['message'] or 'could not be linked' in response_dict['message']:
                    combined_error_list.extend([f"assetId: {response_dict['assetId']} {response_dict['message']}"])
                    continue
                #Active session might exist for another consumer org ID
                response_consumer_org_id = response_dict['overlappedDetails'][0]['consumerOrgId']
                if response_consumer_org_id == consumer_org_id:
                    if len(running_session_found) > 0:
                        #insert_update session record in db
                        insert_update_session_in_db(db=db, session_dict=running_session_found[0])
                        existing_sessions_in_same_org.append({"providerAssetId": response_dict['assetId'],
                                                        "consumerAssetId": running_session_found[0]['consumerAssetId'],
                                                        "message": response_dict['message']}) # 'message' fetched from response
                    else:
                        error_set.add(f"Overlapping session found, Consumer Asset ID not found in consumer org {consumer_org_id} for provider asset id {response_dict['assetId']}")
                else:
                    existing_sessions_in_different_org.append({"providerAssetId": response_dict['assetId'],
                                                    "consumerOrgId": response_dict['overlappedDetails'][0]['consumerOrgId'],
                                                    "message": response_dict['message']})

            elif response_dict['statusCode'] == 404 or ('Session created successfully' in response_dict['message'] \
                                                                                and response_dict['sessionId'] == None):
                error_set.add(f"Session for assetId: {response_dict['assetId']} not created (or) not found")

            else:
                if len(running_session_found) > 0:
                    new_sessions_details.append({"providerAssetId": response_dict['assetId'],
                                                "consumerAssetId": running_session_found[0]['consumerAssetId'],
                                                "sessionId": response_dict['sessionId']})
                    insert_update_session_in_db(db=db, session_dict=running_session_found[0])
                    logger.info("New session inserted in database.")
                else:
                    error_set.add(f"Session created, but Consumer Asset ID not yet created in consumer org {consumer_org_id} for provider asset id {response_dict['assetId']}")

            combined_error_list.extend(list(error_set))

    return new_sessions_details, existing_sessions_in_same_org, existing_sessions_in_different_org, combined_error_list

def insert_update_session_in_db(db: Database, session_dict:dict):
    db_session = db.get_session().query(SC_Session).filter(SC_Session.Session_Id == session_dict['sessionId']).first()
    if db_session is None:
        db.get_session().add(SC_Session(Session_Id = session_dict['sessionId'],
                                        Agreement_Id = session_dict['agreementId'],
                                        Provider_Organization_Id = session_dict['providerOrgId'],
                                        Consumer_Organization_Id = session_dict['consumerOrgId'],
                                        Provider_Asset_Id = session_dict['providerAssetId'],
                                        Consumer_Asset_Id = session_dict['consumerAssetId'],
                                        Provider_Unit_Nr = ''.join(session_dict['providerUnitIds']),
                                        Status = session_dict['status'],
                                        Real_Start = session_dict['realStart'],
                                        Active = 1
                                        )
        )
    else:
        db_session.Agreement_Id = session_dict['agreementId']
        db_session.Provider_Organization_Id = session_dict['providerOrgId']
        db_session.Consumer_Organization_Id = session_dict['consumerOrgId']
        db_session.Provider_Asset_ID = session_dict['providerAssetId']
        db_session.Consumer_Asset_Id = session_dict['consumerAssetId']
        db_session.Provider_Unit_Nr = ''.join(session_dict['providerUnitIds'])
        db_session.Status = session_dict['status']
        db_session.Real_Start = session_dict['realStart']
        db_session.Real_Stop = session_dict['realStop']
        db_session.Active = 1

    db.get_session().commit()
    
def get_session_data_by_framework(access_token: str, agreement_id: str, status: str):
    offset = 0
    session_data = pd.DataFrame()
    while offset is not None:
        response = get_all_sessions_for_a_framework(access_token=access_token, agreement_id=agreement_id, offset=offset, status=status)
        attempt = GeneralConstant.RETRY_LIMIT
        while response.status_code == 429 and attempt > 0:
            logger.error("Too many requests. Waiting 12 seconds before attempting to fetch sessions data")
            time.sleep(GeneralConstant.RETRY_WAITTIME)
            response = get_all_sessions_for_a_framework(access_token=access_token, agreement_id=agreement_id, offset=offset, status=status)
            attempt = attempt - 1
            logger.info(f"Fetch session data attempts left: {attempt}")
        if response.status_code == 200:
            all_data_json = json.loads(response.content)
            offset = pagination_check(content=all_data_json)
            session_data = pd.concat([session_data,pd.DataFrame(all_data_json["items"])], ignore_index=True)
        else:
            error_text = get_scalar_api_error_messages(error_response=response)[0]
            logger.error(f"fetching sessions for framework failed with status code {response.status_code} error: {error_text}")
            break
    return session_data

def handle_400_response(response:Response):
   errors = response.json()["errors"]
   error_list = list()
   if len(errors) != 0:
      if type(errors) is dict:
         for field, msg in errors.items():
            value = re.search('"(.*)"', msg[0]).group()
            if '[' not in field:
                  error_list.append(f"{field}: invalid value {value}")
            else:
                  error_list.append(f"{field.split('[')[0]}: invalid value {value}")
      if type(errors) is list:
         error_list.extend(get_scalar_api_error_messages(error_response=response))
   return error_list


def get_new_existing_missing_sessions_data(db_dataframe, api_dataframe, logger):
    all_sessions_api_list = api_dataframe["Session_Id"].tolist()
    all_sessions_db_list = db_dataframe["Session_Id"].tolist()

    new_sessions = set(all_sessions_api_list) - set(all_sessions_db_list)
    existing_sessions = set(all_sessions_api_list) - new_sessions
    missing_sessions = set(all_sessions_db_list) - set(all_sessions_api_list)
    
    new_sessions = list(new_sessions)
    existing_sessions = list(existing_sessions)
    missing_sessions = list(missing_sessions)
    logger.info(f"Total new sessions: {len(new_sessions)}")
    logger.info(f"Total existing sessions: {len(existing_sessions)}")
    logger.info(f"Total Missing sessions: {len(missing_sessions)}")

    new_sessions_to_insert = api_dataframe.loc[api_dataframe["Session_Id"].isin(new_sessions)]
    sessions_to_update = api_dataframe.loc[api_dataframe["Session_Id"].isin(existing_sessions)]
    sessions_to_deactivate = db_dataframe.loc[db_dataframe["Session_Id"].isin(missing_sessions)]

    new_sessions_to_insert["Active"] = 1
    sessions_to_update["Active"] = 1
    return new_sessions_to_insert, sessions_to_update, sessions_to_deactivate