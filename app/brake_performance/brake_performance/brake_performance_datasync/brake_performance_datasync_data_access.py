from app.common.database import Database
from sqlalchemy import text
from pandas import DataFrame

def get_brake_performance_db_data(db: Database) -> DataFrame:
    select_statement = text('''
                                SELECT Asset_Id assetId,EBPMS_State,EBPMS_State_Timestamp,Convert(Int,Active)Active
                                FROM SCALAR.SC_Asset_Brake_Performance_Activation (nolock) Order by Id                           
                            ''')
   
    return db.query(statement=select_statement, as_dataframe=True)

def add_brake_performance_data_in_db(db: Database, new_brake_performance_asset_data):
    query = text('''INSERT INTO SCALAR.SC_Asset_Brake_Performance_Activation
                    (Asset_Id,EBPMS_State,EBPMS_State_Timestamp,Active,Created_By,Created_Date,Modified_By,Modified_Date)
                    VALUES 
                    (:assetId, :ebpms, CAST(:ebpmsTimestamp AS DATETIME2), '1',
                    'Scalar', getdate(), 'Scalar', getdate())
                ''')
    batch_size = 1000
    new_brake_performance_data_params = new_brake_performance_asset_data.to_dict('records')
    for curr_index in range(0, len(new_brake_performance_data_params), batch_size): 
        curr_brake_performance_data_params = new_brake_performance_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_brake_performance_data_params)
        
def update_brake_performance_data_in_db(db: Database, existing_brake_performance_asset_data):

    query = text('''UPDATE SCALAR.SC_Asset_Brake_Performance_Activation WITH(ROWLOCK)
                    SET EBPMS_State = :ebpms,EBPMS_State_Timestamp= CAST(:ebpmsTimestamp AS DATETIME2)
                    , Active =1
                    , Modified_By = 'Scalar'
                    , Modified_Date = getdate()
                    WHERE Asset_Id = :assetId 
                ''')
    existing_brake_performance_data_params = existing_brake_performance_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_brake_performance_data_params), batch_size):
        curr_existing_brake_performance_data_params = existing_brake_performance_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_brake_performance_data_params)

def remove_brake_performance_asset_data_in_db(db: Database, missing_brake_performance_asset_data):
    query = text('''UPDATE SCALAR.SC_Asset_Brake_Performance_Activation with(ROWLOCK)
                    SET Active=0, Modified_Date = getdate(), Modified_By = 'Scalar'
                    WHERE Asset_Id = :assetId AND Active=1
                ''')
    existing_brake_performance_asset_data_params = missing_brake_performance_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_brake_performance_asset_data_params), batch_size):
        curr_existing_brake_performance_asset_data_params = existing_brake_performance_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_brake_performance_asset_data_params)