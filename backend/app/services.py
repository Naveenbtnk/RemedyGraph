"""Application services for persisted projects, incidents, and bounded audits."""

import hashlib
import re
from pathlib import Path

from fastapi import HTTPException, status

from backend.app.audit.contracts import AuditRunCreate, AuditRunSummary, AuditWorkflowState
from backend.app.audit.workflow import AuditWorkflow
from backend.app.ids import stable_id
from backend.app.llm.base import GenerationRequest, StructuredGenerationProvider
from backend.app.models import ActionExtraction, ActionItem, Incident, Project
from backend.app.schemas import IncidentCreate, ProjectCreate
from backend.app.storage import SQLiteStore


class InMemoryStore(SQLiteStore):
    """Backward-compatible in-memory SQLite store used by tests and local defaults."""

    def __init__(self) -> None:
        super().__init__(":memory:")


class ProjectService:
    def __init__(self, store: SQLiteStore, workspace_root: Path) -> None:
        self.store = store
        self.workspace_root = workspace_root.resolve()

    def create(self, request: ProjectCreate) -> Project:
        candidate = Path(request.repository_path).expanduser().resolve()
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="repository_path must be inside the configured workspace root",
            ) from exc
        if not candidate.is_dir():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="repository_path must point to an existing directory",
            )
        project_id = stable_id("project", candidate)
        project = Project(
            id=project_id,
            name=request.name or candidate.name or str(candidate),
            repository_path=str(candidate),
        )
        self.store.save_project(project)
        return project


class IncidentService:
    def __init__(
        self,
        store: SQLiteStore,
        provider: StructuredGenerationProvider[ActionExtraction],
        max_model_calls: int,
    ) -> None:
        self.store = store
        self.provider = provider
        self.max_model_calls = max_model_calls

    def create(self, request: IncidentCreate) -> Incident:
        if request.project_id is not None and self.store.get_project(request.project_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        incident_id = stable_id("incident", request.source_text)
        title = request.title or self._title(request.source_text)
        base_incident = Incident(
            id=incident_id,
            project_id=request.project_id,
            title=title,
            summary=self._summary(request.source_text),
            affected_services=self._affected_services(request.source_text),
            source_name=request.source_name,
            source_text_hash=hashlib.sha256(request.source_text.encode("utf-8")).hexdigest(),
        )
        existing = self.store.get_incident(incident_id)
        if existing is not None and existing.project_id != request.project_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="stable incident already belongs to another project",
            )
        if existing is None:
            self.store.save_incident(base_incident)
        self.store.reserve_incident_model_call(incident_id, self.max_model_calls)
        extraction = self.provider.generate(
            GenerationRequest(task="extract_actions", input_text=request.source_text),
            ActionExtraction,
        )
        actions = [
            ActionItem(
                id=stable_id("action", incident_id, index, action.text),
                incident_id=incident_id,
                text=action.text,
                source_line=action.source_line,
                source_section=action.source_section,
                order=index,
            )
            for index, action in enumerate(extraction.actions)
        ]
        incident = base_incident.model_copy(update={"actions": actions})
        self.store.save_incident(incident)
        return incident

    @staticmethod
    def _title(text: str) -> str:
        for line in text.splitlines():
            if line.strip().startswith("#"):
                return line.lstrip("#").strip() or "Untitled incident"
        return "Untitled incident"

    @staticmethod
    def _summary(text: str) -> str | None:
        for paragraph in re.split(r"\n\s*\n", text.strip()):
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if lines and not lines[0].startswith("#") and not lines[0].startswith(("-", "*")):
                return " ".join(lines)
        return None

    @staticmethod
    def _affected_services(text: str) -> list[str]:
        match = re.search(r"^\s*affected services?\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if not match:
            return []
        return [service.strip() for service in re.split(r",|;", match.group(1)) if service.strip()]


class AuditService:
    def __init__(self, store: SQLiteStore, workflow: AuditWorkflow) -> None:
        self.store = store
        self.workflow = workflow

    def start(self, request: AuditRunCreate) -> AuditRunSummary:
        project = self.store.get_project(request.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        incident = self.store.get_incident(request.incident_id)
        if incident is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")
        if incident.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="incident does not belong to project",
            )
        return self.workflow.run(project, incident).summary

    def state(self, run_id: str) -> AuditWorkflowState:
        state = self.store.load_audit_state(run_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit run not found")
        return state
