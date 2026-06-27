from sqlalchemy import text
from app.common.constants import GeneralConstant
from app.common.database import Database
from pandas import DataFrame
import pandas as pd

def get_all_fc_region_country_mappings(db: Database):
    query = text('''
                    Select Region_Name,fc.Country_Name from FA_Country (NOLOCK) fc
                    JOIN FA_Region (NOLOCK) fr ON fc.Region_Id=fr.Region_Id
                    ORDER by Region_Cd                              
                ''')
    result = db.query(statement=query, as_dataframe=True)
    return result

def get_new_asset_groups(db: Database, asset_group_names: list, provider_org_id: str):
    group_names_as_str= '\',\''.join(asset_group_names)
    group_names_as_str = '\''+group_names_as_str+'\''  
    query = text(f"SELECT ag.Asset_Group_Id,ag.Asset_Group_Name,ag.Description as Asset_Group_Description,so.Organization_Name as Scalar_Organization_Name,rag.Asset_Group_Name as Root_Asset_Group_Name FROM SCALAR.SC_Asset_Group ag LEFT JOIN SCALAR.SC_Asset_Group rag ON ag.Root_Group_Id=rag.Asset_group_Id LEFT JOIN SCALAR.SC_Organization so ON ag.SC_Organization_Id=so.Organization_Id AND so.Active=1 WHERE ag.Asset_Group_Name  in ({group_names_as_str}) and ag.Active ='1' and ag.SC_Organization_Id='{provider_org_id}' ORDER BY COALESCE (ag.Root_Group_Id,ag.Asset_Group_Id),CASE WHEN ag.Root_Group_Id IS NULL THEN 0 ELSE 1 END")
    result = db.query(statement=query, as_dataframe=True)
    return result

def get_all_tip_fa_users(db: Database, sc_org_id: str):
    query = text('''
                    SELECT DISTINCT sc.User_Id SC_User_Id,sc.SC_Organization_Id, sc.User_Email SC_User_Email, fu.User_Id, fu.User_First_Name, fu.User_Last_Name, fu.User_Email, fu.Tip_User, fu.Fleet_Connected_Ind,
                            fu.FleetRadar_Ind, fu.Language_Id, fu.Organization_Id, fu.Root_Organization_Id, 
                            fa.Role_Id
                    FROM SCALAR.SC_User (NOLOCK) sc
                   LEFT JOIN dbo.FA_User (NOLOCK) fu
                        ON sc.FA_User_Id =fu.User_Id
                   AND fu.Tip_User IN ('Y', 'y') AND fu.Active = 1 AND fu.Fleet_Connected_Ind IN ('Y', 'y')  
                    LEFT JOIN dbo.FA_User_App_Access (NOLOCK) fa
                        ON fu.User_Id=fa.User_Id AND fa.Application_Id = 1 AND fa.Role_Id IN (1, 2, 4) AND fa.Active =1
                    WHERE  sc.SC_Organization_Id = :sc_org_id AND sc.Status IN ('Active', 'Pending')              
                ''')
    result = db.query(statement=query, params={"sc_org_id": sc_org_id}, as_dataframe=True)
    return result
    
def get_user_team_assetgroup_mapping(db: Database, sc_org_id: str, tip_user: list):
    query = text('''
                    SELECT DISTINCT fu.User_Id FA_User_Id, su.User_Id SC_User_Id, su.SC_Organization_Id, su.User_Email SC_User_Email, fu.User_First_Name, fu.User_Last_Name, fu.User_Email FA_User_Email,
                     ut.Team_Id, st.Team_Name, sagt.Asset_Group_Id, sa.Asset_Group_Name, fu.Organization_Id FA_Organization_Id
                    FROM dbo.FA_User (NOLOCK)  fu
                    LEFT JOIN SCALAR.SC_User (NOLOCK) su
                        ON fu.User_Id=su.FA_User_Id AND su.Status IN ('Active', 'Pending') AND fu.Active = 1
                    LEFT JOIN SCALAR.SC_Team_User_Mapping (NOLOCK) ut 
                    	ON ut.User_Id = su.User_Id AND ut.Active = 1
                    LEFT JOIN SCALAR.SC_Team (NOLOCK) st 
                    	ON ut.Team_Id = st.Team_Id AND st.Active = 1
                    LEFT JOIN SCALAR.SC_Asset_Group_Team_Mapping (NOLOCK) sagt 
                    	ON sagt.Team_Id = st.Team_Id AND sagt.Active = 1
                    LEFT JOIN SCALAR.SC_Asset_Group (NOLOCK) sa 
                    	ON sa.Asset_Group_Id = sagt.Asset_Group_Id AND sa.Active = 1                   
                    WHERE fu.Tip_User IN :tip_user AND fu.Fleet_Connected_Ind IN ('Y', 'y')
                    AND su.SC_Organization_Id = :sc_org_id AND fu.Active = 1                     
                ''')
    result = db.query(statement=query, params={"sc_org_id": sc_org_id, "tip_user":tip_user}, params_to_expand=["tip_user"], as_dataframe=True)
    return result

def get_all_asset(db: Database):
    query = text('''
                    SELECT DISTINCT Asset_Id from SCALAR.SC_Asset(NOLOCK) WHERE Active=1                            
                ''')
    return db.query(statement=query, as_dataframe=True)

def get_group_list_for_tip_global_asset_group(db: Database, sc_org_id: str):
    query = text('''SELECT a.Asset_Group_Name Child_Group_Name,a.Asset_Group_Id Child_Asset_Group_Id,a.Description,
                    a.Parent_Group_Id,a.Root_Group_Id
                    FROM SCALAR.SC_Asset_Group (NOLOCK) a
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON a.Parent_Group_Id=a1.Asset_Group_Id
                    WHERE a1.Asset_Group_Name=:main_group AND a1.SC_Organization_Id=:sc_org_id
                    ORDER BY a.Created_Date ASC
            ''')
    return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "sc_org_id": sc_org_id}, as_dataframe=True)

def remove_all_mapped_assets(db: Database, assetgroupid: str):
    query = text('''
                    DELETE FROM SCALAR.SC_Asset_Group_Asset_Mapping
                    WHERE Asset_Group_Id =:asset_group_id                           
                ''')
    db.insert_update_delete_raw(statement=query, params={"asset_group_id": assetgroupid})

def get_assinged_assets_for_report(db: Database, sc_org_id: str):
    query = text('''
                    SELECT ag.Asset_Group_Id,ag.Asset_Group_Name,a1.Asset_Group_Name Root_Asset_Group_Name,sa.Asset_Id Scalar_Asset_Id,
                        Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
                    FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK) agm
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) ag ON agm.Asset_Group_Id= ag.Asset_Group_Id AND ag.Active=1
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id AND a1.Active=1
                    JOIN SCALAR.SC_Asset (NOLOCK) sa ON sa.Asset_Id = agm.Asset_Id AND sa.Active=1
                    WHERE agm.Active=1 AND a1.Asset_Group_Name=:main_group AND a1.SC_Organization_Id=:sc_org_id 
                    Order by ag.Asset_Group_Name                             
                ''')
    return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "sc_org_id": sc_org_id}, as_dataframe=True)

def get_all_agreements_organizations_integrators_db(db: Database):
    query = text('''
                    SELECT sfom.Agreement_Id as mapped_agreement_id, sfom.SC_Organization_Id as mapped_org_id,
                    sfa.Agreement_Id, sfa.Consumer_Org_Id, sfa.Provider_Org_Id,
                    so.Organization_Id as SC_Organization_Id, sfom.FA_Root_Organization_Id,
                    sid.Framework_Id  
                    FROM SCALAR.SC_Agreement_FA_Org_Mapping sfom
                    LEFT OUTER JOIN SCALAR.SC_Framework_Agreement sfa ON sfa.Agreement_Id = sfom.Agreement_Id 
                    LEFT OUTER JOIN SCALAR.SC_Organization so ON so.Organization_Id = sfom.SC_Organization_Id AND so.Active=1
                    LEFT OUTER JOIN SCALAR.SC_Integrator_Details sid ON sid.Framework_Id = sfom.Agreement_Id OR sid.Organization_Id = sfom.SC_Organization_Id AND sid.Active=1
                    WHERE sfom.Active = '1'                  
                ''')
    framework_agreements_db_df = db.query(statement=query, as_dataframe=True)
    return framework_agreements_db_df

def insert_update_db(db: Database, new_frameworks_df,existing_frameworks_df,new_orgs_df,existing_orgs_df,new_integrator_df,existing_integrator_df):
    new_org_query = text('''INSERT INTO SCALAR.SC_Organization 
                 (Organization_Id, Organization_Name, FA_Root_Organization_Id, Is_Provider, Active, 
                 Created_By, Created_Date, Modified_By, Modified_Date, ZF_Consumer_Org, Is_SSO_Enabled) 
                 VALUES(:consumerOrgId, :consumerOrgName, :FA_Root_Organization_Id, 'N', :org_active, 'Scalar', 
                 getdate(), 'script', getdate(), :isExistingCustomer, :org_isSSOEnabled);
                ''')
    existing_org_query = text('''UPDATE SCALAR.SC_Organization SET 
                              Organization_Name=:consumerOrgName, 
                              FA_Root_Organization_Id=FLOOR(:FA_Root_Organization_Id), 
                              Is_Provider='N', 
                              Active=:org_active, 
                              Modified_By='Scalar', Modified_Date=getdate(), 
                              ZF_Consumer_Org=:isExistingCustomer, 
                              Is_SSO_Enabled=:org_isSSOEnabled 
                              WHERE Organization_Id=:consumerOrgId;
                ''')
    new_framework_query = text('''INSERT INTO SCALAR.SC_Framework_Agreement 
                           (Agreement_Id, Agreement_Name, Agreement_Desc, Consumer_Org_Id, Provider_Org_Id, Data_Sharing_Type, Subject_Type, Asset_Type, Is_Existing_Customer, Owner, Payer, Primary_Email_Address, Primary_First_Name, Primary_Last_Name, 
                           Allow_Further_Sharing, Multi_Share_Mode, Session_Contract_Mode, Create_Integrator, Rejected_Reason, Approved_Rejected_Date, Approved_Rejected_By, Stopped_By, Stopped_On, Created_By, Created_Date, Modified_By, Modified_Date, Agreement_Status, Profile_Id) 
                           VALUES(:agreementId, :agreementName, :description, :consumerOrgId, :providerOrgId, :dataSharingType, :subjectType, :assetType, :isExistingCustomer, :ownerReceivingOrg, :payer, :consumerPrimaryEmail, :consumerPrimaryLastName, :consumerPrimaryFirstName, 
                           :allowFurtherSharing, :multiShareMode, :sessionContractMode, :createIntegrator, :rejectedReason, :approvedOrRejectedOn, :approvedOrRejectedBy, :stoppedBy, :stoppedOn, 'Scalar', getdate(), 'Scalar', getdate(), :status, :profileId);
                ''')
    existing_framework_query = text('''UPDATE SCALAR.SC_Framework_Agreement SET 
                                    Agreement_Name=:agreementName, 
                                    Agreement_Desc=:description,
                                    Consumer_Org_Id=:consumerOrgId, 
                                    Provider_Org_Id=:providerOrgId, 
                                    Data_Sharing_Type=:dataSharingType, 
                                    Subject_Type=:subjectType, 
                                    Asset_Type=:assetType, 
                                    Is_Existing_Customer=:isExistingCustomer, 
                                    Owner=:ownerReceivingOrg, 
                                    Payer=:payer, 
                                    Primary_Email_Address=:consumerPrimaryEmail, 
                                    Primary_First_Name=:consumerPrimaryLastName, 
                                    Primary_Last_Name=:consumerPrimaryFirstName, 
                                    Allow_Further_Sharing=:allowFurtherSharing, 
                                    Multi_Share_Mode=:multiShareMode, 
                                    Session_Contract_Mode=:sessionContractMode, 
                                    Create_Integrator=:createIntegrator, 
                                    Rejected_Reason=:rejectedReason, 
                                    Approved_Rejected_Date=:approvedOrRejectedOn, 
                                    Approved_Rejected_By=:approvedOrRejectedBy, 
                                    Stopped_By=:stoppedBy, 
                                    Stopped_On=:stoppedOn, 
                                    Modified_By='Scalar', Modified_Date=getdate(), 
                                    Agreement_Status=:status, 
                                    Profile_Id=:profileId 
                                    WHERE Agreement_Id=:agreementId;
                ''')
    new_integrator_query = text('''INSERT INTO SCALAR.SC_Integrator_Details 
                                (Organization_Id, Integrator_Name, Framework_Id, Client_Id, Client_Secret, Active, 
                                Created_By, Created_Date, Modified_By, Modified_Date) 
                                VALUES(:consumerOrgId, :name, :agreementId, :clientId, :secretId, '1', 'Scalar', getdate(), 'Scalar', getdate());
                ''')
    existing_integrator_query = text('''UPDATE [tip-insight].SCALAR.SC_Integrator_Details SET  
                                     Integrator_Name=:name, 
                                     Framework_Id=:agreementId, 
                                     Client_Id=:clientId, 
                                     Client_Secret=:secretId, 
                                     Active='1', 
                                     Modified_By='Scalar', Modified_Date=getdate() 
                                     WHERE Organization_Id=:consumerOrgId;
                ''')
    batch_size = 1000 
    if not new_orgs_df.empty:
        new_org_data_params = new_orgs_df.to_dict('records')
        for curr_index in range(0, len(new_org_data_params), batch_size): 
            curr_new_org_data_params = new_org_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=new_org_query, params=curr_new_org_data_params)
    if not new_frameworks_df.empty:
        new_framework_data_params = new_frameworks_df.to_dict('records')
        for curr_index in range(0, len(new_framework_data_params), batch_size): 
            curr_new_framework_data_params = new_framework_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=new_framework_query, params=curr_new_framework_data_params)
    if not existing_frameworks_df.empty:
        existing_framework_data_params = existing_frameworks_df.to_dict('records')
        for curr_index in range(0, len(existing_framework_data_params), batch_size): 
            curr_existing_framework_data_params = existing_framework_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=existing_framework_query, params=curr_existing_framework_data_params)
    if not existing_orgs_df.empty:
        existing_orgs_data_params = existing_orgs_df.to_dict('records')
        for curr_index in range(0, len(existing_orgs_data_params), batch_size): 
            curr_existing_org_data_params = existing_orgs_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=existing_org_query, params=curr_existing_org_data_params)
    if not new_integrator_df.empty:
        new_integrator_data_params = new_integrator_df.to_dict('records')
        for curr_index in range(0, len(new_integrator_data_params), batch_size): 
            curr_new_integrator_data_params = new_integrator_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=new_integrator_query, params=curr_new_integrator_data_params)
    if not existing_integrator_df.empty:
        existing_integrator_data_params = existing_integrator_df.to_dict('records')
        for curr_index in range(0, len(existing_integrator_data_params), batch_size): 
            curr_existing_integrator_data_params = existing_integrator_data_params[curr_index:curr_index + batch_size]
            db.insert_update_delete_raw(statement=existing_integrator_query, params=curr_existing_integrator_data_params)

def TIP_add_asset_data_in_db(db: Database, new_asset_data):
    query = text('''INSERT INTO SCALAR.SC_Asset
                    (Asset_Id,Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
                    ,Device_Type,Device_Paired_By,Created_By,Created_Date,Modified_By,Modified_Date,Active,status,Fleet_Id)
                    VALUES 
                    (:assetId, :internalCode, :unit_nr, :devices, :devicestatus, CASE WHEN :devices IS NOT NULL THEN getdate() ELSE NULL END, :devicestype, CASE WHEN :devices IS NOT NULL THEN 'AssetSync' ELSE NULL END, 
                    'AssetSync', getdate(), 'AssetSync', getdate(),:active,:status,:fleet_id)
                ''')
    batch_size = 1000
    new_asset_data_params = new_asset_data.to_dict('records')
    for curr_index in range(0, len(new_asset_data_params), batch_size): 
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def TIP_add_asset_data_in_history(db: Database, new_asset_data):
    query = text('''INSERT INTO SCALAR.SC_Asset_Pairing_History
                    (Asset_Id,Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date
                    ,Device_Type,Device_Paired_By,Created_By,Created_Date,Modified_By,Modified_Date,Active,status,Device_Unpairing_Date)
                    VALUES 
                    (:assetId, :internalCode, :unit_nr, :Device_Number, :Device_Pairing_Status, :Device_Pairing_Date, :Device_Type, :Device_Paired_By, 
                    'AssetSync', getdate(), 'AssetSync', getdate(),'0', :status, getdate())
                ''')
    batch_size = 1000
    new_asset_data_params = new_asset_data.to_dict('records')
    for curr_index in range(0, len(new_asset_data_params), batch_size): 
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def TIP_update_asset_data_in_db(db: Database, existing_asset_data):

    query = text('''UPDATE SCALAR.SC_Asset WITH(ROWLOCK)
                    SET Internal_Code = :internalCode,Unit_Nr= :unit_nr
                    , Status= :status
                    , Fleet_Id = :fleet_id
                    , Modified_By = 'AssetSync'
                    , Modified_Date = getdate()
                    WHERE Asset_Id = :assetId and Active=1
                ''')
    existing_asset_data_params = existing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def TIP_update_new_pairing_data_in_db(db: Database, update_new_pairing_data):

    query = text('''UPDATE SCALAR.SC_Asset WITH(ROWLOCK)
                    SET Device_Number = :devices,Device_Pairing_Status= :devicestatus,
                    Device_Type= :devicestype,Device_Pairing_Date=getdate(),
                    Active=1,Device_Paired_By='AssetSync',
                    Modified_By = 'AssetSync', Modified_Date = getdate()
                    WHERE Asset_Id = :assetId AND Device_Number IS NULL
                ''')
    existing_asset_data_params = update_new_pairing_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def TIP_unpairing_current_device(db: Database, unpairing_device_from_asset_in_DB):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Device_Pairing_Status = 0,
                        Active =0,
                        Device_Unpairing_Date = getdate(),
                        Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId AND Device_Number= :Device_Number
                    AND Device_Pairing_Status = 1
            ''')
    existing_asset_data_params = unpairing_device_from_asset_in_DB.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def TIP_inactive_asset_data(db: Database, new_asset_data):
    query = text('''UPDATE SCALAR.SC_Asset_Pairing_History with(ROWLOCK)
                    SET Active =0, 
                        Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId 
                    AND Active = 1
            ''')
    new_asset_data_params = new_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(new_asset_data_params), batch_size):
        curr_new_asset_data_params = new_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_asset_data_params)

def TIP_remove_asset_data_in_db(db: Database, missing_asset_data):
    query = text('''UPDATE SCALAR.SC_Asset with(ROWLOCK)
                    SET Device_Pairing_Status = 0, Active=0, Status='inActive', Modified_Date = getdate(), Modified_By = 'AssetSync'
                    WHERE Asset_Id = :assetId AND Active=1
                ''')
    existing_asset_data_params = missing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def TIP_delete_asset_data_in_db(db: Database, missing_asset_data):
    query = text('''DELETE from SCALAR.SC_Asset 
                    WHERE Asset_Id = :assetId 
                ''')
    existing_asset_data_params = missing_asset_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_asset_data_params), batch_size):
        curr_existing_asset_data_params = existing_asset_data_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_asset_data_params)

def insert_migration_record_in_db(db: Database, run_id, process_name, start_datetime, stop_datetime, response_code, success_status, response_msg):
    query = text('''INSERT INTO SCALAR.SC_TIP_Migration_Process_Status_Log 
                    (Run_Id, Process_Name, Start_Datetime, Stop_Datetime, Response_Code, Success_Status, 
                    Response_Message, Created_By, Created_Date, Modified_By, Modified_Date) 
                    VALUES(:run_id, :process_name, :start_datetime, :stop_datetime, :response_code, :success_status, :response_msg, 'Scalar', getdate(), 'Scalar', getdate());
                ''')
    db.insert_update_delete_raw(statement=query, params={"run_id": run_id, "process_name": process_name, "start_datetime": start_datetime, "stop_datetime": stop_datetime, "response_code": response_code, "success_status": success_status, "response_msg": response_msg})

def get_asset_data_from_db(db: Database) -> DataFrame:
    select_statement = text('''
                                SELECT Asset_Id assetId,Unit_Nr,Device_Number,Convert(Int,Device_Pairing_Status)Device_Pairing_Status,Device_Type,
                                Device_Pairing_Date,Device_Paired_By,Convert(Int,Active)Active,Status,Fleet_Id
                                FROM SCALAR.SC_Asset (nolock) Order by Id                           
                            ''')
   
    return db.query(statement=select_statement, as_dataframe=True)

def get_tip_migration_status(db:Database):
    select_statement = text('''
                                SELECT SC_Organization_Id, SC_Organization_Name, SKY_Company_id, SKY_Company_code, Migrated_Flag
                                FROM SCALAR.SC_Migrated_SKY_Customer_To_Scalar (NOLOCK) 
                                WHERE SKY_Company_id = 2006 AND SKY_Company_code = 'TIP_HQEUROPE'
                                AND FA_Root_Org_Id IS NULL                        
                            ''')
    result = db.query(statement=select_statement,as_dataframe=True)
    return result
def get_asset_country_group(db:Database, asset_ids:list, provider_org_id:str):
    query = text('''SELECT sa.Asset_Id,fu.UnitNr, branch.Region,branch.Country, sag.Asset_Group_Id Country_Group_Id, sag.Asset_Group_Name
							from SCALAR.Fact_Unit (NOLOCK) fu
                    JOIN  (SELECT Region,BranchNr, 
                    Country = CASE 
                                WHEN Country IN ('UK Trailer', 'UK Tankers') THEN 'United Kingdom'
                                WHEN Country = 'Ireland Tankers' THEN 'Ireland' 
                                ELSE Country
                            END
                    FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON fu.OwningBranchNr = branch.BranchNr
                    JOIN  [SCALAR].[SC_Asset_Group] sag ON sag.Asset_Group_Name = branch.Country
                    JOIN [SCALAR].[SC_Asset] sa ON sa.Unit_Nr=fu.UnitNr
                    AND SC_Organization_Id = :provider_org_id AND sag.Active = 1
                    WHERE sa.Asset_Id IN :asset_ids
                    ORDER BY branch.Region,branch.Country
            ''')
    # return db.query(statement=query, params={"asset_ids": asset_ids, "provider_org_id": provider_org_id}, params_to_expand=["asset_ids"], as_dataframe=True)
    batch_size = 1000
    asset_country_group_df = pd.DataFrame()
    for curr_index in range(0, len(asset_ids), batch_size): 
        curr_asset_ids = asset_ids[curr_index:curr_index + batch_size]
        params={"asset_ids": curr_asset_ids, "provider_org_id": provider_org_id}
        result_df = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_ids'])
        asset_country_group_df = pd.concat([asset_country_group_df,result_df], ignore_index=True)
        # rs_unit_nrs.extend(result_df["UnitNr"].to_list())
    return asset_country_group_df

def get_country_assinged_assets_for_report(db: Database, asset_ids:list, sc_org_id: str):
    query = text('''
                    SELECT a1.Asset_Group_Name Region_Asset_Group_Name,ag.Asset_Group_Name Country_Asset_Group_Name,ag.Asset_Group_Id Country_Asset_Group_Id,sa.Asset_Id Scalar_Asset_Id,
                    Unit_Nr
                    FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK) agm
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) ag ON agm.Asset_Group_Id= ag.Asset_Group_Id AND ag.Description='Country asset group'
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id AND a1.Description='Region asset group'
                    JOIN SCALAR.SC_Asset (NOLOCK) sa ON sa.Asset_Id = agm.Asset_Id AND sa.Active=1
                    WHERE agm.Active=1 and agm.Asset_Id in :asset_ids AND a1.SC_Organization_Id=:sc_org_id 
                    Order by a1.Asset_Group_Name,ag.Asset_Group_Name                             
                ''')
    # return db.query(statement=query, params={"sc_org_id": sc_org_id, "asset_ids": asset_ids}, params_to_expand=["asset_ids"], as_dataframe=True)
    batch_size = 1000
    result_df = pd.DataFrame()
    for curr_index in range(0, len(asset_ids), batch_size): 
        curr_asset_ids = asset_ids[curr_index:curr_index + batch_size]
        params={"asset_ids": curr_asset_ids, "sc_org_id": sc_org_id}
        result_set = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_ids'])
        result_df = pd.concat([result_df,result_set], ignore_index=True)
    return result_df  

def get_child_asset_group_for_TIPGlobal_asset_group_new(db: Database, asset_limit: int, sc_org_id: str):
    query = text('''SELECT ag.Asset_Group_Id,ag.Asset_Group_Name,Count(Asset_Id)Asset_Count,(:asset_limit - Count(Asset_Id))Available_Count
                    FROM SCALAR.SC_Asset_Group (NOLOCK) ag
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id and a1.Active=1
                    LEFT JOIN SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK) agm ON ag.Asset_Group_Id=agm.Asset_Group_Id AND ag.Active=1
                    WHERE ag.Active=1 and a1.Asset_Group_Name=:main_group AND a1.SC_Organization_Id=:sc_org_id
                    Group By ag.Asset_Group_Id,ag.Asset_Group_Name
                    Having Count(Asset_Id) < :asset_limit
            ''')
    return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "asset_limit": asset_limit, "sc_org_id": sc_org_id}, as_dataframe=True)

def get_TIP_Global_assinged_assets_for_report(db: Database, sc_org_id: str, asset_ids: list):
    query = text('''
                    SELECT a1.Asset_Group_Name Parent_Asset_Group_Name,a1.Asset_Group_Id Parent_Asset_Group_Id,ag.Asset_Group_Name Sub_Asset_Group_Name,ag.Asset_Group_Id Sub_Asset_Group_Id,a.Asset_Id,a.Unit_Nr 
                    FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK)  agm
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) ag ON ag.Asset_Group_Id=agm.Asset_Group_Id AND ag.Active=1
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id AND a1.Active=1
                    JOIN SCALAR.SC_Asset (NOLOCK) a ON a.Asset_Id = agm.Asset_Id AND a.Active=1
                    Where agm.Active=1 AND a1.Asset_Group_Name=:main_group AND a1.SC_Organization_Id=:sc_org_id 
                    AND a.Asset_Id in :asset_ids                           
                ''')
    # return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "sc_org_id": sc_org_id, "asset_ids": asset_ids}, params_to_expand=['asset_ids'], as_dataframe=True)
    batch_size = 1000
    result_df = pd.DataFrame()
    for curr_index in range(0, len(asset_ids), batch_size): 
        curr_asset_ids = asset_ids[curr_index:curr_index + batch_size]
        params={"asset_ids": curr_asset_ids, "main_group": GeneralConstant.TIPGLOBALGROUP, "sc_org_id": sc_org_id}
        result_set = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_ids'])
        result_df = pd.concat([result_df,result_set], ignore_index=True)
    return result_df    