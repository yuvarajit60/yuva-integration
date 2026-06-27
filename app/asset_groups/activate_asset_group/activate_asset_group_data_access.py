from sqlalchemy import text
from pandas import DataFrame
from app.common.constants import AdditionalChargeType
from app.common.database import Database


def get_org_unit_details(db: Database, org_ids: list) -> DataFrame:
    select = text('''
                    SELECT org.[Organization_Id],
                           org.[Organization_Name],
                           unit.[UnitNr],
                           tel_unit.[UnitLicenceNr],
                           unit.[CustomerCombiNr],
                           tel_unit.[VIN_Number],
                           tel_unit.[Asset_Id],unit.CustomerReferenceNr,tel_unit.Fleet_Id
                    FROM FA_Organization (NOLOCK)org
                    INNER JOIN (
                                    SELECT  Organization_Id,
                                            Customer_Number_Combi
                                    FROM FA_Org_Cust_Mapping (NOLOCK)
                                    WHERE Active = 1
                                ) org_combi ON org_combi.Organization_Id = org.Organization_Id
                    INNER JOIN (
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
                    LEFT JOIN (
                                SELECT Unit_Nr,
                                       Asset_Id, Active, Device_Pairing_Status,Fleet_Id,Unit_Licence_Nr UnitLicenceNr,VIN_Number
                                FROM SCALAR.SC_Asset (NOLOCK) 
                            ) tel_unit ON tel_unit.Unit_Nr = unit.UnitNr AND tel_unit.Active=1 AND tel_unit.Device_Pairing_Status = 1
                    WHERE org.Organization_Id IN :org_ids AND org.Active = 1
                         AND  ( EXISTS
                                    (
                                        SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
                                        WHERE  ISNULL(unit.CustomerNr, '')  = ISNULL(ac.Customer_Nr, '') AND ISNULL(unit.RateCompanyNr, '') = ISNULL(ac.Company_Nr, '')
											AND ISNULL(unit.RateNr, '') = ISNULL(ac.Rate_Nr, '') AND ISNULL(unit.MasterLeaseNr, '') = ISNULL(ac.Mstrls_Nr, '')
											AND ac.Additional_Charge_Type IN :insight_add_chrg_types
                                            )
                                );
                 ''')
    return db.query(statement=select, params={"org_ids": org_ids, "insight_add_chrg_types": AdditionalChargeType.Insight_Additional_Charge_Types}, params_to_expand=["insight_add_chrg_types", "org_ids"], as_dataframe=True)