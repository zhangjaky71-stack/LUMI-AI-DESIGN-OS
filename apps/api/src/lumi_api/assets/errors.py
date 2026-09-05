from __future__ import annotations


class AssetStorageError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class AssetNotFound(AssetStorageError):
    def __init__(self) -> None:
        super().__init__("ASSET_NOT_FOUND_OR_FORBIDDEN", "asset not found")


class UploadSessionNotFound(AssetStorageError):
    def __init__(self) -> None:
        super().__init__("UPLOAD_SESSION_NOT_FOUND_OR_FORBIDDEN", "upload session not found")


class AssetStorageConflict(AssetStorageError):
    pass


class AssetStorageInvalid(AssetStorageError):
    pass
