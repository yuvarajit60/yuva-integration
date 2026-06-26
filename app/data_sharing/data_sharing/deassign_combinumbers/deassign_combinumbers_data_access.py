from app.common.database import Database
from sqlalchemy import text
from datetime import date


def get_asset_groups(db: Database, sc_provider_org_id: str, fa_root_org_id: int, sc_consumer_org_id: str, fa_org_id: int) -> list:
  query = text('''SELECT Asset_Group_Id, Asset_Group_Name, SC_Organization_Id 
                  FROM SCALAR.SC_Asset_Group WHERE SC_Organization_Id = :sc_provider_org_id AND FA_Organization_Id = :fa_root_org_id AND Active = 1
                  UNION ALL
                  SELECT Asset_Group_Id, Asset_Group_Name, SC_Organization_Id 
                  FROM SCALAR.SC_Asset_Group WHERE SC_Organization_Id = :sc_consumer_org_id AND FA_Organization_Id = :fa_org_id AND Active = 1
                  ''')

  return db.query(statement=query, params={"sc_provider_org_id": sc_provider_org_id, "fa_root_org_id": fa_root_org_id, "sc_consumer_org_id": sc_consumer_org_id, "fa_org_id": fa_org_id}, as_dataframe=True)

def inactivate_asset_from_asset_group_mapping(db: Database, units: list, group_id: str):
  BATCH_SIZE = 1000
  for index in range(0, len(units), BATCH_SIZE):
    curr_units = units[index: index + BATCH_SIZE]
    query = text('''UPDATE SCALAR.SC_Asset_Group_Asset_Mapping
                    SET Active = 0, Modified_Date = getdate()
                    WHERE Asset_Group_Id = :group_id AND Asset_Id IN :units AND Active = 1
                ''')
    db.insert_update_delete_raw(statement=query, params={"group_id": group_id, "units": curr_units}, params_to_expand=["units"])


def get_fc_unit_from_cust_combi_nrs(db: Database, cust_combi_numbers: list):
    # this query will get all interchange out units (including very old historical) for a given customer and comapny number
    # some units may not be insight unit
    query = text('''SELECT u.UnitNr , u.UnitLicenceNr license_nr, a.Asset_Id FROM
                    SCALAR.Fact_Unit u (NOLOCK) JOIN SCALAR.SC_Asset a (NOLOCK) ON u.UnitNr = a.Unit_Nr AND a.Active = 1
                    WHERE u.CustomerCombiNr IN :cust_combi_numbers
            ''')

    params={"cust_combi_numbers": cust_combi_numbers}
    return db.query(statement=query, params=params, params_to_expand=['cust_combi_numbers'])

