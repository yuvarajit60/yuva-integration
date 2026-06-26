from asyncio.log import logger
from multiprocessing import process
import pandas as pd
from app.common.constants import GeneralConstant, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exceptions import ScalarException
from app.common.helpers.asset_group_helper import create_consumer_asset_group_in_api_db
from app.common.helpers.common_data_access import add_new_token_data_into_db, get_FA_organization_hierarchy, get_access_token_details, get_asset_group_data, get_integrator_details, update_access_token
from app.common.scalar_api.authentication import get_access_token
from app.customer_onboarding.customer_onboarding_data_access import get_regional_super_users, get_root_tenancy, save_tenancy_info_in_db, update_tenancy_info_in_db
import os
from datetime import datetime
import time

def create_consumer_asset_group_hierarchy(db: Database,access_token: str, sc_organization_id: str,fa_root_org_id: str):
    
    fa_organization_hierachy = get_FA_organization_hierarchy(db=db,fa_root_org_id=fa_root_org_id)
    if len(fa_organization_hierachy)>0:
        root_asset_group_id=None
        for index,org_hierachy in fa_organization_hierachy.iterrows():
            if root_asset_group_id==None:
                root_asset_group_id = get_asset_group_data(db=db,FA_Organization_Id=fa_root_org_id,sc_organization_id=sc_organization_id)
                if len(root_asset_group_id)>0:
                    root_asset_group_id=root_asset_group_id[0][0]
                else:
                    root_asset_group_id=None
            chid_asset_group_name = org_hierachy['Organization_Name']         
            parent_asset_group_details =get_asset_group_data(db=db,FA_Organization_Id=org_hierachy['Parent_Organization_Id'],sc_organization_id=sc_organization_id)
            if len(parent_asset_group_details)>0:
                parent_asset_group_id=parent_asset_group_details[0][0]
            else:
                parent_asset_group_id=None
            scalar_child_asset_group_response=create_consumer_asset_group_in_api_db(db=db,access_token= access_token, child_asset_group_name=chid_asset_group_name,root_asset_group_id=root_asset_group_id,parent_asset_group_id=parent_asset_group_id,sc_organization_id=sc_organization_id,FA_Organization_Id=org_hierachy['FA_Organization_Id'])
            scalar_child_asset_group_dict={}
            scalar_child_asset_group_dict= scalar_child_asset_group_response.json()
    else:
        raise ScalarException(message=f"There is no child organization for root org {fa_root_org_id}")

    return scalar_child_asset_group_dict,fa_organization_hierachy

def send_success_email_to_regional_super_users(db, root_org_id, consumer_org_name):
    result = []
    env = os.environ['SCALAR_ENV']
    # if env == 'PROD':
    result = get_regional_super_users(db, root_org_id)
    email = Email()
    receivers = []
    recipients = os.environ['ORGANIZATION_CREATION_MAIL_RECIPIENTS']

    if len(result) > 0:
        receivers =result['User_Email'].tolist()
    recipients = recipients.split(",")
    receivers.extend(recipients)
    if env == 'PROD':
        subject = f"Scalar - Customer organization created successfully for {consumer_org_name}"
    else:
        subject = f"Scalar - Customer organization created successfully for {consumer_org_name} - {env}"
    template_name = "organization_creation.html"
    params={"environment": env, 
    "organization_creation_time": datetime.now(),
    "org_name": consumer_org_name
    }  
    params["organization_creation_time"] = datetime.now()
    
    if len(receivers)>0:
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params)
        logger.info(f"Organization creation mail successfully sent to: {receivers}")

def send_error_email_to_super_users(db, root_org_id, consumer_org_name , error_message, process_name):
    result = []
    env = os.environ['SCALAR_ENV']
    # if env == 'PROD':
    result = get_regional_super_users(db, root_org_id)
    email = Email()
    receivers = []
    recipients = os.environ['ORGANIZATION_CREATION_MAIL_RECIPIENTS']

    if len(result) > 0:
        receivers =result['User_Email'].tolist()
    recipients = recipients.split(",")
    receivers.extend(recipients)
    if env == 'PROD':
        subject = f"Scalar - Error in Scalar customer onboarding process for {consumer_org_name}"
    else:
        subject = f"Scalar - Error in Scalar customer onboarding process for {consumer_org_name} - {env}"
    template_name = "organization_creation_error.html"
    params={"environment": env, 
    "organization_creation_time": datetime.now(),
    "org_name": consumer_org_name,
    "process_name" : process_name,
    "error_message": error_message
    }  
    params["organization_creation_time"] = datetime.now()
    
    if len(receivers)>0:
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params)
        logger.info(f"Error in customer onboarding process and mail sent to: {receivers}")

def send_data_sharing_error_email_to_super_users(db, root_org_id, consumer_org_name , error_message):
    result = []
    env = os.environ['SCALAR_ENV']
    # if env == 'PROD':
    result = get_regional_super_users(db, root_org_id)
    email = Email()
    receivers = []
    recipients = os.environ['ORGANIZATION_CREATION_MAIL_RECIPIENTS']

    if len(result) > 0:
        receivers =result['User_Email'].tolist()
    recipients = recipients.split(",")
    receivers.extend(recipients)
    if env == 'PROD':
        subject = f"Scalar customer onboarding - Error in datasharing process for {consumer_org_name}"
    else:
        subject = f"Scalar customer onboarding - Error in datasharing process for {consumer_org_name} - {env}"
    template_name = "organization_creation_data_sharing_error.html"
    params={"environment": env, 
    "organization_creation_time": datetime.now(),
    "org_name": consumer_org_name,
    "error_message": error_message
    }  
    params["organization_creation_time"] = datetime.now()
    
    if len(receivers)>0:
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params)
        logger.info(f"Error in datasharing process and mail sent to: {receivers}")

def inform_fleetadmin_about_tenancy_creation(db: Database, root_org_id):
    
    root_tenancy = get_root_tenancy(db=db,root_org_id=root_org_id)
    if len(root_tenancy) > 0:
        update_tenancy_info_in_db(db=db,farootorgid=root_org_id)
    else:
        save_tenancy_info_in_db(db=db,farootorgid=root_org_id)

def fetch_asset_group_access_token(db: Database, org_id: str, audience: str):
    access_token_details = get_access_token_details(db=db, org_id=org_id, audience=audience)
    if len(access_token_details) != 0 and access_token_details[0][1] <= access_token_details[0][2]:# Access token validity less than one hour
      access_token=access_token_details[0][0]
      return access_token
    elif len(access_token_details) != 0 and access_token_details[0][1] > access_token_details[0][2]:# Access token validity more than one hour
        access_token, access_token_type, expires_in,errors=create_asset_access_token(db=db,org_id=org_id,audience=audience)
        max_attempts = GeneralConstant.ONBOARDING_LIMIT
        if errors is not None: 
            attempt = 0
            while attempt < max_attempts:
                access_token, access_token_type, expires_in,errors=create_asset_access_token(db=db,org_id=org_id,audience=audience)
                if errors is not None:
                    logger.warning(errors)
                    attempt += 1
                    time.sleep(GeneralConstant.ONBOARDING_WAITTIME)
                else:
                    logger.info("Asset group access token has been generated.")
                    attempt=max_attempts
        parameters = {"Organization_Id":org_id,"Audience_Code":audience,"Access_Token":access_token,"Token_Type":access_token_type,"Expires_In":expires_in}
        update_access_token(db=db,params=parameters)
        return access_token
    elif len(access_token_details) == 0:# Access token not generated for given org id and audience code
        access_token, access_token_type, expires_in,errors=create_asset_access_token(db=db,org_id=org_id,audience=audience)
        max_attempts = GeneralConstant.ONBOARDING_LIMIT
        if errors is not None: 
            attempt = 0
            while attempt < max_attempts:
                access_token, access_token_type, expires_in,errors=create_asset_access_token(db=db,org_id=org_id,audience=audience)
                if errors is not None:
                    logger.warning(errors)
                    attempt += 1
                    time.sleep(GeneralConstant.ONBOARDING_WAITTIME)
                else:
                    logger.info("Asset group access token has been generated.")
                    attempt=max_attempts
        parameters = {"Organization_Id":org_id,"Audience_Code":audience,"Access_Token":access_token,"Token_Type":access_token_type,"Expires_In":expires_in}
        add_new_token_data_into_db(db=db,params=parameters)
        return access_token

    
def create_asset_access_token(db: Database, org_id: str, audience: str):
   access_token ="" 
   access_token_type=""
   expires_in =""
   errors =""
   integrator_details = get_integrator_details(db=db, org_id=org_id)
   if len(integrator_details) > 0:
        client_id =integrator_details[0][0]
        client_secret= integrator_details[0][1]              
        access_token, access_token_type, expires_in, errors= get_access_token(client_id=client_id, client_secret=client_secret, audience=audience)
        return access_token, access_token_type, expires_in,errors
   else:
      raise ScalarException(message=f"Failed to retrieve integrator details for org: {org_id} from DB")
 
