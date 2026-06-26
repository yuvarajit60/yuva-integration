import pandas as pd
from sqlalchemy import text
from app.common.database import Database

def get_all_sessions_from_database(db: Database) -> pd.DataFrame:
    query_statement = text('''SELECT Session_Id, Agreement_Id, Provider_Organization_Id, Consumer_Organization_Id, Status, Real_Start,
                            Real_Stop, Desired_Start, Desired_Stop, Provider_Unit_Nr, Provider_Asset_Id, Consumer_Asset_Id,
                            Active, Created_By, Created_Date
                            FROM SCALAR.SC_Session(NOLOCK)''')
    return db.query(statement=query_statement, as_dataframe=True)


def add_new_session_data_into_db(db: Database, new_sessions_to_insert):
    query = text('''INSERT INTO SCALAR.SC_Session
                    (Session_Id, Agreement_Id, Provider_Organization_Id, Consumer_Organization_Id, Status, Real_Start,
                    Real_Stop, Desired_Start, Desired_Stop, Provider_Unit_Nr, Provider_Asset_Id, Consumer_Asset_Id,
                    Active, Created_By, Created_Date, Modified_By, Modified_Date)
                    VALUES 
                    (:Session_Id, :Agreement_Id, :Provider_Organization_Id, :Consumer_Organization_Id, :Status, :Real_Start,
                    :Real_Stop, :Desired_Start, :Desired_Stop, :Provider_Unit_Nr, :Provider_Asset_Id, :Consumer_Asset_Id,
                    :Active, :Created_By, :Created_Date, 'script', getdate())
                ''')
    batch_size = 1000
    new_sessions_params = new_sessions_to_insert.to_dict('records')
    for curr_index in range(0, len(new_sessions_params), batch_size): 
        curr_new_sessions_params = new_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_sessions_params)


def update_existing_sessions_data_into_db(db: Database, sessions_to_update):
    query = text('''UPDATE SCALAR.SC_Session WITH(Rowlock)
                    SET Agreement_Id = :Agreement_Id, Provider_Organization_Id = :Provider_Organization_Id, 
                    Consumer_Organization_Id = :Consumer_Organization_Id, Status = :Status, Real_Start = :Real_Start,
                    Real_Stop = :Real_Stop, Desired_Start = :Desired_Start, Desired_Stop = :Desired_Stop, 
                    Provider_Unit_Nr = :Provider_Unit_Nr, Provider_Asset_Id = :Provider_Asset_Id, 
                    Consumer_Asset_Id = :Consumer_Asset_Id,Active = :Active, Created_By = :Created_By, 
                    Created_Date = :Created_Date, Modified_By = 'script', Modified_Date = getdate()
                    WHERE Session_Id = :Session_Id
                    ''')
    batch_size = 1000
    update_sessions_params = sessions_to_update.to_dict('records')
    for curr_index in range(0, len(update_sessions_params), batch_size): 
        curr_update_params = update_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_update_params)

def deactivate_sessions_missing_in_api(db: Database, sessions_to_deactivate):
    query = text('''UPDATE SCALAR.SC_Session WITH(Rowlock)
                    SET Active = 0, Modified_By = 'script', Modified_Date = getdate()
                    WHERE Session_Id = :Session_Id
                    ''')
    batch_size = 1000
    deactivate_sessions_params = sessions_to_deactivate.to_dict('records')
    for curr_index in range(0, len(deactivate_sessions_params), batch_size): 
        curr_deactivate_params = deactivate_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_deactivate_params)