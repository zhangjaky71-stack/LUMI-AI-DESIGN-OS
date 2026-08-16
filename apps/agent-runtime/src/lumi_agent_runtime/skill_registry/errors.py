from __future__ import annotations


class SkillRegistryError(RuntimeError):
    """Base error for Skill Registry failures."""


class SkillRegistryNotFoundError(SkillRegistryError):
    pass


class SkillRegistryConflictError(SkillRegistryError):
    pass


class SkillRegistryEvaluationError(SkillRegistryError):
    pass


class SkillRegistryDependencyError(SkillRegistryError):
    pass


class SkillRegistryPermissionError(SkillRegistryError):
    pass


class SkillRegistryMaterializationError(SkillRegistryError):
    pass


class SkillRegistryPublicationError(SkillRegistryError):
    pass
