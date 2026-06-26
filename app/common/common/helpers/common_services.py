import os
import json
import random
import string
import time
import logging
import pandas as pd
import xlsxwriter
from io import BytesIO
from sqlalchemy import text, update
from pandas import DataFrame
from datetime import datetime
from xlsxwriter import Workbook
import azure.functions as func
from app.common.models import Response
from azure.storage.blob import BlobServiceClient
from app.common.database_model.scalar_tables import SC_Asset_Group, SC_Job_Execution_Details
from app.common.database import Database
from app.common.constants import GeneralConstant, ResponseCode, StatusCode, ExcelSheetName
from app.common.exceptions import ScalarException
from app.common.scalar_api.asset_group_api import assign_asset_to_assetgroup, create_asset_group, get_specific_asset_group
from app.common.scalar_api.authentication import get_access_token
from app.common.database import Database
from app.common.helpers.common_data_access import add_new_token_data_into_db, get_access_token_details, get_asset_groups_by_fa_root_org_id, get_integrator_details, update_access_token


def has_transic_errors(response: dict) -> list:
    response_err = response['Errors']
    error_list = []
    if response_err is not None:
        error_list = response_err['Error']
        return error_list
    return error_list

def log_errors(error_list: list, field: str, value: str) -> list:
    temp_list = list()
    for error in error_list:
        error_dict = dict()
        error_dict['ErrorMessage'] = error
        error_dict['Field'] = field
        error_dict['Value'] = value
        temp_list.append(error_dict)
    return temp_list


def add_and_populate_sheet(error_list: list, workbook: Workbook, sheet_name: str) -> Workbook:
    if not(len(error_list) == 0):
        sheet = workbook.add_worksheet(sheet_name)
        sheet_index = 1
        for index, key in enumerate(error_list[0].keys()):
            sheet.write(0, index, key)
        for row in error_list:
            for index, value in enumerate(row.values()):
                sheet.write(sheet_index, index, str(value))
            sheet_index += 1
    return workbook


def generate_common_error_report(error_list, migration_name) -> BytesIO:
    if len(error_list) == 0:
        return None
        
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'nan_inf_to_errors': True})
    workbook = add_and_populate_sheet(error_list=error_list, workbook=workbook, sheet_name=migration_name + ' error')
    workbook.close()

    return output


def generate_common_multi_error_report(error_list) -> BytesIO:

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'nan_inf_to_errors': True})
    for err_tupple in error_list:
        sheet_name, err_list = err_tupple
        if len(err_list) > 0:
            workbook = add_and_populate_sheet(err_list, workbook, sheet_name)

    workbook.close()

    return output


def get_data_sharing_record(db: Database, fa_root_org_id: str) -> list: 
    data_sharing_org_id_statement = text(''' 
                                            SELECT company_id, tenancy_populated, company_code, 
                                            brakeplus_tenancy, customer_owned_tenancy, 
                                            fr_integrated, domain_login_company_code, subcontractor_cust_id
                                            FROM t_fc_organization_tenancy
                                            WHERE wam_root_org_id = :rorg
                                            ''')

    result = db.query(statement=data_sharing_org_id_statement, params={"rorg": fa_root_org_id})

    if len(result) > 0 and os.environ['FLEETCONNECTED_ENV'] == "DEV":
        return [{"company_id": os.environ['TEST_COMPANY_ID'] , 
                 "company_code": os.environ['TEST_COMPANY_CODE'] ,
                 "tenancy_populated": result[0]['tenancy_populated'],
                "brakeplus_tenancy": result[0]['brakeplus_tenancy'],
                "fr_integrated": result[0]['fr_integrated'],
                "subcontractor_cust_id": os.environ['TEST_CUSTOMER_ID'],
                "domain_login_company_code":os.environ['TEST_COMPANY_CODE'],
                "customer_owned_tenancy": result[0]['customer_owned_tenancy']}]
    
    return result


def start_job_execution_process(db: Database, job_name: str):
    job_execution_dtls = SC_Job_Execution_Details(Job_Name=job_name,
                                    Status_Cd=StatusCode.RUNNING
                                  )
    db.insert_orm(orm_item=job_execution_dtls)
    return job_execution_dtls.id


def update_job_execution_process(db: Database, job_id, job_status):
    unit_group_links = db.get_session().query(SC_Job_Execution_Details).\
                                            filter(SC_Job_Execution_Details.id == job_id).one()
    unit_group_links.Status_Cd = job_status
    unit_group_links.Execution_End_Date = datetime.now()
    db.get_session().commit()


def get_combined_err_list(units_wout_root_org_list=list(), units_wout_pairing_info_list=list(),
                                            consumer_issues_unit_list=list(), data_shared_unit_list=list(),
                                            already_data_shared_unit_list=list(), 
                                            diff_org_already_data_shared_unit_list = list(),
                                            unknown_errors=list(),
                                            data_sharing_removed_unit_list=list(),
                                            data_sharing_not_exists_list=list(),
                                            bp_activated_unit_list=list(),
                                            bp_already_activated_unit_list=list(),
                                            bp_failed_unit_list=list()):
    combined_err_list = list()
    if len(units_wout_root_org_list) > 0:
        combined_err_list.append((ExcelSheetName.UNITS_WITHOUT_FA_SCALAR_ORG, units_wout_root_org_list))
    if len(units_wout_pairing_info_list) > 0:
        combined_err_list.append((ExcelSheetName.UNITS_WOUT_PAIRING_INFO, units_wout_pairing_info_list))
    if len(consumer_issues_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.UNITS_WITHOUT_SCALAR_CUST_ONBOARDING, consumer_issues_unit_list))
    if len(data_shared_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.DATASHARED_SUCCESSFULLY, data_shared_unit_list))
    if len(already_data_shared_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.ALREADY_DATASHARED_UNITS, already_data_shared_unit_list))
    if len(diff_org_already_data_shared_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.DIFF_ORG_DATASHARED_UNITS, diff_org_already_data_shared_unit_list))
    if len(unknown_errors) > 0:
       combined_err_list.append((ExcelSheetName.UNKOWN_ERRORS, unknown_errors))
    if len(data_sharing_removed_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.DATASHARING_STOPPED_UNITS, data_sharing_removed_unit_list))
    if len(data_sharing_not_exists_list) > 0:
        combined_err_list.append((ExcelSheetName.DATASHARING_NOT_FOUND_UNITS, data_sharing_not_exists_list))
    if len(bp_activated_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.BRAKEPLUS_ACTIVATED_UNITS, bp_activated_unit_list))
    if len(bp_already_activated_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.BRAKEPLUS_ALREADY_ACTIVATED_UNITS, bp_already_activated_unit_list))
    if len(bp_failed_unit_list) > 0:
        combined_err_list.append((ExcelSheetName.BRAKEPLUS_FAILED_UNITS, bp_failed_unit_list))

    return combined_err_list


def get_distinct_count(data_set: DataFrame):
    return len(set(data_set['UnitNr'].to_list()))

    
def save_asset_group_in_db(db: Database,asset_group_id,asset_group_name, asset_group_description,sc_organization_id,root_group_id,parent_group_id,fa_root_org_id):
    db.get_session().execute(update(SC_Asset_Group).where(SC_Asset_Group.Asset_Group_Name == asset_group_name, SC_Asset_Group.SC_Organization_Id == sc_organization_id, SC_Asset_Group.Asset_Group_Id != asset_group_id).values(Active="0"))
    db_record_found = db.get_session().query(SC_Asset_Group).filter_by(Asset_Group_Id = asset_group_id).first()
    if db_record_found:
        db_record_found.Asset_Group_Id = asset_group_id
        db_record_found.Asset_Group_Name = asset_group_name
        db_record_found.Description = asset_group_description
        db_record_found.SC_Organization_Id = sc_organization_id
        db_record_found.Root_Group_Id = root_group_id if db_record_found.Root_Group_Id is not None else None
        db_record_found.Parent_Group_Id = parent_group_id
        db_record_found.FA_Organization_Id = fa_root_org_id
        db_record_found.Active="1"
        db.get_session().commit()
    else:
        new_asset_group = SC_Asset_Group(Asset_Group_Id=asset_group_id,
                                    Asset_Group_Name = asset_group_name,
                                    Description = asset_group_description,
                                    SC_Organization_Id = sc_organization_id,
                                    Root_Group_Id= root_group_id,
                                    Parent_Group_Id =parent_group_id,
                                    FA_Organization_Id =fa_root_org_id,
                                    Active="1"
                                    )
        db.insert_orm(orm_item=new_asset_group)

def assign_assets_to_consumer_group_in_provider_org(db: Database, asset_ids: list, fa_root_org_id: str, access_token: str, provider_org_id: str):
    all_asset_groups_df = get_asset_groups_by_fa_root_org_id(db=db, fa_root_org_id=fa_root_org_id, sc_organization_id=provider_org_id)
    group_ids = all_asset_groups_df['Asset_Group_Id'].tolist()
    if not group_ids:
        raise ScalarException(message="asset group not found in DB")
    asset_group_name = all_asset_groups_df["Asset_Group_Name"].unique()[0]
    parent_group_id = all_asset_groups_df['Parent_Group_Id'].unique()
    root_group_id = all_asset_groups_df['Root_Group_Id'].unique()
    fa_root_org_id = all_asset_groups_df['FA_Organization_Id'].unique()
    if len(parent_group_id) > 1 or len(root_group_id) > 1 or len(fa_root_org_id) > 1:
        raise ScalarException(message="Recieved more than one parent group id, root group id, fa_root id from DB")
    flag = 0
    for consumer_group_id in group_ids:
        asset_group_details = get_specific_asset_group(access_token=access_token, asset_group_id=consumer_group_id)
        if asset_group_details.status_code == 200:
            asset_group_details = asset_group_details.json()
        else:
            error_list = get_scalar_api_error_messages(error_response=asset_group_details)
            return error_list
        asset_ids = list(set(asset_ids) - set(asset_group_details['assetIds']))
        if len(asset_ids) == 0:
            return []
        asset_count = len(asset_group_details['assetIds'])
        if asset_count < GeneralConstant.ASSET_LIMIT:
            assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                                asset_group_id=consumer_group_id,
                                                                asset_ids=asset_ids[:GeneralConstant.ASSET_LIMIT - asset_count])
            error_list = get_scalar_api_error_messages(error_response=assignment_response)
            if len(error_list) > 0:
                return error_list
            asset_ids = asset_ids[GeneralConstant.ASSET_LIMIT - asset_count:]
        if len(asset_ids) > 0:
            flag = 1
        else:
            return []

    if not flag:
        random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
        asset_group_response = create_asset_group(access_token= access_token, name=f"{asset_group_name} - #Copy#{random_id}",description="Consumer Group Copy", parent_group_id=parent_group_id[0])
        if  asset_group_response.status_code == 201:
            asset_group_dict = asset_group_response.json()
            consumer_group_id =asset_group_dict["id"] 
            save_asset_group_in_db(db=db, asset_group_id=consumer_group_id, asset_group_name=f"{asset_group_name} - #Copy#{random_id}", asset_group_description="Consumer Group Copy", sc_organization_id=provider_org_id, root_group_id=root_group_id[0], parent_group_id=parent_group_id[0], fa_root_org_id=str(fa_root_org_id[0]))  
        else:
            error_list = get_scalar_api_error_messages(error_response=asset_group_response)
            raise ScalarException(message=f"Failed to create asset group for org {provider_org_id}-"+' '.join(map(str,error_list)))
    assignment_response = assign_asset_to_assetgroup(access_token=access_token,
                                                                asset_group_id=consumer_group_id,
                                                                asset_ids=asset_ids)
    return get_scalar_api_error_messages(error_response=assignment_response)


def get_all_data(access_token: str, func):
    logger = logging.getLogger()
    offset = 0
    attempt = GeneralConstant.RETRY_LIMIT
    all_data = pd.DataFrame()
    while offset is not None:
        response = func(access_token=access_token, offset=offset)
        if response.status_code == 200:
            all_data_json = json.loads(response.content)
            offset = pagination_check(content=all_data_json)
            all_data = pd.concat([all_data,pd.DataFrame(all_data_json["items"])], ignore_index=True)
        elif (response.status_code == 429 or response.status_code == 504 or response.status_code == 502) and attempt > 0:
            attempt = attempt - 1
            time.sleep(GeneralConstant.RETRY_WAITTIME)
        else:
            error_text = response.reason
            logger.error(f"{error_text}")
            raise ScalarException(message="Error occured while fetching all data from scalar API",
                            response_code=ResponseCode.INTERNAL_ERROR)
    return all_data


def get_scalar_api_error_messages(error_response: Response):
    formatted_errors=[]
    if error_response.status_code >= 300:
        content_type = error_response.headers.get("Content-Type","")
        if "application/json" in content_type or "application/problem+json" in content_type:
            errors = error_response.json().get("errors",[])
            if isinstance(errors, dict):
                formatted_errors.append(", ".join(f"{k}:{v}" for k,v in errors.items()))
            else:
                for error in errors:
                    message = error.get("message","Unknown Error")
                    args=error.get("args",[])
                    error_message = f"{message} - {', '.join(map(str, args))}".strip()
                    formatted_errors.append(error_message)
        else:
            formatted_errors.append(error_response.reason if error_response.text=='' else error_response.text)
        logging.error(formatted_errors)
    return formatted_errors

def create_access_token(db: Database, org_id: str, audience: str):
   
   integrator_details = get_integrator_details(db=db, org_id=org_id)
 
   if len(integrator_details) > 0:
        client_id =integrator_details[0][0]
        client_secret= integrator_details[0][1]              
        access_token, access_token_type, expires_in, errors= get_access_token(client_id=client_id, client_secret=client_secret, audience=audience)
       
        if access_token is None:
            if errors is not None:
                raise ScalarException(message=errors)
            else:
                raise ScalarException(message=f"Failed to create access token for org: {org_id} from authentication API")
        else:
            return access_token, access_token_type, expires_in
   else:
      raise ScalarException(message=f"Failed to retrieve integrator details for org: {org_id} from DB")
 
def fetch_access_token(db: Database, org_id: str, audience: str):
   
    access_token_details = get_access_token_details(db=db, org_id=org_id, audience=audience)
    if len(access_token_details) != 0 and access_token_details[0][1] <= access_token_details[0][2]:# Access token validity less than one hour
      access_token=access_token_details[0][0]
      return access_token
    elif len(access_token_details) != 0 and access_token_details[0][1] > access_token_details[0][2]:# Access token validity more than one hour
      access_token, access_token_type, expires_in=create_access_token(db=db,org_id=org_id,audience=audience)
      parameters = {"Organization_Id":org_id,"Audience_Code":audience,"Access_Token":access_token}
      update_access_token(db=db,params=parameters)
      return access_token
    elif len(access_token_details) == 0:# Access token not generated for given org id and audience code
      access_token, access_token_type, expires_in=create_access_token(db=db,org_id=org_id,audience=audience)
      parameters = {"Organization_Id":org_id,"Audience_Code":audience,"Access_Token":access_token,"Token_Type":access_token_type,"Expires_In":expires_in}
      add_new_token_data_into_db(db=db,params=parameters)
      return access_token
 

def pagination_check(content):
   if content is not None:
      total_pages = content["metadata"]["pagination"]["pageCount"]
      current_page = content["metadata"]["pagination"]["currentPage"] if content["metadata"]["pagination"]["currentPage"] is not None else 0
      if current_page == total_pages:
         nextoffset = None
      else:
         nextoffset = content["metadata"]["pagination"]["nextOffset"]
      if current_page == total_pages and nextoffset is not None:
          raise ScalarException(message="Reached last page but nextoffset is not none")
      elif current_page != total_pages and nextoffset is None:
         raise ScalarException(message="nextoffset is none but did not reach last page")
      else:
          return nextoffset

def save_error_details_in_blob(container_name : str, folder_name : str, error_message : str, process_name: str):
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    container_client = blob_service_client.get_container_client(container_name)
    try: 
        container_client.create_container()
    except:
        pass
    current_date = datetime.now().strftime("%Y-%m-%d")
    folder_path = f"{current_date}/{folder_name}" if folder_name else current_date
    blob_name = f"{folder_path}/{process_name}.txt" if folder_name else f"{process_name}"
    blob = container_client.get_blob_client(blob_name)
    blob.upload_blob(json.dumps(error_message, indent=4), overwrite=True)

