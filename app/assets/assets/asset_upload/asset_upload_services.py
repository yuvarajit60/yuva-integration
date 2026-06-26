import time
import random
import string
from sqlalchemy import text # type: ignore
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Asset, SC_Asset_Group_Asset_Mapping
from app.common.constants import GeneralConstant
from app.common.helpers.common_services import get_scalar_api_error_messages, save_asset_group_in_db
from app.common.helpers.unit_helpers import add_asset_group_mapping_in_db
from app.common.helpers.asset_group_helper import assign_assets_to_assetgroup_in_scalar_and_db
from app.common.scalar_api.asset_group_api import assign_asset_to_assetgroup, create_asset_group
from app.assets.asset_upload.asset_upload_data_access import get_TIPGlobal_main_asset_group, get_child_asset_group_for_TIPGlobal_asset_group,\
    get_asset_mapping_to_country_group

def insert_update_asset_in_db(db:Database, asset_id, unit_nr, internal_code=None, device_number=None, pairing_status=None, pairing_date=None, device_type=None, fleet_id=None, vin_number=None, unit_license_number=None):
    db_asset_record = db.get_session().query(SC_Asset).filter(SC_Asset.Asset_Id == asset_id, SC_Asset.Active == 1).first()

    if db_asset_record is None:
        db.get_session().add(
            SC_Asset(Asset_Id = asset_id,
            Internal_Code = internal_code,
            Unit_Nr = unit_nr,
            Device_Number = device_number,
            Device_Pairing_Status = pairing_status,
            Device_Pairing_Date = pairing_date,
            Device_Type = device_type,
            Device_Paired_By = 'Scalar',
            Active = 1,
            Status = 'active',
            Fleet_Id = fleet_id,
            Unit_Licence_Nr = unit_license_number,
            VIN_Number = vin_number)
        )
    else:
        if internal_code is not None: 
            db_asset_record.Internal_Code = internal_code
        if device_number is not None: 
            db_asset_record.Device_Number = device_number
        if pairing_status is not None:
            db_asset_record.Device_Pairing_Status = pairing_status
        if pairing_date is not None:
            db_asset_record.Device_Pairing_Date = pairing_date
        if device_type is not None:
            db_asset_record.Device_Type = device_type
        if fleet_id is not None:
            db_asset_record.Fleet_Id = fleet_id
        if unit_license_number is not None:
            db_asset_record.Unit_Licence_Nr = unit_license_number
        if vin_number is not None:
            db_asset_record.VIN_Number = vin_number
        db_asset_record.Active = 1
        db_asset_record.Status = 'active'
        
    db.get_session().commit()

def assign_asset_to_asset_groups(logger,db: Database, tip_tmapi_access_token: str, asset_id_list: list, unit_nr:int,provider_org_id: str):
    # This code assigns asset to TIP Global Asset Group and the country asset group the asset belongs to
    # Find child asset group under TIP Global. Create if not present.
    error_list = []
    asset_limit = GeneralConstant.ASSET_LIMIT
    child_group_for_global_main_group= get_child_asset_group_for_TIPGlobal_asset_group(db=db, asset_limit=asset_limit)
    if len(child_group_for_global_main_group)==0:
        random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
        child_asset_group_name = GeneralConstant.TIPGLOBALCHILDGROUP
        TIPGlobal_main_asset_group= get_TIPGlobal_main_asset_group(db=db, org_id= provider_org_id)
        parent_group_details = TIPGlobal_main_asset_group.iloc[0]
        parent_group_id = parent_group_details["Asset_Group_Id"]
        parent_asset_group_name = parent_group_details['Asset_Group_Name']
        child_asset_group_name = f"{child_asset_group_name} - #Copy#{random_id}"
        asset_group_response = create_asset_group(access_token= tip_tmapi_access_token, name=child_asset_group_name,description=child_asset_group_name, parent_group_id=parent_group_id)
        if  asset_group_response.status_code == 201:
            asset_group_dict = asset_group_response.json()
            child_asset_group_id =asset_group_dict["id"] 
            save_asset_group_in_db(db=db, asset_group_id=child_asset_group_id, asset_group_name=child_asset_group_name, asset_group_description=child_asset_group_name, sc_organization_id=provider_org_id, root_group_id=parent_group_id, parent_group_id=parent_group_id, fa_root_org_id=None)  
        else:
            error_list.extend(get_scalar_api_error_messages(error_response=asset_group_response))
            raise Exception(message=f"Failed to create asset group for org {provider_org_id}-"+' '.join(map(str,error_list)))
    if len(child_group_for_global_main_group)>0:
        child_group_details = child_group_for_global_main_group.iloc[0]
        child_asset_group_id = child_group_details["Asset_Group_Id"]
        parent_asset_group_name = child_group_details['Parent_Asset_Group_Name']
        child_asset_group_name = child_group_details['Asset_Group_Name']
    # Assign to TIP Global Asset Group
    errors = assign_assets_to_assetgroup_in_scalar_and_db(db=db,logger=logger,access_token=tip_tmapi_access_token,
                                        asset_group_id=child_asset_group_id,
                                        asset_id_list=asset_id_list,
                                        error_list=error_list)
    if len(errors) > 0:
        logger.error(', '.join(errors))
    # Assign to country asset group
    group_mapping_df = get_asset_mapping_to_country_group(db=db, tip_unit_nr=unit_nr, provider_org_id = provider_org_id)
    if group_mapping_df.empty:
        return {"Child Asset Group Name": child_asset_group_name,
        "Main Asset Group Name": parent_asset_group_name,
        "Region": "Not Found",
        "Country": "Not Found"}
    
    errors = assign_assets_to_assetgroup_in_scalar_and_db(db=db,logger=logger,access_token=tip_tmapi_access_token,
                                        asset_group_id=group_mapping_df.loc[0, 'Country_Group_Id'],
                                        asset_id_list=asset_id_list,
                                        error_list=error_list)
    if len(errors) > 0:
        return {"Child Asset Group Name": child_asset_group_name,
        "Main Asset Group Name": parent_asset_group_name,
        "Region": "",
        "Country": "",
        "Message": f"Asset assignment to tip global successful, assignment to country group failed. Errors: {','.join(errors)}"}
    
    return {"Child Asset Group Name": child_asset_group_name,
        "Main Asset Group Name": parent_asset_group_name,
        "Region": group_mapping_df.loc[0, 'Region'],
        "Country": group_mapping_df.loc[0, 'Country']}
    
def remove_asset_assetgroup_mapping(db: Database, asset_id: str, asset_group_id:str):
    select_statement = text('''
                                UPDATE SCALAR.SC_Asset_Group_Asset_Mapping SET Active = 0, Modified_Date = getdate()
                                WHERE Asset_Id = :asset_id AND Asset_Group_Id = :asset_group_id AND Active = 1                            
                            ''')

    db.insert_update_delete_raw(statement=select_statement, params={"asset_id":asset_id, "asset_group_id":asset_group_id})

def deactivate_asset_in_db(db: Database, asset_id: str):
    select_statement = text('''
                                UPDATE SCALAR.SC_Asset SET Active = 0, Status = 'inActive', Modified_Date = getdate()
                                WHERE Asset_Id = :asset_id AND Active = 1                            
                            ''')

    db.insert_update_delete_raw(statement=select_statement, params={"asset_id":asset_id})
