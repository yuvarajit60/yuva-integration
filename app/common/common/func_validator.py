from dataclasses import field
from marshmallow_dataclass import dataclass
import marshmallow


@dataclass
class User:
    firstName: str = field(default=None)
    lastName: str = field(default=None)
    emailAddress: str = field(default=None)
    language: str = field(default=None)
    roles: list = field(default=None)
    loginType: str = field(default=None)
    userId: str = field(default=None)
    status: str = field(default=None)
    orgId: str = field(default=None)
    sc_orgName: str = field(default=None)
    fa_User_Id: str = field(default=None)

@dataclass
class Asset:
    assetType: str = field(default=None)
    mileage: int = field(default=None)
    assetCategory: str = field(default=None)
    displayName: str = field(default=None)
    licensePlate: str = field(default=None)
    internalCode: str = field(default=None)
    externalCode: str = field(default=None)
    vin: str = field(default=None)
    status: str = field(default=None)
    assetid: str = field(default=None)
    devices: list= field(default=None)
  
@dataclass
class Team:
    teamName: str = field(default=None)
    description: str = field(default=None)
    teamId: str = field(default=None)
    userIds: list = field(default=None)

@dataclass
class CreateUser:
    language: str = field(default="en")
    scalarRoleName: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")}, default=None)
    scalarRoleId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")}, default=None)
    faUserId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")}, default=None)

@dataclass
class CombinumbersPayloadSchema:
    faOrganizationId: int  = field(metadata={"validate": marshmallow.validate.Range(min=1, error="field must not be empty and ID cannot be zero (0)")}, default=None)
    faRootOrganizationId: int = field(metadata={"validate": marshmallow.validate.Range(min=1, error="field must not be empty and ID cannot be zero (0)")}, default=None)
    combiNumbers: list = field(metadata={"validate": marshmallow.validate.Length(min=1, error="Combinumbers list cannot be empty.")}, default=None)