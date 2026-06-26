import os
import requests
from .common_api import get_header, verify, data_sharing_hostname
from ..constants import ApiUrl

def get_all_framework_agreements(access_token : str, limit : int = 100, offset : int = 0):
    url = ApiUrl.FRAMEWORK_AGREEMENTS_URL.format(hostname=data_sharing_hostname) + "?limit={}&offset={}".format(limit,offset)
    header = get_header(access_token=access_token)
    response = requests.get(url, headers=header, verify=verify)        
    return response

def get_specific_framework_agreement(access_token: str, agreement_id : str):
    url = ApiUrl.SPECIFIC_FRAMEWORK_AGREEMENTS_URL.format(hostname=data_sharing_hostname, agreement_id = agreement_id)
    header = get_header(access_token=access_token)
    response = requests.get(url, headers=header, verify=verify)        
    return response

def get_integrator(access_token: str, agreement_id : str):
    url = ApiUrl.INTEGRATOR_URL.format(hostname=data_sharing_hostname, agreement_id = agreement_id)
    header = get_header(access_token=access_token)
    response = requests.get(url, headers=header, verify=verify)        
    return response

def create_framework_agreement(access_token: str, consumerOrgName: str,consumerPrimaryEmail: str,consumerPrimaryLastName: str,consumerPrimaryFirstName: str,profileId: str):
    url = ApiUrl.FRAMEWORK_AGREEMENTS_URL.format(hostname=data_sharing_hostname)
    header = get_header(access_token=access_token)
    req_body= create_frame_work_agreement_json(consumer_Org_Name=consumerOrgName,consumer_Primary_Email=consumerPrimaryEmail,consumer_Primary_LastName=consumerPrimaryLastName,consumer_Primary_FirstName=consumerPrimaryFirstName,profile_Id=profileId)
    response = requests.post(url, json=req_body, headers= header, verify=verify)        
    return response

def create_frame_work_agreement_json(consumer_Org_Name: str,consumer_Primary_Email: str,consumer_Primary_LastName: str,consumer_Primary_FirstName: str,profile_Id: str):
    env = os.environ['SCALAR_ENV']
    if env !='PROD':
        agreement_name = env + "_"+ consumer_Org_Name + " Framework Agreement"
        description = env + "_"+ consumer_Org_Name + " Framework Agreement"
        consumer_Org_Name = env + "_"+ consumer_Org_Name
    else:
        agreement_name = consumer_Org_Name + " Framework Agreement"
        description = consumer_Org_Name + " Framework Agreement"

    frame_work_json={"agreementName": agreement_name,
        "description": description,
        "dataSharingType": "rentalServices", 
        "subjectType": "asset",
        "assetType": "trailer",
        "consumerOrgName": consumer_Org_Name,
        "ownerReceivingOrg": "dataProvider", 
        "isExistingCustomer": False, 
        "payer": "dataProvider", 
        "consumerPrimaryEmail": consumer_Primary_Email,
        "consumerPrimaryLastName": consumer_Primary_LastName,
        "consumerPrimaryFirstName": consumer_Primary_FirstName,
        "allowFurtherSharing": False, 
        "multiShareMode": "forbidden",
        "sessionContractMode": "forbidden",
        "language": "EN", 
        "createIntegrator": True,
        "profileId": profile_Id
    }

    return frame_work_json