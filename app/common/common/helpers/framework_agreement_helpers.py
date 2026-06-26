from asyncio.log import logger
import json
from app.common.database import Database
from app.common.helpers.common_data_access import get_consumer_organization_data
from app.common.helpers.common_services import get_all_data, get_scalar_api_error_messages
from app.common.scalar_api.framework_api import create_framework_agreement, get_all_framework_agreements, get_integrator
from app.common.exceptions import ScalarException
from app.customer_onboarding.customer_onboarding_data_access import save_framework_aggreement, save_integrator_details, save_organization

def check_organization_in_api(db: Database,orgName: str,access_token: str):
    org_df =get_all_data(access_token=access_token,func=get_all_framework_agreements)
    org_name = []
    org_name_list = org_df['consumerOrgName'].tolist()
    if len(org_name_list) > 0 or orgName in org_name_list:
        org_name = org_df.loc[org_df['consumerOrgName']==orgName]
    return org_name

def customer_onboarding(db: Database, orgName: str,primaryEmail: str,primaryLastName: str,primaryFirstName: str,access_token: str,fa_root_org_id: str,profile_id: str):
    
    consumer_org = get_consumer_organization_data(db=db,fa_root_org_id=fa_root_org_id)

    if len(consumer_org) >0:
        raise ScalarException(f"{orgName} already onboarded in scalar with scalar org id ={consumer_org.iloc[0]['Organization_Id']}", display_reqd=True)
    
    frame_work_agreement_response = create_framework_agreement(access_token= access_token, consumerOrgName=orgName,consumerPrimaryEmail=primaryEmail,consumerPrimaryLastName=primaryLastName,consumerPrimaryFirstName=primaryFirstName,profileId=profile_id)
    frame_work_dict ={}
    if frame_work_agreement_response.status_code == 201:
        logger.info("Frameworkagreement created successfully!")
        frame_work_dict = frame_work_agreement_response.json()
        framework_agreement_id =frame_work_dict["agreementId"]
        consumer_organization_id =frame_work_dict["consumerOrgId"]
        consumer_organization_name =frame_work_dict["consumerOrgName"]
        create_integrator =frame_work_dict["createIntegrator"]
        if len(profile_id)>0:
            is_sso_enabled= 1
        else:
            is_sso_enabled =0
        save_organization(db=db,consumer_org_id= consumer_organization_id,consumer_org_name=consumer_organization_name,fa_root_org_id=fa_root_org_id,is_sso_enabled=is_sso_enabled)
        logger.info("Organization saved successfully in database!")
        save_framework_aggreement(db=db,frameworkagreement=frame_work_dict),
        logger.info("Framework details saved successfully in database!")
        if create_integrator == True:
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
                raise ScalarException(message=f"Failed to create integrator for org {orgName} - "+' '.join(map(str,error_list)), display_reqd=True)
    else:
        error_list = get_scalar_api_error_messages(error_response=frame_work_agreement_response)
        logger.error(f"Response code: {frame_work_agreement_response.status_code} and Errors: {error_list}")
        raise ScalarException(message=f"Failed to create framework aggreement for org {orgName} - "+' '.join(map(str,error_list)), display_reqd=True)
    
    return frame_work_dict
        
