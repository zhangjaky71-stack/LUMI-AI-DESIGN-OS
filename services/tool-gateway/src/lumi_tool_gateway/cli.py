from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port_raw = os.getenv("LUMI_TOOL_GATEWAY_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError("TOOL_GATEWAY_PORT_INVALID") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("TOOL_GATEWAY_PORT_INVALID")
    uvicorn.run(
        "lumi_tool_gateway.service:create_runtime_app",
        factory=True,
        host="0.0.0.0",
        port=port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
