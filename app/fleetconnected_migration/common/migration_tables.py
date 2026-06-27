from app.common.helpers.database_helpers import get_database_base, IdMixin, CreationModificationLoggingMixin
from sqlalchemy import Column, String, CHAR, DateTime, Integer
from datetime import datetime

Base = get_database_base()

class SC_Customer_Migration_Process_Status_Log(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Customer_Migration_Process_Status_Log'
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Run_Id = Column(String(40), nullable=False)
    FA_Root_Organization_Id = Column(String(50), nullable=False)
    Process_Name = Column(String(40), nullable=False)
    Company_Code = Column(String(60), nullable = True)
    Start_Datetime = Column(DateTime(8), nullable=False)
    Stop_Datetime = Column(DateTime(8), nullable=False)
    Response_Code = Column(Integer, nullable=False)
    Success_Status = Column(CHAR(1), nullable=False)
    Response_Message = Column(String(5000), nullable=False)

class SC_TIP_Migration_Process_Status_Log(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_TIP_Migration_Process_Status_Log'
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    Run_Id = Column(String(36), nullable=False)
    Process_Name = Column(String(500), nullable=False)
    Start_Datetime = Column(DateTime(8), nullable=False)
    Stop_Datetime = Column(DateTime(8), nullable=False)
    Response_Code = Column(Integer, nullable=False)
    Success_Status = Column(CHAR(1), nullable=False)
    Response_Message = Column(String(5000), nullable=False)

class SC_Migrated_SKY_Customer_To_Scalar(IdMixin, CreationModificationLoggingMixin , Base):
    __tablename__ = 'SC_Migrated_SKY_Customer_To_Scalar'
    __table_args__ = {'schema': 'SCALAR'}
    Id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    SC_Organization_Id = Column(String(40), nullable=False)
    SC_Organization_Name = Column(String(100), nullable=False)
    SKY_Company_id = Column(Integer, nullable=False)
    SKY_Company_Code = Column(String(60), nullable=False)
    FA_Root_Org_Id = Column(Integer, nullable=False)
    Migrated_Flag = Column(CHAR(1), nullable=False)
    Migrated_Date = Column(DateTime(8), nullable=False)