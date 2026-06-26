from asyncio.log import logger
import json
import time
import pandas as pd
from pandas import DataFrame
from app.common.constants import GeneralConstant
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_Team, SC_User, SC_User_Role_Mapping
from app.common.exceptions import ScalarException
from app.common.func_validator import User
from app.common.helpers.common_data_access import get_all_scalar_region_group_ids, get_asset_group_data, get_fa_user_org_mapping_by_id, get_fa_user_region_mapping_by_id
from app.common.helpers.common_services import get_all_data, get_scalar_api_error_messages
from app.common.scalar_api.user_api import create_user, get_all_user, update_user
from app.common.scalar_api.teams_api import create_team
from app.common.helpers.asset_group_helper import create_asset_group_for_consumer_organization, get_specific_asset_group,assignteam_to_assetgroup
from app.common.helpers.team_helpers import create_team_into_db_api, get_team_info_by_name, assignuser_to_team


def get_user(db: Database, user_email: str, org_id: str, access_token: str):
    logger.info(msg=f"Getting user {user_email} from scalar api for org {org_id}")
    
    scalar_user_df = get_all_data(access_token=access_token,func=get_all_user)
    user = []
    email_ids = scalar_user_df['emailAddress'].str.lower().tolist()
    if len(email_ids) == 0 or user_email.lower() not in email_ids:
        user = None
    else:
        user = scalar_user_df.loc[scalar_user_df['emailAddress'].str.lower()==user_email.lower()]
        user['SC_Organization_Id'] = org_id
        for index,u in user.iterrows(): user = u
    return {('userId' if key == 'User_Id' else key): value for key,value in user.items()} if user is not None else None


def create_update_scalar_user(db: Database, user: User, scalar_org_id: str, access_token: str,fa_user_id: str):
    
    scalar_user = get_user(db=db, user_email=user.emailAddress, org_id=scalar_org_id, access_token=access_token)
    
    if scalar_user is None:
        user_response = create_user(access_token=access_token, user_req_body=user.__dict__)
        if user_response.status_code != 201:
            error_list = get_scalar_api_error_messages(error_response = user_response)
            raise ScalarException(message=f"Failed to create user for org {scalar_org_id}-"+' '.join(map(str,error_list)))
        else:
            user_response = json.loads(user_response.content)
            user_response['new_sc_user'] = True

        new_user = SC_User(User_Id = user_response['userId'], 
                                Login_Type = user.loginType, 
                                Status = "Pending", 
                                FA_User_Id = fa_user_id, 
                                SC_Organization_Id = scalar_org_id,
                                User_Email = user.emailAddress)
        add_roles_for_scalar_user_db(db=db, roles=user.roles, role_names=user.role_names, user_response=user_response)
        db.insert_orm(new_user)
    else:
       
        user.Status = 'Active'
        user_response = update_user(access_token=access_token, user_id=scalar_user['userId'], user_req_body=user.__dict__)
        if user_response.status_code != 200:
            error_list = get_scalar_api_error_messages(error_response=user_response)
            raise ScalarException(message=f"Failed to update user for org {scalar_org_id} "+' '.join(map(str,error_list)))
        else:
            user_response = json.loads(user_response.content)
            user_response['new_sc_user'] = False

        db_user_detail = db.get_session().query(SC_User).filter(SC_User.User_Id == scalar_user['userId']).first()
        if db_user_detail is None:
            db.get_session().add(SC_User(
                User_Id = user_response['userId'], 
                Login_Type = user_response['loginType'], 
                Status = user_response['status'], 
                FA_User_Id = fa_user_id, 
                SC_Organization_Id = scalar_org_id,
                User_Email = user_response['emailAddress']
                )
            )
        else:
            db_user_detail.Login_Type = user_response['loginType']
            db_user_detail.Status = user_response['status']
            db_user_detail.FA_User_Id = fa_user_id
            db_user_detail.SC_Organization_Id = scalar_org_id
            db_user_detail.User_Email = user_response['emailAddress']
        if user.roles is not None:
            add_roles_for_scalar_user_db(db=db, roles=user.roles, role_names=user.role_names, user_response=user_response)
        db.get_session().commit()

    return user_response


def add_roles_for_scalar_user_db(db: Database, roles: list, role_names: list, user_response: dict):
    db.get_session().query(SC_User_Role_Mapping).filter(SC_User_Role_Mapping.User_Id == user_response['userId']).delete()
    for i in range(len(roles)):
        db.get_session().add(SC_User_Role_Mapping(
            Role_Id = roles[i],
            User_Id = user_response['userId'],
            Role_Name = role_names[i]
            )
        )


def assign_user_to_team_and_asset_group(db: Database, tmapi_access_token: str, sc_user_id: str, 
                                            groups_df: DataFrame, sc_org_id: str):
    end_response = {}
    for index, row in groups_df.iterrows():
        logger.info(f"user {sc_user_id}, asset groups: {len(groups_df)}")
        team_id, team_name = get_team_id_from_asset_group(db=db, tmapi_access_token=tmapi_access_token, asset_group_id=row['Asset_Group_Id'], asset_group_name=row['Asset_Group_Name'], sc_org_id=sc_org_id)

        if "Error" in team_id:
            end_response["error"] = team_id

        if len(end_response) == 0:
            user_to_team_response = assignuser_to_team(db=db, 
                                user_ids=[sc_user_id], 
                                team_id=team_id,
                                team_name=team_name,
                                org_id=sc_org_id, 
                                access_token=tmapi_access_token)

            team_to_assetgroup_response = assignteam_to_assetgroup(db=db,
                                    asset_group_ids=[row['Asset_Group_Id']],
                                    team_id=team_id, 
                                    org_id=sc_org_id, 
                                    access_token=tmapi_access_token)

            if isinstance(user_to_team_response, str) and isinstance(team_to_assetgroup_response, str):
                #Both assign user to team and team to assetgroup failed
                end_response["error"] = user_to_team_response + ", "+ team_to_assetgroup_response
                logger.info(end_response["error"])

            elif isinstance(user_to_team_response, str) and not isinstance(team_to_assetgroup_response, str):
                # Only User to team assignment failed and team to assetgroup assignment successful
                end_response["error"] = user_to_team_response + ", "+ f"team to assetgroup assignment successful"
                logger.info(end_response["error"])

            elif not isinstance(user_to_team_response, str) and isinstance(team_to_assetgroup_response, str):
                # User to team assignment successful but team to assetgroup assignment failed
                end_response["error"] = "User to team assignment successful" + ", "+ team_to_assetgroup_response
                logger.info(end_response['error'])

    if len(end_response) == 0:
        end_response["success"] = f"User has been assigned to teams and assetgroups in Organization (ID: {sc_org_id})"
        logger.info(end_response["success"])
    return end_response

def get_team_id_from_asset_group(db, tmapi_access_token, asset_group_id, asset_group_name, sc_org_id):
    attempt = GeneralConstant.RETRY_LIMIT
    team_id = ""
    specific_asset_group_response = get_specific_asset_group(access_token=tmapi_access_token, asset_group_id=asset_group_id)
    logger.info(f"specific asset group response code: {specific_asset_group_response.status_code}")
    while specific_asset_group_response.status_code == 429 and attempt > 0:
        time.sleep(GeneralConstant.RETRY_WAITTIME)
        specific_asset_group_response = get_specific_asset_group(access_token=tmapi_access_token, asset_group_id=asset_group_id)
        attempt = attempt - 1
        logger.info(f"specific asset group api attempts left: {attempt}")
    while specific_asset_group_response.status_code == 500 and attempt > 0:
        error_text = get_scalar_api_error_messages(error_response=specific_asset_group_response)
        if 'HTTPSConnectionPool' in error_text:
            logger.info("Too many requests. Waiting 15 seconds before attempting to fetch asset group details.")
            time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
            specific_asset_group_response = get_specific_asset_group(access_token=tmapi_access_token, asset_group_id=asset_group_id)
            attempt = attempt - 1
            logger.info(f"specific asset group api attempts left: {attempt}")
        else:
            logger.error(f"{error_text}")
            break
    if specific_asset_group_response.status_code == 200:
        specific_asset_group = specific_asset_group_response.json()
        team_name = asset_group_name + " Team"
    else:
        raise ScalarException(message=f"Error fetching specific asset group details: {get_scalar_api_error_messages(specific_asset_group_response)[0]} (Org ID: {sc_org_id})")

    if len(specific_asset_group["teamIds"]) == 0:
        # if no teams are assigned to assetgroup, create a team
        create_team_response = create_team_into_db_api(db=db, access_token=tmapi_access_token, team_name= team_name, org_id=sc_org_id)
        if isinstance(create_team_response, dict):
            team_id = create_team_response["id"]
        elif isinstance(create_team_response, list):
            team_id =  f"Error creating team: {create_team_response} (Org ID: {sc_org_id})"
    else:
        # if any team is found assigned to group then find a existing team with matching name or take a team from the assigned teams 
        team_info = get_team_info_by_name(tmapi_access_token=tmapi_access_token, team_name=team_name)
        if team_info is None: #or team_info["id"] not in specific_asset_group["teamIds"]:
            create_team_response = create_team(access_token=tmapi_access_token, teamName= team_name, description=team_name)
            if create_team_response.status_code == 200 or create_team_response.status_code == 201:
                team_id = create_team_response.json()["id"]
                db.get_session().add(SC_Team(
                    Team_Id = create_team_response.json()['id'],
                    Team_Name = team_name,
                    Active = "1",
                    Description = team_name,
                    SC_Organization_Id = sc_org_id
                    )
                )
            else:
                logger.warning(f"Could not create new team so selecting existing team for user assignment")
                team_id = specific_asset_group["teamIds"][0]
        else:
            team_id = team_info["id"]

    return team_id, team_name

def user_assignment(db: Database, user: User, sc_org_id: str, fa_user_dict: dict, scalar_user_id: str, tmapi_access_token: str, logger):
    #User assignment starts here 
    logger.info("User assignment process started")
    if fa_user_dict['Tip_User'] in ('Y', 'y'):
        #TIP User Assignment to Region based asset groups

        if fa_user_dict['Role_Id'] is None or fa_user_dict['Role_Id'] not in (1,2,4):
            message = "No FA role info found for user. TIP Group and team assignment failed."
            logger.error(message)
            return {"error": message}
        
        #Fetch all region group ids
        all_scalar_region_group_ids_df = get_all_scalar_region_group_ids(db=db)
        if fa_user_dict['Role_Id'] == 4: # FA Role ID 4 = Super Admin
            #Assign to all regions assetgroups
            groups_df = all_scalar_region_group_ids_df
        elif fa_user_dict['Role_Id'] == 1: # FA Role ID 1 = Super User
            # assign to EU+User's region
            user_region_mapping_df = get_fa_user_region_mapping_by_id(db=db, fa_user_id=user.faUserId)
            region_names = user_region_mapping_df['Region_Name'].to_list()
            groups_df = all_scalar_region_group_ids_df.loc[all_scalar_region_group_ids_df['Asset_Group_Name'].isin(set(region_names + ["Europe"]))]

        # Role ID 2 = TIP Account User - Only the user mapped assetgroups. Don't add Europe
        elif fa_user_dict['Role_Id'] == 2:
            user_region_mapping_df = get_fa_user_region_mapping_by_id(db=db, fa_user_id=user.faUserId)
            region_names = user_region_mapping_df['Region_Name'].to_list()
            groups_df = all_scalar_region_group_ids_df.loc[all_scalar_region_group_ids_df['Asset_Group_Name'].isin(set(region_names))]
        
        if groups_df is None or len(groups_df) == 0:
                return {"error": "User Region mapping details not found. TIP Group and team assignment failed."}
    else:
        #External user may belong to multiple orgs
        fa_user_org_mapping_df = get_fa_user_org_mapping_by_id(db=db, fa_user_id=user.faUserId)

        if fa_user_org_mapping_df is None or len(fa_user_org_mapping_df) == 0:
            message = "FA User Org mapping details not found. Group assignment unsuccessful."
            logger.warning(message)
            return {"error": message}

        groups_df = pd.DataFrame(columns=["Asset_Group_Id", "Asset_Group_Name"]) 
        for index, row in fa_user_org_mapping_df.iterrows():
            #Search if asset group is already present, create if not present.
            asset_group_data = get_asset_group_data(db=db, FA_Organization_Id=row['Organization_Id'], sc_organization_id=sc_org_id)
            if asset_group_data is None or len(asset_group_data) == 0:
                logger.info("Scalar Asset Group data not found. Creating a group.")
                if row['Organization_Id'] == fa_user_dict['FA_Root_Organization_Id']:
                    message = "Root group does not exist. User Assignment to Group and team failed."
                    logger.warning(message)
                    return {"error": message}

                create_asset_group_response = create_asset_group_for_consumer_organization(db=db, 
                                                                        tmapi_access_token=tmapi_access_token,
                                                                        fa_org_id=row['Organization_Id'], 
                                                                        sc_org_id=sc_org_id)
                # If assetgroup creation failed for some reason
                if create_asset_group_response['asset_group_id'] == None:
                    message = create_asset_group_response['message']
                    return {"error": message}

                groups_df = pd.concat([groups_df, 
                                       pd.DataFrame(
                                                    [{"Asset_Group_Id": create_asset_group_response['asset_group_id'],
                                                    "Asset_Group_Name": create_asset_group_response['asset_group_name']}]
                                                    )
                                        ],ignore_index=True)
            else:
                #If assetgroup exists
                groups_df = pd.concat([groups_df, 
                                       pd.DataFrame(
                                                    [{"Asset_Group_Id": asset_group_data[0][0], 
                                                    "Asset_Group_Name": asset_group_data[0][1]}]
                                                    )
                                        ],ignore_index= True)
    
    #Assigning user to team and asset group                
    message = assign_user_to_team_and_asset_group(db=db, 
                                                    tmapi_access_token=tmapi_access_token, 
                                                    sc_user_id=scalar_user_id,
                                                    groups_df = groups_df,
                                                    sc_org_id=sc_org_id)
    return message