
import pandas as pd
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from sqlalchemy import text
import numpy as np
import logging
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response

loadexceldataintotemdb_bp = func.Blueprint()

@loadexceldataintotemdb_bp.function_name(name="Load_Excel_Data_Into_Temp_Table")
@loadexceldataintotemdb_bp.route(route="loadexceldataintotemdb",  methods=[func.HttpMethod.POST])
@global_exception_handler
def addtestassetdata_api(req: func.HttpRequest) -> func.HttpResponse:
    db = Database()
    logger = logging.getLogger("Load_Excel_Data_Into_Temp_Table")
    file_path = r"D:\Scalar Project\Document\Pairing dates update 15052026.xlsx"

    excel_df = pd.read_excel(file_path)

    excel_df = excel_df.replace({np.nan: None})
    excel_df['SubcontractingStartDate'] = pd.to_datetime(excel_df['SubcontractingStartDate'], errors='coerce')
    excel_df['SubcontractingStartDate'] = excel_df['SubcontractingStartDate'].apply(
    lambda x: x.replace(tzinfo=None) if pd.notnull(x) else None
)

    query = text('''
            INSERT INTO SCALAR.Temp_Pairing_Dates_To_Update
            (UnitNr,TenancyName,IsSubcontracted,SubcontractingStartDate,SubcontractingEndDate,PairingStatus,
                ModemPairingDate,OrigPairingdate,ModemNumber)
            VALUES
            (:UnitNr,:TenancyName,:IsSubcontracted,:SubcontractingStartDate,:SubcontractingEndDate,:PairingStatus,
                :ModemPairingDate,:OrigPairingdate,:ModemNumber
            ); 
                 ''')
    batch_size = 1000
    new_params = excel_df.to_dict('records')
    for curr_index in range(0, len(new_params), batch_size): 
        curr_new_params = new_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_params)
    
    message = "Excel data has inserted in temp table!"
    logger.info(message)
    response = Response(status=True, message=message)
    return func.HttpResponse(
            response.getJsonResponse(),
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON)

   
