"""Provider abstraction used by application services."""

from typing import Generic, Protocol, TypeVar

from backend.app.models import DomainModel

OutputModel = TypeVar("OutputModel", bound=DomainModel)


class GenerationRequest(DomainModel):
    task: str
    input_text: str
    max_output_items: int = 50


class StructuredGenerationProvider(Protocol, Generic[OutputModel]):
    provider_name: str

    def generate(self, request: GenerationRequest, output_model: type[OutputModel]) -> OutputModel:
        """Return validated structured output for a bounded request."""
