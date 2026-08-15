import uvicorn


def main() -> None:
    uvicorn.run(
        "lumi_api.production_app:create_production_app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        factory=True,
    )
