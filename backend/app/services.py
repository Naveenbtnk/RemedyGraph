"""Day 1 application services."""

import hashlib
import re
from pathlib import Path

from fastapi import HTTPException, status

from backend.app.ids import stable_id
from backend.app.llm.base import GenerationRequest, StructuredGenerationProvider
from backend.app.models import ActionExtraction, ActionItem, Incident, Project
from backend.app.schemas import IncidentCreate, ProjectCreate


class InMemoryStore:
    """Small Day 1 store; persistence is intentionally deferred to Day 3."""

    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.incidents: dict[str, Incident] = {}


class ProjectService:
    def __init__(self, store: InMemoryStore, workspace_root: Path) -> None:
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
        self.store.projects[project.id] = project
        return project


class IncidentService:
    def __init__(
        self,
        store: InMemoryStore,
        provider: StructuredGenerationProvider[ActionExtraction],
    ) -> None:
        self.store = store
        self.provider = provider

    def create(self, request: IncidentCreate) -> Incident:
        if request.project_id is not None and request.project_id not in self.store.projects:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        incident_id = stable_id("incident", request.source_text)
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
        title = request.title or self._title(request.source_text)
        incident = Incident(
            id=incident_id,
            project_id=request.project_id,
            title=title,
            summary=self._summary(request.source_text),
            affected_services=self._affected_services(request.source_text),
            source_name=request.source_name,
            source_text_hash=hashlib.sha256(request.source_text.encode("utf-8")).hexdigest(),
            actions=actions,
        )
        self.store.incidents[incident.id] = incident
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
