from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"missing NODE-53 invariants: {missing}")


def forbid(text: str, *needles: str) -> None:
    found = [needle for needle in needles if needle in text]
    if found:
        raise AssertionError(f"forbidden NODE-53 patterns found: {found}")


def main() -> None:
    api = read("apps/web/src/lib/projects/api.ts")
    require(
        api,
        'const PROJECTS_PATH = "/api/v1/projects"',
        "serverApiRequest<unknown>",
        '"Idempotency-Key"',
        "parseProjectCollection",
        "parseProjectDetail",
    )

    types = read("apps/web/src/lib/projects/types.ts")
    require(
        types,
        "ProjectSummary",
        "ProjectBrief",
        "CreateProjectInput",
        "parseProjectCollection",
        "created_at",
        "target_audience",
    )

    actions = read("apps/web/src/app/(shell)/projects/actions.ts")
    require(
        actions,
        '"use server"',
        "createProjectAction",
        "operationId",
        "validate(input, operationId)",
        "redirect(`/projects/",
    )

    dashboard = read("apps/web/src/app/(shell)/projects/dashboard/page.tsx")
    require(
        dashboard,
        "await listProjects()",
        'href="/projects/new"',
        'role="search"',
        "No matching projects",
    )
    forbid(dashboard, "MOCK_PROJECT", "mockProjects", "fakeProjects")

    project_form = read("apps/web/src/components/projects/new-project-form.tsx")
    require(
        project_form,
        "useActionState",
        'name="operationId"',
        'role="alert"',
        "aria-invalid",
        "useFormStatus",
    )
    forbid(project_form.lower(), "localstorage", "sessionstorage")

    detail = read("apps/web/src/app/(shell)/projects/[projectId]/page.tsx")
    require(
        detail,
        "await getProject(projectId)",
        "Creative brief",
        "Deliverables",
        "Constraints",
        'href={`/workspace?project=',
    )

    proxy = read("apps/web/src/proxy.ts")
    require(
        proxy,
        'request.nextUrl.pathname !== "/projects"',
        'new URL("/projects/dashboard", request.url)',
        'matcher: ["/projects"]',
    )

    css = read("apps/web/src/app/(shell)/projects/projects.css")
    require(
        css,
        ".project-grid",
        ".project-form",
        ".field-control[aria-invalid=\"true\"]",
        "@media (max-width: 760px)",
    )

    source = "\n".join(
        read(path)
        for path in (
            "apps/web/src/lib/projects/api.ts",
            "apps/web/src/lib/projects/types.ts",
            "apps/web/src/app/(shell)/projects/actions.ts",
            "apps/web/src/components/projects/new-project-form.tsx",
            "apps/web/src/app/(shell)/projects/dashboard/page.tsx",
            "apps/web/src/app/(shell)/projects/[projectId]/page.tsx",
        )
    ).lower()
    forbid(source, "localstorage", "sessionstorage", "document.cookie")

    print("NODE53_PROJECTS_UI_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
