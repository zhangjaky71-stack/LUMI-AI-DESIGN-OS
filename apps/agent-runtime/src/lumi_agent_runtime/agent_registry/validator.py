from __future__ import annotations

import re
from typing import Protocol

from .definition import AgentDefinition
from .dependencies import DependencyResolver
from .errors import AgentDependencyError, AgentPromptPolicyError
from .provenance import ResolvedDependency

_TEMPLATE_MARKERS = ("{{", "}}", "{%", "%}", "${", "<script")
_SECRET_PATTERN = re.compile(
    r"(?i)(authorization\s*:\s*bearer|api[_-]?key\s*[:=]|begin\s+(?:rsa\s+)?private\s+key)"
)


class AgentSkillPolicy(Protocol):
    def validate(self, definition: AgentDefinition) -> None: ...


class StaticSystemPromptLinter:
    def lint(self, prompt: str) -> None:
        lower = prompt.lower()
        for marker in _TEMPLATE_MARKERS:
            if marker in lower:
                raise AgentPromptPolicyError(
                    f"dynamic template marker forbidden in system prompt: {marker}"
                )
        if "\x00" in prompt:
            raise AgentPromptPolicyError("NUL forbidden in system prompt")
        if _SECRET_PATTERN.search(prompt):
            raise AgentPromptPolicyError("secret-like material forbidden in system prompt")


class AgentValidator:
    def __init__(
        self,
        *,
        dependencies: DependencyResolver,
        prompt_linter: StaticSystemPromptLinter | None = None,
        skill_policy: AgentSkillPolicy | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.prompt_linter = prompt_linter or StaticSystemPromptLinter()
        self.skill_policy = skill_policy

    def validate(self, definition: AgentDefinition) -> tuple[ResolvedDependency, ...]:
        self.prompt_linter.lint(definition.system_prompt)
        if self.skill_policy is not None:
            self.skill_policy.validate(definition)
        try:
            return self.dependencies.resolve(definition)
        except AgentDependencyError:
            raise
        except Exception as exc:
            raise AgentDependencyError(
                f"dependency validation failed for {definition.identity}"
            ) from exc
