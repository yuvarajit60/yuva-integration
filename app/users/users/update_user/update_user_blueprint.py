import logging
import json
import azure.functions as func
import types
from app.common.constants import ContentType, ResponseCode
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User, SC_Organization, SC_User
from app.common.exception_handler import global_exception_handler
from app.common.exceptions import ScalarException
from app.common.func_validator import CreateUser
from app.common.helpers.common_data_access import get_fa_user_details_by_id, get_tip_provider_organization
from app.common.models import Response
from app.users.update_user.update_user_services import create_scalar_user_for_fa_user, remove_scalar_user_for_fa_user, update_scalar_user_for_fa_user

update_user_bp = func.Blueprint()

@update_user_bp.function_name(name="Update_User")
@update_user_bp.route(route="update/user",  methods=[func.HttpMethod.POST])
@global_exception_handler
def update_user(req: func.HttpRequest) -> func.HttpResponse:
    logger = logging.getLogger("update_user")
    db = Database()
    create_scalar_user = False
    migrate_scalar_user = False
    update_scalar_user = False
    remove_scalar_user = False

    user = CreateUser.Schema().loads(json.dumps(req.get_json()))

    fa_user_details_df = get_fa_user_details_by_id(db=db, fa_user_id=user.faUserId)
    if fa_user_details_df is None or len(fa_user_details_df) == 0:
        message = f"No Active FleetAdmin User found with the given ID."
        logger.warning(message)
        raise ScalarException(message=message, response_code=ResponseCode.BAD_REQUEST)
    fa_user_dict = fa_user_details_df.to_dict('records')[0]

    sc_user = db.get_session().query(SC_User.User_Id,
                                     SC_User.SC_Organization_Id,
                                     SC_Organization.FA_Root_Organization_Id,
                                     SC_Organization.Is_SSO_Enabled,
                                     SC_Organization.ZF_Consumer_Org
    ).join(
        FA_User, FA_User.User_Id == SC_User.FA_User_Id
    ).join(
        SC_Organization, SC_Organization.Organization_Id == SC_User.SC_Organization_Id
    ).filter(
        FA_User.User_Id == user.faUserId,
        SC_User.Status.in_(['Active', 'Pending'])
    ).first()

    if sc_user is None:
        if fa_user_dict['Fleet_Connected_Ind'] in ('N', 'n'):
            message = "Non scalar user can not be created."
        else:
            create_scalar_user = True
    elif sc_user is not None:
            if fa_user_dict['Fleet_Connected_Ind'] in ('N', 'n'):
                remove_scalar_user = True
            elif fa_user_dict['Root_Organization_Id'] != sc_user.FA_Root_Organization_Id:
                if fa_user_dict['Tip_User'] in ('Y', 'y') and sc_user.FA_Root_Organization_Id is None:
                    update_scalar_user = True
                else:
                    migrate_scalar_user = True
            elif fa_user_dict['Root_Organization_Id'] == sc_user.FA_Root_Organization_Id:
                if fa_user_dict['Tip_User'] in ('Y', 'y') and sc_user.FA_Root_Organization_Id is not None:
                    migrate_scalar_user = True
                else:
                    update_scalar_user = True
                
    user.emailAddress = fa_user_dict['User_Email']
    user.firstName = fa_user_dict['User_First_Name']
    user.lastName = fa_user_dict['User_Last_Name']
    user.roles = [user.scalarRoleId] if user.scalarRoleId is not None else None
    user.role_names = [user.scalarRoleName] if user.scalarRoleName is not None else None
    user.language = "en" if user.language is None or not user.language else user.language
    user.language = "nb" if user.language == "no" else user.language

    if create_scalar_user or update_scalar_user or migrate_scalar_user:
        if user.scalarRoleId is None or user.scalarRoleName is None:
            message = f"User could not be updated as no Role ID/Names were given."
            logger.error(message)
            raise ScalarException(message=message, response_code=ResponseCode.BAD_REQUEST, display_reqd=True)
    
    if create_scalar_user:
        logger.info("Calling create user scenario")
        #get the scalar org id and create user in it
        if fa_user_dict['Tip_User'] in ('Y', 'y'):
            tip_org_id = get_tip_provider_organization(db=db)
            if tip_org_id is None or len(tip_org_id) == 0:
                message = f"TIP Provider organization details not found."
                logger.warning(message)
                raise ScalarException(message=message, response_code=ResponseCode.INTERNAL_ERROR)
            scalar_org = types.ModuleType("sc")
            scalar_org.Organization_Id = tip_org_id[0]
            scalar_org.Is_SSO_Enabled = tip_org_id[1]
        else:
            scalar_org = db.get_session().query(SC_Organization.Organization_Id, SC_Organization.Is_SSO_Enabled
                                                        ).filter(SC_Organization.FA_Root_Organization_Id == fa_user_dict['Root_Organization_Id'],
                                                                SC_Organization.Active == '1'
                                                                ).first()
        if scalar_org is None:
            raise ScalarException(message=f"Scalar org not found for FA root org {fa_user_dict['Root_Organization_Id']}", response_code=ResponseCode.NOT_FOUND)
        user.loginType = "SSO" if int(scalar_org.Is_SSO_Enabled) else "Password"
        create_scalar_user_for_fa_user(db=db, scalar_org_id=scalar_org.Organization_Id, user=user, fa_user_dict=fa_user_dict, logger=logger)
        message = f"New scalar user for FA user {user.faUserId} has been created successfully in scalar org."
    elif migrate_scalar_user:
        logger.info("Calling migrate user scenario")
        remove_scalar_user_for_fa_user(db=db, scalar_org_id=sc_user.SC_Organization_Id, scalar_user_id=sc_user.User_Id, logger=logger)
        #get new scalar org id and create user in it
        if fa_user_dict['Tip_User'] in ('Y', 'y'):
            tip_org_id = get_tip_provider_organization(db=db)
            if tip_org_id is None or len(tip_org_id) == 0:
                message = f"TIP Provider organization details not found."
                logger.warning(message)
                raise ScalarException(message=message, response_code=ResponseCode.INTERNAL_ERROR)
            migrated_scalar_org = types.ModuleType("sc")
            migrated_scalar_org.Organization_Id = tip_org_id[0]
            migrated_scalar_org.Is_SSO_Enabled = tip_org_id[1]
        else:
            migrated_scalar_org = db.get_session().query(SC_Organization.Organization_Id, SC_Organization.Is_SSO_Enabled
                                                        ).filter(SC_Organization.FA_Root_Organization_Id == fa_user_dict['Root_Organization_Id'],
                                                                SC_Organization.Active == '1'
                                                                ).first()
        if migrated_scalar_org is None:
            raise ScalarException(message=f"Scalar org not found for FA root org {fa_user_dict['Root_Organization_Id']}", response_code=ResponseCode.NOT_FOUND)
        user.loginType = "SSO" if int(migrated_scalar_org.Is_SSO_Enabled) else "Password"
        create_scalar_user_for_fa_user(db=db, scalar_org_id=migrated_scalar_org.Organization_Id, user=user, fa_user_dict=fa_user_dict, logger=logger)
        message = f"Scalar user for FA_user_id {user.faUserId} has been migrated successfully to new scalar org."
    elif update_scalar_user:
        logger.info("Calling update user scenario")
        user.loginType = "SSO" if int(sc_user.Is_SSO_Enabled) else "Password"
        update_scalar_user_for_fa_user(db=db, scalar_org_id=sc_user.SC_Organization_Id, user=user, fa_user_dict=fa_user_dict, logger=logger)
        message = f"Scalar user {sc_user.User_Id} for FA_user_id {user.faUserId} has been updated successfully."
    elif remove_scalar_user:
        logger.info("Calling remove user scenario")
        user.loginType = "SSO" if int(sc_user.Is_SSO_Enabled) else "Password"
        remove_scalar_user_for_fa_user(db=db, scalar_org_id=sc_user.SC_Organization_Id, scalar_user_id=sc_user.User_Id, logger=logger)
        message = f"Scalar user {sc_user.User_Id} for FA_user_id {user.faUserId} has been removed successfully."
    else:
        message = "Nothing to update"
    
    response = Response(status=True, message=message).getJsonResponse()
    return func.HttpResponse(
        response,
        status_code=ResponseCode.SUCCESS,
        mimetype=ContentType.APPLICATION_JSON)