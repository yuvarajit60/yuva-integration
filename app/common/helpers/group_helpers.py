from sqlalchemy import text
from app.common.database import Database


def get_sc_groups(db: Database, fa_organization_ids: list):
    query = text('''
                    SELECT   [Asset_Group_Id]
                            ,[FA_Organization_Id]
                            ,[SC_Organization_Id]
                            ,[Root_Group_Id]
                            ,[Parent_Group_Id]
                            ,[Description]
                            ,[Asset_Group_Name]
                            ,[Active]
                    FROM [SCALAR].[SC_Asset_Group]
                    WHERE FA_Organization_Id IN :FA_Organization_Id and Active = 1
                ''')
                          
    params={"FA_Organization_Id": fa_organization_ids}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=["FA_Organization_Id"])

def get_asset_groups_for_root_org(db: Database, FA_Root_Org_Id: int):
    query = text('''
                    SELECT   [Asset_Group_Id]
                            ,[FA_Organization_Id]
                            ,[SC_Organization_Id]
                            ,[Root_Group_Id]
                            ,[Parent_Group_Id]
                            ,[Description]
                            ,[Asset_Group_Name]
                            ,[Active]
                    FROM [SCALAR].[SC_Asset_Group]
                    WHERE FA_Organization_Id IN (Select Organization_Id from FA_Organization(nolock) where (Organization_Id=:FA_Root_Org_Id or Root_Organization_id=:FA_Root_Org_Id)) and Active = 1
                ''')
                          
    params={"FA_Root_Org_Id": FA_Root_Org_Id}
    return db.query(statement=query, params=params, as_dataframe=True)