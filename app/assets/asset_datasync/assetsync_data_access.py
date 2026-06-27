from app.common.database import Database
from sqlalchemy import text
from pandas import DataFrame

def get_asset_table_data(db: Database) -> DataFrame:
    select_statement = text('''
                                SELECT Asset_Id assetId,Unit_Nr,Device_Number,Convert(Int,Device_Pairing_Status)Device_Pairing_Status,Device_Type,
                                CAST(Device_Pairing_Date AS DATETIME2)Device_Pairing_Date,Device_Paired_By,Convert(Int,Active)Active,Status,Fleet_Id
                                FROM SCALAR.SC_Asset (nolock) Order by Id                           
                            ''')
   
    return db.query(statement=select_statement, as_dataframe=True)

def add_asset_data_in_db(db: Database, new_asset_data):
    query = text('''INSERT INTO SCALAR.SC_Asset
                    (Asset_Id,Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
                    ,Device_Type,Device_Paired_By,Created_By,Created_Date,Modified_By,Modified_Date,Active,Status,Fleet_Id,Unit_Licence_Nr,VIN_Number)
                    VALUES 
                    (:assetId, :internalCode, :unit_nr, :devices, :devicestatus, CASE WHEN :devices IS NOT NULL THEN getdate() ELSE NULL END, :devicestype, CASE WHEN :devices IS NOT NULL THEN 'AssetSync' ELSE NULL END, 
                    'AssetSync', getdate(), 'AssetSync', getdate(),:active,:status,:fleet_id,:licensePlate,:vin)
                ''')
    batch_size = 1000
    new_asset_data_params = new_asset_data.to_dict('records')
    for curr_index in range(0, len(new_asset_data_params), batch_size): 
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def add_asset_data_in_history(db: Database, new_asset_data):
    query = text('''INSERT INTO SCALAR.SC_Asset_Pairing_History
                    (Asset_Id,Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
                    ,Device_Type,Device_Paired_By,Created_By,Created_Date,Modified_By,Modified_Date,Active,status,Device_Unpairing_Date)
                    VALUES 
                    (:assetId, :internalCode, :unit_nr, :Device_Number, :Device_Pairing_Status, :Device_Pairing_Date, :Device_Type, :Device_Paired_By, 
                    'AssetSync', getdate(), 'AssetSync', getdate(),'0', :status, getdate())
                ''')
    batch_size = 1000
    new_asset_data_params = new_asset_data.to_dict('records')
    for curr_index in range(0, len(new_asset_data_params), batch_size): 
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def update_asset_data_in_db(db: Database, existing_asset_data):

    query = text('''UPDATE SCALAR.SC_Asset WITH(ROWLOCK)
                    SET Internal_Code = :internalCode,Unit_Nr= :unit_nr
                    , Status= :status, Fleet_Id= :fleet_id, Unit_Licence_Nr= :licensePlate, VIN_Number= :vin
                    , Modified_By = 'AssetSync'
                    , Modified_Date = getdate()
                    WHERE Asset_Id = :assetId and Active=1
                ''')
    existing_asset_data_params = existing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def update_new_pairing_data_in_db(db: Database, update_new_pairing_data):

    query = text('''UPDATE SCALAR.SC_Asset WITH(ROWLOCK)
                    SET Device_Number = :devices,Device_Pairing_Status= :devicestatus,
                    Device_Type= :devicestype,Device_Pairing_Date=getdate(),
                    Active=1,Device_Paired_By='AssetSync',
                    Modified_By = 'AssetSync', Modified_Date = getdate()
                    WHERE Asset_Id = :assetId AND Device_Number IS NULL
                ''')
    existing_asset_data_params = update_new_pairing_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def unpairing_current_device(db: Database, unpairing_device_from_asset_in_DB):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Device_Pairing_Status = 0,
                        Active =0,
                        Device_Unpairing_Date = getdate(),
                        Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId AND Device_Number= :Device_Number
                    AND Device_Pairing_Status = 1
            ''')
    existing_asset_data_params = unpairing_device_from_asset_in_DB.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def inactive_asset_data(db: Database, new_asset_data):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Active =0, 
                        Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId 
                    AND Active = 1
            ''')
    new_asset_data_params = new_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(new_asset_data_params), batch_size):
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def remove_asset_data_in_db(db: Database, missing_asset_data):
    query = text('''UPDATE SCALAR.SC_Asset with(ROWLOCK)
                    SET Device_Pairing_Status = 0, Active=0, Status='inActive', Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId AND Active=1
                ''')
    existing_asset_data_params = missing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def delete_asset_data_in_db(db: Database, missing_asset_data):
    query = text('''DELETE from SCALAR.SC_Asset 
                    WHERE Asset_Id = :assetId 
                ''')
    existing_asset_data_params = missing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

# def add_asset_data(db: Database, new_asset_data):
#     query = text('''INSERT INTO SCALAR.SC_Asset
#                     (Asset_Id,Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
#                     ,Device_Type,Device_Paired_By,Created_By,Created_Date,Modified_By,Modified_Date,Active,status,Fleet_Id)
#                     VALUES 
#                     (:assetId, :internalCode, :unit_nr, :devices, :devicestatus, getdate(), :devicestype, 'AssetSync', 
#                     'AssetSync', getdate(), 'AssetSync', getdate(),:active,:status,:fleet_id)
#                 ''')
#     batch_size = 1000
#     new_asset_data_params = new_asset_data.to_dict('records')
#     for curr_index in range(0, len(new_asset_data_params), batch_size): 
#         curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
#         db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

# def truncate_asset_data(db: Database):
#     query = text('''TRUNCATE TABLE SCALAR.SC_Asset
#             ''')
#     return db.insert_update_delete_raw(statement=query)
