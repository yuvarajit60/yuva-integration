import pandas as pd
from asyncio.log import logger
import json
from sqlalchemy import text, update
import time

from app.common.constants import GeneralConstant
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Asset_Group_Team_Mapping, SC_Team
from app.common.exceptions import ScalarException
from app.common.helpers.common_data_access import get_asset_group_data, get_region_country_group_of_consumer, save_child_asset_group, \
                                                    save_main_asset_group, get_fa_organization_details
from app.common.helpers.common_services import get_scalar_api_error_messages, save_asset_group_in_db, pagination_check
from app.common.scalar_api.asset_group_api import create_asset_group, get_specific_asset_group, get_all_asset_groups, update_asset_group, assign_asset_to_assetgroup
from app.common.helpers.unit_helpers import add_asset_group_mapping_in_db, get_asset_api_data
from app.common.scalar_api.teams_api import assign_asset_groups_to_team

def assignteam_to_assetgroup(db: Database, asset_group_ids: list, team_id: str, org_id: str, access_token: str):

    assign_team_response = assign_asset_groups_to_team(access_token=access_token, team_id=team_id, asset_group_ids=asset_group_ids)
    attempt = GeneralConstant.ASSIGNMENT_LOOKUP_LIMIT
    while assign_team_response.status_code != 200 and attempt > 0:
        # to-do if exception needed to raise
        error_list = get_scalar_api_error_messages(error_response=assign_team_response)
        if "Team not found in organization. -" in error_list or "{0} is invalid. -" in error_list:
            logger.warning(f"Reattempting asset group to team assignment, remaining attempts: {attempt-1}")
            time.sleep(GeneralConstant.ASSIGNMENT_LOOKUP_WAITTIME)
            assign_team_response = assign_asset_groups_to_team(access_token=access_token, team_id=team_id, asset_group_ids=asset_group_ids)
            attempt = attempt - 1
        else:
            break
    if assign_team_response.status_code != 200:
        return f"Failed to assign team to asset group for org {org_id}-"+' '.join(map(str,error_list))
    
    for group_id in asset_group_ids:
        db_team_asset_group_mapping = db.get_session().query(SC_Asset_Group_Team_Mapping).filter(SC_Asset_Group_Team_Mapping.Asset_Group_Id == group_id, SC_Asset_Group_Team_Mapping.Team_Id == team_id).first()
        if db_team_asset_group_mapping is None:
            db.get_session().add(SC_Asset_Group_Team_Mapping(
                        Asset_Group_Id = group_id,
                        Team_Id = team_id,
                        Active = "1"
                    ))
        elif db_team_asset_group_mapping.Active == '0':
            db_team_asset_group_mapping.Active = '1'
        db.get_session().commit()
    return assign_team_response


def create_consumer_org_asset_group_in_provider(db: Database, provider_org_id: str, fa_root_org_id: str, access_token: str):
    consumer_asset_group_id_api = None
    message = ""
    asset_group_db_df = get_region_country_group_of_consumer(db=db, fa_root_organization_id=fa_root_org_id, provider_org_id=provider_org_id)
    region_asset_group_id =asset_group_db_df[asset_group_db_df['Asset_Group_Name'] == asset_group_db_df['Region_Name']].iloc[0]['Asset_Group_Id'] if not asset_group_db_df[asset_group_db_df['Asset_Group_Name'] == asset_group_db_df['Region_Name']].empty else None
    if region_asset_group_id is None:
        raise ScalarException(message="Region asset group not found in DB")
    
    if asset_group_db_df['Region_Name'].iloc[0] != "Europe":
        country_name = asset_group_db_df['Country_Name'].iloc[0]
        country_asset_group_id_api = get_specific_subgroup_id(access_token=access_token, asset_group_id=region_asset_group_id, sub_group_name=country_name)
        if isinstance(country_asset_group_id_api, list):
            raise ScalarException(message=f"Error occured while fetching subgroup details for region asset group {region_asset_group_id} "+' '.join(map(str,country_asset_group_id_api)))
    
        if country_asset_group_id_api is None:
            asset_group_response = create_asset_group(access_token= access_token, name=country_name,description="Country asset group", parent_group_id=region_asset_group_id)
            if asset_group_response.status_code == 201:
                logger.info("Country asset group in provider org created successfully!")
                asset_group_dict = asset_group_response.json()
                country_asset_group_id_api = asset_group_dict["id"]
            else:
                error_list = get_scalar_api_error_messages(error_response=asset_group_response)
                raise ScalarException(message=f"Failed to create country asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))
        
        save_asset_group_in_db(db=db, asset_group_id=country_asset_group_id_api, asset_group_name=country_name, asset_group_description="Country asset group", sc_organization_id=provider_org_id, root_group_id=region_asset_group_id, parent_group_id=region_asset_group_id, fa_root_org_id=None)
        logger.info("Country asset group details saved successfully in database!")
    else:
        country_asset_group_id_api = region_asset_group_id

    consumer_name = asset_group_db_df['Organization_Name'].iloc[0]
    consumer_asset_group_in_db = asset_group_db_df[asset_group_db_df['FA_Organization_Id'].notna() & ~asset_group_db_df['Asset_Group_Name'].str.contains('#Copy#')].iloc[0] if not asset_group_db_df[asset_group_db_df['FA_Organization_Id'].notna() & ~asset_group_db_df['Asset_Group_Name'].str.contains('#Copy#')].empty else None
    if consumer_asset_group_in_db is None:
        asset_group_response = create_asset_group(access_token= access_token, name=consumer_name,description="TIP Consumer Group", parent_group_id=country_asset_group_id_api)
        if  asset_group_response.status_code == 201:
            logger.info("Consumer asset group in provider org created successfully in Scalar.")
            asset_group_dict = asset_group_response.json()
            consumer_asset_group_id_api =asset_group_dict["id"]  
        else:
            error_list = get_scalar_api_error_messages(error_response=asset_group_response)[0]
            if "Group already exists." in error_list:
                asset_group_dict = get_asset_group_details_by_name(access_token=access_token, asset_group_name=consumer_name, fa_org_id= fa_root_org_id)
                if asset_group_dict is None or len(asset_group_dict) == 0:
                    message = f"Unable to fetch asset group details by name for {consumer_name} (ID: {fa_root_org_id})."
                    logger.error(message)
                    raise ScalarException(message=message)
                consumer_asset_group_id_api =asset_group_dict["id"]
            else:
                raise ScalarException(message=f"Failed to create asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))

        if consumer_asset_group_id_api is not None:
            save_asset_group_in_db(db=db, asset_group_id=consumer_asset_group_id_api,
                                    asset_group_name=consumer_name, 
                                    asset_group_description="TIP Consumer Group", 
                                    sc_organization_id=provider_org_id, 
                                    root_group_id=region_asset_group_id, 
                                    parent_group_id=country_asset_group_id_api, 
                                    fa_root_org_id=fa_root_org_id)
            logger.info("Asset group already exists. Details updated in database.")
            message += "Existing asset group details updated in database."

    elif consumer_asset_group_in_db['Asset_Group_Name'] != consumer_name:
        consumer_asset_group_id_api = consumer_asset_group_in_db["Asset_Group_Id"]
        asset_group_response = update_asset_group(access_token = access_token, 
                                    asset_group_id = consumer_asset_group_id_api, name= consumer_name,
                                    description="TIP Consumer Group")
        if  asset_group_response.status_code == 200:
            save_asset_group_in_db(db=db, 
                                   asset_group_id=consumer_asset_group_id_api, 
                                   asset_group_name=consumer_name, 
                                   asset_group_description="TIP Consumer Group", 
                                   sc_organization_id=provider_org_id, 
                                   root_group_id=region_asset_group_id, 
                                   parent_group_id=country_asset_group_id_api, 
                                   fa_root_org_id=fa_root_org_id)
        else:
            error_list = get_scalar_api_error_messages(error_response=asset_group_response)
            raise ScalarException(message=f"Failed to update asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))
    else:
        logger.info("Consumer asset group already present in provider org.")
        return consumer_asset_group_in_db["Asset_Group_Id"]
    
    logger.info("Consumer asset group details saved successfully in Scalar and DB.")
    return consumer_asset_group_id_api

def get_specific_subgroup_id(access_token: str, asset_group_id: str, sub_group_name: str):
    response = get_specific_asset_group(access_token=access_token, asset_group_id=asset_group_id)
    if response.status_code == 200:
            all_data_json = response.json()
            subgroups_df = pd.DataFrame(all_data_json["subGroups"],columns=['name','id'])

            return subgroups_df.loc[subgroups_df['name'] == sub_group_name]['id'].values[0] if subgroups_df.loc[subgroups_df['name'] == sub_group_name]['id'].empty!=True else None
    else:
        errors = get_scalar_api_error_messages(error_response=response)
        logger.error(f"{errors}")
        return 
    
def create_consumer_asset_group_in_api_db(db: Database,access_token: str, child_asset_group_name: str, root_asset_group_id: str, parent_asset_group_id: str, sc_organization_id: str, FA_Organization_Id: str):   
    message = ""
    scalar_child_asset_group_response = create_asset_group(access_token= access_token, name=child_asset_group_name,description=child_asset_group_name,parent_group_id=parent_asset_group_id)
    scalar_child_asset_group_dict ={}

    attempt = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
    while scalar_child_asset_group_response.status_code == 429 and attempt > 0:
        logger.info("Too many requests. Waiting 15 seconds before attempting to create another asset group.")
        time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
        scalar_child_asset_group_response = create_asset_group(access_token= access_token, name=child_asset_group_name,description=child_asset_group_name,parent_group_id=parent_asset_group_id)
        attempt = attempt - 1

    if scalar_child_asset_group_response.status_code == 429:
        message = f"Unable to create asset group for {child_asset_group_name} (ID: {FA_Organization_Id}). \
            Too many requests. Retry attempts exhausted."
        logger.error(message)
        raise ScalarException(message=message)
    elif  scalar_child_asset_group_response.status_code == 201:
        logger.info("Asset child group created successfully!")
        scalar_child_asset_group_dict = scalar_child_asset_group_response.json()
        scalar_child_asset_group_id =scalar_child_asset_group_dict["id"]
        save_asset_group_in_db(db=db, asset_group_id=scalar_child_asset_group_id, asset_group_name=child_asset_group_name, asset_group_description=child_asset_group_name, sc_organization_id=sc_organization_id, root_group_id=root_asset_group_id, parent_group_id=parent_asset_group_id, fa_root_org_id=FA_Organization_Id)
        logger.info("Asset child group details saved successfully in database!")
        message += "Asset group created successfully and updated in database"
    else:
        error_msg = get_scalar_api_error_messages(scalar_child_asset_group_response)[0]
        if "Group already exists." in error_msg:
            asset_group_dict = get_asset_group_details_by_name(access_token=access_token, asset_group_name=child_asset_group_name, fa_org_id= FA_Organization_Id)
            if asset_group_dict is None or len(asset_group_dict) == 0:
                message = f"Unable to fetch asset group details by name for {child_asset_group_name} (ID: {FA_Organization_Id})."
                logger.error(message)
                raise ScalarException(message=message)
            save_asset_group_in_db(db=db, asset_group_id=asset_group_dict['id'],
                                    asset_group_name=child_asset_group_name, 
                                    asset_group_description=child_asset_group_name, 
                                    sc_organization_id=sc_organization_id, 
                                    root_group_id=root_asset_group_id, 
                                    parent_group_id=parent_asset_group_id, 
                                    fa_root_org_id=FA_Organization_Id)
            logger.info("Asset group already exists. Details updated in database.")
            message += "Existing asset group details updated in database."
        else:
            message += f"Error creating asset group. Message: {error_msg}"
            logger.error(message)
            raise ScalarException(message=message)

    return scalar_child_asset_group_response


def get_asset_group_details_by_name(access_token: str, asset_group_name, fa_org_id):
    #Search by name, return details as dictionary
    offset = 0
    asset_group_dict_list = []
    asset_group_info = None
    while offset is not None:
        response = get_all_asset_groups(access_token=access_token, offset=offset)
        attempt = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
        while response.status_code == 429 and attempt > 0:
            logger.info("Too many requests. Waiting 15 seconds before attempting to fetch asset group details by name.")
            time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
            response = get_all_asset_groups(access_token=access_token, offset=offset)
            attempt = attempt - 1
        if response.status_code == 429:
            message = f"Unable to fetch asset group details by name for {asset_group_name} (ID: {fa_org_id}). \
            Too many requests. Retry attempts exhausted."
            logger.error(message)
            raise ScalarException(message=message)
        elif response.status_code == 200:
            all_data_json = json.loads(response.content)
            offset = pagination_check(content=all_data_json)
            asset_group_dict_list.extend(all_data_json["items"])
        else:
            error_text = get_scalar_api_error_messages(error_response=response)
            logger.error(f"{error_text}")
            break
    if len(asset_group_dict_list) > 0:
        for asset_group_dict in asset_group_dict_list:
            if asset_group_dict['name'] == asset_group_name:
                asset_group_info = asset_group_dict

    return asset_group_info


def create_asset_group_for_consumer_organization(db: Database, tmapi_access_token:str, fa_org_id: int, sc_org_id: str):
    end_response = {}
    end_response['asset_group_id'] = None

    fa_org_details_df = get_fa_organization_details(db=db, fa_org_id=fa_org_id)
    
    if fa_org_details_df is None or len(fa_org_details_df) == 0:
        end_response['message'] = "Corresponding FA Organization does not exist. Asset Group could not be created."
        logger.warning(end_response['message'])
        return end_response

    fa_org_details_dict = fa_org_details_df.to_dict('records')[0]

    if fa_org_details_dict['Root_Organization_Id'] is None and fa_org_details_dict['Parent_Organization_Id'] is None:
        end_response['message'] = "The Organization is a root organization. Asset Group could not be created."
        logger.warning(end_response['message'])
        return end_response

    parent_asset_group_details = get_asset_group_data(db=db, FA_Organization_Id=fa_org_details_dict['Parent_Organization_Id'], sc_organization_id=sc_org_id)
    
    if parent_asset_group_details is None or len(parent_asset_group_details) == 0:
        end_response['message'] = "Corresponding parent group does not exist. Asset Group could not be created."
        logger.warning(end_response['message'])
        return end_response

    create_asset_group_response = create_consumer_asset_group_in_api_db(db=db,access_token=tmapi_access_token,
                                        child_asset_group_name=fa_org_details_dict["Organization_Name"],
                                        root_asset_group_id=parent_asset_group_details[0][3],
                                        parent_asset_group_id=parent_asset_group_details[0][0],
                                        sc_organization_id=sc_org_id,
                                        FA_Organization_Id=fa_org_id)

    if create_asset_group_response.status_code == 200:    
        end_response['message'] = "Asset group created successfully."
        end_response['asset_group_id'] = create_asset_group_response.json()["groupId"]
        end_response['asset_group_name'] = fa_org_details_dict["Organization_Name"]
    else:
        error_msg = get_scalar_api_error_messages(create_asset_group_response)[0]
        if "Group already exists." in  error_msg:
            end_response["asset_group_name"] = error_msg.split(' - ')[1]
            asset_group_dict = get_asset_group_details_by_name(access_token=tmapi_access_token, 
                                                            asset_group_name=end_response["asset_group_name"])
            end_response["asset_group_id"] = asset_group_dict['id']
        else:
            end_response["message"] = error_msg
    return end_response

def remove_asset_group_mapping_from_db(db: Database, asset_nrs: list, group_id):
    query = text('''
                    UPDATE SCALAR.SC_Asset_Group_Asset_Mapping WITH(Rowlock)
                    SET Active='0', Modified_By='Scalar', Modified_Date=GETDATE()
                    WHERE Asset_Group_Id =:group_id AND Asset_Id IN :asset_nrs
            ''')
    params={"group_id": group_id, "asset_nrs": asset_nrs}
    db.insert_update_delete_raw(statement=query, params=params, params_to_expand=['asset_nrs'])

def fetch_all_assets_and_groups_from_api(db:Database, org_id):
    logger.info(f"Fetching all assets and their assetgroup details in {org_id}")
    asset_list_from_api = get_asset_api_data(db=db,org_id=org_id)
    asset_list_from_api["groupIds"] = asset_list_from_api["assignees"].apply(
                                            lambda x: x.get("groupIds", []) if isinstance(x, dict) else []
                                            )
    asset_data_df = asset_list_from_api[["assetId", "groupIds"]]
    asset_data_df = asset_data_df[asset_data_df["groupIds"].map(lambda x: bool(x))]

    asset_data_df = asset_data_df.explode("groupIds").reset_index(drop=True)

    return asset_data_df

def assign_assets_to_assetgroup_in_scalar_and_db(db:Database,logger, access_token ,asset_group_id,asset_id_list, error_list):
    # Assign asset to asset group - any
    assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                    asset_group_id=asset_group_id,
                                                    asset_ids=asset_id_list)
    
    attempt = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
    while assignment_response.status_code == 429 and attempt > 0:
        logger.info("Too many requests. Waiting 15 seconds before attempting to assign asset to asset group.")
        time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
        assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                    asset_group_id=asset_group_id,
                                                    asset_ids=asset_id_list)
        attempt = attempt - 1

    attempt = GeneralConstant.ASSIGNMENT_LOOKUP_LIMIT
    while assignment_response.status_code ==500 and attempt > 0:
        # retry asset assignemt 5 times
        error_msg = get_scalar_api_error_messages(error_response=assignment_response)[0]
        logger.error(error_msg)
        if "The AssigneeId {0} of type {1} was not found" in error_msg:
            logger.warning(f"Reattempting asset to assetgroup assignment, remaining attempts {attempt}")
            time.sleep(GeneralConstant.ASSIGNMENT_LOOKUP_WAITTIME)
            assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                    asset_group_id=asset_group_id,
                                                    asset_ids=asset_id_list)
            attempt = attempt - 1
        else:
            break

    # if all attempts exhausted and no successful response return error msg
    if assignment_response.status_code != 200:
        error_msg = get_scalar_api_error_messages(error_response=assignment_response)[0]
        logger.error(error_msg)
        error_list.append(error_msg)
        return error_list
    else:
        add_asset_group_mapping_in_db(db=db, asset_nrs=asset_id_list, group_id= asset_group_id)
        message = f"Assets assigned to Asset Group and the mapping is saved in DB successfully"
        logger.info(message)
        return []