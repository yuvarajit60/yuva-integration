import os
import urllib
import sqlalchemy
import pandas as pd 
import numpy as np
from sqlalchemy.sql.elements import TextClause

class FleetConnectedDatabase:
    def __init__(self):
        connection_string = os.environ["FC_DB_CONN"]
        params = urllib.parse.quote_plus(connection_string)
        self.engine = sqlalchemy.create_engine("mssql+pyodbc:///?odbc_connect={}".format(params), echo=True)
        Session = sqlalchemy.orm.sessionmaker(bind=self.engine)
        self.session = Session()
    

    def query(self, statement: TextClause, params_to_expand=list(), params=dict(), as_dataframe=False):
        if len(params_to_expand) > 0:
            statement = self.__bindparams(statement=statement, params_to_expand=params_to_expand)

        if as_dataframe:
            return pd.read_sql(statement, self.engine, params=params).replace({np.nan: None})

        return self.session.execute(statement, params).fetchall()
    
    def insert_update_delete_raw(self, statement: TextClause, params_to_expand=list(), params=dict()):
        if len(params_to_expand) > 0:
            statement = self.__bindparams(statement=statement, params_to_expand=params_to_expand)
        self.session.execute(statement, params)
        self.session.commit()