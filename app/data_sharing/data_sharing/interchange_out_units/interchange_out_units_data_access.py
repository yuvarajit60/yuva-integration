from sqlalchemy import text
from datetime import datetime

from app.common.constants import AdditionalChargeType
from app.common.database import Database

def get_interchange_out_units(db: Database, last_successful_execution_ts: datetime):
    query = text('''SELECT u.UnitNr, sa.UnitLicenceNr, sa.VIN_Number, u.CustomerCombiNr,u.Region Region_Name,u.BranchName Owning_Branch_Name,
                    u.Country Country_Name,u.IntchType, u.IntchOutDateTime, u.CustomerName Customer_Name, u.RateNr, u.MasterLeaseNr, 
                    fa_org_combi.Customer_Number_Combi as fa_combi_nr, fa_org.Organization_Id,
                    fa_org.Organization_Name AS organization_name, fa_org.Root_Organization_Id,
                    CASE WHEN fa_org.Root_Organization_Id is null THEN fa_org.Organization_Name ELSE p_fa_org.Organization_Name END AS root_org_name,
                    fa_org.Organization_Level,fa_org.FleetConnected_Ind,fa_org.Fleetradar_Ind,
                    sa.Asset_Id,u.CustomerReferenceNr,sa.Fleet_Id
                    FROM (
							SELECT fu.UnitNr, fu.UnitLicenceNr, fu.SerialNr, fu.CustomerCombiNr, branch.Region, branch.BranchName,
							branch.Country, fu.IntchType, fu.IntchOutDateTime, cust.CustomerName, 
							fu.RateNr, fu.MasterLeaseNr, fu.RateCompanyNr, fu.CustomerNr,fu.CustomerReferenceNr
							from SCALAR.Fact_Unit (NOLOCK) fu
							LEFT JOIN (SELECT BranchNr, BranchName, Country, Region FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON fu.OwningBranchNr = branch.BranchNr
							LEFT JOIN (SELECT CustomerName, CustomerCombinr FROM Floki.[Dim_Customer] (NOLOCK)) cust ON  fu.CustomerCombiNr = cust.CustomerCombinr
							WHERE fu.RateNr	is not null 
							AND (fu.IntchInDateTime is null OR fu.IntchInDateTime > getdate())
							AND (fu.IntchOutCommitDateTime >= CONVERT(DATETIME, CONVERT(DATE, :last_successful_execution_ts)) 
                            OR fu.IntchOutDateTime >= CONVERT(DATETIME, CONVERT(DATE, :last_successful_execution_ts)))
							UNION ALL
							SELECT fu1.UnitNr, fu1.UnitLicenceNr, fu1.SerialNr, intch.CustomerCombiNr as customer_combi_nr, branch.Region, branch.BranchName,
							branch.Country, intch.IntchType as intch_type, intch.IntchOutDateTime as intch_out_datetime, cust.CustomerName, 
							intch.RateNr as rate_nr, intch.MasterLeaseNr as mstrls_nr, intch.RateCompanyNr as rate_company_nr, intch.CustomerNr as customer_nr,fu1.CustomerReferenceNr
							FROM SCALAR.Fact_Interchange (NOLOCK) intch	
							JOIN SCALAR.Fact_Unit (NOLOCK) fu1 on intch.UnitNr = fu1.UnitNr
							LEFT JOIN (SELECT BranchNr, BranchName, Country, Region FROM [Floki].[Dim_Branch] (NOLOCK)) branch ON fu1.OwningBranchNr = branch.BranchNr
							LEFT JOIN (SELECT CustomerName, CustomerCombinr FROM [Floki].[Dim_Customer] (NOLOCK)) cust ON fu1.CustomerCombiNr = cust.CustomerCombinr
							WHERE intch.OutTransactionTime >= CONVERT(DATETIME, CONVERT(DATE, :last_successful_execution_ts)) and intch.OutTransactionTime <= getdate() and intch.IntchOutDateTime > getdate()
					) u 
                    LEFT JOIN (SELECT Organization_Id,
                                Customer_Number_Combi, Active
                                FROM FA_Org_Cust_Mapping (NOLOCK)) fa_org_combi
                             ON fa_org_combi.Customer_Number_Combi = u.CustomerCombiNr 
                             AND fa_org_combi.Active = 1
                    LEFT JOIN (SELECT Organization_Id,
                                Root_Organization_Id,
                                Parent_Organization_Id,
                                Organization_Name,
                                Organization_Level,
                                FleetConnected_Ind,
                                Fleetradar_Ind,
                                Active,Country_Id
                                FROM FA_Organization (NOLOCK)) fa_org
                            ON fa_org_combi.Organization_Id = fa_org.Organization_Id 
                            AND fa_org.Active=1 and fa_org.FleetConnected_Ind = 'Y' 
                    LEFT JOIN (SELECT Organization_Id,
                                Root_Organization_Id,
                                Parent_Organization_Id,
                                Organization_Name,
                                Organization_Level,
                                FleetConnected_Ind,
                                Fleetradar_Ind,
                                Active
                                FROM FA_Organization (NOLOCK)) p_fa_org 
							ON fa_org.Root_Organization_Id = p_fa_org.Organization_Id and fa_org.Active = 1 and p_fa_org.Active=1
                                AND p_fa_org.FleetConnected_Ind = 'Y' 
                    LEFT JOIN (SELECT Asset_Id, Unit_Nr, Device_Pairing_Status ,Active,Fleet_Id, Unit_Licence_Nr UnitLicenceNr,VIN_Number 
                            FROM SCALAR.SC_Asset (NOLOCK)) sa
                            ON u.UnitNr = sa.Unit_Nr AND sa.Active=1 AND sa.Device_Pairing_Status  = '1'
                    WHERE  EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
                                    WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
                                    AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
                                    AND ac.Additional_Charge_Type IN :insight_add_chrg_types)
            ''')
    params={"last_successful_execution_ts": last_successful_execution_ts, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=["insight_add_chrg_types"])
