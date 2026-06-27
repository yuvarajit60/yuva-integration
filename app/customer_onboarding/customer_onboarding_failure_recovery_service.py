import os
import pandas as pd
from app.common.constants import GeneralConstant
from app.common.database import Database
from app.common.exceptions import ScalarException
from app.common.helpers.asset_group_helper import get_asset_group_details_by_name
from app.common.helpers.common_data_access import get_FA_organization_hierarchy, get_agreement_id, get_asset_group_data, get_consumer_organization_data, get_integrator_details, get_region_country_group_of_consumer
from app.common.helpers.common_services import get_all_data, get_scalar_api_error_messages, save_asset_group_in_db
from app.common.scalar_api.asset_group_api import create_asset_group, get_specific_asset_group
from app.common.scalar_api.framework_api import create_framework_agreement, get_all_framework_agreements, get_integrator
from app.customer_onboarding.customer_onboarding_data_access import save_framework_aggreement, save_integrator_details, save_organization
from app.customer_onboarding.customer_onboarding_services import fetch_asset_group_access_token
import time

def sync_framework_agreement_in_api_db(db: Database, orgName: str,primaryEmail: str,primaryLastName: str,primaryFirstName: str,access_token: str,fa_root_org_id: str,profile_id: str, logger):   
    message = ""
    consumer_organization_id = ""
    framework_agreement_id = None
    frame_work_agreement_response = create_framework_agreement(access_token= access_token, consumerOrgName=orgName,consumerPrimaryEmail=primaryEmail,consumerPrimaryLastName=primaryLastName,consumerPrimaryFirstName=primaryFirstName,profileId=profile_id)
    frame_work_dict ={}
    if  frame_work_agreement_response.status_code == 201:
        logger.info("Frameworkagreement created successfully in Scalar!")
        frame_work_dict = frame_work_agreement_response.json()
        framework_agreement_id =frame_work_dict["agreementId"]
        consumer_organization_id =frame_work_dict["consumerOrgId"]
        consumer_organization_name = frame_work_dict["consumerOrgName"]
        create_integrator =frame_work_dict["createIntegrator"]
    else:
        error_msg = get_scalar_api_error_messages(frame_work_agreement_response)[0]
        if ("Framework agreement name already in use." in error_msg or ("Organization with name" in error_msg and "already exists for" in error_msg)):
            all_frameworks_df = get_all_data(access_token=access_token,func=get_all_framework_agreements)
            if len(all_frameworks_df)>0:
                env = os.environ['SCALAR_ENV']
                if env !='PROD':
                    orgName = env + "_"+ orgName
                specific_frameworks_df = all_frameworks_df.loc[all_frameworks_df["consumerOrgName"]==orgName]
                if len(specific_frameworks_df)>0:
                    frame_work_dict= specific_frameworks_df.iloc[0].to_dict()
                    framework_agreement_id = specific_frameworks_df.iloc[0]["agreementId"]
                    consumer_organization_id = specific_frameworks_df.iloc[0]["consumerOrgId"]
                    consumer_organization_name = specific_frameworks_df.iloc[0]["consumerOrgName"]
                    create_integrator = specific_frameworks_df.iloc[0]["createIntegrator"]
                else:
                    error_msg = error_msg + f" Failed to find org {orgName} from TIP framework agreement list."
    if framework_agreement_id is None:
        message=f"{error_msg} Scalar system not allowing to create framework agreement for FA root org {fa_root_org_id}."
        logger.error(message)
        raise ScalarException(message)
    if len(profile_id)>0:
        is_sso_enabled= 1
    else:
        is_sso_enabled =0
    consumer_org = get_consumer_organization_data(db=db,fa_root_org_id=fa_root_org_id)
    if len(consumer_org) == 0:
        save_organization(db=db,consumer_org_id= consumer_organization_id,consumer_org_name=orgName,fa_root_org_id=fa_root_org_id,is_sso_enabled=is_sso_enabled)
        logger.info("Organization saved successfully in database!")
    agreement_data = get_agreement_id(db=db, org_id=consumer_organization_id)
    if agreement_data is None:
        save_framework_aggreement(db=db,frameworkagreement=frame_work_dict),
        logger.info("Framework details saved successfully in database!")
    if create_integrator == True:
        integrator_data= get_integrator_details(db= db, org_id=consumer_organization_id)
        if len(integrator_data)==0:
            integrator_response = get_integrator(access_token= access_token, agreement_id= framework_agreement_id)
            integrator_dict ={}
            if integrator_response.status_code == 200:
                integrator_dict = integrator_response.json()
                integrator_name =integrator_dict["name"]
                client_id =integrator_dict["clientId"]
                secret_id =integrator_dict["secretId"]
                save_integrator_details(db=db,consumer_org_id=consumer_organization_id, integrator_name=integrator_name, framework_id=framework_agreement_id,client_id=client_id,client_secret=secret_id)
                logger.info("Integrator details saved successfully in database!")
            else:
                error_list = get_scalar_api_error_messages(error_response=integrator_response)
                logger.error(f"Response code: {integrator_response.status_code} and Errors: {error_list}")
    return consumer_organization_id,consumer_organization_name  
    
# def sync_customer_asset_group_data(db: Database, sc_organization_id: str, fa_root_org_id: int, logger):
#     logger.info(f"Customer asset group hierarchy creation has been initiated.")
#     asset_group_access_token = fetch_asset_group_access_token(db=db,org_id=sc_organization_id,audience="TMAPI")          
#     fa_organization_hierachy = get_FA_organization_hierarchy(db=db,fa_root_org_id=fa_root_org_id)
#     if len(fa_organization_hierachy)>0:
#         root_asset_group_id=None
#         for index,org_hierachy in fa_organization_hierachy.iterrows():
#             if root_asset_group_id==None:
#                 root_asset_group_id = get_asset_group_data(db=db,FA_Organization_Id=fa_root_org_id,sc_organization_id=sc_organization_id)
#                 if len(root_asset_group_id)>0:
#                     root_asset_group_id=root_asset_group_id[0][0]
#                 else:
#                     root_asset_group_id=None
#             chid_asset_group_name = org_hierachy['Organization_Name']         
#             parent_asset_group_details =get_asset_group_data(db=db,FA_Organization_Id=org_hierachy['Parent_Organization_Id'],sc_organization_id=sc_organization_id)
#             if len(parent_asset_group_details)>0:
#                 parent_asset_group_id=parent_asset_group_details[0][0]
#             else:
#                 parent_asset_group_id=None
#             create_customer_asset_group_in_api_db(db=db,access_token= asset_group_access_token, child_asset_group_name=chid_asset_group_name,root_asset_group_id=root_asset_group_id,parent_asset_group_id=parent_asset_group_id,sc_organization_id=sc_organization_id,FA_Organization_Id=org_hierachy['FA_Organization_Id'], logger = logger)

#         logger.info(f"Customer asset group hierarchy creation completed.")
#     else:
#         logger.info(f"There is no child organization for root org {fa_root_org_id}")

# def create_customer_asset_group_in_api_db(db: Database,access_token: str, child_asset_group_name: str, root_asset_group_id: str, parent_asset_group_id: str, sc_organization_id: str, FA_Organization_Id: str, logger):   
#     message = ""
#     scalar_child_asset_group_response = create_asset_group(access_token= access_token, name=child_asset_group_name,description=child_asset_group_name,parent_group_id=parent_asset_group_id)
#     scalar_child_asset_group_dict ={}

#     attempt = GeneralConstant.ASSET_GROUP_RETRY_LIMIT
#     while scalar_child_asset_group_response.status_code == 429 and attempt > 0:
#         logger.info("Too many requests. Waiting 15 seconds before attempting to create another asset group.")
#         time.sleep(GeneralConstant.ASSET_GROUP_RETRY_WAITTIME)
#         scalar_child_asset_group_response = create_asset_group(access_token= access_token, name=child_asset_group_name,description=child_asset_group_name,parent_group_id=parent_asset_group_id)
#         attempt = attempt - 1

#     if scalar_child_asset_group_response.status_code == 429:
#         message = f"Unable to create asset group for {child_asset_group_name} (ID: {FA_Organization_Id}). \
#             Too many requests. Retry attempts exhausted."
#         logger.error(message)
#         # raise ScalarException(message=message)
#     elif  scalar_child_asset_group_response.status_code == 201:
#         logger.info("Asset child group created successfully!")
#         scalar_child_asset_group_dict = scalar_child_asset_group_response.json()
#         scalar_child_asset_group_id =scalar_child_asset_group_dict["id"]
#         save_asset_group_in_db(db=db, asset_group_id=scalar_child_asset_group_id, asset_group_name=child_asset_group_name, asset_group_description=child_asset_group_name, sc_organization_id=sc_organization_id, root_group_id=root_asset_group_id, parent_group_id=parent_asset_group_id, fa_root_org_id=FA_Organization_Id)
#         logger.info("Asset child group details saved successfully in database!")
#         message += "Asset group created successfully and updated in database"
#     else:
#         error_msg = get_scalar_api_error_messages(scalar_child_asset_group_response)[0]
#         if "Group already exists." in error_msg:
#             asset_group_dict = get_asset_group_details_by_name(access_token=access_token, asset_group_name=child_asset_group_name, fa_org_id= FA_Organization_Id)
#             if asset_group_dict is None or len(asset_group_dict) == 0:
#                 message = f"Unable to fetch asset group details by name for {child_asset_group_name} (ID: {FA_Organization_Id})."
#                 logger.error(message)
#                 # raise ScalarException(message=message)
#             save_asset_group_in_db(db=db, asset_group_id=asset_group_dict['id'],
#                                     asset_group_name=child_asset_group_name, 
#                                     asset_group_description=child_asset_group_name, 
#                                     sc_organization_id=sc_organization_id, 
#                                     root_group_id=root_asset_group_id, 
#                                     parent_group_id=parent_asset_group_id, 
#                                     fa_root_org_id=FA_Organization_Id)
#             logger.info("Asset group already exists. Details updated in database.")
#             message += "Existing asset group details updated in database."
#         else:
#             message += f"Error creating asset group. Message: {error_msg}"
#             logger.error(message)
#             # raise ScalarException(message=message)

# def sync_provider_asset_group_data(db: Database, provider_org_id: str, fa_root_org_id: int, logger):
#     logger.info(f"Provider asset group creation has been initiated.")
#     access_token = fetch_asset_group_access_token(db=db,org_id=provider_org_id,audience="TMAPI")          
#     asset_group_db_df = get_region_country_group_of_consumer(db=db, fa_root_organization_id=fa_root_org_id, provider_org_id=provider_org_id)
#     region_asset_group_id =asset_group_db_df[asset_group_db_df['Asset_Group_Name'] == asset_group_db_df['Region_Name']].iloc[0]['Asset_Group_Id'] if not asset_group_db_df[asset_group_db_df['Asset_Group_Name'] == asset_group_db_df['Region_Name']].empty else None
#     if region_asset_group_id is None:
#         logger.info(f"Region asset group not found in DB")    
#     if asset_group_db_df['Region_Name'].iloc[0] != "Europe":
#         country_name = asset_group_db_df['Country_Name'].iloc[0]
#         country_asset_group_id_api = get_specific_subgroup_id(access_token=access_token, asset_group_id=region_asset_group_id, sub_group_name=country_name, logger=logger)
#         if isinstance(country_asset_group_id_api, list):
#             logger.info(f"Error occured while fetching subgroup details for region asset group {region_asset_group_id} "+' '.join(map(str,country_asset_group_id_api)))
    
#         if country_asset_group_id_api is None:
#             asset_group_response = create_asset_group(access_token= access_token, name=country_name,description="Country Group", parent_group_id=region_asset_group_id)
#             if asset_group_response.status_code == 201:
#                 logger.info("Country asset group in provider org created successfully!")
#                 asset_group_dict = asset_group_response.json()
#                 country_asset_group_id_api = asset_group_dict["id"]
#             else:
#                 error_list = get_scalar_api_error_messages(error_response=asset_group_response)
#                 logger.info(f"Failed to create country asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))
        
#         save_asset_group_in_db(db=db, asset_group_id=country_asset_group_id_api, asset_group_name=country_name, asset_group_description="Country Group", sc_organization_id=provider_org_id, root_group_id=region_asset_group_id, parent_group_id=region_asset_group_id, fa_root_org_id=None)
#         logger.info("Country asset group details saved successfully in database!")
#     else:
#         country_asset_group_id_api = region_asset_group_id

#     consumer_name = asset_group_db_df['Organization_Name'].iloc[0]
#     consumer_asset_group_in_db = asset_group_db_df[asset_group_db_df['FA_Organization_Id'].notna() & ~asset_group_db_df['Asset_Group_Name'].str.contains('#Copy#')].iloc[0] if not asset_group_db_df[asset_group_db_df['FA_Organization_Id'].notna() & ~asset_group_db_df['Asset_Group_Name'].str.contains('#Copy#')].empty else None
#     if consumer_asset_group_in_db is None:
#         asset_group_response = create_asset_group(access_token= access_token, name=consumer_name,description="TIP Consumer Group", parent_group_id=country_asset_group_id_api)
#         if  asset_group_response.status_code == 201:
#             logger.info("Consumer asset group in provider org created successfully in Scalar.")
#             asset_group_dict = asset_group_response.json()
#             consumer_asset_group_id_api =asset_group_dict["id"]
#             save_asset_group_in_db(db=db, 
#                                    asset_group_id=consumer_asset_group_id_api, 
#                                    asset_group_name=consumer_name, 
#                                    asset_group_description="TIP Consumer Group", 
#                                    sc_organization_id=provider_org_id, 
#                                    root_group_id=region_asset_group_id, 
#                                    parent_group_id=country_asset_group_id_api, 
#                                    fa_root_org_id=fa_root_org_id)   
#         else:
#             error_list = get_scalar_api_error_messages(error_response=asset_group_response)[0]
#             if "Group already exists." not in error_list:
#                 logger.info(f"Failed to create asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))
#     elif consumer_asset_group_in_db['Asset_Group_Name'] != consumer_name:
#         consumer_asset_group_id_api = consumer_asset_group_in_db["Asset_Group_Id"]
#         asset_group_response = update_asset_group(access_token = access_token, 
#                                     asset_group_id = consumer_asset_group_id_api, name= consumer_name,
#                                     description="TIP Consumer Group")
#         if  asset_group_response.status_code == 200:
#             save_asset_group_in_db(db=db, 
#                                    asset_group_id=consumer_asset_group_id_api, 
#                                    asset_group_name=consumer_name, 
#                                    asset_group_description="TIP Consumer Group", 
#                                    sc_organization_id=provider_org_id, 
#                                    root_group_id=region_asset_group_id, 
#                                    parent_group_id=country_asset_group_id_api, 
#                                    fa_root_org_id=fa_root_org_id)
#         else:
#             error_list = get_scalar_api_error_messages(error_response=asset_group_response)
#             raise logger.info(f"Failed to update asset group for provider org {provider_org_id} "+' '.join(map(str,error_list)))
#     else:
#         logger.info("Consumer asset group already present in provider org.")
#         return consumer_asset_group_in_db["Asset_Group_Id"]
    
#     logger.info("Consumer asset group details saved successfully in Scalar and DB.")
#     return consumer_asset_group_id_api

# def get_specific_subgroup_id(access_token: str, asset_group_id: str, sub_group_name: str, logger):
#     response = get_specific_asset_group(access_token=access_token, asset_group_id=asset_group_id)
#     if response.status_code == 200:
#             all_data_json = response.json()
#             subgroups_df = pd.DataFrame(all_data_json["subGroups"],columns=['name','id'])

#             return subgroups_df.loc[subgroups_df['name'] == sub_group_name]['id'].values[0] if subgroups_df.loc[subgroups_df['name'] == sub_group_name]['id'].empty!=True else None
#     else:
#         errors = get_scalar_api_error_messages(error_response=response)
#         logger.error(f"{errors}")
#         return 
 
