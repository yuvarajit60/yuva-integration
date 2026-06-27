from datetime import datetime
from app.common.constants import Connection
from app.common.database_model.scalar_tables import SC_Asset_Group, SC_User, SC_User_Role_Mapping, ScalarAutoPairingLog
from sqlalchemy import text
from pandas import DataFrame
 
from app.common.database import Database
 
 
def get_integrator_details(db: Database, org_id: str) -> DataFrame:
    select_statement = text('''
                                SELECT Client_Id,
                                      Client_Secret
                                FROM SCALAR.SC_Integrator_Details (NOLOCK)
                                WHERE Active=1 and Organization_id = :org_id  
                            ''')
   
    return db.query(statement=select_statement, params={"org_id": org_id})
 
def get_access_token_details(db: Database, org_id: str, audience: str) -> DataFrame:
    select_statement = text('''
                                SELECT Access_Token,
                                DATEDIFF(SECOND, Token_Start_Time,getdate()) Access_Seconds,Expires_In
                                FROM SCALAR.SC_Access_Token_Details (NOLOCK)
                                WHERE Organization_id = :org_id and Audience_Code= :audience
                            ''')
   
    return db.query(statement=select_statement, params={"org_id": org_id, "audience": audience})
 
def add_new_token_data_into_db(db: Database, params):
    query = text('''INSERT INTO SCALAR.SC_Access_Token_Details
                    (Organization_Id,Audience_Code,Access_Token,Token_Type,Expires_In,Token_Start_Time,Created_By
                        ,Created_Date,Modified_By,Modified_Date)
                    VALUES
                    (:Organization_Id, :Audience_Code, :Access_Token, :Token_Type, :Expires_In, getdate(),
                    'scalar', getdate(), 'scalar', getdate())
                ''')
    db.insert_update_delete_raw(statement=query, params=params)
 
def update_access_token(db: Database, params):
    query = text('''UPDATE SCALAR.SC_Access_Token_Details WITH(Rowlock)
                    SET Access_Token = :Access_Token, Token_Start_Time= getdate(), Modified_Date = getdate(), Modified_By = 'Scalar'
                    WHERE Organization_Id = :Organization_Id and Audience_Code= :Audience_Code
                   
            ''')
    return db.insert_update_delete_raw(statement=query, params=params)

def save_user(db: Database, user_id, login_type, status, fa_user_id, sc_organization_id):
        sc_user = SC_User(User_Id=user_id,
                                        Login_Type = login_type, 
                                        Status=status,
                                        FA_User_Id=fa_user_id,
                                        SC_Organization_Id=sc_organization_id
                                        )
        db.insert_orm(orm_item=sc_user)

def save_user_role(db: Database, user_id, role_id, role_name):
        sc_user_role = SC_User_Role_Mapping(User_Id=user_id,
                                        Role_Id = role_id, 
                                        Role_Name=role_name
                                        )
        db.insert_orm(orm_item=sc_user_role)

def delete_sc_user_role(db: Database, user_id):
    query = text('''
                delete from SCALAR.SC_User_Role_Mapping
                where User_Id = :user_id
                ''')
    db.insert_update_delete_raw(statement=query, params={"user_id":user_id})

def delete_sc_user(db: Database, user_id):
    query = text('''
                delete from SCALAR.SC_User
                where User_Id = :user_id
                ''')
    db.insert_update_delete_raw(statement=query, params={"user_id":user_id})

def get_tip_provider_organization(db: Database):
    select_statement = text('''
                                SELECT Organization_Id, Is_SSO_Enabled
                                FROM SCALAR.SC_Organization (NOLOCK) WHERE Is_Provider = 'Y' AND Active =1
                            ''')
   
    result = db.query(statement=select_statement)

    if len(result) > 0:
        return result[0]
    else:
        return None
    
def get_all_organizations(db: Database) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Id, Organization_Name, Is_provider
                                FROM SCALAR.SC_Organization (NOLOCK) where Active=1 AND ZF_Consumer_Org=0                               
                            ''')
    result = db.query(statement=select_statement, as_dataframe=True)
    return result


def get_consumer_organization_data(db: Database,fa_root_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Id,Organization_Name,convert(int,ZF_Consumer_Org)ZF_Consumer_Org, Is_SSO_Enabled
                                FROM SCALAR.SC_Organization (NOLOCK) where FA_Root_Organization_Id= :fa_root_org_id and Active=1                               
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id}, as_dataframe=True)
    
    return result

def get_cust_org_detail(db: Database,consumer_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT FA_Root_Organization_Id,Organization_Name
                                FROM SCALAR.SC_Organization (NOLOCK) where Organization_Id= :consumer_org_id and Active=1                               
                            ''')
    result = db.query(statement=select_statement, params={"consumer_org_id": consumer_org_id}, as_dataframe=True)
    return result

def get_agreement_data(db: Database,agreement_name) -> DataFrame:
    select_statement = text('''
                                SELECT Agreement_Name
                                FROM SCALAR.SC_Framework_Agreement (NOLOCK) where Agreement_Name= :agreement_name and Agreement_Status='approved'                              
                            ''')
    result = db.query(statement=select_statement, params={"agreement_name": agreement_name})
    return result

def get_agreement_id(db: Database, org_id: str):
    select_statement = text(''' SELECT Agreement_Id from SCALAR.SC_Framework_Agreement (NOLOCK)
                                WHERE Consumer_Org_Id = :org_id and Agreement_Status = 'approved'
                            ''')
    result = db.query(statement=select_statement, params={"org_id":org_id})
    if len(result) > 0:
        return result[0]
    else:
        return None
    
def get_region_country_group_of_consumer(db: Database, fa_root_organization_id: str, provider_org_id: str):
    select_statement = text('''
                                SELECT oi.Organization_Name,r.Region_Name,c.Country_Name,ag.Asset_Group_Id,ag.Asset_Group_Name,ag.FA_Organization_Id
                                FROM FA_Organization oi
                                JOIN FA_Region r ON oi.Region_Id =r.Region_Id 
                                JOIN FA_Country c ON oi.Country_Id =c.Country_Id 
                                LEFT JOIN SCALAR.SC_Asset_Group ag ON (ag.Asset_Group_Name = r.Region_Name OR ag.Asset_Group_Name = c.Country_Name OR ag.FA_Organization_Id=:fa_root_organization_id) AND ag.SC_Organization_Id=:provider_org_id AND ag.Active = '1'
                                WHERE oi.Organization_Id =:fa_root_organization_id and oi.Active = '1' AND oi.Root_Organization_Id IS NULL
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_organization_id": fa_root_organization_id, "provider_org_id": provider_org_id}, as_dataframe=True)
    return result

def get_asset_group_data(db: Database,FA_Organization_Id,sc_organization_id) -> DataFrame:
    select_statement = text('''
                                SELECT Asset_Group_Id, Asset_Group_Name, Description, Root_Group_Id, Parent_Group_Id
                                FROM SCALAR.SC_Asset_Group (NOLOCK) where SC_Organization_Id =:sc_organization_id AND FA_Organization_Id= :FA_Organization_Id and Active=1                               
                            ''')
    result = db.query(statement=select_statement, params={"FA_Organization_Id": FA_Organization_Id,"sc_organization_id": sc_organization_id})
    return result

def save_main_asset_group(db: Database,asset_group_id,asset_group_name, asset_group_description,sc_organization_id, fa_root_org_id):
    sc_organization = SC_Asset_Group(Asset_Group_Id=asset_group_id,
                                    Asset_Group_Name = asset_group_name,
                                    Description = asset_group_description,
                                    SC_Organization_Id = sc_organization_id,
                                    Root_Group_Id= None,
                                    Parent_Group_Id =None,
                                    FA_Organization_Id =fa_root_org_id,
                                    Active="1"
                                    )
    db.insert_orm(orm_item=sc_organization)

def save_child_asset_group(db: Database,asset_group_id,asset_group_name, asset_group_description,sc_organization_id,root_group_id,parent_group_id,fa_root_org_id):
    sc_organization = SC_Asset_Group(Asset_Group_Id=asset_group_id,
                                    Asset_Group_Name = asset_group_name,
                                    Description = asset_group_description,
                                    SC_Organization_Id = sc_organization_id,
                                    Root_Group_Id= root_group_id,
                                    Parent_Group_Id =parent_group_id,
                                    FA_Organization_Id =fa_root_org_id,
                                    Active="1"
                                    )
    db.insert_orm(orm_item=sc_organization)

def get_asset_groups_by_fa_root_org_id(db: Database, fa_root_org_id: str, sc_organization_id: str):
    select_statement = text('''
                                SELECT * FROM SCALAR.SC_Asset_Group
                                WHERE FA_Organization_Id = :fa_root_org_id 
                                AND SC_Organization_Id = :sc_organization_id AND Active = '1'
                            ''')
   
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id,"sc_organization_id": sc_organization_id}, as_dataframe=True)
    return result

def get_organization_profile(db: Database):
    select_statement = text('''
                                SELECT Profile_Id FROM [SCALAR].[SC_Organization_Profile] (NOLOCK)
                                WHERE Source= :source AND SSO_Profile=1 AND Active=1
                            ''')
   
    result = db.query(statement=select_statement, params={"source": Connection.CUSTOMER_CONNECTION})
    if len(result) > 0:
        return result[0][0]
    else:
        return None
    
def get_FA_root_org_details(db: Database,fa_root_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Name FROM FA_Organization (NOLOCK)
                                WHERE Organization_Id = :fa_root_org_id AND Root_Organization_Id IS NULL AND FleetConnected_Ind='Y' AND Active=1
                                                              
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id})
    
    if len(result) > 0:
        return result[0][0]
    else:
        return None
        
def get_fa_organization_details(db: Database, fa_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Name, Root_Organization_Id, Parent_Organization_Id, 
                                Region_Id, Country_Id, Fleetconnected_Ind, Organization_Level
                                FROM FA_Organization (NOLOCK) WHERE Organization_Id= :fa_org_id AND Active = 1                          
                            ''')
    result = db.query(statement=select_statement, params={"fa_org_id": fa_org_id}, as_dataframe=True)
    return result
    
def get_last_successfull_job_execution_ts(db: Database, job_name: str):
    last_execution_ts: datetime = None
    query = text('''SELECT Execution_End_Date
                    FROM SCALAR.SC_Job_Execution_Details 
                    WHERE Status_Cd = 'S' AND job_name = :job_name
                    AND Execution_End_Date = 
                        (SELECT max(Execution_End_Date) 
                        FROM SCALAR.SC_Job_Execution_Details 
                        WHERE Status_Cd = 'S' AND job_name = :job_name)
                ''')
    params = {"job_name": job_name}
    result = db.query(statement=query, params=params, as_dataframe=True)
    if len(result) > 0:
        last_execution_ts = result["Execution_End_Date"][0]
    return last_execution_ts

def get_fa_user_details_by_id(db: Database, fa_user_id:str):
    select_statement = text(''' SELECT fu.User_First_Name, fu.User_Last_Name, fu.User_Email, fu.Tip_User,
                                        fu.Fleet_Connected_Ind, fu.FleetRadar_Ind, fu.Language_Id, fu.Organization_Id, 
                                        fu.Root_Organization_Id, fr.Role_Id
                                FROM dbo.FA_User (NOLOCK) fu
                                LEFT JOIN dbo.FA_User_App_Access (NOLOCK) fr
                                ON fu.User_Id=fr.User_Id AND fr.Application_Id = 1 AND fr.Role_Id IN (1, 2, 4) AND fr.Active= 1
                                WHERE fu.Active = 1  								
								AND fu.User_Id = :fa_user_id                         
                            ''')
    result = db.query(statement=select_statement, params={"fa_user_id": fa_user_id}, as_dataframe=True)
    return result

def get_fa_user_org_mapping_by_id(db: Database, fa_user_id: str):
    select_statement = text(''' SELECT User_Id, Organization_Id
                                FROM FA_User_Org_Mapping (NOLOCK) WHERE User_Id= :fa_user_id
                                AND Active= 1                         
                            ''')
    result = db.query(statement=select_statement, params={"fa_user_id": fa_user_id}, as_dataframe=True)
    return result

def get_all_scalar_region_group_ids(db:Database):
    select_statement = text(''' SELECT sa.Asset_Group_Id, sa.Asset_Group_Name
                                FROM SCALAR.SC_Asset_Group (NOLOCK) sa 
                                JOIN FA_Region fa ON fa.Region_Name = sa.Asset_Group_Name
                                AND sa.Active= 1                         
                            ''')
    result = db.query(statement=select_statement, as_dataframe=True)
    return result

def get_fa_user_region_mapping_by_id(db:Database, fa_user_id:str):
    select_statement = text(''' SELECT FA_User_Region_Mapping.User_Id, FA_Region.Region_Name
                                FROM FA_Region
                                INNER JOIN FA_User_Region_Mapping ON FA_Region.Region_Id=FA_User_Region_Mapping.Region_Id 
                                AND FA_User_Region_Mapping.Active = 1 
                                WHERE FA_User_Region_Mapping.User_Id = :fa_user_id                       
                            ''')
    result = db.query(statement=select_statement, params={"fa_user_id": fa_user_id}, as_dataframe=True)
    return result

def log_auto_pairing_failure_event(db: Database, message: str, event_log):
    event_log.Error_Ind = 1
    event_log.Error_Message = message
    db.get_session().commit()

def log_auto_pairing_failure_event_old(db: Database, message: str, event_log: int):
    event_log_update = db.get_session().query(ScalarAutoPairingLog).\
                                            filter(ScalarAutoPairingLog.Id == event_log).one()
    event_log_update.error_ind = 1
    event_log_update.error_msg = message
    db.get_session().commit()


def get_FA_organization_hierarchy(db: Database,fa_root_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Id AS FA_Organization_Id,TRIM(Organization_Name)Organization_Name,Parent_Organization_Id,Organization_Level 
                                FROM FA_Organization (NOLOCK)
                                WHERE (Organization_Id = :fa_root_org_id or Root_Organization_Id= :fa_root_org_id) 
                                AND Active=1 
                                ORDER BY Organization_Level                               
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id},as_dataframe=True)

    return result

def update_fleetconnected_ind_in_fa_organization(db: Database,fa_org_id:str, has_fc_access:bool):
    select_statement = text('''
                                UPDATE FA_Organization SET Fleetconnected_Ind = :fc_ind
                                WHERE Organization_Id = :fa_org_id                              
                            ''')
    if has_fc_access == True: 
        fc_ind = 'Y'
    else:
        fc_ind = 'N'
    db.insert_update_delete_raw(statement=select_statement, params={"fc_ind":fc_ind, "fa_org_id":fa_org_id})

def get_sc_org_info_by_list_of_root_orgs(db: Database, fa_root_org_list:list) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Id, FA_Root_Organization_Id
                                FROM [SCALAR].[SC_Organization] sc(NOLOCK)
                            WHERE sc.FA_Root_Organization_Id IN :fa_root_org_list AND sc.Active = 1                          
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_list":fa_root_org_list},params_to_expand=["fa_root_org_list"], as_dataframe=True)
    return result
