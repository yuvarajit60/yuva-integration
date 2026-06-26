from app.common.database import Database
from pandas import DataFrame
from sqlalchemy import text

def get_scalar_role_mappings(db: Database, tip_employee, fr_role_id) -> DataFrame:
    query = text('''
                    SELECT SC_Role_Name
                    FROM SCALAR.SC_Role_Mapping(NOLOCK)
                    WHERE FR_Role_Id = :fr_role_id and Tip_Employee = :tip_employee
                ''')
    result = db.query(statement=query, params={"fr_role_id":fr_role_id, "tip_employee":tip_employee.upper()})
    return result