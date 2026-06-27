from .common_services import (
    generate_common_multi_error_report, get_combined_err_list)


def get_units_by_root_orgs(units_df):
    units_by_root_orgs = {}

    df_by_root_org_id = units_df.groupby(['Root_Organization_Id'])
    for root_org_id, frame in df_by_root_org_id:
        root_org_id = root_org_id[0]
        df_by_org_id = frame.groupby(['Organization_Id'])
        units_by_root_orgs[root_org_id] = {}
        for org_id, unit_data_frame in df_by_org_id:
            org_id = org_id[0]
            units_by_root_orgs[root_org_id][org_id] = unit_data_frame
    return units_by_root_orgs


def get_control_report_records(unit_df) :
    control_report_records = []
    for index, unit in unit_df.iterrows():
        control_report_record = {}
        control_report_record["Unit_Number"] = int(unit["UnitNr"])
        control_report_record["License_Plate_Number"] = unit["UnitLicenceNr"]
        # trailer_id = unit["transic_trailer_id"]
        # control_report_record["Transics_Trailer_Id"] = int(trailer_id) if trailer_id is not None else trailer_id
        control_report_record["Customer_Combi_Number"] = unit["CustomerCombiNr"]
        control_report_record["Region"] = unit["Region_Name"]
        control_report_record["Country"] = unit["Country_Name"]
        control_report_record["Customer_Name"] = unit["Customer_Name"]
        control_report_record["Rate_Number"] = unit["RateNr"]
        control_report_record["Master_Lease_Number"] = unit["MasterLeaseNr"]
        r_org_id = unit["Root_Organization_Id"]
        control_report_record["Root_Org_Id"] = int(r_org_id) if r_org_id is not None else r_org_id
        control_report_record["Root_Org_Name"] = unit["root_org_name"]
        org_id = unit["Organization_Id"]
        control_report_record["Org_Id"] = int(org_id) if org_id is not None else org_id
        control_report_record["Org_Name"] = unit["organization_name"]
        control_report_record["Asset_Id"] = unit["Asset_Id"]
        control_report_records.append(control_report_record)
    return control_report_records


def generate_process_control_report(units_wout_root_org_list, units_wout_pairing_info_list,
                                            consumer_issues_unit_list, data_shared_unit_list,
                                            already_data_shared_unit_list, 
                                            diff_org_already_data_shared_unit_list,
                                            unknown_errors):

    combined_err_list = get_combined_err_list(units_wout_root_org_list=units_wout_root_org_list,
                        units_wout_pairing_info_list=units_wout_pairing_info_list,
                        consumer_issues_unit_list=consumer_issues_unit_list,
                        data_shared_unit_list=data_shared_unit_list,
                        already_data_shared_unit_list=already_data_shared_unit_list,
                        diff_org_already_data_shared_unit_list = diff_org_already_data_shared_unit_list,
                        unknown_errors=unknown_errors)
    error_report_content = None
    if len(combined_err_list) > 0:
        error_report_content = generate_common_multi_error_report(error_list=combined_err_list)
    return error_report_content