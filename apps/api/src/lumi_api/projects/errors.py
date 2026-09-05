from __future__ import annotations


class ProjectApplicationError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class ProjectNotFound(ProjectApplicationError):
    def __init__(self) -> None:
        super().__init__("PROJECT_NOT_FOUND", "project not found")


class ProjectConflict(ProjectApplicationError):
    pass


class ProjectInvalid(ProjectApplicationError):
    pass
