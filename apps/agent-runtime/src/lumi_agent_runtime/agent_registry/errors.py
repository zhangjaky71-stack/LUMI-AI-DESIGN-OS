from __future__ import annotations


class AgentRegistryError(RuntimeError):
    """Base error for Agent Registry failures."""


class AgentRegistryNotFoundError(AgentRegistryError):
    pass


class AgentRegistryConflictError(AgentRegistryError):
    pass


class AgentRegistryAliasError(AgentRegistryError):
    pass


class AgentRegistryScopeError(AgentRegistryError):
    pass


class AgentRegistryPublicationError(AgentRegistryError):
    pass
