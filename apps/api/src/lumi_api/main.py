from fastapi import FastAPI

from lumi_api.config import get_settings

settings = get_settings()
app = FastAPI(title="LUMI API", version=settings.lumi_version)


def _payload(status: str = "ok") -> dict[str, str]:
    return {"service": "api", "status": status, "version": settings.lumi_version}


@app.get("/health/live", tags=["health"])
def health_live() -> dict[str, str]:
    return _payload()


@app.get("/health/ready", tags=["health"])
def health_ready() -> dict[str, str]:
    # NODE-03 will add real dependency readiness checks.
    return _payload()


@app.get("/version", tags=["meta"])
def version() -> dict[str, str]:
    return _payload()
