from lumi_api.assets.router import create_asset_storage_router
from lumi_api.assets.runtime import build_asset_storage_runtime
from lumi_api.project_app import app, session_factory, settings

asset_runtime = build_asset_storage_runtime(settings=settings, session_factory=session_factory)
app.title = "LUMI Asset Storage Runtime"
app.include_router(create_asset_storage_router(asset_runtime))
