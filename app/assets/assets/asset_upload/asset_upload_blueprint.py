import json
import logging
import os
import azure.functions as func
import pandas as pd
import numpy as np
from app.assets.asset_upload.asset_upload_data_access import get_customer_asset_details
from app.common.helpers.datasharing_helper import consumer_asset_name_change
from app.common.models import Response
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.constants import ContentType, ResponseCode, AudienceCode
from app.common.helpers.common_services import fetch_access_token, get_scalar_api_error_messages
from app.common.database_model.scalar_tables import SC_Asset, SC_Asset_Group_Asset_Mapping
from app.common.scalar_api.asset_api import create_asset, update_asset, get_specific_asset
from app.common.scalar_api.asset_group_api import unassign_asset_from_assetgroup
from app.common.helpers.common_data_access import get_tip_provider_organization

from app.assets.asset_upload.asset_upload_services import insert_update_asset_in_db, assign_asset_to_asset_groups, remove_asset_assetgroup_mapping, deactivate_asset_in_db

asset_upload_bp = func.Blueprint()

@asset_upload_bp.function_name(name="Asset_Upload_To_Scalar")
@asset_upload_bp.route(route="asset/upload",  methods=[func.HttpMethod.POST])
@global_exception_handler
def asset_upload_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Asset_Upload_To_Scalar")
    db = Database()
    asset_dict_list = req.get_json()
    
    if asset_dict_list is None or len(asset_dict_list) == 0 or not isinstance(asset_dict_list, list):
        message = f"Please provide valid asset details."
        logger.warning(message)
        response = Response(status=False, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.BAD_REQUEST,
                mimetype=ContentType.APPLICATION_JSON
            )

    tip_scalar_org_id = get_tip_provider_organization(db=db)
    if tip_scalar_org_id is None or len(tip_scalar_org_id) == 0:
        raise ScalarException(message="Provider organization details not found in DB.")
    tip_scalar_org_id = tip_scalar_org_id[0]
    tip_amapi_access_token = fetch_access_token(db=db, org_id=tip_scalar_org_id, audience=AudienceCode.ASSET)

    tip_tmapi_access_token = fetch_access_token(db=db, org_id=tip_scalar_org_id, audience=AudienceCode.TEAMS)


    fields = ["TIP Unit Nr","License Nr","Fleet Id","VIN Number","Category","Action",
        "Status","Message","Main Asset Group","Child Asset Group","Region","Country","Consumer Org Id","Customer Name"]
    asset_dataframe = pd.DataFrame(data=asset_dict_list, columns=fields)
    asset_dataframe = asset_dataframe.replace([np.nan, np.inf, -np.inf, ''], None)
    asset_dataframe["Message"] = ""

    logger.info("Starting asset actions:")

    for index,row in asset_dataframe.iterrows():

        try:
            if (row['TIP Unit Nr'] is None or not str(row['TIP Unit Nr']).isnumeric()) or (row['Action'] not in ['CREATE', 'UPDATE', 'DELETE']):
                asset_dataframe.loc[index,'Status'] = "False"
                asset_dataframe.loc[index,'Message'] = 'TIP Unit Nr (or) Action cannot be null (or) invalid.'
                continue

            db_asset_record = db.get_session().query(SC_Asset).filter(SC_Asset.Unit_Nr == row['TIP Unit Nr'], SC_Asset.Active==1).first()

            if row['Action'] == 'CREATE':
                row_dict = row[["License Nr","VIN Number","Category"]].to_dict()
                row_dict['licensePlate'] = row_dict.pop('License Nr')
                row_dict['vin'] = row_dict.pop('VIN Number')
                row_dict['assetCategory'] = row_dict.pop('Category')

                if any(val is None for val in row_dict.values()):
                    asset_dataframe.loc[index,'Status'] = "False"
                    asset_dataframe.loc[index,'Message'] = 'All of the fields (Category, License Nr, VIN Number) are mandatory.'
                    logger.info(asset_dataframe.loc[index, 'Message'])
                elif db_asset_record is None:
                    logger.info(f"Creating asset for Unit {row['TIP Unit Nr']}")
                    create_asset_response = create_asset(access_token=tip_amapi_access_token,
                                                asset_category=row['Category'],
                                                license_plate=row['License Nr'],
                                                tip_unit_nr=row['TIP Unit Nr'],
                                                customer_ref_no=row['Fleet Id'],
                                                vin= row['VIN Number'],
                                                group_ids=None,
                                                devices=[]
                                                )
                    if create_asset_response.status_code == 201:
                        logger.info(f"Asset created for unit {row['TIP Unit Nr']} successfully") 
                        response_json = create_asset_response.json()
                        if len(response_json['devices']) > 0:
                            device_type = response_json['devices'][0].split(":")[0]
                            device_number = response_json['devices'][0]
                            pairing_status = 1
                        else:
                            device_type = None
                            device_number = None
                            pairing_status = 0

                        insert_update_asset_in_db(db=db, asset_id=response_json['assetId'],
                                                    unit_nr=row['TIP Unit Nr'],
                                                    internal_code = response_json['internalCode'],
                                                    device_number=device_number,
                                                    device_type=device_type,
                                                        pairing_status = pairing_status,
                                                        fleet_id=response_json.get("fleetId", None),
                                                        vin_number= response_json.get("vinNumber", None),
                                                        unit_license_number= response_json.get("licensePlate", None)
                                                        ) 
                        logger.info(f"Asset info is saved in DB successfully")
                        asset_dataframe.loc[index,'Status'] = "True"
                        asset_dataframe.loc[index,'Message'] = f"Asset created and updated in DB successfully."

                        try:
                            asset_assignment_response = assign_asset_to_asset_groups(logger=logger,db=db, tip_tmapi_access_token=tip_tmapi_access_token,
                                                            asset_id_list=[response_json['assetId']],
                                                            unit_nr = row['TIP Unit Nr'],
                                                            provider_org_id=tip_scalar_org_id)
                        except Exception as e:
                            asset_dataframe.loc[index, 'Message'] += ' '+ str(e)
                            continue

                        if not isinstance(asset_assignment_response, list):
                            logger.info(f"Asset Assigned to Asset Group {asset_assignment_response['Child Asset Group Name']} under {asset_assignment_response['Main Asset Group Name']}")
                            asset_dataframe.loc[index, 'Main Asset Group'] = asset_assignment_response['Main Asset Group Name']
                            asset_dataframe.loc[index, 'Child Asset Group'] = asset_assignment_response['Child Asset Group Name']
                            asset_dataframe.loc[index, 'Region'] = asset_assignment_response['Region']
                            asset_dataframe.loc[index, 'Country'] = asset_assignment_response['Country']
                            if 'Message' in asset_assignment_response.keys():
                                asset_dataframe.loc[index,'Message'] = asset_assignment_response['Message']
                        else:
                            error_msg = f"Failed to assign asset of Unit {row['TIP Unit Nr']} to TIP Global Asset Group."
                            asset_dataframe.loc[index,'Message'] = error_msg
                    else:
                        asset_dataframe.loc[index,'Status'] = "False"
                        asset_dataframe.loc[index,'Message'] = ', '.join(get_scalar_api_error_messages(error_response=create_asset_response))
                        logger.info(f"Error creating asset for Unit Nr {row['TIP Unit Nr']}. Errors: {asset_dataframe.loc[index,'Message']}")
                else:
                    logger.info(f"Asset already exists for Unit {row['TIP Unit Nr']}. Cannot create.")
                    asset_dataframe.loc[index,'Status'] = "False"
                    asset_dataframe.loc[index,'Message'] = 'Asset already exists.'

            elif row['Action'] == 'UPDATE':
                row_dict = row[["License Nr","Fleet Id", "VIN Number","Category"]].replace({np.nan:None}).to_dict()
                row_dict['licensePlate'] = row_dict.pop('License Nr')
                row_dict['fleetId'] = row_dict.pop('Fleet Id')
                row_dict['vin'] = row_dict.pop('VIN Number')
                row_dict['assetCategory'] = row_dict.pop('Category')
                if row_dict['licensePlate'] is not None:
                    row_dict['displayName'] = f"{row['TIP Unit Nr']} ({row_dict['licensePlate']})"

                if db_asset_record is None:
                    logger.info(f"Asset does not exist exists for Unit {row['TIP Unit Nr']}. Cannot Update.")
                    asset_dataframe.loc[index,'Status'] = "False"
                    asset_dataframe.loc[index,'Message'] = 'Asset does not exist in DB. Update failed.'

                # Any one of vin number, licenseplate, fleetid, category should be present.
                elif all(val is None for val in row_dict.values()):
                    asset_dataframe.loc[index,'Status'] = "False"
                    asset_dataframe.loc[index,'Message'] = 'Atleast one of the fields in (Category, License Nr, Fleet Id, VIN Number) should not be null.'
                    logger.info(asset_dataframe.loc[index, 'Message'])

                else:
                    logger.info(f"Updating asset info for unit {row['TIP Unit Nr']}")
                    payload = {key: val for key, val in row_dict.items() if val is not None}

                    update_asset_response = update_asset(access_token=tip_amapi_access_token,
                                                    assetid=db_asset_record.Asset_Id,
                                                    json_payload=payload)
                    if update_asset_response.status_code == 200:
                        logger.info("Update Asset successful.")
                        response_json = update_asset_response.json()
                        if len(response_json['devices']) > 0:
                            pairing_status = 1
                            device_type = response_json['devices'][0].split(':')[0]
                            device_number = response_json['devices'][0]
                        else:
                            pairing_status = 0
                            device_type = None
                            device_number = None

                        vin_number = response_json.get("vin", None)
                        fleet_id = response_json.get("fleetId", None)
                        unit_license_nr =response_json.get("licensePlate", None)

                        insert_update_asset_in_db(db=db, asset_id=response_json['assetId'],
                                                    unit_nr=row['TIP Unit Nr'],
                                                    internal_code = response_json['internalCode'],
                                                        pairing_status = pairing_status,
                                                        device_number=device_number,
                                                        device_type=device_type,
                                                        fleet_id=fleet_id,
                                                        vin_number=vin_number,
                                                        unit_license_number=unit_license_nr
                                                        )
                        asset_dataframe.loc[index,'Status'] = "True"
                        asset_dataframe.loc[index,'Message'] = 'Asset updated in TIP Scalar successfully.'
                        try:
                            customer_asset_details = get_customer_asset_details(db= db, asset_Id=response_json['assetId'])
                            if len(customer_asset_details)>0:
                                customer_asset_details["VIN_Number"] = vin_number
                                customer_asset_details["UnitLicenceNr"] = unit_license_nr
                                customer_asset_details["Fleet_Id"] = fleet_id
                                consumer_org_id = customer_asset_details.loc[0,'SC_Organization_Id']
                                consumer_org_name = customer_asset_details.loc[0, 'SC_Organization_Name']
                                asset_assignment_response = consumer_asset_name_change(db= db, consumer_assets_df= customer_asset_details, consumer_org_id= consumer_org_id )
                                asset_dataframe.loc[index,'Message'] += ' Asset updated in customer successfully'
                                asset_dataframe.loc[index,'Consumer Org Id'] = consumer_org_id
                                asset_dataframe.loc[index,'Customer Name'] = consumer_org_name
                        except Exception as e:
                            asset_dataframe.loc[index,'Status'] = 'False'
                            asset_dataframe.loc[index, 'Message'] += ' '+ str(e)
                            continue
                    else:
                        asset_dataframe.loc[index,'Status'] = 'False'
                        asset_dataframe.loc[index,'Message'] = ','.join(get_scalar_api_error_messages(error_response=update_asset_response))
                        logger.info(f"Error occured while updating asset for unit {row['TIP Unit Nr']}. Errors: {asset_dataframe.loc[index,'Message']}")

            elif row['Action'] == 'DELETE':
                if db_asset_record is None:
                    asset_dataframe.loc[index,'Status'] = "False"
                    asset_dataframe.loc[index,'Message'] = f'Asset with Unit Number ({row["TIP Unit Nr"]}) does not exist or is already deleted.'
                    logger.info(asset_dataframe.loc[index, 'Message'])
                else:
                    # Unassign asset from assetgroup
                    db_assetgroup_asset_mapping = db.get_session().query(SC_Asset_Group_Asset_Mapping).filter(SC_Asset_Group_Asset_Mapping.Asset_Id == db_asset_record.Asset_Id, SC_Asset_Group_Asset_Mapping.Active == 1).all()
                    if len(db_assetgroup_asset_mapping) == 0:
                        pass
                    else:
                        for db_rec in db_assetgroup_asset_mapping:
                            remove_asset_assetgroup_mapping(db=db, asset_id=db_rec.Asset_Id, asset_group_id=db_rec.Asset_Group_Id)
                    api_assetgroup_mapping = get_specific_asset(access_token=tip_amapi_access_token, assetid=db_asset_record.Asset_Id)
                    if api_assetgroup_mapping.status_code == 200:
                        group_ids = api_assetgroup_mapping.json()['assignees']['groupIds']
                        if len(group_ids) > 0:
                            for group in group_ids:
                                unassign_asset_from_assetgroup(access_token=tip_tmapi_access_token, asset_ids=[db_asset_record.Asset_Id], asset_group_id=group)

                    delete_asset_response = update_asset(access_token=tip_amapi_access_token, 
                                                        assetid=db_asset_record.Asset_Id,
                                                            json_payload={"status": "inActive"})

                    if delete_asset_response.status_code == 200:
                        deactivate_asset_in_db(db=db, asset_id=db_asset_record.Asset_Id)

                        asset_dataframe.loc[index,'Status'] = "True"
                        asset_dataframe.loc[index,'Message'] = 'Asset deleted successfully'
                        logger.info(asset_dataframe.loc[index, 'Message'])
                    else:
                        asset_dataframe.loc[index,'Status'] = "False"
                        asset_dataframe.loc[index,'Message'] = ', '.join(get_scalar_api_error_messages(error_response=delete_asset_response))
                        logger.info(f"Error occured while deleting asset {row['TIP Unit Nr']}. Errors: {asset_dataframe.loc[index, 'Message']}")
        except Exception as e:
            logger.error(e, exc_info=True)
            asset_dataframe.loc[index,'Status'] = "False"
            asset_dataframe.loc[index, 'Message'] += ' ' + str(e)
            asset_dataframe.loc[index, 'Message'] = asset_dataframe.loc[index, 'Message'].strip()
            continue
        
    response_list = asset_dataframe.replace({np.nan:None}).to_dict('records')                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  

    return func.HttpResponse(
            json.dumps(response_list, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)