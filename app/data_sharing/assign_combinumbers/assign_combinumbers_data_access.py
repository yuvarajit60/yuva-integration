from sqlalchemy import text
from pandas import DataFrame
from app.common.database import Database
from app.common.constants import AdditionalChargeType

def get_org_names(db: Database, org_id: str, root_org_id: str):
    org_name = None
    root_org_name = None
    select_statement = text('''
                             SELECT Organization_Id,
                                    Organization_Name
                             FROM FA_Organization
                             WHERE Organization_Id IN :org_ids
                            ''')

    org_ids = [org_id, root_org_id]
    temp_df = db.query(statement=select_statement, params={"org_ids": org_ids}, params_to_expand=["org_ids"], as_dataframe=True)
    org_id_df = temp_df.loc[temp_df['Organization_Id'] == org_id]
    root_org_id_df = temp_df.loc[temp_df['Organization_Id'] == root_org_id]

    if len(org_id_df) > 0:
        org_name = org_id_df.iloc[0]['Organization_Name']
    if len(root_org_id_df) > 0:
        root_org_name = root_org_id_df.iloc[0]['Organization_Name']
    
    return org_name, root_org_name

def get_insight_units_linked_to_combinumbers(db: Database, combi_nrs: list) -> DataFrame:
    select_statement = text('''SELECT UnitNr,tel_unit.UnitLicenceNr, Asset_Id, CustomerCombiNr,CustomerReferenceNr,Fleet_Id,tel_unit.VIN_Number FROM SCALAR.Fact_Unit(NOLOCK) u
	LEFT JOIN (SELECT Unit_Nr,
					Asset_Id,Device_Number,Device_Pairing_Status ,Active,Fleet_Id,Unit_Licence_Nr UnitLicenceNr,VIN_Number
					FROM SCALAR.SC_Asset(NOLOCK) 
					)tel_unit ON u.UnitNr = tel_unit.Unit_Nr and tel_unit.Active=1 and tel_unit.Device_Pairing_Status  = 1
	WHERE u.CustomerCombiNr IN :comb_nrs
		AND (EXISTS 
				(SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
				WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
				AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
				AND ac.Additional_Charge_Type IN :insight_add_chrg_types
				)
			)
		AND u.IntchType NOT IN ('Sitting', 'NA'); '''
                                )

    return db.query(statement=select_statement,
                    params={"comb_nrs": combi_nrs, "insight_add_chrg_types": AdditionalChargeType.Insight_Additional_Charge_Types},
                    params_to_expand=["comb_nrs", "insight_add_chrg_types"],
                    as_dataframe=True)
