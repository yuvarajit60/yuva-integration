from datetime import datetime
from io import BytesIO
import logging
import os
import azure.functions as func
import pandas as pd

from app.common.constants import AudienceCode, ContentType, ResponseCode
from app.common.database import Database
from app.common.email import Email
from app.common.exception_handler import global_exception_handler
from app.common.helpers.common_data_access import get_tip_provider_organization
from app.common.helpers.common_services import fetch_access_token, get_all_data, get_scalar_api_error_messages, save_asset_group_in_db
from app.common.models import Response
from app.common.scalar_api.asset_group_api import create_asset_group, get_all_asset_groups
from app.fleetconnected_migration.tip_migration.fc_tip_migration_data_access import get_all_fc_region_country_mappings, get_new_asset_groups

tip_hierarchy_bp = func.Blueprint()
@tip_hierarchy_bp.function_name(name="Tip_Asset_Group_Hierarchy")
@tip_hierarchy_bp.route(route="tip/assetgroup/hierarchy",  methods=[func.HttpMethod.POST])
@global_exception_handler
def create_tip_hierarchy_api(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger = logging.getLogger("Tip_Hierarchy")
        db = Database()
        new_asset_groups = []
        error_asset_groups = []
        message = {}
        provider_org_id = get_tip_provider_organization(db=db)[0]
        access_token = fetch_access_token(db=db, org_id=provider_org_id, audience=AudienceCode.TEAMS)
        region_country_df = get_all_fc_region_country_mappings(db=db)
        # get all existing asset groups and filter their hierarchy
        existing_asset_groups_api_df = get_all_data(access_token=access_token, func=get_all_asset_groups)
        hierarchy_df = existing_asset_groups_api_df.merge(
            existing_asset_groups_api_df[['id', 'name']].rename(columns={'id':'region_id','name':'Region_Name'}),
            left_on='parentGroupId',
            right_on='region_id',
            how='left'
        )
        hierarchy_df = hierarchy_df.rename(columns={'name':'Country_Name'})
        hierarchy_df = hierarchy_df.drop(columns=['subGroupIds'])
        df_valid = hierarchy_df.merge(
            region_country_df, 
            on=['Region_Name','Country_Name'],
            how='inner'
        )
        df_missing = region_country_df.merge(
            hierarchy_df,
            on=['Region_Name','Country_Name'],
            how='left',
            indicator=True
        )
        missing_region_country = df_missing[df_missing['_merge'] == 'left_only']
        # add Europe region to the dataframe without any country
        region_country_df.loc[len(region_country_df)] = ['Europe',None]
        europe_region_df = existing_asset_groups_api_df[(existing_asset_groups_api_df['name']=='Europe')& (existing_asset_groups_api_df['parentGroupId'].isnull())]
        if europe_region_df.empty:
            missing_region_country.loc[len(missing_region_country)] = {'Region_Name':'Europe'}

        for index, region_country_pair in missing_region_country.iterrows():
            print(region_country_pair)
            chkregion = existing_asset_groups_api_df[(existing_asset_groups_api_df['name']==region_country_pair['Region_Name'])& (existing_asset_groups_api_df['parentGroupId'].isnull())]
            # chkcountry = df_valid[df_valid['Country_Name']==region_country_pair['Country_Name']].drop_duplicates()
            if pd.notna(region_country_pair['Region_Name']):
                if chkregion.empty:
                    region_asset_group_response = create_asset_group(access_token=access_token, name=region_country_pair['Region_Name'], description="Region asset group")
                    if region_asset_group_response.status_code != 201:
                        errors = get_scalar_api_error_messages(region_asset_group_response)[0]
                        error_asset_groups.append({"Asset Group Name":region_country_pair['Region_Name'],"errors": errors})
                        logger.info(errors)
                        message[region_country_pair['Region_Name']] = errors
                        continue
                    else:
                        region_group_id = region_asset_group_response.json()['id']
                        existing_asset_groups_api_df.loc[len(existing_asset_groups_api_df)] = {'name':region_country_pair['Region_Name'],'id':region_group_id}
                        new_asset_groups.append({"Asset Group Name":region_country_pair['Region_Name'],"Asset Group Id": region_group_id,"Type":"Region"})
                        save_asset_group_in_db(db=db, 
                                                asset_group_id=region_group_id, 
                                                asset_group_name=region_country_pair['Region_Name'], 
                                                asset_group_description="Region asset group", 
                                                sc_organization_id=provider_org_id, 
                                                root_group_id=None, 
                                                parent_group_id=None, 
                                                fa_root_org_id=None
                                                )
                else:
                    region_group_id = chkregion['id'].to_list()[0]
            if pd.notna(region_country_pair['Country_Name']):
                country_asset_group_response = create_asset_group(access_token=access_token, name=region_country_pair['Country_Name'], description="Country asset group", parent_group_id=region_group_id)
                if country_asset_group_response.status_code != 201:
                    errors = get_scalar_api_error_messages(country_asset_group_response)[0]
                    error_asset_groups.append({"Asset Group Name":region_country_pair['Country_Name'],"errors": errors})
                    logger.error(errors)
                    message[region_country_pair['Country_Name']] = errors
                    continue
                else:
                    country_group_id = country_asset_group_response.json()['id']
                    new_asset_groups.append({"Asset Group Name":region_country_pair['Country_Name'],"Asset Group Id": country_group_id,"Type":"Country"})
                save_asset_group_in_db(db=db, 
                                        asset_group_id=country_group_id, 
                                        asset_group_name=region_country_pair['Country_Name'], 
                                        asset_group_description="Country asset group", 
                                        sc_organization_id=provider_org_id,
                                        root_group_id=region_group_id, 
                                        parent_group_id=region_group_id, 
                                        fa_root_org_id=None
                                        )
        
        # add tip global asset group record in df for assets
        if existing_asset_groups_api_df[(existing_asset_groups_api_df['name']=='TIP Global')& (existing_asset_groups_api_df['parentGroupId'].isnull())].empty:
            tip_global_group_response = create_asset_group(access_token=access_token, name="TIP Global", description="TIP Global asset group")
            if tip_global_group_response.status_code == 201:
                tip_global_group_id = tip_global_group_response.json()['id']
                new_asset_groups.append({"Asset Group Name":"TIP Global","Asset Group Id": tip_global_group_id,"Type":"Global"})
                save_asset_group_in_db(db=db, 
                                            asset_group_id=tip_global_group_id, 
                                            asset_group_name="TIP Global", 
                                            asset_group_description="TIP Global asset group", 
                                            sc_organization_id=provider_org_id,
                                            root_group_id=None, 
                                            parent_group_id=None, 
                                            fa_root_org_id=None
                                            )
            else:
                errors = get_scalar_api_error_messages(tip_global_group_response)[0]
                if "Group already exists." not in errors:
                    logger.info(errors)
                    message["TIP Global"] = errors
                    error_asset_groups.append({"Asset Group Name":"TIP Global","errors": errors})        
        else:
            tip_global_group_id = existing_asset_groups_api_df[(existing_asset_groups_api_df['name']=='TIP Global')& (existing_asset_groups_api_df['parentGroupId'].isnull())]['id'].to_list()[0]
        
        if existing_asset_groups_api_df[(existing_asset_groups_api_df['name']=='Assets')& (existing_asset_groups_api_df['parentGroupId']==tip_global_group_id)].empty:
            assets_group_response = create_asset_group(access_token=access_token, name="Assets", description="TIP Global asset subgroup", parent_group_id=tip_global_group_id)
            if assets_group_response.status_code != 201:
                errors = get_scalar_api_error_messages(assets_group_response)[0]
                logger.info(errors)
                message["Assets"] = errors
                error_asset_groups.append({"Asset Group Name":"Assets","errors": errors})
                
            else:
                assets_group_id = assets_group_response.json()['id']
                new_asset_groups.append({"Asset Group Name":"Assets","Asset Group Id": assets_group_id,"Type":"Global"})
                save_asset_group_in_db(db=db, 
                                        asset_group_id=assets_group_id, 
                                        asset_group_name="Assets", 
                                        asset_group_description="TIP Global asset subgroup", 
                                        sc_organization_id=provider_org_id,
                                        root_group_id=tip_global_group_id, 
                                        parent_group_id=tip_global_group_id, 
                                        fa_root_org_id=None
                                        )
    except Exception as e:
        message["error"] = str(e)
        error_asset_groups.append({"Unknown errors":e})
        if region_country_df.empty:
            region_country_df = pd.DataFrame(columns=['Region_Name','Country_Name'])
    finally:
        asset_group_names = pd.unique(region_country_df[['Region_Name','Country_Name']].values.ravel()).tolist()[:-1]
        total_asset_groups_in_db_df = get_new_asset_groups(db=db,asset_group_names=asset_group_names+["TIP Global","Assets"],provider_org_id=provider_org_id)
        tip_hierarchy_report = BytesIO()
        with pd.ExcelWriter(tip_hierarchy_report, engine='xlsxwriter') as writer:
            if len(total_asset_groups_in_db_df) > 0:
                total_asset_groups_in_db_df.to_excel(writer, sheet_name='Total Asset Groups', index=None, header=True)
            if len(new_asset_groups) > 0:
                pd.DataFrame(new_asset_groups).to_excel(writer, sheet_name='New Asset Groups', index=None, header=True)
            if len(error_asset_groups) > 0:
                pd.DataFrame(error_asset_groups).to_excel(writer, sheet_name='Errors', index=None, header=True)
        
        email = Email()
        receivers = os.environ['MIGRATION_REPORT_MAIL_DL'].split(",")
        env = os.environ['SCALAR_ENV']
        file_name = f"TIP_Hierarchy_Report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        subject = f"Scalar Migration - TIP hierarchy for region, country, tip_global - " + env
        template_name = "tip_hierarchy.html"
        
        params = {
            "total_asset_groups":len(total_asset_groups_in_db_df),
            "new_asset_groups":len(new_asset_groups),
            "errors":len(error_asset_groups)
        }
        params["environment"] = os.environ['SCALAR_ENV']
        params["exectution_time"] = datetime.now()
        attachment = None
        file_name = f"{file_name} - {datetime.now().strftime('%Y-%m-%d')}.xlsx"
        if tip_hierarchy_report is not None:
            tip_hierarchy_report.seek(0)
            attachment = tip_hierarchy_report.read()
        email.send_email(receivers=receivers, subject=subject, template_name=template_name, params=params, 
                            attachment=attachment, filename=file_name)
        
        message["end"] = "Finished creating region, country, TIP Global asset groups in provider org."
        response = Response(status=True, message=message).getJsonResponse()
        return func.HttpResponse(
                response,
                status_code=ResponseCode.SUCCESS,
                mimetype=ContentType.APPLICATION_JSON)