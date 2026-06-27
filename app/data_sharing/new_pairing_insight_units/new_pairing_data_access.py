from sqlalchemy import text

from app.common.database import Database
from app.common.constants import AdditionalChargeType


def get_new_pairing_insight_units(db: Database):
    query = text('''SELECT u.UnitNr, sa.UnitLicenceNr, sa.VIN_Number, u.CustomerCombiNr, branch.Region Region_Name, branch.BranchName Owning_Branch_Name,
                    branch.Country Country_Name, u.IntchType, u.IntchOutDateTime, cust.CustomerName as Customer_Name, u.RateNr, u.MasterLeaseNr, 
                    fa_org_combi.Customer_Number_Combi as fa_combi_nr, 
                    fa_org.Organization_Id, fa_org.Organization_Name AS organization_name, fa_org.Root_Organization_Id,
                    CASE WHEN fa_org.Root_Organization_Id is null THEN fa_org.Organization_Name ELSE r_fa_org.Organization_Name END AS root_org_name,
                    fa_org.Organization_Level,fa_org.FleetConnected_Ind,fa_org.Fleetradar_Ind,
                    sa.Asset_Id,u.CustomerReferenceNr,sa.Fleet_Id
                    FROM SCALAR.Fact_Unit (nolock) u 
                    JOIN (SELECT distinct Unit_Nr
                        FROM SCALAR.SC_Insight_Unit_Missing_Pairing (nolock)
                        WHERE Treated = 0) m ON u.UnitNr = m.Unit_Nr
					JOIN (SELECT Asset_Id, Unit_Nr, Unit_Licence_Nr UnitLicenceNr, VIN_Number, Device_Pairing_Status ,Active,Fleet_Id
                            FROM SCALAR.SC_Asset (nolock)) sa
                            ON u.UnitNr = sa.Unit_Nr AND sa.Active=1 AND sa.Device_Pairing_Status = '1'
                    JOIN (SELECT Organization_Id,
                                Customer_Number_Combi, Active
                                FROM FA_Org_Cust_Mapping (nolock)) fa_org_combi
                             ON fa_org_combi.Customer_Number_Combi = u.CustomerCombiNr
                             AND fa_org_combi.Active = 1
                    JOIN (SELECT Organization_Id,
                                Root_Organization_Id,
                                Parent_Organization_Id,
                                Organization_Name,
                                Organization_Level,
                                FleetConnected_Ind,
                                Fleetradar_Ind,
                                Active,Country_Id
                                FROM FA_Organization (nolock)) fa_org 
                            ON fa_org_combi.Organization_Id = fa_org.Organization_Id 
                            AND fa_org.Active = 1 and fa_org.FleetConnected_Ind = 'Y' and fa_org.Fleetradar_Ind = 'Y'
                    JOIN (SELECT Organization_Id,
                                Organization_Name,
                                Active,
                                FleetConnected_Ind,
                                Fleetradar_Ind
                                FROM FA_Organization (nolock)) r_fa_org 
							ON fa_org.Root_Organization_Id = r_fa_org.Organization_Id and fa_org.Active = 1 and r_fa_org.Active = 1
                                AND r_fa_org.FleetConnected_Ind = 'Y' and r_fa_org.Fleetradar_Ind = 'Y'
					LEFT JOIN (SELECT BranchNr, BranchName, Country, Region FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON u.OwningBranchNr = branch.BranchNr
					LEFT JOIN (SELECT CustomerName, CustomerCombinr FROM [Floki].[Dim_Customer] (NOLOCK)) cust ON u.CustomerCombiNr = cust.CustomerCombinr
                    WHERE EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
                                    WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
                                    AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
                                    AND ac.Additional_Charge_Type IN :insight_add_chrg_types)
                ''')
    params={"insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=["insight_add_chrg_types"])
