from sqlalchemy import text
from pandas import DataFrame
from app.common.constants import AdditionalChargeType
from app.common.database import Database

def get_cust_combi_numbers(db: Database, organization_id: int) -> list:
    query = text('''SELECT convert(varchar,Customer_Number_Combi)Customer_Number_Combi
                    FROM FA_Org_Cust_Mapping
                    WHERE Organization_Id = :organization_id
                    AND Active = '1' 
                ''')
    result = db.query(statement=query, params={"organization_id": organization_id}, as_dataframe=True)
    return result['Customer_Number_Combi'].tolist()

def get_insight_units_by_combi_numbers(db: Database, cust_combi_numbers: list, root_org_id: int):
    query = text(''' SELECT u.UnitNr, tu.Asset_Id, u.UnitLicenceNr, u.CustomerCombiNr, wo.Organization_Id, wo.Root_Organization_Id
                FROM SCALAR.Fact_Unit (NOLOCK) u
                JOIN FA_Org_Cust_Mapping (NOLOCK) woc
                    ON woc.Customer_Number_Combi = u.CustomerCombiNr AND woc.Active = 1
                JOIN FA_Organization (NOLOCK) wo
                    ON woc.Organization_Id = wo.Organization_Id AND wo.Active = 1
                LEFT JOIN SCALAR.SC_Asset (NOLOCK) tu
                    ON tu.Unit_Nr = u.UnitNr AND tu.Active=1 AND tu.Device_Pairing_Status = '1'
                WHERE u.CustomerCombiNr IN :cust_combi_numbers and wo.root_organization_id = :root_org_id
                AND EXISTS ( SELECT Rate_Nr
                                        FROM SCALAR.Additional_Charges ac
                                        WHERE  u.CustomerNr = ac.Customer_Nr  
                                                and u.RateNr = ac.Rate_Nr 
                                                and u.MasterLeaseNr = ac.Mstrls_Nr
                                                and u.RateCompanyNr = ac.Company_Nr
                                                and ac.Additional_Charge_Type in :insight_add_chrg_types)
            ''')
    params={"cust_combi_numbers": cust_combi_numbers, "root_org_id":root_org_id, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['cust_combi_numbers', 'insight_add_chrg_types'])

def get_fa_users_by_fa_org_id(db: Database, fa_org_id: str):
    query = text('''
                    SELECT Id from FA_User_Org_Mapping WHERE Organization_Id = :org_id and Active = '1'
                 ''')
    params={"org_id":fa_org_id}
    return db.query(statement=query, params=params, as_dataframe=True)   

def get_fa_organization(db: Database, fa_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Name, Root_Organization_Id, Parent_Organization_Id, 
                                Region_Id, Country_Id, Fleetconnected_Ind, Organization_Level
                                FROM FA_Organization (NOLOCK) WHERE Organization_Id= :fa_org_id                         
                            ''')
    result = db.query(statement=select_statement, params={"fa_org_id": fa_org_id}, as_dataframe=True)
    return result