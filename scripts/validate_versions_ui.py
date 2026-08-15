from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/web/src/app/app/projects/[projectId]/versions/page.tsx",
    "apps/web/src/components/versions-ui/versions-ui.tsx",
    "apps/web/src/components/versions-ui/versions-ui.module.css",
    "apps/web/src/lib/versions-ui/types.ts",
    "apps/web/src/lib/versions-ui/contracts.ts",
    "apps/web/src/lib/versions-ui/versions-server.ts",
    "apps/web/src/lib/versions-ui/versions-gateway.ts",
    "apps/web/src/lib/versions-ui/contracts.test.ts",
    "apps/web/src/lib/versions-ui/versions-gateway.test.ts",
    "apps/web/e2e/versions-ui.spec.ts",
    "docs/runtime/VERSIONS-UI-V1.md",
    "reports/nodes/NODE-59/acceptance.md",
    ".github/workflows/versions-ui.yml",
]


def text(path: str) -> str:
    full = ROOT / path
    if not full.exists():
        raise AssertionError(f"missing required file: {path}")
    return full.read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"missing {label}: {needle}")


def forbid(haystack: str, needle: str, label: str) -> None:
    if needle in haystack:
        raise AssertionError(f"forbidden {label}: {needle}")


def main() -> None:
    for path in REQUIRED:
        text(path)

    tsconfig = text("apps/web/tsconfig.json")
    gateway = text("apps/web/src/lib/versions-ui/versions-gateway.ts")
    types = text("apps/web/src/lib/versions-ui/types.ts")
    ui = text("apps/web/src/components/versions-ui/versions-ui.tsx")
    server = text("apps/web/src/lib/versions-ui/versions-server.ts")
    e2e = text("apps/web/e2e/versions-ui.spec.ts")
    project_page = text("apps/web/src/app/app/projects/[projectId]/page.tsx")

    require(tsconfig, '"@lumi/artifact-sdk"', "canonical Artifact SDK alias")
    require(gateway, 'from "@lumi/artifact-sdk"', "canonical Artifact SDK import")
    require(gateway, "new ArtifactEngine()", "NODE-42 ArtifactEngine use")
    require(gateway, "branch.head_version_id !== safe.expected_head_version_id", "pre-restore CAS check")
    require(gateway, "this.#engine.restore(", "canonical restore runtime")
    require(gateway, 'kind: "INFO"', "restore/fork notice")
    require(gateway, "this.#engine.addBranch(branch)", "canonical fork branch")
    require(gateway, "exact: true as const", "exact compare identity")
    require(gateway, "PROVENANCE_FORBIDDEN", "provenance authorization boundary")
    require(gateway, "Your current compare targets were not changed", "concurrent head does not retarget compare")
    require(ui, "恢复会创建一个新的 DRAFT", "restore append-only explanation")
    require(ui, "No raw system prompt or chain-of-thought", "safe provenance copy")
    require(ui, "SIDE_BY_SIDE", "side-by-side compare")
    require(ui, "OVERLAY", "overlay compare")
    require(ui, "WIPE", "wipe compare")
    require(server, 'type: "DESIGN_DOCUMENT"', "Design IR fixture")
    require(server, 'type: "RASTER_IMAGE"', "Raster fixture")
    require(types, "SafeVersionProvenance", "safe provenance model")
    require(project_page, "/versions", "project Versions entry")

    combined = "\n".join([gateway, types, ui, server])
    for durable in ("localStorage", "sessionStorage", "indexedDB"):
        forbid(combined, durable, "browser canonical storage")
    for private_field in ("chain_of_thought:", "system_prompt:", "raw_tool_payload:", "raw_prompt:"):
        forbid(combined, private_field, "private execution field")

    for marker in (
        "restores v2 by appending DRAFT v5",
        "forks an exact historical version",
        "concurrent newer head",
        "raster side-by-side and wipe",
        "provenance permission restrictions",
    ):
        require(e2e, marker, "browser coverage")

    unit = text("apps/web/src/lib/versions-ui/versions-gateway.test.ts")
    require(unit, "BRANCH_HEAD_CONFLICT", "stale-head unit coverage")
    require(unit, 'type === "DERIVED_FROM"', "restore lineage unit coverage")
    require(unit, 'status).toBe("APPROVED")', "approved immutability unit coverage")

    print("NODE-59 Versions UI static architecture validation: PASS")


if __name__ == "__main__":
    main()
