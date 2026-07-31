from pydantic import BaseModel, ConfigDict, Field


class LocalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_key: str = Field(min_length=1, max_length=100)


class IdentitySummary(BaseModel):
    user_id: str
    subject: str
    display_name: str
    role: str
    permissions: list[str]
    dataset_ids: list[str]
    issuer: str
    expires_in_seconds: int | None = None


class IdentityAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=120)
    enabled: bool = True
