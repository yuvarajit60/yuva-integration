from sqlalchemy import text
from app.common.constants import BPAdditionalChargeType
from app.common.database import Database


def get_brake_plus_units_with_no_bp_addl_charge(db: Database):
    query = text('''SELECT u.UnitNr Unit_Nr,u.UnitLicenceNr License_Nr,sa.Asset_Id,so.Organization_Id SC_Organization_Id,Organization_Name SC_Organization_Name,FA_Root_Organization_Id FA_Root_Org_Id FROM SCALAR.SC_Asset (NOLOCK) sa
                    LEFT OUTER JOIN SCALAR.Fact_Unit u ON u.UnitNr = sa.Unit_Nr
                    JOIN SCALAR.SC_Session (NOLOCK) ss ON ss.Status='running' AND sa.Asset_Id =ss.Provider_Asset_Id AND ss.Active=1
                    JOIN SCALAR.SC_Organization so ON so.Organization_Id =Consumer_Organization_Id AND so.Active=1
                    JOIN SCALAR.SC_Asset_Brake_Performance_Activation (NOLOCK) bp ON ss.Provider_Asset_Id = bp.Asset_Id AND bp.Active=1 AND (bp.EBPMS_State = 'enabled' OR bp.EBPMS_State = 'enabling')
                    WHERE sa.Active=1 AND sa.Device_Pairing_Status = '1' 
                    AND NOT EXISTS (SELECT ac.Rate_Nr
                                             FROM SCALAR.Additional_Charges ac
                                             WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
                                             AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
                                             AND ac.Additional_Charge_Type IN :fc_charge_types)
                ''')
    return db.query(statement=query, params={"fc_charge_types": BPAdditionalChargeType.BP_Insight_Additional_Charge_Types}, params_to_expand=["fc_charge_types"], as_dataframe=True)

def update_existing_bp_data_in_db(db: Database, existing_bp_data):
    query = text('''UPDATE SCALAR.SC_Asset_Brake_Performance_Activation with(rowlock)
                    SET EBPMS_State = :ebpms, EBPMS_State_Timestamp = :ebpmsTimestamp,
                    Modified_Date = getdate()
                    WHERE Asset_Id = :assetId
                ''')
    existing_bp_params = existing_bp_data.to_dict('records')
    batch_size = 1000
    for curr_index in range(0, len(existing_bp_params), batch_size):
        curr_existing_bp_params = existing_bp_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_existing_bp_params)