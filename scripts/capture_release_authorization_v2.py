#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_PR = 135
EXPECTED_BASE_REF = "node-73-final-acceptance-release"
EXPECTED_HEAD_REF = "release-closure-p0"
POLICY_KIND = "LUMI_RELEASE_APPROVAL_POLICY_V2"
REQUEST_KIND = "LUMI_RELEASE_AUTHORIZATION_REQUEST_V2"
AUTHORIZATION_KIND = "LUMI_RELEASE_AUTHORIZATION_V2"
ROLES = ("product", "engineering", "security", "operations", "release_owner")
HANDOFF_KEYS = {
    "on_call_owner",
    "support_owner",
    "incident_commander_rotation",
    "first_day_watch_owner",
    "quality_cost_review_owner",
    "security_dependency_review_owner",
    "dr_drill_owner",
    "capacity_review_owner",
}
MANDATORY_SOD = {
    tuple(sorted(("engineering", "security"))),
    tuple(sorted(("security", "release_owner"))),
}
DECISIVE_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class ReleaseAuthorizationV2Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseAuthorizationV2Error(message)


def present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def normalize_sha(value: object, *, label: str) -> str:
    require(isinstance(value, str) and bool(SHA40.fullmatch(value.lower())), f"{label} must be exact SHA40")
    return value.lower()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseAuthorizationV2Error(f"unable to read JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def repo_file(raw: object, *, prefixes: tuple[str, ...]) -> Path:
    require(present(raw), "repository file path is missing/PENDING")
    path = (ROOT / str(raw)).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ReleaseAuthorizationV2Error(f"path escapes repository: {raw}") from exc
    require(any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in prefixes), f"path outside allowed roots: {raw}")
    require(path.is_file(), f"required file missing: {raw}")
    return path


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ReleaseAuthorizationV2Error(f"path escapes repository: {path}") from exc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(path: Path) -> dict[str, str]:
    return {"path": relative(path), "sha256": digest(path)}


def verify_ref(ref: object, *, label: str, prefixes: tuple[str, ...]) -> Path:
    require(isinstance(ref, Mapping), f"{label} must be an object")
    path = repo_file(ref.get("path"), prefixes=prefixes)
    expected = ref.get("sha256")
    require(isinstance(expected, str) and bool(SHA256.fullmatch(expected.lower())), f"{label}.sha256 must be SHA-256")
    require(digest(path) == expected.lower(), f"{label} SHA-256 mismatch")
    return path


def source_rc(payload: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = payload.get("source_release_candidate")
    if not isinstance(value, Mapping):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def validate_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    require(payload.get("schema_version") == 2, "approval policy schema_version must be 2")
    require(payload.get("kind") == POLICY_KIND, "approval policy kind mismatch")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "approval policy repository mismatch")
    require(payload.get("pull_request") == EXPECTED_PR, "approval policy pull request mismatch")
    require(payload.get("base_ref") == EXPECTED_BASE_REF, "approval policy base_ref mismatch")
    require(payload.get("head_ref") == EXPECTED_HEAD_REF, "approval policy head_ref mismatch")
    minimum = payload.get("minimum_distinct_actors")
    require(isinstance(minimum, int) and not isinstance(minimum, bool) and 3 <= minimum <= len(ROLES), "minimum_distinct_actors must be between 3 and 5")
    require(payload.get("require_human_reviewers") is True, "human reviewers must be required")
    require(payload.get("require_exact_evidence_head_review_commit") is True, "reviews must bind the exact Evidence Head")
    require(payload.get("require_pr_author_exclusion") is True, "PR author exclusion must be required")
    require(payload.get("require_latest_decisive_review") is True, "latest decisive review semantics must be required")

    roles = payload.get("roles")
    require(isinstance(roles, Mapping) and set(roles) == set(ROLES), f"approval roles must equal {sorted(ROLES)}")
    normalized_roles: dict[str, dict[str, list[str]]] = {}
    for role in ROLES:
        value = roles[role]
        require(isinstance(value, Mapping), f"approval role {role} must be an object")
        logins = value.get("allowed_logins")
        require(isinstance(logins, list) and bool(logins), f"approval role {role} allowed_logins must be non-empty")
        normalized: list[str] = []
        for login in logins:
            require(isinstance(login, str) and login.upper() != "PENDING" and bool(LOGIN.fullmatch(login)), f"approval role {role} contains invalid/PENDING login")
            require(not login.endswith("[bot]"), f"approval role {role} cannot use bot reviewer {login}")
            normalized.append(login)
        require(len(normalized) == len(set(normalized)), f"approval role {role} contains duplicate logins")
        normalized_roles[role] = {"allowed_logins": sorted(normalized)}

    sod = payload.get("separation_of_duties")
    require(isinstance(sod, list), "separation_of_duties must be an array")
    normalized_pairs: set[tuple[str, str]] = set()
    for item in sod:
        require(isinstance(item, list) and len(item) == 2, "separation_of_duties entries must contain two roles")
        left, right = item
        require(isinstance(left, str) and isinstance(right, str) and left in ROLES and right in ROLES and left != right, "invalid separation_of_duties role pair")
        normalized_pairs.add(tuple(sorted((left, right))))
    require(MANDATORY_SOD.issubset(normalized_pairs), "mandatory Engineering/Security or Security/Release Owner separation is missing")
    return {
        "schema_version": 2,
        "kind": POLICY_KIND,
        "repository": EXPECTED_REPOSITORY,
        "pull_request": EXPECTED_PR,
        "base_ref": EXPECTED_BASE_REF,
        "head_ref": EXPECTED_HEAD_REF,
        "minimum_distinct_actors": minimum,
        "roles": normalized_roles,
        "separation_of_duties": [list(pair) for pair in sorted(normalized_pairs)],
        "require_human_reviewers": True,
        "require_exact_evidence_head_review_commit": True,
        "require_pr_author_exclusion": True,
        "require_latest_decisive_review": True,
    }


def validate_request(payload: Mapping[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    require(payload.get("schema_version") == 2, "authorization request schema_version must be 2")
    require(payload.get("kind") == REQUEST_KIND, "authorization request kind mismatch")
    release_id = payload.get("release_id")
    require(present(release_id) and bool(SAFE_ID.fullmatch(str(release_id))), "authorization request release_id is invalid/PENDING")
    git_sha, version, migration_head = source_rc(payload)
    source_sha = normalize_sha(git_sha, label="authorization request source RC git_sha")
    require(present(version) and present(migration_head), "authorization request source RC version/migration_head missing")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "authorization request repository mismatch")
    require(payload.get("pull_request") == EXPECTED_PR, "authorization request pull request mismatch")
    policy_path = verify_ref(payload.get("approval_policy"), label="approval_policy", prefixes=("reports/final-acceptance/",))
    policy = validate_policy(load_json(policy_path))
    handoff = payload.get("operational_handoff")
    require(isinstance(handoff, Mapping) and set(handoff) == HANDOFF_KEYS, f"operational_handoff must equal {sorted(HANDOFF_KEYS)}")
    normalized_handoff: dict[str, str] = {}
    for key in HANDOFF_KEYS:
        value = handoff.get(key)
        require(present(value), f"operational_handoff.{key} is missing/PENDING")
        normalized_handoff[key] = str(value)
    return ({
        "schema_version": 2,
        "kind": REQUEST_KIND,
        "release_id": str(release_id),
        "source_release_candidate": {
            "git_sha": source_sha,
            "version": str(version),
            "migration_head": str(migration_head),
        },
        "repository": EXPECTED_REPOSITORY,
        "pull_request": EXPECTED_PR,
        "approval_policy": frozen(policy_path),
        "operational_handoff": normalized_handoff,
    }, policy_path, policy)


def review_identity(review: Mapping[str, Any]) -> tuple[str, int]:
    submitted = review.get("submitted_at")
    identifier = review.get("id")
    return str(submitted or ""), int(identifier) if isinstance(identifier, int) else -1


def latest_decisive_reviews(reviews: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for review in sorted(reviews, key=review_identity):
        state = review.get("state")
        user = review.get("user")
        login = user.get("login") if isinstance(user, Mapping) else None
        if state in DECISIVE_REVIEW_STATES and isinstance(login, str):
            latest[login] = review
    return latest


def validate_pr_payload(payload: Mapping[str, Any], *, evidence_head_sha: str) -> dict[str, Any]:
    evidence = normalize_sha(evidence_head_sha, label="Evidence Head SHA")
    require(payload.get("number") == EXPECTED_PR, "GitHub PR number mismatch")
    require(payload.get("state") == "open", "release authorization requires PR #135 to remain open")
    head = payload.get("head")
    base = payload.get("base")
    author = payload.get("user")
    require(isinstance(head, Mapping) and isinstance(base, Mapping), "GitHub PR head/base metadata missing")
    require(head.get("ref") == EXPECTED_HEAD_REF, "GitHub PR head ref mismatch")
    require(base.get("ref") == EXPECTED_BASE_REF, "GitHub PR base ref mismatch")
    require(head.get("sha") == evidence, "GitHub PR head SHA does not equal Evidence Head SHA")
    head_repo = head.get("repo")
    require(isinstance(head_repo, Mapping) and head_repo.get("full_name") == EXPECTED_REPOSITORY, "GitHub PR head repository mismatch")
    require(isinstance(author, Mapping) and present(author.get("login")), "GitHub PR author identity missing")
    html_url = payload.get("html_url")
    require(isinstance(html_url, str) and html_url.startswith(f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}"), "GitHub PR canonical URL mismatch")
    return {
        "number": EXPECTED_PR,
        "url": html_url,
        "state": "open",
        "base_ref": EXPECTED_BASE_REF,
        "head_ref": EXPECTED_HEAD_REF,
        "head_sha": evidence,
        "author": str(author["login"]),
    }


def approval_record(review: Mapping[str, Any], *, role: str, actor: str, evidence_head_sha: str) -> dict[str, Any]:
    evidence = normalize_sha(evidence_head_sha, label="Evidence Head SHA")
    identifier = review.get("id")
    url = review.get("html_url")
    submitted = review.get("submitted_at")
    require(isinstance(identifier, int) and identifier > 0, f"GitHub approval review id missing for {role}")
    require(isinstance(url, str) and url.startswith(f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}"), f"GitHub approval review URL invalid for {role}")
    require(present(submitted), f"GitHub approval submitted_at missing for {role}")
    require(review.get("commit_id") == evidence, f"GitHub approval for {role} is not bound to Evidence Head SHA")
    return {
        "status": "APPROVED",
        "actor": actor,
        "review_id": identifier,
        "review_url": url,
        "commit_id": evidence,
        "submitted_at": str(submitted),
    }


def select_role_approvals(policy: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]], *, evidence_head_sha: str, pr_author: str) -> dict[str, dict[str, Any]]:
    evidence = normalize_sha(evidence_head_sha, label="Evidence Head SHA")
    latest = latest_decisive_reviews(reviews)
    approved: dict[str, Mapping[str, Any]] = {}
    for actor, review in latest.items():
        if review.get("state") != "APPROVED" or review.get("commit_id") != evidence:
            continue
        if actor == pr_author or actor.endswith("[bot]"):
            continue
        approved[actor] = review
    candidates: dict[str, list[str]] = {}
    for role in ROLES:
        allowed = policy["roles"][role]["allowed_logins"]
        candidates[role] = sorted(actor for actor in allowed if actor in approved)
        require(bool(candidates[role]), f"no current Evidence-Head APPROVED review is available for role {role}")
    minimum = int(policy["minimum_distinct_actors"])
    sod = {tuple(pair) for pair in policy["separation_of_duties"]}
    assignment: dict[str, str] = {}

    def compatible(role: str, actor: str) -> bool:
        return all(tuple(sorted((role, other_role))) not in sod or actor != other_actor for other_role, other_actor in assignment.items())

    def search(index: int) -> bool:
        if index == len(ROLES):
            return len(set(assignment.values())) >= minimum
        role = ROLES[index]
        for actor in sorted(candidates[role], key=lambda value: (value in assignment.values(), value)):
            if not compatible(role, actor):
                continue
            assignment[role] = actor
            if search(index + 1):
                return True
            assignment.pop(role, None)
        return False

    require(search(0), "GitHub approvals cannot satisfy minimum distinct actors and separation-of-duties policy")
    return {role: approval_record(approved[assignment[role]], role=role, actor=assignment[role], evidence_head_sha=evidence) for role in ROLES}


def build_authorization(request_path: Path, request: Mapping[str, Any], policy_path: Path, policy: Mapping[str, Any], pr_payload: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]], *, evidence_head_sha: str) -> dict[str, Any]:
    evidence = normalize_sha(evidence_head_sha, label="Evidence Head SHA")
    pr = validate_pr_payload(pr_payload, evidence_head_sha=evidence)
    approvals = select_role_approvals(policy, reviews, evidence_head_sha=evidence, pr_author=pr["author"])
    release_id = str(request["release_id"])
    source_sha, version, migration_head = source_rc(request)
    return {
        "schema_version": 2,
        "kind": AUTHORIZATION_KIND,
        "status": "PASS",
        "authorization_id": f"release-auth-v2-{release_id}-{evidence[:12]}",
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "release_id": release_id,
        "source_release_candidate": {
            "git_sha": str(source_sha),
            "version": str(version),
            "migration_head": str(migration_head),
        },
        "evidence_head_sha": evidence,
        "repository": EXPECTED_REPOSITORY,
        "pull_request": pr,
        "request_ref": frozen(request_path),
        "approval_policy": frozen(policy_path),
        "distinct_approver_count": len({item["actor"] for item in approvals.values()}),
        "approvals": approvals,
        "operational_handoff": dict(request["operational_handoff"]),
    }


def validate_authorization_report(report: Mapping[str, Any], *, expected_release_id: str | None = None, expected_source_rc: tuple[Any, Any, Any] | None = None, expected_evidence_head_sha: str | None = None) -> dict[str, Any]:
    require(report.get("schema_version") == 2, "authorization report schema_version must be 2")
    require(report.get("kind") == AUTHORIZATION_KIND, "authorization report kind mismatch")
    require(report.get("status") == "PASS", "authorization report status must be PASS")
    require(report.get("repository") == EXPECTED_REPOSITORY, "authorization report repository mismatch")
    release_id = report.get("release_id")
    require(present(release_id) and bool(SAFE_ID.fullmatch(str(release_id))), "authorization report release_id invalid")
    if expected_release_id is not None:
        require(release_id == expected_release_id, "authorization report release_id mismatch")
    source_value = source_rc(report)
    source_sha = normalize_sha(source_value[0], label="authorization report Source RC SHA")
    require(present(source_value[1]) and present(source_value[2]), "authorization report Source RC version/migration missing")
    if expected_source_rc is not None:
        require(source_value == expected_source_rc, "authorization report Source RC identity mismatch")
    evidence = normalize_sha(report.get("evidence_head_sha"), label="authorization report Evidence Head SHA")
    if expected_evidence_head_sha is not None:
        require(evidence == normalize_sha(expected_evidence_head_sha, label="expected Evidence Head SHA"), "authorization report Evidence Head mismatch")
    request_path = verify_ref(report.get("request_ref"), label="authorization request_ref", prefixes=("reports/final-acceptance/",))
    request, policy_path, policy = validate_request(load_json(request_path))
    require(request.get("release_id") == release_id and source_rc(request) == source_value, "authorization request release/Source RC mismatch")
    require(report.get("approval_policy") == frozen(policy_path), "authorization report approval policy ref mismatch")
    pr = report.get("pull_request")
    require(isinstance(pr, Mapping) and pr.get("head_sha") == evidence and pr.get("number") == EXPECTED_PR, "authorization report PR/Evidence Head mismatch")
    author = pr.get("author")
    require(present(author), "authorization report PR author missing")
    approvals = report.get("approvals")
    require(isinstance(approvals, Mapping) and set(approvals) == set(ROLES), f"authorization approvals must equal {sorted(ROLES)}")
    selected: dict[str, str] = {}
    for role in ROLES:
        item = approvals[role]
        require(isinstance(item, Mapping) and item.get("status") == "APPROVED", f"authorization role {role} is not APPROVED")
        actor = item.get("actor")
        require(isinstance(actor, str) and actor in policy["roles"][role]["allowed_logins"], f"authorization actor is not allowed for role {role}")
        require(actor != author and not actor.endswith("[bot]"), f"authorization role {role} must be approved by a non-author human")
        require(isinstance(item.get("review_id"), int) and item["review_id"] > 0, f"authorization role {role} review_id invalid")
        require(item.get("commit_id") == evidence, f"authorization role {role} review is not Evidence-Head-bound")
        require(present(item.get("submitted_at")), f"authorization role {role} submitted_at missing")
        selected[role] = actor
    require(len(set(selected.values())) >= int(policy["minimum_distinct_actors"]), "authorization does not satisfy minimum distinct actors")
    for left, right in policy["separation_of_duties"]:
        require(selected[left] != selected[right], f"authorization violates separation of duties: {left}/{right}")
    require(report.get("distinct_approver_count") == len(set(selected.values())), "authorization distinct_approver_count mismatch")
    require(report.get("operational_handoff") == request.get("operational_handoff"), "authorization operational handoff differs from request")
    return {
        "status": "PASS",
        "release_id": str(release_id),
        "source_release_candidate": {
            "git_sha": source_sha,
            "version": str(source_value[1]),
            "migration_head": str(source_value[2]),
        },
        "evidence_head_sha": evidence,
        "approval_statuses": {role: "APPROVED" for role in ROLES},
        "actors": selected,
        "distinct_approver_count": len(set(selected.values())),
        "operational_handoff": dict(request["operational_handoff"]),
        "request_path": request_path,
        "policy_path": policy_path,
    }


def fetch_json(url: str, *, token: str | None, label: str) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "lumi-node73-release-authorization-v2"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ReleaseAuthorizationV2Error(f"{label} failed with HTTP {exc.code}; Pull Requests read permission may be required") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReleaseAuthorizationV2Error(f"{label} failed: {exc}") from exc
    require(isinstance(payload, dict), f"{label} returned non-object JSON")
    return payload


def fetch_reviews(*, token: str | None) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/pulls/{EXPECTED_PR}/reviews?per_page=100&page={page}"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "lumi-node73-release-authorization-v2"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ReleaseAuthorizationV2Error(f"GitHub PR reviews lookup failed with HTTP {exc.code}; Pull Requests read permission may be required") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ReleaseAuthorizationV2Error(f"GitHub PR reviews lookup failed: {exc}") from exc
        require(isinstance(payload, list), "GitHub PR reviews lookup returned non-array JSON")
        reviews.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return reviews
    raise ReleaseAuthorizationV2Error("GitHub PR reviews exceed supported 1000-review safety bound")


def capture(request_path: Path, *, evidence_head_sha: str, token: str | None) -> dict[str, Any]:
    request, policy_path, policy = validate_request(load_json(request_path))
    evidence = normalize_sha(evidence_head_sha, label="Evidence Head SHA")
    pr = fetch_json(f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/pulls/{EXPECTED_PR}", token=token, label="GitHub release PR lookup")
    reviews = fetch_reviews(token=token)
    report = build_authorization(request_path, request, policy_path, policy, pr, reviews, evidence_head_sha=evidence)
    validate_authorization_report(report, expected_release_id=str(request["release_id"]), expected_source_rc=source_rc(request), expected_evidence_head_sha=evidence)
    return report


def self_test() -> dict[str, Any]:
    parent = ROOT / "reports" / "final-acceptance"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="_auth-v2-", dir=parent) as temp_raw:
        temp = Path(temp_raw)
        source_sha = "a" * 40
        evidence_sha = "b" * 40
        policy_path = temp / "approval-policy-v2.json"
        policy = {
            "schema_version": 2,
            "kind": POLICY_KIND,
            "repository": EXPECTED_REPOSITORY,
            "pull_request": EXPECTED_PR,
            "base_ref": EXPECTED_BASE_REF,
            "head_ref": EXPECTED_HEAD_REF,
            "minimum_distinct_actors": 3,
            "roles": {
                "product": {"allowed_logins": ["alice"]},
                "engineering": {"allowed_logins": ["bob"]},
                "security": {"allowed_logins": ["carol"]},
                "operations": {"allowed_logins": ["alice", "dave"]},
                "release_owner": {"allowed_logins": ["dave"]},
            },
            "separation_of_duties": [["engineering", "security"], ["security", "release_owner"]],
            "require_human_reviewers": True,
            "require_exact_evidence_head_review_commit": True,
            "require_pr_author_exclusion": True,
            "require_latest_decisive_review": True,
        }
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        request_path = temp / "authorization-request-v2.json"
        handoff = {key: f"owner-{index}" for index, key in enumerate(sorted(HANDOFF_KEYS), start=1)}
        request = {
            "schema_version": 2,
            "kind": REQUEST_KIND,
            "release_id": "rc-auth-v2-selftest",
            "source_release_candidate": {"git_sha": source_sha, "version": "1.0.0-rc", "migration_head": "0020"},
            "repository": EXPECTED_REPOSITORY,
            "pull_request": EXPECTED_PR,
            "approval_policy": frozen(policy_path),
            "operational_handoff": handoff,
        }
        request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        normalized_request, normalized_policy_path, normalized_policy = validate_request(request)
        pr = {"number": EXPECTED_PR, "state": "open", "html_url": f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}", "user": {"login": "pr-author"}, "head": {"ref": EXPECTED_HEAD_REF, "sha": evidence_sha, "repo": {"full_name": EXPECTED_REPOSITORY}}, "base": {"ref": EXPECTED_BASE_REF}}
        reviews = [{"id": index, "state": "APPROVED", "html_url": f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}#pullrequestreview-{index}", "commit_id": evidence_sha, "submitted_at": f"2026-08-20T00:0{index}:00Z", "user": {"login": actor}} for index, actor in enumerate(("alice", "bob", "carol", "dave"), start=1)]
        report = build_authorization(request_path, normalized_request, normalized_policy_path, normalized_policy, pr, reviews, evidence_head_sha=evidence_sha)
        clean = validate_authorization_report(report, expected_release_id="rc-auth-v2-selftest", expected_source_rc=(source_sha, "1.0.0-rc", "0020"), expected_evidence_head_sha=evidence_sha)
        require(clean["source_release_candidate"]["git_sha"] != clean["evidence_head_sha"], "clean fixture must prove Source RC and Evidence Head may differ")
        mutations = []
        wrong_head = json.loads(json.dumps(report)); wrong_head["evidence_head_sha"] = "c" * 40; mutations.append(wrong_head)
        wrong_source = json.loads(json.dumps(report)); wrong_source["source_release_candidate"]["git_sha"] = "c" * 40; mutations.append(wrong_source)
        wrong_commit = json.loads(json.dumps(report)); wrong_commit["approvals"]["security"]["commit_id"] = source_sha; mutations.append(wrong_commit)
        bot = json.loads(json.dumps(report)); bot["approvals"]["security"]["actor"] = "robot[bot]"; mutations.append(bot)
        pr_swap = json.loads(json.dumps(report)); pr_swap["pull_request"]["head_sha"] = source_sha; mutations.append(pr_swap)
        status = json.loads(json.dumps(report)); status["status"] = "PENDING"; mutations.append(status)
        blocked = 0
        for item in mutations:
            try:
                validate_authorization_report(item, expected_release_id="rc-auth-v2-selftest", expected_source_rc=(source_sha, "1.0.0-rc", "0020"), expected_evidence_head_sha=evidence_sha)
            except ReleaseAuthorizationV2Error:
                blocked += 1
                continue
            raise ReleaseAuthorizationV2Error("negative V2 authorization drill did not block")
        return {"status": "PASS", "negative_drills": blocked, "clean_distinct_approvers": clean["distinct_approver_count"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture NODE-73 non-cyclic GitHub authorization for Evidence Head")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--evidence-head-sha")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            print(json.dumps(self_test(), indent=2, sort_keys=True))
            return 0
        require(args.request is not None and args.output is not None and args.evidence_head_sha is not None, "--request, --evidence-head-sha and --output are required")
        token = os.environ.get("RELEASE_APPROVAL_TOKEN")
        require(bool(token), "RELEASE_APPROVAL_TOKEN is required")
        report = capture(args.request.resolve(), evidence_head_sha=args.evidence_head_sha, token=token)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "release_id": report["release_id"], "evidence_head_sha": report["evidence_head_sha"], "distinct_approver_count": report["distinct_approver_count"]}, sort_keys=True))
        return 0
    except (ReleaseAuthorizationV2Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release authorization V2 blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
