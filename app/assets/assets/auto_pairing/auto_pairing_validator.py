from dataclasses import field
from marshmallow_dataclass import dataclass
from datetime import datetime
import marshmallow.validate
from typing import List


@dataclass
class Location:
    lat: float = field(default=0.0)
    lon: float = field(default=0.0)


@dataclass
class EventData:
    registeredOn: datetime = field(default=None)
    organizationId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    unitId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    status: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    reason: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    assetId: str = field(default=None)
    candidateAssetIds: list = field(default=None)
    assetVIN: str = field(default=None)
    sensorVIN: str = field(default=None)
    location: Location = field(default=None)

@dataclass
class AutoPairingEventRequest:
    eventType: str = field(default=None)
    eventVersion: int = field(default=None)
    eventData: EventData = field(default=None)

@dataclass
class AutoPairingBatchRequest:
    eventBatchId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    eventSubscriptionId: str = field(metadata={"validate": marshmallow.validate.Length(min=1, error="field must not be empty")},default=None)
    eventBatchTime: datetime = field(default=None)
    eventsData: List[AutoPairingEventRequest] = field(default_factory=list)
