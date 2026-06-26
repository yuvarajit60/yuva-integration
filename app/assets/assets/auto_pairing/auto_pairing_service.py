
import pandas as pd
import random
import string
from asyncio.log import logger
from app.assets.auto_pairing.auto_pairing_data_access import add_new_pairing_info, add_new_pairing_info_in_history, delete_asset, get_pairing_info_for_device_number_with_other_asset, get_pairing_info_for_each_other, get_pairing_info_for_unit_nr_with_other_device, inactive_asset, unpair_current_pairing
from app.common.database import Database
from datetime import datetime
from app.common.constants import GeneralConstant

from app.common.exceptions import ScalarException
    

def save_pairing_info(db: Database, unit_nr: str, asset_id: str, 
                            device_number: str, device_type: str, pairing_date: datetime):

    device_pairing_info = get_pairing_info_for_device_number_with_other_asset(db=db, device_number=device_number, unit_nr=unit_nr)
    if len(device_pairing_info) > 0:
        for index,pairing in device_pairing_info.iterrows():
            # unpair the given unit from another device
            # unpair_current_pairing(db=db, unit_nr=pairing["Unit_Nr"],device_number=device_number)
            delete_asset(db=db,asset_id = pairing["Asset_Id"])
            add_new_pairing_info(db=db, unit_nr=pairing["Unit_Nr"], asset_id = pairing["Asset_Id"], 
                    device_imei=None, device_type=None, pairing_date=None, device_paired_by=None)
            add_new_pairing_info_in_history(db=db, unit_nr=pairing["Unit_Nr"], asset_id = pairing["Asset_Id"], 
                                device_imei=pairing["Device_Number"], device_type=pairing["Device_Type"], pairing_date=pairing["Device_Pairing_Date"], 
                                device_unpairing_date=pairing_date, device_paired_by= pairing["Device_Paired_By"])
    unit_pairing_info = get_pairing_info_for_unit_nr_with_other_device(db=db, device_number=device_number, unit_nr=unit_nr)
    if len(unit_pairing_info) > 0:
        for index,pairing in unit_pairing_info.iterrows():
            # so unpair the given device from another unit
            # unpair_current_pairing(db=db, unit_nr= unit_nr,device_number=pairing["Device_Number"])
            delete_asset(db=db,asset_id = pairing["Asset_Id"])
            add_new_pairing_info(db=db, unit_nr=pairing["Unit_Nr"], asset_id = pairing["Asset_Id"], 
                    device_imei=None, device_type=None, pairing_date=None, device_paired_by=None)
            add_new_pairing_info_in_history(db=db, unit_nr=pairing["Unit_Nr"], asset_id = pairing["Asset_Id"], 
                    device_imei=pairing["Device_Number"], device_type=pairing["Device_Type"], pairing_date=pairing["Device_Pairing_Date"], 
                    device_unpairing_date=pairing_date, device_paired_by= pairing["Device_Paired_By"])
    pairing_info = get_pairing_info_for_each_other(db=db, device_number=device_number, unit_nr=unit_nr)
    new_pairing= False
    if len(pairing_info) == 0 :
        # now pair them together
        # inactive_asset(db=db,asset_id= asset_id)
        # delete_asset(db=db,asset_id = asset_id)
        add_new_pairing_info(db=db, unit_nr=unit_nr, asset_id = asset_id, 
            device_imei=device_number, device_type=device_type, pairing_date=pairing_date, device_paired_by='AutoPairing')
        new_pairing =True
    return new_pairing
