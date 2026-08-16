from __future__ import annotations

import os

from .errors import SecretUnavailable


class EnvironmentSecretProvider:
    """Gateway-only environment binding. Never pass the returned value into request/result objects."""

    DEFAULT_NAMES = {
        ("openai", "api_key"): "OPENAI_API_KEY",
        ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    }

    def __init__(self, names: dict[tuple[str, str], str] | None = None) -> None:
        self.names = dict(self.DEFAULT_NAMES)
        if names:
            self.names.update(names)

    def get_secret(self, provider: str, name: str) -> str:
        env_name = self.names.get((provider, name))
        if not env_name:
            raise SecretUnavailable(f"no secret binding configured for {provider}:{name}")
        value = os.environ.get(env_name)
        if not value:
            raise SecretUnavailable(f"secret unavailable for {provider}:{name}")
        return value


class MappingSecretProvider:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self._values = dict(values)

    def get_secret(self, provider: str, name: str) -> str:
        try:
            return self._values[(provider, name)]
        except KeyError as exc:
            raise SecretUnavailable(f"secret unavailable for {provider}:{name}") from exc
