from __future__ import annotations


class SkillRegistryError(RuntimeError):
    code = "SKILL_REGISTRY_ERROR"


class SkillDefinitionInvalidError(SkillRegistryError):
    code = "SKILL_DEFINITION_INVALID"


class SkillNotFoundError(SkillRegistryError):
    code = "SKILL_NOT_FOUND"


class SkillVersionResolutionError(SkillRegistryError):
    code = "SKILL_VERSION_RESOLUTION_FAILED"


class SkillReleaseError(SkillRegistryError):
    code = "SKILL_RELEASE_INVALID"


class SkillDependencyCycleError(SkillRegistryError):
    code = "SKILL_DEPENDENCY_CYCLE"


class SkillDependencyConflictError(SkillRegistryError):
    code = "SKILL_DEPENDENCY_CONFLICT"


class SkillCompatibilityError(SkillRegistryError):
    code = "SKILL_AGENT_INCOMPATIBLE"


class SkillPermissionError(SkillRegistryError):
    code = "SKILL_PERMISSION_ESCALATION"


class SkillCapabilityError(SkillRegistryError):
    code = "SKILL_CAPABILITY_UNAVAILABLE"


class SkillSelectionError(SkillRegistryError):
    code = "SKILL_SELECTION_FAILED"
