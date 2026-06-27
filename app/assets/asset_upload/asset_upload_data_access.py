from app.common.constants import GeneralConstant
from app.common.database import Database
from sqlalchemy import text

def get_TIPGlobal_main_asset_group(db: Database, org_id: str):
    query = text('''SELECT Asset_Group_Id,Asset_Group_Name,Description FROM SCALAR.SC_Asset_Group(NOLOCK) 
                    WHERE Asset_Group_Name=:main_group AND SC_Organization_Id=:org_id
                    AND Active=1
            ''')
    return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "org_id": org_id}, as_dataframe=True)

def get_child_asset_group_for_TIPGlobal_asset_group(db: Database, asset_limit: int):
    query = text('''Select ag.Asset_Group_Name,ag.Asset_Group_Id,a1.Asset_Group_Name Parent_Asset_Group_Name,a1.Asset_Group_Id Parent_Asset_Group_Id,Count(Asset_Id)Asset_Count from SCALAR.SC_Asset_Group_Asset_Mapping agm
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) ag ON ag.Asset_Group_Id=agm.Asset_Group_Id AND ag.Active=1
                    JOIN SCALAR.SC_Asset_Group (NOLOCK) a1 ON ag.Parent_Group_Id=a1.Asset_Group_Id AND a1.Active=1
                    WHERE agm.Active=1 AND a1.Asset_Group_Name=:main_group
                    Group By ag.Asset_Group_Id,ag.Asset_Group_Name,a1.Asset_Group_Name,a1.Asset_Group_Id
                    Having Count(Asset_Id) < :asset_limit
            ''')
    return db.query(statement=query, params={"main_group": GeneralConstant.TIPGLOBALGROUP, "asset_limit": asset_limit}, as_dataframe=True)

def get_asset_mapping_to_country_group(db:Database, tip_unit_nr:int, provider_org_id:str):
    query = text('''SELECT fu.UnitNr, branch.Region,branch.Country, sag.Asset_Group_Id Country_Group_Id, sag.Asset_Group_Name
							from SCALAR.Fact_Unit (NOLOCK) fu
                    JOIN  (SELECT Region,BranchNr, 
                    Country = CASE 
                                WHEN Country IN ('UK Trailer', 'UK Tankers') THEN 'United Kingdom'
                                WHEN Country = 'Ireland Tankers' THEN 'Ireland' 
                                ELSE Country
                            END
                    FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON fu.OwningBranchNr = branch.BranchNr
                    JOIN  [SCALAR].[SC_Asset_Group] sag ON sag.Asset_Group_Name = branch.Country
                    AND SC_Organization_Id = :provider_org_id AND sag.Active = 1
                    WHERE fu.UnitNr = :tip_unit_nr
            ''')
    return db.query(statement=query, params={"tip_unit_nr": tip_unit_nr, "provider_org_id": provider_org_id}, as_dataframe=True)

def get_customer_asset_details(db: Database, asset_Id: str):
    query = text('''SELECT SO.Organization_Name SC_Organization_Name,SO.Organization_Id SC_Organization_Id,SS.Consumer_Asset_Id consumerAssetId,SA.Asset_Id providerAssetId
                        ,u.UnitNr
                        FROM SCALAR.SC_Session(NOLOCK) SS
                        JOIN SCALAR.SC_Asset(NOLOCK) SA ON SS.Provider_Asset_Id = SA.Asset_Id
                        JOIN SCALAR.SC_Organization(NOLOCK) SO ON SO.Organization_Id = SS.Consumer_Organization_Id
                        JOIN SCALAR.Fact_Unit (NOLOCK) u ON u.UnitNr = SA.Unit_Nr
                        Where SA.Active=1 AND SA.Asset_Id=:provider_asset_id
                        AND SS.Status='running'
            ''')
    return db.query(statement=query, params={"provider_asset_id": asset_Id}, as_dataframe=True)
