"""HTTP request and response schemas."""

from pydantic import Field

from backend.app.models import ActionItem, DomainModel, Incident, Project


class ProjectCreate(DomainModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    repository_path: str = Field(min_length=1, max_length=4096)


class ProjectResponse(Project):
    pass


class IncidentCreate(DomainModel):
    project_id: str | None = None
    source_text: str = Field(min_length=1, max_length=1_000_000)
    source_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)


class IncidentResponse(Incident):
    pass


class HealthResponse(DomainModel):
    status: str
    service: str
    version: str


class ActionItemResponse(ActionItem):
    pass
