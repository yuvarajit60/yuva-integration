from app.common.constants import GeneralConstant
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Asset, SC_Asset_pairing_history, ScalarAutoPairingLog
from sqlalchemy import text
from datetime import datetime

def log_auto_pairing_event(db: Database, event_BatchId: str, event_SubscriptionId: str, event_BatchTime: datetime, auto_pairing_req):
        scalarAutoPairingLog = ScalarAutoPairingLog(
                Event_Batch_Id = event_BatchId,
                Event_Subscription_Id = event_SubscriptionId,
                Event_Batch_Time = event_BatchTime,
                Event_Type = auto_pairing_req.eventType,
                Event_Version = auto_pairing_req.eventVersion,
                Device_Number = auto_pairing_req.eventData.unitId,
                Asset_Id = auto_pairing_req.eventData.assetId,
                Candidate_Asset_Ids= None if auto_pairing_req.eventData.candidateAssetIds is None else ','.join(auto_pairing_req.eventData.candidateAssetIds),
                Organization_Id = auto_pairing_req.eventData.organizationId,
                AssetVIN = auto_pairing_req.eventData.assetVIN,
                SensorVIN = auto_pairing_req.eventData.sensorVIN,
                Error_Ind =0,
                Error_Message= None,
                Status = auto_pairing_req.eventData.status,
                Reason = auto_pairing_req.eventData.reason,
                Event_Timestamp = auto_pairing_req.eventData.registeredOn,
                #Latitude = None if auto_pairing_req.eventData.reason=="ManualPair" else auto_pairing_req.eventData.location.lat,
                Latitude = None if auto_pairing_req.eventData.location is None else auto_pairing_req.eventData.location.lat,
                #Longitude = None if auto_pairing_req.eventData.reason=="ManualPair" else auto_pairing_req.eventData.location.lon
                Longitude = None if auto_pairing_req.eventData.location is None else auto_pairing_req.eventData.location.lon
        )
        db.insert_orm(orm_item=scalarAutoPairingLog)
        return scalarAutoPairingLog


def get_unit_for_unit_nr(db: Database, unit_nr: str):
    query = text('''SELECT UnitNr, UnitLicenceNr,CustomerReferenceNr, br.Country,
                        CASE WHEN br.Region in ('UK Trailers & Ireland','UK & Ireland Tankers') THEN 'UK & Ireland'
	                    WHEN br.Region='Med' THEN 'Mediterranean' ELSE br.Region END Region, 
                        AssetLevel2, SerialNr 
                        FROM SCALAR.Fact_Unit (NOLOCK) fu
                        LEFT JOIN Floki.Dim_Branch (NOLOCK) br ON fu.OwningBranchNr = br.BranchNr
                        where UnitNr = :unit_nr
            ''')
    return db.query(statement=query, params={"unit_nr": unit_nr}, as_dataframe=True)


def get_unit_for_asset_id(db: Database, asset_id: str):
    query = text('''SELECT Unit_Nr FROM SCALAR.SC_Asset (NOLOCK)
                        WHERE Asset_Id = :asset_id
                        AND Active = 1
            ''')
    result= db.query(statement=query, params={"asset_id": asset_id})
    if len(result) > 0:
        return result[0]
    else:
        return None
    
def get_pairing_info_for_device_number_with_other_asset(db: Database, device_number: str, unit_nr: str):
    query = text('''SELECT CONVERT(VARCHAR,Unit_Nr)Unit_Nr,Asset_Id,Device_Pairing_Status,Device_Pairing_Date,Device_Type,Device_Number,Device_Paired_By FROM SCALAR.SC_Asset (NOLOCK)
                        WHERE Device_Number = :device_number
                        AND Device_Pairing_Status = 1 AND Active=1 AND Unit_Nr<>:unit_nr
            ''')
    return db.query(statement=query, params={"device_number": device_number,"unit_nr": unit_nr}, as_dataframe=True)
    
def get_pairing_info_for_unit_nr_with_other_device(db: Database, device_number: str, unit_nr: str):
    query = text('''SELECT Device_Number,Asset_Id,Device_Pairing_Status,Device_Pairing_Date,Device_Type,Unit_Nr,Device_Paired_By
                    FROM SCALAR.SC_Asset (NOLOCK)
                    WHERE Unit_Nr = :unit_nr AND Device_Pairing_Status = 1 AND Active=1  AND Device_Number<>:device_number
            ''')
    return db.query(statement=query, params={"unit_nr": unit_nr,"device_number": device_number}, as_dataframe=True)

def get_pairing_info_for_each_other(db: Database, device_number: str, unit_nr: str):
    query = text('''SELECT CONVERT(VARCHAR,Unit_Nr)Unit_Nr FROM SCALAR.SC_Asset (NOLOCK)
                        WHERE Device_Number = :device_number
                        AND Device_Pairing_Status = 1 AND Active=1 AND Unit_Nr=:unit_nr AND Device_Number=:device_number
            ''')
    return db.query(statement=query, params={"device_number": device_number,"unit_nr": unit_nr}, as_dataframe=True)


def unpair_current_pairing(db: Database, unit_nr: str, device_number: str):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Device_Pairing_Status = 0, Active=0, Modified_Date = getdate(), Modified_By = 'AutoPairing'
                    WHERE unit_nr = :unit_nr AND Device_Number = :device_number
                    AND Device_Pairing_Status = 1 AND Active=1
            ''')
    return db.insert_update_delete_raw(statement=query, params={"unit_nr": unit_nr, "device_number": device_number})

def get_pairing_info_for_device_number(db: Database, device_number: str, asset_id: str):
    query = text('''SELECT CONVERT(VARCHAR,Unit_Nr)Unit_Nr,Device_Pairing_Date,Device_Paired_By FROM SCALAR.SC_Asset (NOLOCK)
                        WHERE Device_Number = :device_number
                        AND Asset_Id= :asset_id
                        AND Device_Pairing_Status = 1 AND Active=1 
            ''')
    return db.query(statement=query, params={"device_number": device_number,"asset_id": asset_id}, as_dataframe=True)
 

def unpair_current_pairing_device(db: Database, device_number: str, asset_id: str):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Device_Pairing_Status = 0, Active=0, Modified_Date = getdate(), Modified_By = 'AutoPairing'
                    WHERE Device_Number = :device_number AND Asset_Id= :asset_id
                    AND Device_Pairing_Status = 1 AND Active=1
            ''')
    return db.insert_update_delete_raw(statement=query, params={"device_number": device_number,"asset_id": asset_id})

def unpairing_device(db: Database, device_number: str, asset_id: str):
    query = text('''UPDATE SCALAR.SC_Asset with(ROWLOCK)
                    SET Device_Pairing_Status = 0, Modified_Date = getdate(), Modified_By = 'AutoPairing'
                    WHERE Asset_Id= :asset_id
                    AND Device_Pairing_Status = 1 AND Active=1
            ''')
    return db.insert_update_delete_raw(statement=query, params={"device_number": device_number,"asset_id": asset_id})

def inactive_asset(db: Database, asset_id: str):
    query = text('''UPDATE SCALAR.SC_Asset with(ROWLOCK)
                    SET Active = 0, Modified_Date = getdate(), Modified_By = 'AutoPairing'
                    WHERE Asset_Id= :asset_id
                    AND Active = 1
            ''')
    return db.insert_update_delete_raw(statement=query, params={"asset_id": asset_id})

def delete_asset(db: Database, asset_id: str):
    query = text('''DELETE from SCALAR.SC_Asset 
                    WHERE Asset_Id = :asset_id
            ''')
    return db.insert_update_delete_raw(statement=query, params={"asset_id": asset_id})

def add_new_pairing_info(db: Database, unit_nr: str, asset_id: str,
                            device_imei: str, device_type: str, pairing_date: datetime, device_paired_by: str):

    db_record_found = db.get_session().query(SC_Asset).filter_by(Asset_Id = asset_id)\
                                                .filter_by(Unit_Nr = unit_nr).first()
    if db_record_found:
        db_record_found.Device_Number = device_imei
        db_record_found.Device_Pairing_Status = 1 if device_imei is not None else 0
        db_record_found.Device_Pairing_Date = pairing_date
        db_record_found.Device_Type = device_type
        db_record_found.Active=1
        db_record_found.Device_Paired_By = device_paired_by
        db.get_session().commit()
    else:
        pairing_record = SC_Asset(Asset_Id = asset_id,
                                        Internal_Code = unit_nr,
                                        Unit_Nr = unit_nr,
                                        Device_Number = device_imei,
                                        Device_Pairing_Status = 1 if device_imei is not None else 0,
                                        Device_Pairing_Date = pairing_date,
                                        Device_Type = device_type,
                                        Device_Paired_By = device_paired_by,
                                        Active = 1,
                                        Status = 'active',
                                        Created_By = 'AutoPairing',
                                        Modified_By = 'AutoPairing'
                                        )
        db.insert_orm(orm_item=pairing_record)
def add_new_pairing_info_in_history(db: Database, unit_nr: str, asset_id: str, 
                            device_imei: str, device_type: str, pairing_date: datetime, device_unpairing_date: datetime, device_paired_by: str):

    # db_record_found = db.get_session().query(SC_Asset_pairing_history).filter_by(Asset_Id = asset_id)\
    #                                             .filter_by(Unit_Nr = unit_nr)\
    #                                             .filter_by(Device_Pairing_Status = 0)\
    #                                             .filter_by(Device_Number=None).first()
    # if db_record_found:
    #     db_record_found.Device_Number = device_imei
    #     db_record_found.Device_Pairing_Status = 1
    #     db_record_found.Device_Pairing_Date = pairing_date
    #     db_record_found.Device_Type = device_type
    #     db_record_found.Active=1
    #     db_record_found.Device_Paired_By = 'Scalar'
    #     db.get_session().commit()
    # else:
    pairing_record = SC_Asset_pairing_history(Asset_Id = asset_id,
                                    Internal_Code = unit_nr,
                                    Unit_Nr = unit_nr,
                                    Device_Number = device_imei,
                                    Device_Pairing_Status = 1 if device_imei is not None else 0,
                                    Device_Pairing_Date = pairing_date,
                                    Device_Type = device_type,
                                    Device_Paired_By = device_paired_by,
                                    Active = 0,
                                    Status = 'active',
                                    Device_Unpairing_Date = device_unpairing_date,
                                    Created_By = 'AutoPairing',
                                    Modified_By = 'AutoPairing'
                                    )
    db.insert_orm(orm_item=pairing_record)
        





