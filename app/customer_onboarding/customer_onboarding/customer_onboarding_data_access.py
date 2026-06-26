from sqlalchemy import text
from pandas import DataFrame
from app.common.constants import AdditionalChargeType, Application
from app.common.database_model.scalar_tables import FA_Org_Application_Mapping, SC_Organization, SC_Framework_Agreement, SC_Integrator_Details
from app.common.database import Database

def save_organization(db: Database, consumer_org_id, consumer_org_name, fa_root_org_id,is_sso_enabled):
    sc_organization = SC_Organization(Organization_Id=consumer_org_id,
                                    Organization_Name = consumer_org_name, 
                                    FA_Root_Organization_Id=fa_root_org_id,
                                    Is_Provider="N",
                                    ZF_Consumer_Org=0,
                                    Is_SSO_Enabled=is_sso_enabled,
                                    Active="1"
                                    )
    db.insert_orm(orm_item=sc_organization)

def save_framework_aggreement(db: Database,frameworkagreement):
    sc_framework_agreement = SC_Framework_Agreement( Agreement_Id=frameworkagreement["agreementId"],
    Agreement_Name = frameworkagreement["agreementName"],
    Agreement_Desc = frameworkagreement["description"],
    Consumer_Org_Id = frameworkagreement["consumerOrgId"],
    Provider_Org_Id = frameworkagreement["providerOrgId"],
    Data_Sharing_Type = frameworkagreement["dataSharingType"],
    Subject_Type = frameworkagreement["subjectType"],
    Asset_Type =  frameworkagreement["assetType"],
    Is_Existing_Customer =  "N",
    Owner = frameworkagreement["ownerReceivingOrg"],
    Payer = frameworkagreement["payer"],
    Primary_Email_Address = frameworkagreement["consumerPrimaryEmail"],
    Primary_First_Name = frameworkagreement["consumerPrimaryLastName"],
    Primary_Last_Name = frameworkagreement["consumerPrimaryFirstName"],
    Allow_Further_Sharing = "N",
    Multi_Share_Mode = frameworkagreement["multiShareMode"],
    Session_Contract_Mode = frameworkagreement["sessionContractMode"],
    Create_Integrator = "Y",
    Rejected_Reason = None,
    Approved_Rejected_Date = None,
    Approved_Rejected_By = "Scalar",
    Stopped_By = None,
    Stopped_On = None,
    Agreement_Status = "approved",
    Profile_Id=frameworkagreement["profileId"]
    )

    db.insert_orm(orm_item=sc_framework_agreement)

def save_integrator_details(db: Database, consumer_org_id, integrator_name, framework_id,client_id,client_secret):
    sc_integrator_details = SC_Integrator_Details(Organization_Id=consumer_org_id,
                                    Integrator_Name = integrator_name, 
                                    Framework_Id=framework_id,
                                    Client_Id=client_id,
                                    Client_Secret=client_secret,
                                    Active="1"
                                    )
    db.insert_orm(orm_item=sc_integrator_details)

def get_FA_root_org(db: Database,fa_root_org_id) -> DataFrame:
    select_statement = text('''
                                SELECT Organization_Name FROM FA_Organization (NOLOCK)
                                WHERE Organization_Id = :fa_root_org_id AND Root_Organization_Id IS NULL AND Active=1
                                                              
                            ''')
    result = db.query(statement=select_statement, params={"fa_root_org_id": fa_root_org_id})
    
    if len(result) > 0:
        return result[0][0]
    else:
        return None
    
def get_regional_super_users(db, root_org_id):
    query = text('''SELECT distinct o.Organization_Id, Super_User_Email User_Email
                    FROM FA_Organization (NOLOCK) o
                    JOIN FA_Region fr ON fr.Region_Id = o.Region_Id
                    JOIN FA_Regional_Super_User (NOLOCK) u on u.Region_Cd = fr.Region_Cd
                    WHERE o.Organization_Id = :root_org_id and o.Root_Organization_Id IS NULL --AND o.Active=1

                ''')
    return db.query(statement=query, params={"root_org_id": root_org_id},as_dataframe=True)

def get_insight_units(db: Database, fa_root_org_id: str) -> DataFrame:
    select = text('''
                    SELECT org.[Organization_Id],
                           org.[Organization_Name],
                           unit.[UnitNr],
                           sa_unit.[UnitLicenceNr],
                           sa_unit.[VIN_Number],
                           sa_unit.[Asset_Id],
                           org.[Root_Organization_Id],
                           unit.CustomerCombiNr,unit.CustomerReferenceNr,sa_unit.Fleet_Id
                    FROM FA_Organization (NOLOCK) org
                    LEFT JOIN (
                                    SELECT  Organization_Id, 
                                            Customer_Number_Combi
                                    FROM FA_Org_Cust_Mapping (NOLOCK)
                                    WHERE Active = 1
                                ) org_combi ON org_combi.Organization_Id = org.Organization_Id 
                    LEFT JOIN (
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
                                       Asset_Id, Active,
                                       Device_Pairing_Status,Fleet_Id,Unit_Licence_Nr UnitLicenceNr,VIN_Number
                                FROM SCALAR.SC_Asset (NOLOCK)
                            ) sa_unit ON sa_unit.Unit_Nr = unit.UnitNr and sa_unit.Active=1 and sa_unit.Device_Pairing_Status = 1
                    WHERE org.Root_Organization_Id = :fa_root_org_id AND org.Active = 1
                         AND org.FleetConnected_Ind = 'Y'
                         AND  ( EXISTS
                                    (
                                        SELECT Rate_Nr
                                        FROM SCALAR.Additional_Charges ac
                                        WHERE  unit.CustomerNr = ac.Customer_Nr AND unit.RateCompanyNr = ac.Company_Nr
				                            AND unit.RateNr = ac.Rate_Nr AND unit.MasterLeaseNr = ac.Mstrls_Nr
                                            and ac.Additional_Charge_Type in :fc_charge_types
                                    )
                            );
                 ''')
    return db.query(statement=select, params={"fa_root_org_id": fa_root_org_id, "fc_charge_types": AdditionalChargeType.Insight_Additional_Charge_Types}, params_to_expand=["fc_charge_types"], as_dataframe=True)

def get_root_tenancy(db, root_org_id):
    query = text('''SELECT Root_Org_Id
                    FROM FA_Root_Org_Tenancy (NOLOCK)                     
                    WHERE Root_Org_Id = :root_org_id 
                ''')
    return db.query(statement=query, params={"root_org_id": root_org_id})

def save_tenancy_info_in_db(db: Database, farootorgid):
    query = text('''INSERT INTO FA_Root_Org_Tenancy
                    ([Root_Org_Id],[Tenancy_Created_dt],[Created_Date],[Modified_Date])
                    VALUES (:fa_root_org_id, getdate(), getdate(), getdate())

            ''')
    return db.insert_update_delete_raw(statement=query, params={"fa_root_org_id": farootorgid})

def update_tenancy_info_in_db(db: Database, farootorgid):
    query = text('''UPDATE FA_Root_Org_Tenancy WITH(Rowlock)
                    SET Tenancy_Created_dt = getdate(), Modified_Date=getdate()
                    WHERE Root_Org_Id = :fa_root_org_id                    
            ''')
    return db.insert_update_delete_raw(statement=query, params={"fa_root_org_id": farootorgid})

def update_faorg_fcflag_in_db(db: Database, farootorgid):
    query = text('''UPDATE FA_Organization WITH(Rowlock)
                    SET Fleetconnected_Ind = 'Y', Modified_Date=getdate()
                    WHERE Active=1 AND (Root_Organization_Id =:fa_root_org_id or Organization_Id = :fa_root_org_id) AND  (Fleetconnected_Ind IS NULL OR Fleetconnected_Ind ='N')              
            ''')
    return db.insert_update_delete_raw(statement=query, params={"fa_root_org_id": farootorgid})

def get_sc_application_id(db):
    query = text('''SELECT Application_Id
                    FROM FA_Application
                    WHERE Application_Name = :app_id AND Active=1
                ''')
    result = db.query(statement=query, params={"app_id": Application.APP_NAME})
    if len(result) > 0:
        return result[0][0]
    else:
        return None

def save_fa_org_application_mapping(db: Database, organization_id, application_id):

    db_record_found = db.get_session().query(FA_Org_Application_Mapping).filter_by(Organization_Id = organization_id)\
                                                .filter_by(Application_Id = application_id)\
                                                .first()
    if db_record_found:
        db_record_found.Active = 1
        db.get_session().commit()
    else:
        org_record = FA_Org_Application_Mapping(Organization_Id = organization_id,
                                        Application_Id = application_id,
                                        Active = 1
                                        )
        db.insert_orm(orm_item=org_record)