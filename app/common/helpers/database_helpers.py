from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, BigInteger, String, DateTime
from datetime import datetime


def get_database_base():
    return declarative_base()

class IdMixin(object):
    id = Column(BigInteger, primary_key=True, nullable=False)

class CreationModificationLoggingMixin(object):
    Created_By = Column(String(50), nullable=False, default='Scalar')
    Created_Date = Column(DateTime, default=datetime.now)
    Modified_By = Column(String(50), nullable=False, default='Scalar')
    Modified_Date = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PipelineRunMixin(object):
    fc_insert_dt = Column(DateTime, nullable= False, default=datetime.now, onupdate=datetime.now)
    pipeline_run_id = Column(String(50), nullable=True)
    pipeline_name = Column(String(50), nullable=True, default='Scalar')