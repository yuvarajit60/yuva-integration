import pandas as pd
from sqlalchemy import text
from app.common.database import Database
from app.common.database_model.scalar_tables import SC_User
from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase
from app.common.constants import AdditionalChargeType, GeneralConstant


def get_all_sessions_from_database(db: Database, sc_org_id: str) -> pd.DataFrame:
    query_statement = text('''SELECT Session_Id, Agreement_Id, Provider_Organization_Id, Consumer_Organization_Id, Status, Real_Start,
                            Real_Stop, Desired_Start, Desired_Stop, Provider_Unit_Nr, Provider_Asset_Id, Consumer_Asset_Id,
                            Active, Created_By, Created_Date
                            FROM SCALAR.SC_Session(NOLOCK)
                            WHERE Consumer_Organization_Id = :sc_org_id''')
    return db.query(statement=query_statement, params={"sc_org_id": sc_org_id},as_dataframe=True)


def add_new_session_data_into_db(db: Database, new_sessions_to_insert):
    query = text('''INSERT INTO SCALAR.SC_Session
                    (Session_Id, Agreement_Id, Provider_Organization_Id, Consumer_Organization_Id, Status, Real_Start,
                    Real_Stop, Desired_Start, Desired_Stop, Provider_Unit_Nr, Provider_Asset_Id, Consumer_Asset_Id,
                    Active, Created_By, Created_Date, Modified_By, Modified_Date)
                    VALUES 
                    (:Session_Id, :Agreement_Id, :Provider_Organization_Id, :Consumer_Organization_Id, :Status, :Real_Start,
                    :Real_Stop, :Desired_Start, :Desired_Stop, :Provider_Unit_Nr, :Provider_Asset_Id, :Consumer_Asset_Id,
                    :Active, :Created_By, :Created_Date, 'script', getdate())
                ''')
    batch_size = 1000
    new_sessions_params = new_sessions_to_insert.to_dict('records')
    for curr_index in range(0, len(new_sessions_params), batch_size): 
        curr_new_sessions_params = new_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_new_sessions_params)


def update_existing_sessions_data_into_db(db: Database, sessions_to_update):
    query = text('''UPDATE SCALAR.SC_Session WITH(Rowlock)
                    SET Agreement_Id = :Agreement_Id, Provider_Organization_Id = :Provider_Organization_Id, 
                    Consumer_Organization_Id = :Consumer_Organization_Id, Status = :Status, Real_Start = :Real_Start,
                    Real_Stop = :Real_Stop, Desired_Start = :Desired_Start, Desired_Stop = :Desired_Stop, 
                    Provider_Unit_Nr = :Provider_Unit_Nr, Provider_Asset_Id = :Provider_Asset_Id, 
                    Consumer_Asset_Id = :Consumer_Asset_Id,Active = :Active, Created_By = :Created_By, 
                    Created_Date = :Created_Date, Modified_By = 'script', Modified_Date = getdate()
                    WHERE Session_Id = :Session_Id
                    ''')
    batch_size = 1000
    update_sessions_params = sessions_to_update.to_dict('records')
    for curr_index in range(0, len(update_sessions_params), batch_size): 
        curr_update_params = update_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_update_params)

def deactivate_sessions_missing_in_api(db: Database, sessions_to_deactivate):
    query = text('''UPDATE SCALAR.SC_Session WITH(Rowlock)
                    SET Active = 0, Modified_By = 'script', Modified_Date = getdate()
                    WHERE Session_Id = :Session_Id AND Active = 1
                    ''')
    batch_size = 1000
    deactivate_sessions_params = sessions_to_deactivate.to_dict('records')
    for curr_index in range(0, len(deactivate_sessions_params), batch_size): 
        curr_deactivate_params = deactivate_sessions_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_deactivate_params)

def get_units_for_fa_org_id(db: Database, fa_root_org_id: str):
    query = text('''
                    SELECT org.[Organization_Id],
                           org.[Organization_Name],
                           unit.[UnitNr],
                           unit.[UnitLicenceNr],
                           unit.[SerialNr] VIN_Number,
                           sa_unit.[Asset_Id] Provider_Asset_Id,
                           ss.Consumer_Asset_Id,
                           org.[Root_Organization_Id],
                           unit.CustomerCombiNr,sc.Organization_Id SC_Organization_Id,unit.CustomerReferenceNr,sa_unit.Fleet_Id
                    FROM FA_Organization (NOLOCK) org
                    LEFT JOIN (
                                    SELECT  Organization_Id, 
                                            Customer_Number_Combi
                                    FROM FA_Org_Cust_Mapping (NOLOCK)
                                    WHERE Active = 1
                                ) org_combi ON org_combi.Organization_Id = org.Organization_Id 
                    LEFT JOIN (
                                SELECT  UnitNr, 
                                        UnitLicenceNr, 
                                        SerialNr, 
                                        CustomerCombiNr,
                                        CustomerNr,
                                        RateNr,
                                        MasterLeaseNr,
                                        CompanyNr,
                                        RateCompanyNr,
                                        IntchType,
                                        LegalEntity,CustomerReferenceNr
                                FROM SCALAR.Fact_Unit (NOLOCK)
                                WHERE IntchType NOT IN ('Sitting', 'NA')
                                ) unit ON unit.CustomerCombiNr = org_combi.Customer_Number_Combi
                    INNER JOIN (
                                SELECT Unit_Nr,
                                       Asset_Id,
                                       Device_Pairing_Status,
                                       Active,Fleet_Id
                                FROM SCALAR.SC_Asset (NOLOCK)
                            ) sa_unit ON sa_unit.Unit_Nr = unit.UnitNr AND sa_unit.Active=1
					INNER JOIN SCALAR.SC_Organization sc ON sc.FA_Root_Organization_Id = org.Root_Organization_Id AND sc.Active=1
					INNER JOIN ( SELECT Provider_Asset_Id,Consumer_Asset_Id,Status,Consumer_Organization_Id
								FROM SCALAR.SC_Session(NOLOCK)
							)ss ON ss.Provider_Asset_Id = sa_unit.Asset_Id AND sc.Organization_Id=ss.Consumer_Organization_Id AND ss.Status ='running'
                    WHERE org.Root_Organization_Id = :fa_root_org_id
                         AND org.FleetConnected_Ind = 'Y'                             
                ''')
    return db.query(statement=query, params={"fa_root_org_id": fa_root_org_id}, as_dataframe=True)

def get_assinged_assets_for_report(db: Database, sc_org_id: str, fa_root_org_id: str):
    query = text('''
                     SELECT ag.SC_Organization_Id,so.Organization_Name Scalar_Organization_Name,ag.Asset_Group_Id,ag.Asset_Group_Name,ag.Description,a1.Asset_Group_Id Root_Asset_Group_Id,a1.Asset_Group_Name Root_Asset_Group_Name,ss.Consumer_Asset_Id Scalar_Asset_Id,
                        Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date 
					FROM SCALAR.SC_Asset_Group_Asset_Mapping agm
                    JOIN SCALAR.SC_Asset_Group(NOLOCK) ag  ON ag.Asset_Group_Id =agm.Asset_Group_Id
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id
                    JOIN SCALAR.SC_Session (NOLOCK) ss ON ss.Consumer_Asset_Id = agm.Asset_Id AND ss.Status ='running'
                    JOIN SCALAR.SC_Asset (NOLOCK) sa ON sa.Asset_Id = ss.Provider_Asset_Id AND sa.Active=1
                    JOIN FA_Organization(NOLOCK) fo ON fo.Organization_Id = ag.FA_Organization_Id  AND fo.Active=1
                    JOIN SCALAR.SC_Organization(NOLOCK) so ON so.Organization_Id = ag.SC_Organization_Id  AND so.Active=1 
                    Where (fo.Organization_Id= :fa_root_org_id OR fo.Root_Organization_id = :fa_root_org_id )
                    UNION ALL
                    SELECT ag.SC_Organization_Id,so.Organization_Name Scalar_Organization_Name,ag.Asset_Group_Id,ag.Asset_Group_Name,ag.Description,a1.Asset_Group_Id Root_Asset_Group_Id,a1.Asset_Group_Name Root_Asset_Group_Name,sa.Asset_Id Scalar_Asset_Id,
                        Internal_Code,Unit_Nr,Device_Number,Device_Pairing_Status,Device_Pairing_Date 
                    FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK) agm
                    JOIN SCALAR.SC_Asset_Group(NOLOCK) ag  ON ag.Asset_Group_Id =agm.Asset_Group_Id
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id
                    JOIN SCALAR.SC_Asset (NOLOCK) sa ON sa.Asset_Id = agm.Asset_Id AND sa.Active=1
                    JOIN FA_Organization(NOLOCK) fo ON fo.Organization_Id = ag.FA_Organization_Id  AND fo.Active=1
                    JOIN SCALAR.SC_Organization(NOLOCK) so ON so.Organization_Id = ag.SC_Organization_Id  AND so.Active=1
                    WHERE ag.SC_Organization_Id= :sc_org_id
                    AND (fo.Organization_Id = :fa_root_org_id OR fo.Root_Organization_id= :fa_root_org_id)
                ''')
    return db.query(statement=query, params={"fa_root_org_id": fa_root_org_id, "sc_org_id": sc_org_id}, as_dataframe=True)

def get_customer_asset_group_for_report(db: Database, fa_root_org_id: str):
    query = text('''
                    Select sg.SC_Organization_Id,so.Organization_Name Scalar_Organization_Name,sg.Asset_Group_Id,sg.Asset_Group_Name,sg.Description,sg.Root_Group_Id,
			        sg2.Asset_Group_Name Root_Asset_Group_Name,sg.Parent_Group_Id,sg1.Asset_Group_Name Parent_Asset_Group_Name,sg.FA_Organization_Id
                    FROM SCALAR.SC_Asset_Group(NOLOCK) sg 
					JOIN SCALAR.SC_Organization(nolock) so ON so.Organization_Id= sg.SC_Organization_Id AND so.Active=1 
					LEFT OUTER JOIN SCALAR.SC_Asset_Group(NOLOCK) sg1 ON sg.Parent_Group_Id =sg1.Asset_Group_Id AND sg1.Active=1
                    LEFT OUTER JOIN SCALAR.SC_Asset_Group(NOLOCK) sg2 ON sg.Root_Group_Id =sg2.Asset_Group_Id AND sg2.Active=1
					WHERE sg.Active=1 AND sg.FA_Organization_Id in (Select Organization_Id from FA_Organization(nolock) 
                    WHERE (Organization_Id=:fa_root_org_id or Root_Organization_id=:fa_root_org_id) AND Active=1)
                    ORDER BY (case when so.Organization_Name='TIP HQ' then 1 else 0 end) desc,FA_Organization_Id                            
                ''')
    return db.query(statement=query, params={"fa_root_org_id": fa_root_org_id}, as_dataframe=True)

from app.fleetconnected_migration.customer_migration.fc_customer_migration_data_access import get_customer_asset_group_for_report

def get_subcontracted_tenancy_record(fc_db: FleetConnectedDatabase, root_org_id: str) -> list: 
    subcontracted_tenancy_company_id_statement = text('''
                                                        SELECT company_id, tenancy_populated, company_code, brakeplus_tenancy, customer_owned_tenancy, fr_integrated, domain_login_company_code, subcontractor_cust_id
                                                        FROM t_fc_organization_tenancy
                                                        WHERE wam_root_org_id = :rorg AND tenancy_populated = 1
                                                        ''')

    result = fc_db.query(statement=subcontracted_tenancy_company_id_statement,
                                                params={"rorg": root_org_id})

    if len(result) == 0 or result == None:
        return None
    else:
        return result[0]

def get_data_sharing_details_from_scalar_db(db: Database, sc_org_id:str):
    select_statement = text('''
                                SELECT DISTINCT se.Session_Id, se.Consumer_Organization_Id, se.Provider_Asset_ID,
                                se.Consumer_Asset_Id, se.Status, se.Real_Start, se.Real_Stop, convert(int,sa.Unit_Nr)unit_nr
                                FROM SCALAR.SC_Session (NOLOCK) se
                                FULL OUTER JOIN SCALAR.SC_Asset (NOLOCK) sa ON se.Provider_Asset_Id =sa.Asset_Id 
                                AND se.Active = 1 AND sa.Active = 1
                                WHERE se.Consumer_Organization_Id = :sc_org_id                   
                            ''')
    result = db.query(statement=select_statement, params={"sc_org_id": sc_org_id}, as_dataframe=True)
    return result

def get_scalar_migration_status(db:Database, fa_root_org_id):
    select_statement = text('''
                                SELECT SC_Organization_Id, SC_Organization_Name, SKY_Company_id, SKY_Company_code, Migrated_Flag
                                FROM SCALAR.SC_Migrated_SKY_Customer_To_Scalar (NOLOCK) 
                                WHERE FA_Root_Org_Id = :fa_root_org_id                          
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id}, as_dataframe=True)
    return result

def get_all_users_from_db_for_org(db: Database, sc_org_id: str):
    existing_users = db.get_session().query(SC_User).filter(SC_User.Status.in_(['Active','Pending']), SC_User.SC_Organization_Id == sc_org_id).all()
    return existing_users

def cust_sync_user_role_mapping_in_db(db: Database, user_role_to_map, batch_size, logger):
    user_role_mapping_data_count = len(user_role_to_map)
    for curr_index in range(0, user_role_mapping_data_count, batch_size): 
        db.insert_orm_list(user_role_to_map[curr_index:curr_index + batch_size])
    logger.info(msg=f"Inserted user role mapping for {len(user_role_to_map)} users")

def update_migration_log_table(db: Database, params):
    query = text('''INSERT INTO SCALAR.SC_Migration_Process_Status_Log
                    Run_Id, 
                    ''')
    db.insert_update_delete_raw(statement=query, params=params)

def get_all_fa_users_in_a_scalar_organization(db: Database, sc_org_id: str):
    query = text('''SELECT DISTINCT sc.User_Id SC_User_Id,sc.SC_Organization_Id, sc.User_Email SC_User_Email, fu.User_Id FA_User_Id, fu.User_First_Name, fu.User_Last_Name, fu.User_Email FA_User_Email, fu.Tip_User, 
                            fu.Fleet_Connected_Ind, fu.FleetRadar_Ind, fu.Language_Id, fo.Organization_Id FA_Organization_Id, 
                            fu.Root_Organization_Id FA_Root_Organization_Id
                    FROM SCALAR.SC_User (NOLOCK)  sc
                    LEFT JOIN dbo.FA_User (NOLOCK) fu
                    ON sc.FA_User_Id =fu.User_Id
                    AND fu.Tip_User IN ('N', 'n') AND fu.Active = 1 AND fu.Fleet_Connected_Ind IN ('Y', 'y')
                    LEFT JOIN dbo.FA_User_Org_Mapping (NOLOCK) fo
                    ON fu.User_Id=fo.User_Id AND fo.Active = 1
	                WHERE sc.SC_Organization_Id = :sc_org_id AND sc.Status IN ('Active', 'Pending')                       
                ''')
    result = db.query(statement=query, params={"sc_org_id": sc_org_id}, as_dataframe=True)
    if result is None or len(result) == 0: 
        return None
    else: 
        return result

def get_scalar_region_migration_status(db:Database, region_id):
    select_statement = text('''
                                SELECT Region_Cd, Migrated_Flag
                                FROM SCALAR.SC_Migrated_Region_To_Scalar (NOLOCK) 
                                WHERE Region_Id = :region_id                          
                            ''')
    result = db.query(statement=select_statement, params={"region_id": region_id}, as_dataframe=True)
    return result

def get_scalar_assets_for_fa_root_org(db:Database, fa_root_org_id: int):
    select_statement = text('''
                                SELECT sa_unit.Asset_Id,sa_unit.Unit_Nr,unit.UnitLicenceNr,Device_Number,Device_Pairing_Status,Device_Pairing_Date FROM SCALAR.SC_Asset (NOLOCK) sa_unit
                                JOIN SCALAR.Fact_Unit (NOLOCK) unit ON sa_unit.Unit_Nr = convert(varchar,unit.UnitNr) 
                                JOIN FA_Org_Cust_Mapping (NOLOCK) org_combi ON unit.CustomerCombiNr = org_combi.Customer_Number_Combi and org_combi.Active=1
                                JOIN FA_Organization (NOLOCK) org ON org_combi.Organization_Id = org.Organization_Id and org.Active=1
                                WHERE (org.Organization_Id=:farootorgid or org.Root_Organization_Id=:farootorgid) and sa_unit.Active=1
                                AND org.FleetConnected_Ind = 'Y'
                               
                            ''')
    result = db.query(statement=select_statement, params={"farootorgid": fa_root_org_id}, as_dataframe=True)
    return result

def inform_to_fleetconnected_database(fc_db: FleetConnectedDatabase, fa_root_org_id):
    
    query = text(f'''
                   UPDATE [dbo].[t_fc_organization_tenancy]
                    SET tenancy_populated=2,
                    last_modified_by = 'Scalar',
                    last_modified_dt = getdate()
                    WHERE wam_root_org_id = :fa_root_org_id and tenancy_populated=1                     
            ''')
    fc_db.insert_update_delete_raw(statement=query, params={"fa_root_org_id": fa_root_org_id})

