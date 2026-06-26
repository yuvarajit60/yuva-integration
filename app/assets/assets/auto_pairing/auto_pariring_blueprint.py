from datetime import datetime
from typing import ChainMap
import requests
import json
import os
import azure.functions as func
import logging

from app.assets.auto_pairing.auto_pairing_data_access import add_new_pairing_info, add_new_pairing_info_in_history, delete_asset, get_pairing_info_for_device_number, get_unit_for_unit_nr, log_auto_pairing_event, get_unit_for_asset_id,   unpair_current_pairing_device, unpairing_device
from app.assets.auto_pairing.auto_pairing_service import save_pairing_info
from app.assets.auto_pairing.auto_pairing_validator import AutoPairingBatchRequest, AutoPairingEventRequest
from app.common.exceptions import AutoPairingException, ScalarException
from app.common.helpers.common_data_access import get_tip_provider_organization, log_auto_pairing_failure_event
from app.common.helpers.common_services import  fetch_access_token
from app.common.models import Response
from app.common.database import Database
from app.common.constants import AutoPairingEvent, AutoPairingEventType, ContentType, GeneralConstant, ResponseCode
from app.common.exception_handler import global_exception_handler
from app.common.scalar_api.asset_group_api import assign_asset_to_assetgroup
from sqlalchemy.exc import SQLAlchemyError

autopairing_bp = func.Blueprint()

@autopairing_bp.function_name(name="Auto_Pairing")
@autopairing_bp.route(route="tip/asset/autopairing",  methods=[func.HttpMethod.POST])
@global_exception_handler
def autopairing_api(req: func.HttpRequest) -> func.HttpResponse:
    db = Database()
    logger = logging.getLogger("Auto_Pairing")
    output_data = []
    error_data =[]
    req_body = req.get_json()
    if req_body["eventsData"][0]["eventType"]=="test.ping":
        event_message = f"Event message processed successfully."
        response = {"status":True, "message":event_message}  
        return func.HttpResponse(
                json.dumps(response, default=str),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON)
    
    auto_pairing_req = AutoPairingBatchRequest.Schema().loads(json.dumps(req_body))
    logger.info(f"Auto pairing batch: {auto_pairing_req.eventBatchId}")
    event_BatchId = auto_pairing_req.eventBatchId
    event_SubscriptionId = auto_pairing_req.eventSubscriptionId
    event_BatchTime = auto_pairing_req.eventBatchTime.replace(tzinfo=None)
    events_Data = auto_pairing_req.eventsData

    if len(events_Data)==0:
        message=f"There is no event to process."
        raise ScalarException(message=message)
    
    for event in events_Data: 
        # record all pairing events
        event_log = log_auto_pairing_event(db=db, event_BatchId=event_BatchId, event_SubscriptionId=event_SubscriptionId, event_BatchTime=event_BatchTime, auto_pairing_req=event)
        try:
            eventdata = event.eventData
            event_type = event.eventType
            device_number = eventdata.unitId
            asset_id = eventdata.assetId
            reason = eventdata.reason
            pairing_date = eventdata.registeredOn.replace(tzinfo=None)
            device_type = device_number.split(':')[0]

            logger.info(f"Auto pairing event: {event_type}")
            pairing_message = "" 
            message= ""
                        
            if AutoPairingEventType.DEVICE_PAIRIED ==event_type:   
                if reason == AutoPairingEvent.DEVICE_SUCCESSFULLY_AUTO_PAIRED or reason == AutoPairingEvent.DEVICE_SUCCESSFULLY_MANUAL_PAIRED:
                    asset_record = get_unit_for_asset_id(db=db,asset_id=asset_id)
                    if asset_record is None:
                        message=f"Provided asset id {asset_id} does not exist in scalar."
                        log_auto_pairing_failure_event(db=db, message=message, event_log=event_log)
                        error_data.append({"eventtype":event_type, "device": device_number, "message": message})
                        continue
                        
                    else:
                        unit_nr=asset_record[0]
                        if unit_nr is None:
                                message=f"unit number not found for asset id- {asset_id} in scalar."
                                log_auto_pairing_failure_event(db=db, message=message, event_log=event_log)
                                error_data.append({"eventtype":event_type, "device": device_number, "message": message})
                                continue

                    if unit_nr is not None: 
                        new_pairing= save_pairing_info(db = db, unit_nr=unit_nr, asset_id = asset_id, 
                                            device_number=device_number, device_type=device_type, pairing_date=pairing_date)
                        if new_pairing:
                            pairing_message=f"Asset {asset_id} paired with device {device_number} successfully!"
                        else:
                            pairing_message=f"Asset {asset_id} paired with device {device_number} already in scalar!"
                        logger.info(pairing_message)
                else:
                    pairing_message=f"Failure pairing details saved in log table for {device_number}."
                    logger.info(pairing_message)
            elif AutoPairingEventType.DEVICE_UNPAIRED == event_type:
                asset_record = get_unit_for_asset_id(db=db,asset_id=asset_id)
                if asset_record is None:
                    message=f"Provided asset id {asset_id} does not exist in scalar."
                    log_auto_pairing_failure_event(db=db, message=message, event_log=event_log)
                    error_data.append({"eventtype":event_type, "device": device_number, "message": message})
                    continue
                device_pairing_info= get_pairing_info_for_device_number(db=db, device_number=device_number, asset_id= asset_id)
                if len(device_pairing_info) > 0:
                    unit_nr= device_pairing_info.iloc[0]["Unit_Nr"]
                    # unpair_current_pairing_device(db=db,device_number=device_number, asset_id= asset_id)
                    delete_asset(db=db,asset_id = asset_id)
                    add_new_pairing_info(db=db, unit_nr=unit_nr, asset_id = asset_id, 
                                    device_imei=None, device_type=None, pairing_date=None)
                    add_new_pairing_info_in_history(db=db, unit_nr=unit_nr, asset_id = asset_id, 
                        device_imei=device_number, device_type=device_type, pairing_date=pairing_date)
                    # unpairing_device(db=db,device_number=device_number, asset_id= asset_id)
                    pairing_message=f"Asset {asset_id} unpaired from device {device_number} successfully!"
                    logger.info(pairing_message)
                else:
                    pairing_message=f"Device {device_number} not paired with asset {asset_id} in scalar."
                    log_auto_pairing_failure_event(db=db, message=pairing_message, event_log=event_log)
                    error_data.append({"eventtype":event_type, "device": device_number, "message": pairing_message})
                    continue   
            else:
                error_message=f"Invalid event type- {event_type}. Please provide valid event type in request for device - {device_number}."
                log_auto_pairing_failure_event(db=db, message=error_message, event_log=event_log)
                error_data.append({"eventtype":event_type, "device": device_number, "message": error_message})
                continue
            logger.info(pairing_message)
            output_data.append({
                "eventtype":event_type,
                "device": device_number,
                "message": pairing_message
                })
        except SQLAlchemyError as sae:
            logger.error(sae, exc_info=True)
            error_message = GeneralConstant.DB_EXCP_MESSAGE
            log_auto_pairing_failure_event(db=db, message=error_message, event_log=event_log)
            error_data.append({"eventtype":event_type, "device": device_number, "message": error_message})
            continue    
        except Exception as e:
            logger.error(e, exc_info=True)
            error_message = "Application Exception"
            log_auto_pairing_failure_event(db=db, message=error_message, event_log=event_log)
            error_data.append({"eventtype":event_type, "device": device_number, "message": error_message})
            continue
    
    event_message = f"Event message processed successfully."
    response = {"status":True, "message":event_message}
    output_data.extend(error_data)
    final_output = response.copy()
    final_output['events'] = output_data   
    return func.HttpResponse(
            json.dumps(final_output, default=str),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)

    
   