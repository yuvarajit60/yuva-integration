SELECT  [unit_nr], 
		[serial_nr], 
		[license_nr], 
		[additional_chrg_typ], 
		[additional_chrg],
		wam_org.[organization_id],
		wam_org.[root_organization_id],
		[parent_organization_id], 
		[organization_name_txt], 
		[organization_level],
		[user_sso_id],
		[user_title_txt],
		[user_forename_txt],
		[user_surname_txt],
		[user_known_as_txt],
		[user_email_txt],
		[registration_cd],
		[language_id],
		[language_code]
FROM [bi_fact_unit] unit
LEFT JOIN (SELECT   [additional_chrg_typ], 
					[additional_chrg], 
					[rate_nr] 
			FROM [bi_additional_charges]) add_chrg ON add_chrg.rate_nr = unit.rate_nr
LEFT JOIN (SELECT [organization_id], 
				  [customer_combi_number] 
			FROM [wam_org_combinum]) wam_org_combi ON wam_org_combi.customer_combi_number = unit.customer_combi_nr 
LEFT JOIN (SELECT   [organization_id], 
					[root_organization_id],
					[parent_organization_id], 
					[organization_name_txt], 
					[organization_level] 
			FROM [wam_organization]) wam_org ON wam_org_combi.organization_id = wam_org.organization_id
LEFT JOIN (SELECT   [user_sso_id],
					[user_title_txt],
					[user_forename_txt],
					[user_surname_txt],
					[user_known_as_txt],
					[user_email_txt],
					[language_id],
					[language_code],
					[registration_cd],
					[root_organization_id],
					[organization_id]
			FROM [cp_user_profile]) cp_profile ON wam_org.organization_id = cp_profile.organization_id AND wam_org.root_organization_id = cp_profile.root_organization_id
WHERE unit.unit_nr IN (:unr) 