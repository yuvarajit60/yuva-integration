from app.common.database import Database
from app.common.exception_handler import global_exception_handler
import azure.functions as func
import logging
from sqlalchemy import text
from app.common.models import Response
from app.common.constants import  ContentType, ResponseCode
from app.fleetconnected_migration.common.fleetconnected_database import FleetConnectedDatabase

customer_data_load_to_migration_table_bp = func.Blueprint()
@customer_data_load_to_migration_table_bp.function_name(name="Load_SKY_Customer_into_Migration_Table")
@customer_data_load_to_migration_table_bp.route(route="load/skycustomer/migrationtable",  methods=[func.HttpMethod.POST])
@global_exception_handler
def load_sky_customer_into_migration_table(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Load_SKY_Customer_Into_Migration_Table")
    db = Database()
    fc_db = FleetConnectedDatabase()

    query = text('''
               SELECT distinct SKY_Company_id FROM [SCALAR].[SC_Migrated_SKY_Customer_To_Scalar](NOLOCK)
            ''')
    company_id_df= db.query(statement=query, as_dataframe=True)

    company_id_list = company_id_df["SKY_Company_id"].tolist()
    company_ids_as_str= '\',\''.join(map(str,company_id_list))
    company_ids_as_str = '\''+company_ids_as_str+'\''
    query = text(f'''
                 SELECT [tenancy_name] SC_Organization_Name,[company_id] SKY_Company_id,[company_code] SKY_Company_code, 
                 wam_root_org_id FA_Root_Org_Id
                 FROM [dbo].[t_fc_organization_tenancy] WHERE tenancy_populated = 1 AND main_tenancy = 0
                 AND [company_id] NOT IN ({company_ids_as_str})                            
            ''')
    fc_customer_df= fc_db.query(statement=query, as_dataframe=True)
    query = text('''INSERT INTO SCALAR.SC_Migrated_SKY_Customer_To_Scalar
                (SC_Organization_Id,SC_Organization_Name,SKY_Company_id,SKY_Company_code,
                 FA_Root_Org_Id,Migrated_Flag,Created_By,Created_Date,Modified_By,Modified_Date)
                VALUES 
                (NULL,:SC_Organization_Name, :SKY_Company_id, :SKY_Company_code, :FA_Root_Org_Id,
                0,'script', getdate(), 'script', getdate())
            ''')
    batch_size = 1000
    customers_params = fc_customer_df.to_dict('records')
    for curr_index in range(0, len(customers_params), batch_size): 
        curr_customers_params = customers_params[curr_index:curr_index + batch_size]
        db.insert_update_delete_raw(statement=query, params=curr_customers_params)

    message = f"Customer data loaded from Insight (t_fc_organization_tenancy) DB into Migration table Successfully!"
    logger.warning(message)
    response = Response(status=True, message=message).getJsonResponse()
    return func.HttpResponse(
            response,
            status_code=ResponseCode.SUCCESS,
            mimetype=ContentType.APPLICATION_JSON
        )