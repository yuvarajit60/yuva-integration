from datetime import datetime
import json
import os
import pandas as pd
from sqlalchemy import func

from app.common.constants import AudienceCode
from app.common.email import Email
from app.common.func_validator import User
from app.common.helpers.common_data_access import get_all_organizations
from app.common.helpers.common_services import get_all_data
from app.common.database import Database
from app.common.database_model.scalar_tables import FA_User, SC_User, SC_User_Role_Mapping
from app.common.exceptions import ScalarException
from app.common.helpers.common_services import fetch_access_token
from app.common.scalar_api.roles_api import get_all_role
from app.common.scalar_api.user_api import get_all_user
from app.users.user_datasync.usersync_data_access import sync_user_role_mapping_in_db, sync_users_in_db


def get_allusers_allroles_for_allorg(db: Database, logger):
    org_list = get_all_organizations(db=db)
    org_count = len(org_list)
    if org_list.empty:
        raise ScalarException(message="Could not retrieve any organization data from DB")
    
    all_users_df = pd.DataFrame()
    all_roles_df = pd.DataFrame()
    for scalar_org_id in org_list['Organization_Id']:
        access_token = fetch_access_token(db=db, org_id=scalar_org_id, audience=AudienceCode.USER)
        logger.info(msg=f"Getting users and roles from api for org {scalar_org_id}")
        
        single_org_user_df = get_all_data(access_token=access_token,func=get_all_user)
        single_org_user_df = single_org_user_df[single_org_user_df['status'].isin(['Active','Pending'])]
        if single_org_user_df.empty:
            #raise ScalarException(message=f"Could not retrieve any user for org: {scalar_org_id} from API")
            msg=f"Could not retrieve any user for org: {scalar_org_id} from API"
            logger.info(msg)
        single_org_user_df['orgId'] = scalar_org_id
        single_org_user_df['sc_orgName'] = org_list.loc[org_list['Organization_Id']==scalar_org_id,'Organization_Name'].values[0]
        all_users_df = pd.concat([all_users_df,single_org_user_df], ignore_index=True)

        single_org_role_df = get_all_data(access_token=access_token,func=get_all_role)
        if single_org_role_df.empty:
            #raise ScalarException(message=f"Could not retrieve any role for org: {scalar_org_id} from API")
            msg=f"Could not retrieve any role for org: {scalar_org_id} from API"
            logger.info(msg)
        all_roles_df = pd.concat([all_roles_df,single_org_role_df], ignore_index=True)
    return all_users_df, all_roles_df, org_count

def sync_user_db(db: Database, user_api_data: pd.DataFrame, user_db_data: pd.DataFrame, logger, batch_size: int = 1000):    

    inserted_users = {}
    updated_users = {}
    deleted_users = {}
    failed_users = []

    existing_user_ids  = {user.User_Id for user in user_db_data} 
    existing_emails = {user.User_Email for user in user_db_data} 

    # get FA_user ids from FA_User table based on email addesss without checking scalar status and active status
    email_ids = user_api_data['emailAddress'].dropna().str.lower().tolist()
    fa_users = []
    for curr_index in range(0, len(email_ids), batch_size): 
        curr_email_ids = email_ids[curr_index:curr_index + batch_size]
        result_set = db.get_session().query(FA_User).filter(func.lower(FA_User.User_Email).in_(curr_email_ids)).all()
        fa_users.extend(result_set)

    email_to_fa_users_mapping = {}
    for fa_user in fa_users:
        email_to_fa_users_mapping[fa_user.User_Email.lower()] = fa_user.User_Id
    
    users_to_update = []
    users_to_insert = []
    user_role_to_map = {}
    for index, user in user_api_data.iterrows():
        try:
            api_user_detail = User.Schema().loads(json.dumps(json.loads(user.to_json())))
            email = api_user_detail.emailAddress.lower()
            
            fauserid = email_to_fa_users_mapping.get(email)
            if fauserid is None:
                logger.info(msg=f"FA_User_Id not found for {email}")

            userid = api_user_detail.userId
            logintype = api_user_detail.loginType
            status = api_user_detail.status
            scalar_orgid = api_user_detail.orgId
            scalar_orgname = api_user_detail.sc_orgName
            roles = api_user_detail.roles
            if userid in existing_user_ids:
                # update existing user
                logger.info(msg=f"Updating existing user object {userid}")

                db_user = next(user for user in user_db_data if user.User_Id==userid)
                db_user.Login_Type = logintype
                db_user.Status = status
                db_user.FA_User_Id = email_to_fa_users_mapping.get(email)
                db_user.SC_Organization_Id = scalar_orgid
                db_user.User_Email = email
                users_to_update.append(db_user)
                updated_users[userid] = scalar_orgname
                user_role_to_map[userid] = roles
                existing_user_ids.remove(userid)
            else:
                # prepare new user
                logger.info(msg=f"Creating new user object {userid}")
                if email in existing_emails:
                    logger.info(msg=f"duplicate user email for email id: {email}")

                new_user = SC_User(User_Id=userid, 
                                Login_Type = logintype, 
                                Status = status, 
                                FA_User_Id = email_to_fa_users_mapping.get(api_user_detail.emailAddress.lower()), 
                                SC_Organization_Id = scalar_orgid,
                                User_Email = email)
                users_to_insert.append(new_user)
                inserted_users[userid] = scalar_orgname
                user_role_to_map[userid] = roles
        except Exception as e:
            logger.info(msg=f"Failed to insert or update user {user['userId']}: {e}")
            failed_users.append({'userId' : userid, 'orgId' : scalar_orgid, 'error' : str(e)})
    
    for user_to_delete in existing_user_ids:
        # delete users present in db but not in API
        logger.info(msg=f"Deleting missing user object {user_to_delete}")

        db_user = next(user for user in user_db_data if user.User_Id==user_to_delete)
        db_user.Status = 'Inactive'
        deleted_users[user_to_delete]=db_user.SC_Organization_Id
    # insert and update commit to db based on batch-size 
    sync_users_in_db(db=db, users_to_insert = users_to_insert, users_to_update = users_to_update, batch_size = batch_size, logger = logger)

    inserted_users_df = pd.DataFrame(inserted_users.items(), columns=['UserId','SC_OrgName'])
    updated_users_df = pd.DataFrame(updated_users.items(), columns=['UserId','SC_OrgName'])
    deleted_users_df = pd.DataFrame(deleted_users.items(), columns=['UserId','SC_OrgId'])
    failed_users_df = pd.DataFrame(failed_users)

    return inserted_users_df, updated_users_df, deleted_users_df,user_role_to_map, failed_users_df

def user_role_mapping(db: Database, roles_api_data, user_role_map, logger):
    user_role_to_map = []
    inserted_user_role_mappings = {}
    failed_user_role_mapping =[]
    for userid, roleids in user_role_map.items():
        for roleid in roleids:
            try:
                role_name = roles_api_data.loc[roles_api_data['roleId']==roleid]['roleName'].values[0]
                user_role_mapping = SC_User_Role_Mapping(User_Id = userid,
                                                                Role_Id = roleid,
                                                                Role_Name = role_name)
                user_role_to_map.append(user_role_mapping)
                inserted_user_role_mappings[userid] = role_name
            except Exception as e:
                logger.info(msg=f"Failed to insert role mapping for user {userid}: {e}")
                failed_user_role_mapping.append({'userId' : userid, 'RoleId' : roleid, 'error' : str(e)})
    
    sync_user_role_mapping_in_db(db=db, user_role_to_map=user_role_to_map, batch_size=1000, logger=logger)
    
    inserted_user_role_mappings_df = pd.DataFrame(inserted_user_role_mappings.items(), columns=['UserId','RoleName'])
    failed_user_role_mapping_df = pd.DataFrame(failed_user_role_mapping)

    return inserted_user_role_mappings_df, failed_user_role_mapping_df
            
def send_sync_report(usersync_report, params):
    email = Email()
    receivers = os.environ['REPORT_MAIL_DL'].split(",")
    env = os.environ['SCALAR_ENV']
    file_name = f"User_Sync_Report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    subject = f"Scalar - Data Sync: User sync Report"
    template_name = "user_data_sync_report.html"
    if os.environ['SCALAR_ENV'] != 'PROD':
        subject = f"Scalar - Data Sync: User sync report - {os.environ['SCALAR_ENV']}"
    params["environment"] = os.environ['SCALAR_ENV']
    params["exectution_time"] = datetime.now()
    attachment = None
    file_name = f"{file_name} - {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    if usersync_report is not None:
        usersync_report.seek(0)
        attachment = usersync_report.read()
    email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                        attachment=attachment, filename=file_name)