class StatusCode:
    FAILURE = "F"
    SUCCESSFUL = "S"
    NOT_YET_RUNNING = "N"
    RUNNING = "R"

class AudienceCode:
    USER = "UMAPI"
    ASSET = "AMAPI"
    TEAMS = "TMAPI"
    DATA_SHARING = "DASAPI"
    BRAKE_PERFORMANCE = "BPAPI"

class ResponseCode():
    SUCCESS = 200
    ACCEPTED = 202
    NOT_FOUND = 404
    BAD_REQUEST = 400
    INTERNAL_ERROR = 500



class TrailerIdentifier:
    # Source http://integrators_ft.transics.com/Administration/Get_Trailers.html

    ID = "ID" # corresponds to 'Code' field in Transics
    CODE = "CODE" # corresponds to 'Vehicle external code' in Transics
    LICENSE_PLATE = "LICENSE_PLATE"
    TRANSICS_ID = "TRANSICS_ID"


class ErrorFields:
    PRE_PROCESSING_ACTIVITY_ID = 'PRE-PROCESSING ACTIVITY ID'
    ROOT_ORGANIZATION_ID = "ROOT ORGANIZATION ID"
    ROOT_ORGANIZATION_NAME = "ROOT_ORGANIZATION_NAME"
    ROOT_ORGANIZATION_ID_NAME = "ROOT_ORGANIZATION_ID_NAME"
    ORGANIZATION_ID = "ORGANIZATION_ID"
    ORGANIZATION_NAME = "ORGANIZATION_NAME"
    EXCEPTION = 'EXCEPTION'
    REGION_COUNTRY = 'REGION_COUNTRY'
    ORGANIZATION_ID_NAME = "ORGANIZATION_ID_NAME"
    TENANCY_REQUEST_ID = "TENANCY_REQUEST_ID"
    GROUP_SUB_GROUP = "GROUP_SUB_GROUP_NAMES"
    SUBSCRIPTION_ID = "SubscriptionId"


class TransicsUserIdentifier:
    EMAIL = "EMAIL"

class ContentType:
    APPLICATION_JSON = "application/json"

class GeneralConstant:
    DB_EXCP_MESSAGE = "DB exception occurred"
    INTCH_OUT_UNIT_JOB_NAME = "INSIGHT_INTCH_OUT_UNIT_JOB"
    NEW_PAIRING_UNIT_JOB_NAME = "INSIGHT_NEW_PAIRING_UNIT_JOB"
    COPY_MOVE_ALONG_UNIT_JOB_NAME = "INSIGHT_COPY_MOVE_ALONG_UNIT_JOB"
    INTCH_IN_UNIT_JOB_NAME = "INSIGHT_INTCH_IN_UNIT_JOB"
    BRAKE_PLUS_ACTIVATE_UNIT_JOB_NAME = "INSIGHT_BRAKE_PLUS_ACTIVATE_UNIT_JOB"
    BRAKE_PLUS_DEACTIVATE_UNIT_JOB_NAME = "INSIGHT_BRAKE_PLUS_DEACTIVATE_UNIT_JOB"
    INSIGHT_UPDATE_DATA_SHARING_JOB_NAME = "INSIGHT_UPDATE_DATA_SHARING_JOB"
    SUBSCRIPTION_NOT_FOUND = "SUBSCRIPTION_NOT_FOUND"
    TRAILERS = "TRAILERS"
    REEFER = "Reefer"
    ERROR_IDENTIFIER_NOT_FOUND = "ERROR_IDENTIFIER_NOT_FOUND"
    POST_SUBCONTRACTING_PAUSE_TIME_IN_SECS = 5
    PAUSE_TIME_IN_SECS = 2
    BP_ACTIVATION_PAUSE_TIME_IN_SECS = 100
    ERROR_INSERT_UNIQUE_ID = "ERROR_INSERT_UNIQUE_ID"
    ERROR_ALREADY_ATTACHED = "ERROR_ALREADY_ATTACHED"
    ERROR_UNIQUE_EMAIL_ID = "The email address should be unique"
    ASSET_LIMIT = 5000
    TIPGLOBALGROUP = "TIP Global"
    TIPGLOBALCHILDGROUP = "Assets"
    ASSIGNMENT_LOOKUP_WAITTIME = 3
    ASSIGNMENT_LOOKUP_LIMIT = 5
    RETRY_WAITTIME = 12
    RETRY_LIMIT = 5
    ASSET_GROUP_RETRY_WAITTIME = 15
    ASSET_GROUP_RETRY_LIMIT = 4
    ONBOARDING_WAITTIME = 30
    ONBOARDING_LIMIT = 10

class ApiUrl:
    AUTHENTICATION_URL = "{hostname}/integrators/token"
    ALL_USER_URL = "{hostname}/users"
    ALL_ROLE_URL = "{hostname}/roles"
    SPECIFIC_USER_URL = "{hostname}/users/{user_id}"
    CREATE_USER_URL = "{hostname}/users/"
    UPDATE_USER_URL = "{hostname}/users/{user_id}"
    FRAMEWORK_AGREEMENTS_URL = "{hostname}/framework-agreements"
    SPECIFIC_FRAMEWORK_AGREEMENTS_URL = "{hostname}/framework-agreements/{agreement_id}"
    INTEGRATOR_URL = "{hostname}/framework-agreements/{agreement_id}/integrator"
    ASSET_URL = "{hostname}/assets"
    SPECIFIC_ASSET_URL = "{hostname}/assets/{assetid}"
    SESSIONS_URL = "{hostname}/sessions"
    SESSIONS_FOR_A_FRAMEWORK_URL = "{hostname}/sessions?frameworkAgreementId={agreement_id}"
    SPECIFIC_SESSION_URL = "{hostname}/sessions/{session_id}"
    STOP_SESSION_URL = "{hostname}/actions/stop-session"
    TEAM_URL = "{hostname}/teams"
    USER_IN_TEAM_URL = "{hostname}/teams/{team_id}/users"
    SPECIFIC_TEAM_URL = "{hostname}/teams/{team_id}"
    ASSIGN_USER_TO_TEAM_URL = "{hostname}/actions/assign-users"
    UNASSIGN_USER_TO_TEAM_URL = "{hostname}/actions/unassign-users"
    ASSIGN_ASSET_GROUP_TO_TEAM_URL = "{hostname}/actions/assign-asset-groups"
    UNASSIGN_ASSET_GROUP_TO_TEAM_URL = "{hostname}/actions/unassign-asset-groups"
    ASSET_GROUP_URL = "{hostname}/asset-groups"
    SPECIFIC_ASSET_GROUP_URL = "{hostname}/asset-groups/{asset_group_id}"
    ASSIGN_ASSET_GROUP_URL = "{hostname}/actions/assign-assets"
    UNASSIGN_ASSET_GROUP_URL = "{hostname}/actions/unassign-assets"
    BRAKE_PERFORMANCE_URL = "{hostname}/assets"
    SPECIFIC_BRAKE_PERFORMANCE_URL = "{hostname}/assets/{assetid}"
    BRAKE_EBPMS_ENABLE_URL = "{hostname}/actions/enable-ebpms"
    BRAKE_EBPMS_DISABLE_URL = "{hostname}/actions/disable-ebpms"

class AdditionalChargeType:
    Insight_Additional_Charge_Types = ["IN CAAS TI",
                                "IN REEF TI ",
                                "IN TPMS TI",
                                "IN API TIP",
                                "IN EBPMS T",
                                "IN DP TIP",
                                "IN CAAS 3P",
                                "IN REEF 3P",
                                "IN TPMS 3P",
                                "IN API 3P",
                                "IN EBPMS 3",
                                "IN DP 3P",
                                "INS TIPD",
                                "INS COTIPD",
                                "INS TPTIPD",
                                "INS APTIPD",
                                "INS EBTIPD",
                                "IN DP TIPD",
                                "INS 3PD",
                                "INS CO3PD",
                                "INS TP 3PD",
                                "IN API 3PD",
                                "INS BP 3PD",
                                "INS DP 3PD",
                                "SEP.APTIPD",
                                "SEP.API3P",
                                "SEP.API3PD",
                                "SEP.APITIP",
                                "SEP.BP3PD",
                                "SEP.CAAS3P",
                                "SEP.CAASTI",
                                "SEP.CO3PD",
                                "SEP.COTIPD",
                                "SEP.DP3P",
                                "SEP.DP3PD",
                                "SEP.DPTIP",
                                "SEP.DPTIPD",
                                "SEP.EBPMS3",
                                "SEP.EBPMST",
                                "SEP.EBTIPD",
                                "SEP.INS3PD",
                                "SEP.REEF3P",
                                "SEP.REEFTI",
                                "SEP.TIPD",
                                "SEP.TP3PD",
                                "SEP.TPMS3P",
                                "SEP.TPMSTI",
                                "SEP.TPTIPD"]

class ExcelSheetName:
    ALREADY_DATASHARED_UNITS = "Already DataShared units"
    DIFF_ORG_DATASHARED_UNITS = "DataShared in Different Org"
    DATASHARED_SUCCESSFULLY = "DataShared successfully"
    UNKOWN_ERRORS = "Unknown errors"
    UNITS_WOUT_PAIRING_INFO = "Units without pairing info"
    UNITS_WITHOUT_FA_SCALAR_ORG = "Units without FA Scalar Org"
    UNITS_WITHOUT_SCALAR_CUST_ONBOARDING = "Units without Scalar onboarding"
    DATASHARING_STOPPED_UNITS = "Datasharing stopped units"
    DATASHARING_NOT_FOUND_UNITS = "Datasharing not found units"
    BRAKEPLUS_ACTIVATED_UNITS = "Brake plus activated units"
    BRAKEPLUS_ALREADY_ACTIVATED_UNITS = "BrakeplusAlreadyActivatedUnits"
    BRAKEPLUS_FAILED_UNITS = "Brake plus failed units"


class AutoPairingEvent:
    DEVICE_SUCCESSFULLY_AUTO_PAIRED = "AutoPair"
    DEVICE_SUCCESSFULLY_MANUAL_PAIRED = "ManualPair"
    DEVICE_SUCCESSFULLY_MANUAL_UNPAIRED = "ManualUnpair"
    DEVICE_NOT_PAIRED_VIN_NOT_FOUND = "NotFound"
    DEVICE_NOT_PAIRED_MULTIPLE_MATCH_FOUND = "MultipleMatchFound"
    DEVICE_NOT_PAIRED_INVALID_DATA = "InvalidData"
    DEVICE_NOT_PAIRED_UNKNOWN = "Unknown"

class AutoPairingEventType:
    DEVICE_PAIRIED ="unit.paired"
    DEVICE_UNPAIRED = "unit.unpaired"

class EventKey:
    DEVICE_IMEI = "deviceImei"
    VIN = "vin"
    DEVICE_TYPE = "deviceType"


class VehicleCategory:
    GENERAL_CARGO = "GeneralCargo"
    REFRIGERATED_TRANSPORT = "RefrigeratedTransport"

class TrailerIdentifier:
    # Source http://integrators_ft.transics.com/Administration/Get_Trailers.html

    ID = "ID" # corresponds to 'Code' field in Transics
    CODE = "CODE" # corresponds to 'Vehicle external code' in Transics
    LICENSE_PLATE = "LICENSE_PLATE"
    TRANSICS_ID = "TRANSICS_ID"

class Connection:
    TIP_CONNECTION ="TIP"
    CUSTOMER_CONNECTION = "CUSTOMER"

class Application:
    APP_NAME ="SCALAR"

class BPAdditionalChargeType:
    BP_Insight_Additional_Charge_Types = ["IN EBPMS T", "IN EBPMS 3", "INS EBTIPD", "INS BP 3PD", "SEP.BP3PD", "SEP.EBPMS3", "SEP.EBPMST", "SEP.EBTIPD"]



