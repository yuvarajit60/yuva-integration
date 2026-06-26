import json
import logging
import azure.functions as func
from app.common.database import Database
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.scalar_api.roles_api import get_all_role
from app.users.get_scalar_roles.get_scalar_roles_data_access import get_scalar_role_mappings
from app.common.helpers.common_services import fetch_access_token
from app.common.constants import ContentType, ResponseCode
from app.common.helpers.common_data_access import get_consumer_organization_data,get_tip_provider_organization

role_org = func.Blueprint()

@role_org.function_name(name="Get_Scalar_Roles")
@role_org.route(route="scalarroles",  methods=[func.HttpMethod.GET])
@global_exception_handler
def role_org_api(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("Get_Scalar_Roles")
    db = Database()
    fa_root_org_id = req.params.get('faRootOrganizationId')
    tip_employee = req.params.get('tipEmployee')
    fr_role_id = req.params.get('frRoleId')

    if fr_role_id is None or not fr_role_id:
        raise ScalarException(message="FR Role ID is required.")

    if tip_employee is None or not tip_employee:
        raise ScalarException(message="Tip Employee should be defined.")
    
    if tip_employee not in ('Y','y','N','n'):
        raise ScalarException(message="Tip Employee should be Y or N")
       
    role_names = get_scalar_role_mappings(db=db,tip_employee= tip_employee,fr_role_id=fr_role_id)

    if tip_employee.lower() == 'y':
        logger.info("Fetching Provider organization roles for FA Org Id : {fa_org_id}")
        provider_organization_id = get_tip_provider_organization(db=db)
        if provider_organization_id is None:
            raise ScalarException(message="There is no provider Organization data in database", display_reqd=True)
        org_id=provider_organization_id[0]
        access_token = fetch_access_token(db=db, org_id=org_id, audience='UMAPI')

    else:
        if fa_root_org_id is None or not fa_root_org_id.isnumeric():
            raise ScalarException(message="FA Root Org  ID must be a valid numeric value.")
        logger.info("Fetching consumer organization roles for Org id")
        sc_org_details_df = get_consumer_organization_data(db=db, fa_root_org_id=fa_root_org_id)
        if sc_org_details_df is not None and len(sc_org_details_df) > 0:
            sc_org_id = sc_org_details_df.loc[0,'Organization_Id']
        else:
            raise ScalarException(message="Customer is not Scalar Organization", 
                                response_code=ResponseCode.INTERNAL_ERROR, display_reqd=True)

        access_token = fetch_access_token(db=db, org_id=sc_org_id, audience='UMAPI')

    scalar_org_role_df = get_all_role(access_token=access_token)
    
    if scalar_org_role_df.status_code == 200 :
        matched_roles = []
        try:
            scalar_roles = scalar_org_role_df.json().get("items",[])
        except:
            raise ScalarException(message="Invalid format")

        for scalar_role in scalar_roles:
            RoleId = scalar_role.get("roleId")
            RoleName = scalar_role.get("roleName")

            if RoleName.lower() in [name[0].lower() for name in role_names]:
                matched_roles.append({"roleId": RoleId, "roleName":RoleName})
    else:
        raise ScalarException(message="Roles could not be retrieved for the scalar organization.", 
                                response_code=ResponseCode.INTERNAL_ERROR)
    
    return func.HttpResponse(
        json.dumps(matched_roles, default=str),
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)

      
