from app.common.database import Database
from sqlalchemy import text
from datetime import date

def get_auto_pairing_log(db: Database, from_date: date, end_date: date):
    query = text('''WITH CTE AS (
                    SELECT *, row_number() OVER(PARTITION BY Event_Type, Device_Number,
                    Status,Reason ORDER BY Created_Date desc) AS row_num
                    FROM SCALAR.SC_Auto_Pairing_Log WHERE CONVERT(date, Created_Date) BETWEEN :from_date AND :end_date and ( Error_Ind = 1 OR Status = 'failed' )
                    )
                    SELECT Event_Type as 'Event Type', Device_Number as 'Device Number', AssetVIN, SensorVIN as 'SensorVIN',
                    Asset_Id as ' Scalar Asset Trailer Id',Error_Message as 'Error Message',
                    case when Reason is NULL then 'ManualUnpair' else Reason end as 'Reason',Latitude as 'Latittude', Longitude as 'Longitude', Event_Timestamp as 'Event Timestamp',
                    LEFT(Device_Number, CHARINDEX(':', Device_Number) - 1) as 'Device_Type', Created_Date as 'Log time'
                    FROM cte
                    WHERE row_num = 1 ORDER BY Created_Date
            ''')
    params={"from_date": from_date, "end_date": end_date}
    return db.query(statement=query, params=params, as_dataframe=True)
