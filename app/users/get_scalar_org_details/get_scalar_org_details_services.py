from app.common.constants import Connection
from app.common.database import Database
from sqlalchemy.engine.row import Row
from app.common.helpers.common_data_access import get_tip_provider_organization,get_consumer_organization_data
from app.users.get_scalar_org_details.get_scalar_org_details_data_access import get_fa_scalar_user_details,get_connection_name
from app.fleetconnected_migration.common.migration_tables import SC_Migrated_SKY_Customer_To_Scalar

def user_scalar_org(db:Database, fa_user_id: str):
    response = {}
    connection = ""
    response["teaser"] = None
    response["show"] = False
    
    user_details = get_fa_scalar_user_details(db=db, user_id = fa_user_id)

    if user_details :
        user_details_dict = dict(zip(["FA_User_Id","SC_User_Id","TIP_User","Fleet_Connected_Ind","root_org_id"],user_details[0]))
        
        response["faUserId"] = user_details_dict["FA_User_Id"]
        response["scUserId"] = user_details_dict["SC_User_Id"]
        response["rootOrgId"] = user_details_dict["root_org_id"] 
        response["tipUser"] = user_details_dict["TIP_User"]

        if user_details_dict["TIP_User"] in ('Y', 'y'):
            scalar_org = get_tip_provider_organization(db=db)
            if scalar_org:
                if isinstance(scalar_org,Row):
                    connection = get_connection_name(db=db, source=Connection.TIP_CONNECTION)
            if len(scalar_org)> 0 :  
                if user_details_dict["SC_User_Id"]:
                    response["teaser"] = False
                    response["show"] = True
                    response["organizationId"] = scalar_org[0] 
                    if connection:
                        response["connectionName"] = connection[0][0]
                        response["region"] = connection[0][1]
                else:
                    response["teaser"] = None
                    response["show"] = False
        else:
            scalar_org = get_consumer_organization_data(db=db, fa_root_org_id=user_details_dict["root_org_id"] )
            connection = get_connection_name(db=db, source=Connection.CUSTOMER_CONNECTION)
            if len(scalar_org)>0:
                if user_details_dict["SC_User_Id"]: # User is scalar
                    response['show'] = True
                    response['teaser'] = False
                    if connection:
                        response["connectionName"] = connection[0][0]
                        response["region"] = connection[0][1]
                    response["organizationId"] = scalar_org.iloc[0]["Organization_Id"]
                else: # User is non-scalar
                    response['show'] = False
                    response['teaser'] = None
            else:
                customer_migration_status = db.get_session().query(SC_Migrated_SKY_Customer_To_Scalar).filter(SC_Migrated_SKY_Customer_To_Scalar.FA_Root_Org_Id == user_details_dict["root_org_id"], \
                                                                                                              SC_Migrated_SKY_Customer_To_Scalar.SKY_Company_id != 2006).first()
                if customer_migration_status is None: # Not Scalar, also not FC Customer
                    response['show'] = True
                    response['teaser'] = True
                elif int(customer_migration_status.Migrated_Flag) == 0: # Not scalar but FC
                    response['show'] = False
                    response['teaser'] = None


    return response

