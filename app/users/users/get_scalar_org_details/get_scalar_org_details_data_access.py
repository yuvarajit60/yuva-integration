from app.common.database import Database
from pandas import DataFrame
from sqlalchemy import text


def get_fa_scalar_user_details(db: Database, user_id: str) -> DataFrame:
    query = text('''SELECT FA_User_Id,SC_User_Id,Tip_User,Fleet_Connected_Ind,root_org_id FROM
                    (SELECT DISTINCT u.User_Id as FA_User_Id,sc.User_Id as SC_User_Id,u.Tip_User,Fleet_Connected_Ind,
                    Null root_org_id
                    FROM FA_User (NOLOCK) u
                    LEFT JOIN SCALAR.SC_User (NOLOCK) sc on sc.FA_User_Id=:user_id AND sc.Status IN('Active','Pending') 
                    LEFT JOIN SCALAR.SC_Organization (NOLOCK) so ON so.Organization_Id = sc.SC_Organization_Id AND Is_Provider='Y' AND so.Active = 1
                    WHERE u.Active=1 AND upper(u.User_Id) = upper(:user_id) AND Tip_User='Y'
                    UNION ALL
                    SELECT DISTINCT u.User_Id as FA_User_Id,sc.User_Id as SC_User_Id,u.Tip_User,Fleet_Connected_Ind,
                    CASE WHEN o.Root_Organization_Id is null THEN convert(varchar,o.Organization_Id) ELSE convert(varchar,o.Root_Organization_Id) END AS root_org_id
                    FROM FA_User (NOLOCK) u
                    LEFT JOIN FA_Organization (NOLOCK) o ON u.Organization_Id=o.Organization_Id AND o.Active=1
                    LEFT JOIN SCALAR.SC_Organization (NOLOCK) so ON so.FA_Root_Organization_Id = u.Root_Organization_Id 
                    LEFT JOIN SCALAR.SC_User (NOLOCK) sc on sc.FA_User_Id=:user_id AND so.Organization_Id = sc.SC_Organization_Id AND sc.Status IN('Active','Pending')
                    AND Is_Provider='N' AND so.Active = 1
                    WHERE u.Active=1 AND upper(u.User_Id) = upper(:user_id) AND Tip_User='N')T
                ''')
    result = db.query(statement=query, params={"user_id":user_id})
    return result


def get_connection_name(db: Database, source: str) -> DataFrame:
    query = text('''
                    SELECT Connection_Name, Region_Cd from SCALAR.SC_Organization_Profile(NOLOCK)
                    WHERE Source = :source AND Active =1
                ''')
    result = db.query(statement=query, params={"source":source})
    return result 

