from ..helpers.database_helpers import get_database_base, IdMixin, CreationModificationLoggingMixin
from sqlalchemy import Column, BigInteger, String, ForeignKey, CHAR, DateTime, Integer,Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mssql import TINYINT
from datetime import datetime

Base = get_database_base()

class SC_Asset(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Asset'
    __table_args__ = {'schema': 'SCALAR'}
    Asset_Id = Column(String(40), nullable=False)
    Internal_Code = Column(String(50), nullable=True)
    Unit_Nr = Column(Integer, nullable=True)
    Device_Number = Column(String(50), nullable=True)
    Device_Pairing_Status = Column(CHAR(1), nullable=False)
    Device_Pairing_Date = Column(DateTime(8), nullable=True)
    Device_Type = Column(String(60),nullable=True)
    Device_Paired_By = Column(String(50),nullable=False)
    Active = Column(CHAR(1), nullable=False)
    Status = Column(String(20), nullable=False)
    Fleet_Id = Column(String(60), nullable=True)
    Unit_Licence_Nr = Column(String(60), nullable=True)
    VIN_Number = Column(String(100), nullable=True)

class SC_Asset_pairing_history(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Asset_Pairing_History'
    __table_args__ = {'schema': 'SCALAR'}
    Asset_Id = Column(String(40), nullable=False)
    Internal_Code = Column(String(50), nullable=True)
    Unit_Nr = Column(Integer, nullable=True)
    Device_Number = Column(String(50), nullable=True)
    Device_Pairing_Status = Column(CHAR(1), nullable=False)
    Device_Pairing_Date = Column(DateTime(8), nullable=True)
    Device_Type = Column(String(60),nullable=True)
    Device_Paired_By = Column(String(50),nullable=False)
    Active = Column(CHAR(1), nullable=False)
    Status = Column(String(20), nullable=False)
    Device_Unpairing_Date = Column(DateTime(8), nullable=True)

class SC_User(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_User"
    __table_args__ = {'schema': 'SCALAR'}
    User_Id = Column(String(50), primary_key=True, nullable=False, autoincrement=False)
    Login_Type = Column(String(50), nullable=False)
    Status = Column(String(10), nullable=False)
    FA_User_Id = Column(String(50), nullable=False)
    SC_Organization_Id = Column(String(40), nullable=False)
    User_Email = Column(String(200), nullable=False)

class FA_User(CreationModificationLoggingMixin, Base):
    __tablename__ = "FA_User"
    User_Id = Column(String(50), primary_key=True, nullable=False, autoincrement=False)
    User_Email = Column(String(100), nullable=True)
    Active = Column(CHAR(1), nullable=False)
    Tip_User = Column(CHAR(1), nullable=False)
    Root_Organization_Id = Column(String(40), nullable=True)

class SC_User_Role_Mapping(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_User_Role_Mapping"
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    User_Id = Column(String(50), nullable=False)
    Role_Id = Column(String(50), nullable=False)
    Role_Name = Column(String(1), nullable=False)

class SC_Team(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Team"
    __table_args__ = {'schema': 'SCALAR'}
    Team_Id = Column(String(50), primary_key=True, nullable=False, autoincrement=False)
    Team_Name = Column(String(50), nullable=False)
    Active = Column(String(10), nullable=False)
    Description = Column(String(50), nullable=False)
    SC_Organization_Id = Column(String(40), nullable=False)

class SC_Team_User_Mapping(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Team_User_Mapping"
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    User_Id = Column(String(50), nullable=False)
    Team_Id = Column(String(50), nullable=False)
    Active = Column(String(1), nullable=False)

class SC_Organization(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Organization'
    __table_args__ = {'schema': 'SCALAR'}
    Organization_Id = Column(String(40), primary_key=True, nullable=False, autoincrement=False)
    Organization_Name = Column(String(100), nullable=False)
    FA_Root_Organization_Id = Column(Integer, nullable=True)
    Is_Provider = Column(CHAR(1), nullable=False)
    ZF_Consumer_Org= Column(CHAR(1), nullable=False)
    Is_SSO_Enabled= Column(CHAR(1), nullable=False)
    Active = Column(CHAR(1), nullable=False)

class SC_Framework_Agreement(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Framework_Agreement'
    __table_args__ = {'schema': 'SCALAR'}
    Agreement_Id = Column(String(40), primary_key=True, nullable=False, autoincrement=False)
    Agreement_Name = Column(String(100), nullable=False)
    Agreement_Desc = Column(String(500), nullable=False)
    Consumer_Org_Id = Column(String(40), nullable=False)
    Provider_Org_Id = Column(String(40), nullable=False)
    Data_Sharing_Type = Column(String(50), nullable=False)
    Subject_Type = Column(String(50), nullable=False)
    Asset_Type = Column(String(100), nullable=False)
    Is_Existing_Customer = Column(CHAR(1), nullable=False)
    Owner = Column(String(50), nullable=False)
    Payer = Column(String(50), nullable=False)
    Primary_Email_Address = Column(String(200), nullable=True)
    Primary_First_Name = Column(String(50), nullable=True)
    Primary_Last_Name = Column(String(50), nullable=True)
    Allow_Further_Sharing = Column(CHAR(1), nullable=False)
    Multi_Share_Mode = Column(String(40), nullable=False)
    Session_Contract_Mode = Column(String(40), nullable=False)
    Create_Integrator = Column(CHAR(1), nullable=False)
    Rejected_Reason = Column(String(40), nullable=True)
    Approved_Rejected_Date = Column(DateTime, default=datetime.now)
    Approved_Rejected_By = Column(String(50), nullable=True)
    Stopped_By = Column(String(50), nullable=True)
    Stopped_On = Column(DateTime,nullable=True)
    Agreement_Status = Column(String(15), nullable=False)
    Profile_Id = Column(String(40), nullable=True)


class SC_Integrator_Details(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Integrator_Details'
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Organization_Id = Column(String(40), nullable=False)
    Integrator_Name = Column(String(500), nullable=False)
    Framework_Id = Column(String(40), nullable=False)
    Client_Id = Column(String(100), nullable=False)
    Client_Secret = Column(String(500), nullable=False)
    Active = Column(CHAR(1), nullable=False)

class SC_Session(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Session"
    __table_args__ = {'schema': 'SCALAR'}
    Session_Id = Column(String(50), primary_key=True, nullable=False)
    Agreement_Id = Column(String(50), nullable=False)
    Provider_Organization_Id = Column(String(40), nullable=False)
    Consumer_Organization_Id = Column(String(40), nullable=False)
    Provider_Asset_Id = Column(String(40), nullable=False)
    Consumer_Asset_Id = Column(String(50), nullable=True, default="")
    Provider_Unit_Nr = Column(String(40), nullable=True)
    Status = Column(String(40), nullable=False, default="")
    Real_Start = Column(DateTime, nullable=True)
    Real_Stop = Column(DateTime, nullable=True)
    Desired_start = Column(DateTime, nullable=True)
    Desired_Stop = Column(DateTime, nullable=True)
    Active = Column(String(1), nullable=False, default=1)

class SC_Job_Execution_Details(IdMixin, Base):
    __tablename__ = "SC_Job_Execution_Details"
    __table_args__ = {'schema': 'SCALAR'}
    # Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Job_Name = Column(String(50), nullable=False)
    Status_Cd = Column(String(1), nullable=False)
    Execution_Start_Date = Column(DateTime, nullable=False, default=datetime.now)
    Execution_End_Date = Column(DateTime, nullable=True, default=None)

class SC_Asset_Group(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Asset_Group"
    __table_args__ = {'schema': 'SCALAR'}
    Asset_Group_Id = Column(String(50), primary_key=True, nullable=False)
    Asset_Group_Name = Column(String(100), nullable=False)
    Description = Column(String(100), nullable=False)
    SC_Organization_Id = Column(String(40), nullable=False)
    Root_Group_Id = Column(String(50), nullable=True)
    Parent_Group_Id = Column(String(50), nullable=True)
    FA_Organization_Id = Column(Integer, nullable=True)
    Active = Column(CHAR(1), nullable=False)

class SC_Asset_Group_Asset_Mapping(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Asset_Group_Asset_Mapping"
    __table_args__ = {'schema': 'SCALAR'}
    Asset_Group_Id = Column(String(50), primary_key=True, nullable=False)
    Asset_Id = Column(String(40), nullable=False)
    Active = Column(CHAR(1), nullable=False)

class SC_Asset_Group_Team_Mapping(CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Asset_Group_Team_Mapping"
    __table_args__ = {'schema': 'SCALAR'}
    Asset_Group_Id = Column(String(50), primary_key=True, nullable=False)
    Team_Id = Column(String(40), nullable=False)
    Active = Column(CHAR(1), nullable=False)

class ScalarAutoPairingLog(IdMixin, CreationModificationLoggingMixin, Base):
    __tablename__ = "SC_Auto_Pairing_Log"
    __table_args__ = {'schema': 'SCALAR'}
    #Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Event_Batch_Id = Column(String(50), nullable=False)
    Event_Subscription_Id = Column(String(50), nullable=False)
    Event_Batch_Time = Column(DateTime, nullable=False, default=datetime.now())
    Event_Type = Column(String(50), nullable=False)
    Event_Version = Column(Integer, nullable=False)
    Device_Number = Column(String(50), nullable=False)
    Asset_Id = Column(String(100), nullable=True)
    Candidate_Asset_Ids = Column(String(1000), nullable=True)
    Organization_Id = Column(String(40), nullable=False)
    AssetVIN = Column(String(50), nullable=True)
    SensorVIN = Column(String(50), nullable=True)
    Error_Ind = Column(Integer, nullable=True)
    Error_Message = Column(String(100), nullable=True)
    Status = Column(String(20), nullable=False)
    Reason = Column(String(50), nullable=False)
    Event_Timestamp = Column(DateTime, nullable=False, default=datetime.now())
    Latitude = Column(Float, nullable=False)
    Longitude = Column(Float, nullable=False)

class FA_Org_Application_Mapping(CreationModificationLoggingMixin, Base):
    __tablename__ = "FA_Org_Application_Mapping"
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Organization_Id = Column(BigInteger, nullable=False)
    Application_Id = Column(Integer, nullable=False)
    Active = Column(String(1), nullable=False)

class FA_User_App_Access(CreationModificationLoggingMixin, Base):
    __tablename__ = "FA_User_App_Access"
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    User_Id = Column(String(50), nullable=False)
    Application_Id = Column(Integer, nullable=False)
    Active = Column(String(1), nullable=False)