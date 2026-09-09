"""FastAPI application factory and Day 1 HTTP surface."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.llm.mock import MockLLMProvider
from backend.app.schemas import (
    HealthResponse,
    IncidentCreate,
    IncidentResponse,
    ProjectCreate,
    ProjectResponse,
)
from backend.app.services import IncidentService, InMemoryStore, ProjectService
from backend.app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    store = InMemoryStore()
    provider = MockLLMProvider()
    project_service = ProjectService(store, resolved_settings.workspace_root)
    incident_service = IncidentService(store, provider)

    app = FastAPI(title=resolved_settings.app_name, version=resolved_settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", service=resolved_settings.app_name, version=resolved_settings.app_version
        )

    @api.post("/projects", response_model=ProjectResponse, status_code=201, tags=["projects"])
    def create_project(request: ProjectCreate) -> ProjectResponse:
        return ProjectResponse.model_validate(project_service.create(request).model_dump())

    @api.post("/incidents", response_model=IncidentResponse, status_code=201, tags=["incidents"])
    def create_incident(request: IncidentCreate) -> IncidentResponse:
        return IncidentResponse.model_validate(incident_service.create(request).model_dump())

    app.include_router(api)
    return app


app = create_app()
