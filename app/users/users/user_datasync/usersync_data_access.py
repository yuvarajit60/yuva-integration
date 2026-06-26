from app.common.database import Database
from app.common.database_model.scalar_tables import SC_User, SC_User_Role_Mapping


def sync_users_in_db(db: Database, users_to_insert, users_to_update, batch_size, logger):
    insert_update_data_count = max(len(users_to_insert), len(users_to_update))
    for curr_index in range(0, insert_update_data_count, batch_size): 
        db.insert_orm_list(users_to_insert[curr_index:curr_index + batch_size])
    logger.info(msg=f"Inserted {len(users_to_insert)} users and Updated {len(users_to_update)} users")

def sync_user_role_mapping_in_db(db: Database, user_role_to_map, batch_size, logger):
    deleted_user_role_count = db.get_session().query(SC_User_Role_Mapping).delete()
    logger.info(msg=f"Deleted SC_User_Role_Mapping table data for {deleted_user_role_count} rows")
    
    user_role_mapping_data_count = len(user_role_to_map)
    for curr_index in range(0, user_role_mapping_data_count, batch_size): 
        db.insert_orm_list(user_role_to_map[curr_index:curr_index + batch_size])
    logger.info(msg=f"Inserted user role mapping for {len(user_role_to_map)} users")

def get_all_users_from_db(db: Database):
    # user_ids = all_users_api_data['userId'].tolist()
    existing_users = db.get_session().query(SC_User).all()
    return existing_users