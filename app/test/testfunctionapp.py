from sqlalchemy import text
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
from app.common.constants import ContentType, ResponseCode
from app.common.models import Response
import logging
import json

addtestassetdata_bp = func.Blueprint()

@addtestassetdata_bp.function_name(name="Add_Test_Asset_Data")
@addtestassetdata_bp.route(route="addtestassetdata",  methods=[func.HttpMethod.POST])
@global_exception_handler
def addtestassetdata_api(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger = logging.getLogger("add_test_asset_data")
        db = Database()
        AssetId = req.get_json().get('AssetId')
        InternalCode = req.get_json().get('InternalCode')
        UnitNr = req.get_json().get('UnitNr')
        DeviceNumber = req.get_json().get('DeviceNumber')
        DevicePairingStatus = req.get_json().get('DevicePairingStatus')
        DevicePairingDate = req.get_json().get('DevicePairingDate')
        DeviceType = req.get_json().get('DeviceType')
        DevicePairedBy = req.get_json().get('DevicePairedBy')
        Status = req.get_json().get('Status')
        FleetId = req.get_json().get('FleetId')

        query = text('''UPDATE SCALAR.SC_Asset WITH(ROWLOCK)
                        SET Internal_Code = :Internal_Code,Unit_Nr= :Unit_Nr
                        , Device_Number = :Device_Number
                        , Device_Pairing_Status = :Device_Pairing_Status
                        , Device_Pairing_Date= :Device_Pairing_Date
                        , Device_Type = :Device_Type
                        , Device_Paired_By = :Device_Paired_By
                        , Status= :Status, Fleet_Id= :Fleet_Id
                        , Modified_By = 'testdata'
                        , Modified_Date = getdate()
                        WHERE Asset_Id = :Asset_Id
            ''')
        db.insert_update_delete_raw(statement=query, 
                                        params={"Asset_Id": AssetId, 
                                                "Internal_Code": InternalCode,
                                                "Unit_Nr": UnitNr,
                                                "Device_Number": DeviceNumber,
                                                "Device_Pairing_Status": DevicePairingStatus,
                                                "Device_Pairing_Date": DevicePairingDate,
                                                "Device_Type": DeviceType,
                                                "Device_Paired_By": DevicePairedBy,
                                                "Status" : Status,
                                                "Fleet_Id": FleetId
                                                })
        message = "Record_Updated!"
        logger.info(message)
        response = Response(status=True, message=message)
        return func.HttpResponse(
                response.getJsonResponse(),
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON)
    except Exception as e:
        logger.error(e, exc_info=True)
        status_code=getattr(e,'status_code',500)
        
        return func.HttpResponse(
            json.dumps({"error":repr(e)},default=str),
            status_code=status_code,
            mimetype=ContentType.APPLICATION_JSON
        )
