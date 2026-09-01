from __future__ import annotations


class GenerationControlPlaneError(RuntimeError):
    code = "GENERATION_CONTROL_PLANE_ERROR"


class GenerationInvalid(GenerationControlPlaneError):
    code = "GENERATION_REQUEST_INVALID"


class GenerationConflict(GenerationControlPlaneError):
    code = "GENERATION_CONFLICT"


class GenerationNotFound(GenerationControlPlaneError):
    code = "GENERATION_NOT_FOUND_OR_FORBIDDEN"
