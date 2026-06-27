from sqlalchemy import text
from datetime import datetime

from app.common.constants import AdditionalChargeType
from app.common.database import Database

def get_interchange_in_units(db: Database, last_successful_execution_ts: datetime):
    query = text('''SELECT intch.UnitNr, u.UnitLicenceNr, u.CustomerCombiNr, intch.intch_in_cust_combi_nr, intch.RateNr, intch.MasterLeaseNr, intch.CompanyNr, intch.CustomerNr,
                    fa_org_combi.Customer_Number_Combi as wam_combi_nr, intch.IntchType, intch.IntchInDateTime, branch.BranchName Owning_Branch_Name, branch.Country Country_Name, branch.Region as Region_Name,
                    cust.CustomerName Customer_Name,fa_org.Organization_Id, fa_org.Organization_Name AS organization_name, fa_org.Root_Organization_Id,
                    CASE WHEN fa_org.Root_Organization_Id is null THEN fa_org.Organization_Name ELSE r_fa_org.Organization_Name END AS root_org_name,
                    fa_org.Organization_Level,
                    sa.Asset_Id
                    FROM (SELECT UnitNr, IntchKey, IntchType, IntchInDateTime, IntchInCommitDateTime, 
                        CustomerCombiNr as intch_in_cust_combi_nr, RateNr, MasterLeaseNr, CompanyNr, CustomerNr, RateCompanyNr 
                        FROM SCALAR.Fact_Interchange (NOLOCK)
                        WHERE CustomerNr not in (500, 700)
                        ) intch
                    JOIN (SELECT UnitNr, CustomerCombiNr, UnitLicenceNr, OwningBranchNr, --owning_country_name, region,
						CustomerNr,
                        CASE WHEN IntchKey IS NULL THEN PreviousIntchKey ELSE IntchKey END AS intchg_key
                        FROM SCALAR.Fact_Unit(nolock)) u
                        ON (intch.IntchKey = u.intchg_key)
                    LEFT JOIN (SELECT Organization_Id,
                                Customer_Number_Combi, Active
                                FROM FA_Org_Cust_Mapping (nolock)) fa_org_combi
                             ON fa_org_combi.Customer_Number_Combi = intch.intch_in_cust_combi_nr
                             AND fa_org_combi.Active = 1
                    LEFT JOIN (SELECT Organization_Id,
                                Root_Organization_Id,
                                Parent_Organization_Id,
                                Organization_Name,
                                Organization_Level,
                                FleetConnected_Ind,
                                Fleetradar_Ind,Active,Country_Id
                                FROM FA_Organization (nolock)) fa_org
                            ON fa_org_combi.Organization_Id = fa_org.Organization_Id
                            AND fa_org.Active = 1 AND fa_org.FleetConnected_Ind = 'Y' 
                    LEFT JOIN (SELECT Organization_Id,
                                Organization_Name,
                                Active,
                                FleetConnected_Ind,
                                Fleetradar_Ind
                                FROM FA_Organization (nolock)) r_fa_org
                            ON fa_org.Root_Organization_Id = r_fa_org.Organization_Id and fa_org.Active = 1 and r_fa_org.Active = 1
                            AND r_fa_org.FleetConnected_Ind = 'Y' 
                    LEFT JOIN (SELECT Asset_Id, Unit_Nr, Device_Pairing_Status ,Active
                            FROM SCALAR.SC_Asset (nolock)) sa
                            ON u.UnitNr = sa.Unit_Nr AND sa.Active=1 AND sa.Device_Pairing_Status = '1'
					LEFT JOIN (SELECT BranchNr, BranchName, Country, Region FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON u.OwningBranchNr = branch.BranchNr
					LEFT JOIN (SELECT CustomerName, CustomerCombinr FROM [Floki].[Dim_Customer] (NOLOCK)) cust ON u.CustomerCombiNr = cust.CustomerCombinr
                    WHERE (
                            (intch.IntchInDateTime < getdate()
                            AND (intch.IntchInCommitDateTime >= CONVERT(DATETIME, CONVERT(DATE, :last_successful_execution_ts))
                                OR
                                intch.IntchInDateTime >= CONVERT(DATETIME, CONVERT(DATE, :last_successful_execution_ts)))
                            )
                        )
                    AND EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
								WHERE  intch.CustomerNr = ac.Customer_Nr AND intch.RateCompanyNr = ac.Company_Nr
								AND intch.RateNr = ac.Rate_Nr AND intch.MasterLeaseNr = ac.Mstrls_Nr
								AND ac.Additional_Charge_Type IN :insight_add_chrg_types)                      
                ''')

    params={"last_successful_execution_ts": last_successful_execution_ts, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=["insight_add_chrg_types"])
    