from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str
    version: str
    database: Literal["available", "unavailable"]


class CapabilitySet(BaseModel):
    implemented: list[str]
    planned: list[str]


class PlatformInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform_name: str
    application_version: str
    data_policy: str
    clinical_validation_status: str
    capabilities: CapabilitySet
