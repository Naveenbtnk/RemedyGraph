"""FastAPI application factory and HTTP routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.audit.budget import BudgetExceeded
from backend.app.audit.workflow import AuditWorkflow
from backend.app.guards.contracts import GuardExecution, GuardSpec
from backend.app.guards.runner import GuardSafetyError
from backend.app.guards.service import GuardService
from backend.app.llm.mock import MockLLMProvider
from backend.app.schemas import (
    ActionVerdictsResponse,
    AuditRunCreate,
    AuditRunResponse,
    EvidenceGraphResponse,
    EvidenceResponse,
    GuardApprovalRequest,
    GuardExecutionsResponse,
    GuardPreviewsResponse,
    HealthResponse,
    IncidentCreate,
    IncidentResponse,
    ProjectCreate,
    ProjectResponse,
)
from backend.app.services import AuditService, IncidentService, ProjectService
from backend.app.settings import Settings, get_settings
from backend.app.storage import SQLiteStore, StorageBusyError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    store = SQLiteStore(resolved_settings.database_path)
    provider = MockLLMProvider()
    project_service = ProjectService(store, resolved_settings.workspace_root)
    incident_service = IncidentService(store, provider, resolved_settings.max_model_calls)
    audit_workflow = AuditWorkflow(store, resolved_settings)
    audit_service = AuditService(store, audit_workflow)
    guard_service = GuardService(
        store,
        resolved_settings.workspace_root,
        timeout_seconds=resolved_settings.guard_timeout_seconds,
        output_limit=resolved_settings.guard_output_limit,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            store.close()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )

    @app.exception_handler(BudgetExceeded)
    def budget_exceeded(_request: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc), "failure_code": exc.failure_code.value},
        )

    @app.exception_handler(StorageBusyError)
    def storage_busy(_request: Request, exc: StorageBusyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc), "failure_code": exc.failure_code},
        )

    @app.exception_handler(GuardSafetyError)
    def guard_safety_error(_request: Request, exc: GuardSafetyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc), "failure_code": "guard_safety_violation"},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
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

    @api.post("/runs", response_model=AuditRunResponse, status_code=201, tags=["audits"])
    def create_run(request: AuditRunCreate) -> AuditRunResponse:
        return AuditRunResponse.model_validate(audit_service.start(request).model_dump())

    @api.get("/runs/{run_id}", response_model=AuditRunResponse, tags=["audits"])
    def get_run(run_id: str) -> AuditRunResponse:
        return AuditRunResponse.model_validate(audit_service.state(run_id).summary.model_dump())

    @api.get("/runs/{run_id}/actions", response_model=ActionVerdictsResponse, tags=["audits"])
    def get_run_actions(run_id: str) -> ActionVerdictsResponse:
        return ActionVerdictsResponse(verdicts=audit_service.state(run_id).verdicts)

    @api.get("/runs/{run_id}/evidence", response_model=EvidenceResponse, tags=["audits"])
    def get_run_evidence(run_id: str) -> EvidenceResponse:
        return EvidenceResponse(evidence=audit_service.state(run_id).evidence)

    @api.get("/runs/{run_id}/graph", response_model=EvidenceGraphResponse, tags=["audits"])
    def get_run_graph(run_id: str) -> EvidenceGraphResponse:
        state = audit_service.state(run_id)
        return EvidenceGraphResponse(nodes=state.graph_nodes, edges=state.graph_edges)

    @api.post(
        "/runs/{run_id}/guards/preview",
        response_model=GuardPreviewsResponse,
        tags=["guards"],
    )
    def preview_guards(run_id: str) -> GuardPreviewsResponse:
        return GuardPreviewsResponse(guards=guard_service.preview(run_id))

    @api.get("/runs/{run_id}/guards", response_model=GuardPreviewsResponse, tags=["guards"])
    def list_guards(run_id: str) -> GuardPreviewsResponse:
        return GuardPreviewsResponse(guards=guard_service.list_guards(run_id))

    @api.post(
        "/runs/{run_id}/guards/{guard_id}/approve",
        response_model=GuardSpec,
        tags=["guards"],
    )
    def approve_guard(run_id: str, guard_id: str, request: GuardApprovalRequest) -> GuardSpec:
        return guard_service.decide(
            run_id,
            guard_id,
            approved=request.approved,
            preview_sha256=request.preview_sha256,
        )

    @api.post(
        "/runs/{run_id}/guards/{guard_id}/execute",
        response_model=GuardExecution,
        tags=["guards"],
    )
    def execute_guard(run_id: str, guard_id: str) -> GuardExecution:
        return guard_service.execute(run_id, guard_id)

    @api.get(
        "/runs/{run_id}/guards/{guard_id}/executions",
        response_model=GuardExecutionsResponse,
        tags=["guards"],
    )
    def list_guard_executions(run_id: str, guard_id: str) -> GuardExecutionsResponse:
        return GuardExecutionsResponse(executions=guard_service.executions(run_id, guard_id))

    app.include_router(api)
    app.state.store = store
    app.state.audit_workflow = audit_workflow
    app.state.guard_service = guard_service
    return app


app = create_app()
