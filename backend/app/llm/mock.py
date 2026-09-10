"""A deterministic, network-free provider for local development and tests."""

import re

from backend.app.llm.base import GenerationRequest
from backend.app.models import ActionExtraction, ExtractedAction


class MockLLMProvider:
    provider_name = "mock"

    _ACTION_TASK = "extract_actions"
    _ACTION_PREFIX = re.compile(r"^\s*(?:[-*+] |\d+[.)] )")
    _ACTION_VERB = re.compile(
        r"\b(add|alert|bound|configure|confirm|create|decrease|define|document|enable|enforce|gate|"
        r"increase|implement|limit|prove|reduce|remove|route|set|test|use|validate)\b",
        re.IGNORECASE,
    )
    _SPLIT = re.compile(
        r"\s*(?:;|\s+(?:and|&)\s+)(?=(?:add|alert|bound|configure|confirm|create|decrease|define|"
        r"document|enable|enforce|gate|increase|implement|limit|prove|reduce|remove|route|set|test|"
        r"use|validate)\b)",
        re.IGNORECASE,
    )

    def generate(
        self, request: GenerationRequest, output_model: type[ActionExtraction]
    ) -> ActionExtraction:
        if request.task != self._ACTION_TASK:
            raise ValueError(f"mock provider does not support task: {request.task}")
        if output_model is not ActionExtraction:
            raise ValueError(f"mock provider does not support output: {output_model.__name__}")

        actions: list[ExtractedAction] = []
        current_section: str | None = None
        for line_number, raw_line in enumerate(request.input_text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                current_section = stripped.lstrip("#").strip() or None
                continue
            if not self._ACTION_PREFIX.match(raw_line) or not self._ACTION_VERB.search(stripped):
                continue
            action_text = self._ACTION_PREFIX.sub("", stripped).strip()
            for part in self._SPLIT.split(action_text):
                normalized = part.strip().rstrip(".")
                if normalized:
                    actions.append(
                        ExtractedAction(
                            text=normalized,
                            source_line=line_number,
                            source_section=current_section,
                        )
                    )
                    if len(actions) >= request.max_output_items:
                        return ActionExtraction(actions=actions)
        return ActionExtraction(actions=actions)
