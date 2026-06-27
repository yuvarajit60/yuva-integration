import pandas as pd
from sqlalchemy import text
from pandas import DataFrame
from asyncio.log import logger
from app.common.constants import AdditionalChargeType, AudienceCode
from app.common.database import Database

from app.common.database_model.scalar_tables import SC_Asset_Group_Asset_Mapping
from app.common.helpers.common_services import fetch_access_token, get_all_data, get_scalar_api_error_messages
from app.common.scalar_api.asset_api import get_all_assets
from app.common.scalar_api.asset_group_api import assign_asset_to_assetgroup

# def check_units_not_exists_in_sc_group_link(db: Database, asset_nrs: list, group_id: str):
#     query = text('''SELECT Asset_Id 
#                     FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK)
#                     WHERE Asset_Group_Id = :group_id 
#                     AND Active = '1' 
#                     AND Asset_Id IN :asset_nrs
#             ''')
#     params={"group_id": group_id, "asset_nrs": asset_nrs}
#     asset_group_links = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_nrs'])
#     existing_asset_numbers = asset_group_links['Asset_Id'].to_list()
#     return list(set(asset_nrs) - set(existing_asset_numbers))

def check_units_not_exists_in_sc_group_link(db: Database, asset_nrs: list, group_id: str):
    query = text('''SELECT Asset_Id 
                    FROM SCALAR.SC_Asset_Group_Asset_Mapping (NOLOCK)
                    WHERE Asset_Group_Id = :group_id 
                    AND Active = '1' 
                    AND Asset_Id IN :asset_nrs
            ''')
    batch_size = 1000
    existing_asset_numbers = set()
    for curr_index in range(0, len(asset_nrs), batch_size): 
        curr_asset_ids = asset_nrs[curr_index:curr_index + batch_size]
        params={"group_id": group_id, "asset_nrs":curr_asset_ids}
        asset_group_links = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_nrs'])
        if asset_group_links is not None and not asset_group_links.empty:
            existing_asset_numbers.update(asset_group_links['Asset_Id'].tolist())

    return list(set(asset_nrs) - existing_asset_numbers)

def add_asset_group_mapping_in_db(db: Database, asset_nrs: list, group_id: str):
    sc_unit_group_links = []
    asset_nrs = check_units_not_exists_in_sc_group_link(db=db, asset_nrs=asset_nrs, group_id=group_id)
    for asset_nr in asset_nrs:
        group_link = SC_Asset_Group_Asset_Mapping(Asset_Id=asset_nr,
                                                        Asset_Group_Id=group_id,
                                                        Active='1')
        sc_unit_group_links.append(group_link)
 
    db.insert_orm_list(orm_list=sc_unit_group_links)
   
def assign_asset_to_groups_in_consumer_org(consumer_access_token: str, consumer_group_id: str, consumer_asset_ids: list):
    assignment_response = assign_asset_to_assetgroup(access_token=consumer_access_token,
                                                        asset_group_id=consumer_group_id,
                                                        asset_ids=consumer_asset_ids)
 
    return get_scalar_api_error_messages(error_response=assignment_response)

def get_insight_org_units_by_cust_org_id(db: Database, cust_org_id: str):
    query = text('''SELECT DISTINCT u.UnitNr,u.UnitLicenceNr,u.CustomerCombiNr,sa.Asset_Id,sa.Device_Pairing_Status, fcm.Customer_Number_Combi as linked_customer_combi_number,
                fo.Organization_Id,fo.Organization_Name,ro.Organization_Id Root_Organization_Id,ro.Organization_Name  Root_Organization_Name
                FROM SCALAR.Fact_Unit u (NOLOCK)
                JOIN FA_Org_Cust_Mapping fcm (NOLOCK) ON fcm.Customer_Number_Combi=u.CustomerCombiNr AND fcm.Active=1
                JOIN FA_Organization fo (NOLOCK) ON fo.Organization_Id=fcm.Organization_Id AND fo.Active = 1 AND fo.FleetConnected_Ind = 'Y'
                JOIN FA_Organization ro (NOLOCK) ON ro.Organization_Id=fo.Root_Organization_Id AND ro.Active = 1 AND ro.FleetConnected_Ind = 'Y'
                JOIN SCALAR.SC_Organization so (NOLOCK) ON so.FA_Root_Organization_Id=fo.Root_Organization_Id AND so.Active=1
                LEFT OUTER JOIN SCALAR.SC_Asset sa (NOLOCK) ON sa.Unit_Nr=u.UnitNr AND sa.Active=1 
                WHERE so.Organization_Id = :cust_org_id
                AND EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
                            WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
                            AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
                            AND ac.Additional_Charge_Type IN :insight_add_chrg_types)
            ''')
    params={"cust_org_id": cust_org_id, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['insight_add_chrg_types'])


def get_insight_units_by_root_org(db: Database, root_org_id: int):
    query = text('''SELECT DISTINCT u.UnitNr,u.UnitLicenceNr,u.CustomerCombiNr,'True' as insight_unit 
				FROM SCALAR.Fact_Unit u (NOLOCK)
				WHERE u.CustomerCombiNr IN 
				(SELECT DISTINCT Customer_Number_Combi
					FROM FA_Org_Cust_Mapping (NOLOCK)
					WHERE Organization_Id IN
						(SELECT Organization_Id
							FROM FA_Organization (NOLOCK)
							WHERE (Root_Organization_Id = :root_org_id OR Organization_Id= :root_org_id) AND Active=1)
					AND Active=1)
				AND EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
				WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
				AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
				AND ac.Additional_Charge_Type IN :insight_add_chrg_types)

            ''')
    params={"root_org_id": root_org_id, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['insight_add_chrg_types'])


def get_non_insight_units_by_root_org(db: Database, root_org_id: int, asset_ids):
    rs_unit_nrs = []
    query = text('''SELECT DISTINCT u.UnitNr,sa.Asset_Id,'False' as insight_unit
                FROM SCALAR.Fact_Unit u(NOLOCK)
				JOIN SCALAR.SC_Asset sa (NOLOCK)  ON sa.Unit_Nr =u.UnitNr AND sa.Active = 1
                WHERE u.CustomerCombiNr IN
				(SELECT DISTINCT Customer_Number_Combi 
					FROM FA_Org_Cust_Mapping ocm (NOLOCK) WHERE Organization_Id IN
						(SELECT fo.Organization_Id FROM FA_Organization fo (NOLOCK)
							WHERE (fo.Organization_Id= :root_org_id OR Root_Organization_Id= :root_org_id) AND fo.Active = 1)
				AND ocm.Active = 1)
				AND sa.Asset_Id in :asset_ids
            ''')
    
    batch_size = 1000
    rs_unit_nrs = pd.DataFrame()
    for curr_index in range(0, len(asset_ids), batch_size): 
        curr_asset_ids = asset_ids[curr_index:curr_index + batch_size]
        params={"root_org_id": root_org_id, "asset_ids":curr_asset_ids}
        result_df = db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_ids'])
        rs_unit_nrs = pd.concat([rs_unit_nrs,result_df], ignore_index=True)
        # rs_unit_nrs.extend(result_df["UnitNr"].to_list())
    return rs_unit_nrs

def get_insight_units_by_asset_ids(db: Database, root_org_id: int, asset_ids: list):
    query = text('''SELECT DISTINCT u.UnitNr,u.UnitLicenceNr,u.CustomerCombiNr,'True' as insight_unit 
				FROM SCALAR.Fact_Unit u (NOLOCK)
				WHERE u.CustomerCombiNr IN 
				(SELECT DISTINCT Customer_Number_Combi
					FROM FA_Org_Cust_Mapping (NOLOCK)
					WHERE Organization_Id IN
						(SELECT Organization_Id
							FROM FA_Organization (NOLOCK)
							WHERE (Root_Organization_Id = :root_org_id OR Organization_Id= :root_org_id) AND Active=1)
					AND Active=1)
                AND u.UnitNr IN (SELECT Unit_Nr FROM SCALAR.SC_Asset (NOLOCK) WHERE Active=1 AND Asset_Id IN :asset_ids)
				AND EXISTS (SELECT ac.Rate_Nr FROM SCALAR.Additional_Charges ac (NOLOCK)
				WHERE  u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
				AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
				AND ac.Additional_Charge_Type IN :insight_add_chrg_types)

            ''')
    params={"root_org_id": root_org_id, "asset_ids": asset_ids, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['asset_ids','insight_add_chrg_types'])


def insert_missing_pairing_insight_unit(db, param_list):
    query = text('''INSERT INTO SCALAR.SC_Insight_Unit_Missing_Pairing
                    (Unit_Nr, License_Nr, Customer_Combi_Nr, FA_Root_Organization_Id, FA_Organization_Id,
                    Treated, Process_Name, Treatment_Date, Created_By, Created_Date, Modified_By, Modified_Date)
                    VALUES (:Unit_Nr, :License_Nr, :Customer_Combi_Nr, :Root_Organization_Id, :Organization_Id,
                    0, :Process_Name, null, 'Scalar', getdate(), 'Scalar', getdate())

            ''')
    db.insert_update_delete_raw(statement=query, params=param_list)


def update_missing_pairing_insight_unit_as_treated(db: Database, treated_units):
    BATCH_SIZE = 1000
    for index in range(0, len(treated_units), BATCH_SIZE):
        curr_units = treated_units[index: index + BATCH_SIZE]
        query = text('''UPDATE SCALAR.SC_Insight_Unit_Missing_Pairing WITH(ROWLOCK)
                        SET Treated = 1, Treatment_Date = getdate(),
                        Modified_By = 'Scalar', Modified_Date = getdate()
                        WHERE Treated = 0 and Unit_Nr in :treated_units
            ''')
        params={"treated_units": curr_units}
        db.insert_update_delete_raw(statement=query, params=params, params_to_expand=['treated_units'])


def add_missing_pairing_insight_unit(db: Database, missing_pairing_units_df, process_name):
    missing_pairing_units = missing_pairing_units_df['UnitNr'].tolist()
    new_missing_pairing_insight_units = get_new_missing_pairing_insight_unit(db, missing_pairing_units)
    if len(new_missing_pairing_insight_units) > 0:
        new_missing_pairing_units_df = missing_pairing_units_df.loc[missing_pairing_units_df['UnitNr'].isin(new_missing_pairing_insight_units)]
        param_list = list()
        for _, row in new_missing_pairing_units_df.iterrows():
            param = dict()
            param['Unit_Nr'] = row['UnitNr']
            param['License_Nr'] = row['UnitLicenceNr']
            param['Customer_Combi_Nr'] = row['CustomerCombiNr']
            param['Root_Organization_Id'] = row['Root_Organization_Id']
            param['Organization_Id'] = row['Organization_Id']
            param['Process_Name'] = process_name
            param_list.append(param)
            
        insert_missing_pairing_insight_unit(db, param_list)

def get_new_missing_pairing_insight_unit(db, missing_pairing_units):
    result_units = list()
    query = text('''SELECT Unit_Nr
                    FROM SCALAR.SC_Insight_Unit_Missing_Pairing (NOLOCK)
                    WHERE Treated = 0 AND Unit_Nr in :missing_pairing_units
            ''')
    batch_size = 1000        
    for index in range(0, len(missing_pairing_units), batch_size):
        curr_missing_pairing_units = missing_pairing_units[index:index + batch_size]
        params = {"missing_pairing_units": curr_missing_pairing_units}
        result = db.query(statement=query, params=params, params_to_expand=['missing_pairing_units'], as_dataframe=True)
        result_units.extend(result['Unit_Nr'].tolist())
    return list(set(missing_pairing_units) - set(result_units))

def get_asset_api_data(db:Database, org_id: str):
    access_token = fetch_access_token(db=db, org_id=org_id, audience=AudienceCode.ASSET)
    asset_data = get_all_data(access_token=access_token,func=get_all_assets)
    if asset_data is not None:
        asset_data_df = pd.DataFrame(asset_data)  
    return asset_data_df

def get_asset_data(db: Database) -> DataFrame:
    select_statement = text('''
                                SELECT Asset_Id assetId,Unit_Nr,Device_Number,Convert(Int,Device_Pairing_Status)Device_Pairing_Status,Convert(Int,Active)Active,Status
                                FROM SCALAR.SC_Asset (nolock) Order by Id                           
                            ''')
   
    return db.query(statement=select_statement, as_dataframe=True)

def get_insight_units_by_combi_numbers(db: Database, cust_combi_numbers: list, root_org_id: int):
    query = text(''' SELECT u.UnitNr, tu.Asset_Id, u.UnitLicenceNr, u.CustomerCombiNr, wo.Organization_Id, wo.Root_Organization_Id
                FROM SCALAR.Fact_Unit (NOLOCK) u
                JOIN FA_Org_Cust_Mapping (NOLOCK) woc
                    ON woc.Customer_Number_Combi = u.CustomerCombiNr AND woc.Active = 1
                JOIN FA_Organization (NOLOCK) wo
                    ON woc.Organization_Id = wo.Organization_Id AND wo.Active = 1
                LEFT JOIN SCALAR.SC_Asset (NOLOCK) tu
                    ON tu.Unit_Nr = u.UnitNr AND tu.Active=1 AND tu.Device_Pairing_Status = '1'
                WHERE u.CustomerCombiNr IN :cust_combi_numbers and wo.root_organization_id = :root_org_id
                AND EXISTS ( SELECT Rate_Nr
                                        FROM SCALAR.Additional_Charges ac
                                        WHERE   u.CustomerNr = ac.Customer_Nr AND u.RateCompanyNr = ac.Company_Nr
												AND u.RateNr = ac.Rate_Nr AND u.MasterLeaseNr = ac.Mstrls_Nr
                                                and ac.Additional_Charge_Type in :insight_add_chrg_types)
            ''')
    params={"cust_combi_numbers": cust_combi_numbers, "root_org_id":root_org_id, "insight_add_chrg_types":AdditionalChargeType.Insight_Additional_Charge_Types}
    return db.query(statement=query, params=params, as_dataframe=True, params_to_expand=['cust_combi_numbers', 'insight_add_chrg_types'])


def cust_combi_nr_linked_to_org_only(insight_units: DataFrame, organization_id: int):
    df_by_cust_comni_nr = insight_units.groupby(['CustomerCombiNr'])
    cc_nr_linked_org_only = False
    for cust_comni_nr, frame in df_by_cust_comni_nr:
        df_by_org_id = frame.groupby(['Organization_Id'])
        cc_nr_linked_org_only = True
        for org_id, unit_data in df_by_org_id:
            if org_id[0] != organization_id:
                cc_nr_linked_org_only = False
                break
        if cc_nr_linked_org_only:
            break
    logger.info(f"cust_combi_nr_linked_to_org_only: {cc_nr_linked_org_only}")
    return cc_nr_linked_org_only

def is_combi_number_removal_allowed(db: Database, cust_combi_numbers: list, root_org_id: int, org_id: int):
    cust_combi_nr_removal_allowed = True
    tip_asset_deassignment_allowed = True
    logger.info(f"Combi numbers found: {cust_combi_numbers}")
    if len(cust_combi_numbers) > 0:
        insight_units = get_insight_units_by_combi_numbers(db=db, cust_combi_numbers=cust_combi_numbers, root_org_id=root_org_id)
        logger.info(f"Total insight units found: {len(insight_units)}") 
        if len(insight_units) > 0 :
            cc_nr_linked_org_only = cust_combi_nr_linked_to_org_only(insight_units, org_id)
            if cc_nr_linked_org_only:
                cust_combi_nr_removal_allowed = False
                tip_asset_deassignment_allowed = None
            else:
                tip_asset_deassignment_allowed = False

    return cust_combi_nr_removal_allowed,tip_asset_deassignment_allowed

