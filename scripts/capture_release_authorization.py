#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
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
    ("engineering", "security"),
    ("security", "release_owner"),
}
POLICY_KIND = "LUMI_RELEASE_APPROVAL_POLICY_V1"
REQUEST_KIND = "LUMI_RELEASE_AUTHORIZATION_REQUEST_V1"
AUTHORIZATION_KIND = "LUMI_RELEASE_AUTHORIZATION_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
DECISIVE_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}


class ReleaseAuthorizationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseAuthorizationError(message)


def _present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseAuthorizationError(f"unable to read JSON {path}: {exc}") from exc
    _require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def _repo_file(raw: object, *, prefixes: tuple[str, ...]) -> Path:
    _require(_present(raw), "repository file path is missing/PENDING")
    path = (ROOT / str(raw)).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ReleaseAuthorizationError(f"path escapes repository: {raw}") from exc
    _require(any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in prefixes), f"path outside allowed roots: {raw}")
    _require(path.is_file(), f"required file missing: {raw}")
    return path


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ReleaseAuthorizationError(f"path escapes repository: {path}") from exc


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frozen(path: Path) -> dict[str, str]:
    return {"path": _relative(path), "sha256": _digest(path)}


def _verify_ref(ref: object, *, label: str, prefixes: tuple[str, ...]) -> Path:
    _require(isinstance(ref, Mapping), f"{label} must be an object")
    path = _repo_file(ref.get("path"), prefixes=prefixes)
    expected = ref.get("sha256")
    _require(isinstance(expected, str) and bool(SHA256.fullmatch(expected.lower())), f"{label}.sha256 must be SHA-256")
    _require(_digest(path) == expected.lower(), f"{label} SHA-256 mismatch")
    return path


def _rc(payload: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = payload.get("release_candidate")
    if not isinstance(value, Mapping):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def validate_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    _require(payload.get("schema_version") == 1, "approval policy schema_version must be 1")
    _require(payload.get("kind") == POLICY_KIND, "approval policy kind mismatch")
    _require(payload.get("repository") == EXPECTED_REPOSITORY, "approval policy repository mismatch")
    _require(payload.get("pull_request") == EXPECTED_PR, "approval policy pull request mismatch")
    _require(payload.get("base_ref") == EXPECTED_BASE_REF, "approval policy base_ref mismatch")
    _require(payload.get("head_ref") == EXPECTED_HEAD_REF, "approval policy head_ref mismatch")
    minimum = payload.get("minimum_distinct_actors")
    _require(isinstance(minimum, int) and not isinstance(minimum, bool) and 3 <= minimum <= len(ROLES), "approval policy minimum_distinct_actors must be between 3 and 5")
    _require(payload.get("require_human_reviewers") is True, "approval policy must require human reviewers")
    _require(payload.get("require_exact_rc_review_commit") is True, "approval policy must require exact RC review commits")

    roles = payload.get("roles")
    _require(isinstance(roles, Mapping) and set(roles) == set(ROLES), f"approval policy roles must equal {sorted(ROLES)}")
    normalized_roles: dict[str, dict[str, list[str]]] = {}
    for role in ROLES:
        value = roles[role]
        _require(isinstance(value, Mapping), f"approval policy role {role} must be an object")
        logins = value.get("allowed_logins")
        _require(isinstance(logins, list) and bool(logins), f"approval policy role {role} allowed_logins must be non-empty")
        normalized: list[str] = []
        for login in logins:
            _require(isinstance(login, str) and login.upper() != "PENDING" and bool(LOGIN.fullmatch(login)), f"approval policy role {role} contains invalid/PENDING login")
            _require(not login.endswith("[bot]"), f"approval policy role {role} cannot use bot reviewer {login}")
            normalized.append(login)
        _require(len(normalized) == len(set(normalized)), f"approval policy role {role} contains duplicate logins")
        normalized_roles[role] = {"allowed_logins": sorted(normalized)}

    sod = payload.get("separation_of_duties")
    _require(isinstance(sod, list), "approval policy separation_of_duties must be an array")
    normalized_pairs: set[tuple[str, str]] = set()
    for item in sod:
        _require(isinstance(item, list) and len(item) == 2, "approval policy separation_of_duties entries must contain two roles")
        left, right = item
        _require(isinstance(left, str) and isinstance(right, str) and left in ROLES and right in ROLES and left != right, "approval policy separation_of_duties contains invalid role pair")
        normalized_pairs.add(tuple(sorted((left, right))))
    required_pairs = {tuple(sorted(pair)) for pair in MANDATORY_SOD}
    _require(required_pairs.issubset(normalized_pairs), "approval policy is missing mandatory Engineering/Security or Security/Release Owner separation")

    return {
        "schema_version": 1,
        "kind": POLICY_KIND,
        "repository": EXPECTED_REPOSITORY,
        "pull_request": EXPECTED_PR,
        "base_ref": EXPECTED_BASE_REF,
        "head_ref": EXPECTED_HEAD_REF,
        "minimum_distinct_actors": minimum,
        "roles": normalized_roles,
        "separation_of_duties": [list(pair) for pair in sorted(normalized_pairs)],
        "require_human_reviewers": True,
        "require_exact_rc_review_commit": True,
    }


def validate_request(payload: Mapping[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    _require(payload.get("schema_version") == 1, "authorization request schema_version must be 1")
    _require(payload.get("kind") == REQUEST_KIND, "authorization request kind mismatch")
    release_id = payload.get("release_id")
    _require(_present(release_id) and bool(SAFE_ID.fullmatch(str(release_id))), "authorization request release_id is invalid/PENDING")
    git_sha, version, migration_head = _rc(payload)
    _require(isinstance(git_sha, str) and bool(SHA40.fullmatch(git_sha.lower())), "authorization request RC git_sha must be SHA40")
    _require(_present(version) and _present(migration_head), "authorization request RC version/migration_head is missing/PENDING")
    _require(payload.get("repository") == EXPECTED_REPOSITORY, "authorization request repository mismatch")
    _require(payload.get("pull_request") == EXPECTED_PR, "authorization request pull request mismatch")

    policy_path = _verify_ref(
        payload.get("approval_policy"),
        label="approval_policy",
        prefixes=("reports/final-acceptance/",),
    )
    policy = validate_policy(_load_json(policy_path))

    handoff = payload.get("operational_handoff")
    _require(isinstance(handoff, Mapping) and set(handoff) == HANDOFF_KEYS, f"authorization request operational_handoff must equal {sorted(HANDOFF_KEYS)}")
    normalized_handoff: dict[str, str] = {}
    for key in HANDOFF_KEYS:
        value = handoff.get(key)
        _require(_present(value), f"authorization request operational_handoff.{key} is missing/PENDING")
        normalized_handoff[key] = str(value)

    normalized = {
        "schema_version": 1,
        "kind": REQUEST_KIND,
        "release_id": str(release_id),
        "release_candidate": {
            "git_sha": git_sha.lower(),
            "version": str(version),
            "migration_head": str(migration_head),
        },
        "repository": EXPECTED_REPOSITORY,
        "pull_request": EXPECTED_PR,
        "approval_policy": _frozen(policy_path),
        "operational_handoff": normalized_handoff,
    }
    return normalized, policy_path, policy


def validate_pr_payload(payload: Mapping[str, Any], *, expected_sha: str) -> dict[str, Any]:
    _require(payload.get("number") == EXPECTED_PR, "GitHub PR number mismatch")
    _require(payload.get("state") == "open", "release authorization requires the NODE-73 PR to remain open")
    head = payload.get("head")
    base = payload.get("base")
    author = payload.get("user")
    _require(isinstance(head, Mapping) and isinstance(base, Mapping), "GitHub PR head/base metadata missing")
    _require(head.get("ref") == EXPECTED_HEAD_REF, "GitHub PR head ref mismatch")
    _require(base.get("ref") == EXPECTED_BASE_REF, "GitHub PR base ref mismatch")
    head_sha = head.get("sha")
    _require(isinstance(head_sha, str) and head_sha.lower() == expected_sha.lower(), "GitHub PR head SHA does not equal the final RC SHA")
    head_repo = head.get("repo")
    _require(isinstance(head_repo, Mapping) and head_repo.get("full_name") == EXPECTED_REPOSITORY, "GitHub PR head repository mismatch")
    _require(isinstance(author, Mapping) and _present(author.get("login")), "GitHub PR author identity missing")
    html_url = payload.get("html_url")
    _require(isinstance(html_url, str) and html_url.startswith(f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}"), "GitHub PR canonical URL mismatch")
    return {
        "number": EXPECTED_PR,
        "url": html_url,
        "state": "open",
        "base_ref": EXPECTED_BASE_REF,
        "head_ref": EXPECTED_HEAD_REF,
        "head_sha": expected_sha.lower(),
        "author": str(author["login"]),
    }


def _review_identity(review: Mapping[str, Any]) -> tuple[str, int]:
    submitted = review.get("submitted_at")
    identifier = review.get("id")
    return (str(submitted or ""), int(identifier) if isinstance(identifier, int) else -1)


def latest_decisive_reviews(reviews: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for review in sorted(reviews, key=_review_identity):
        state = review.get("state")
        user = review.get("user")
        login = user.get("login") if isinstance(user, Mapping) else None
        if state not in DECISIVE_REVIEW_STATES or not isinstance(login, str):
            continue
        latest[login] = review
    return latest


def _approval_record(review: Mapping[str, Any], *, role: str, actor: str, rc_sha: str) -> dict[str, Any]:
    identifier = review.get("id")
    url = review.get("html_url")
    submitted = review.get("submitted_at")
    commit_id = review.get("commit_id")
    _require(isinstance(identifier, int) and identifier > 0, f"GitHub approval review id missing for {role}")
    _require(isinstance(url, str) and url.startswith(f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}"), f"GitHub approval review URL invalid for {role}")
    _require(_present(submitted), f"GitHub approval submitted_at missing for {role}")
    _require(isinstance(commit_id, str) and commit_id.lower() == rc_sha.lower(), f"GitHub approval for {role} is not bound to the exact RC SHA")
    return {
        "status": "APPROVED",
        "actor": actor,
        "review_id": identifier,
        "review_url": url,
        "commit_id": rc_sha.lower(),
        "submitted_at": str(submitted),
    }


def select_role_approvals(
    policy: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
    *,
    rc_sha: str,
    pr_author: str,
) -> dict[str, dict[str, Any]]:
    latest = latest_decisive_reviews(reviews)
    approved: dict[str, Mapping[str, Any]] = {}
    for actor, review in latest.items():
        if review.get("state") != "APPROVED":
            continue
        commit_id = review.get("commit_id")
        if not isinstance(commit_id, str) or commit_id.lower() != rc_sha.lower():
            continue
        if actor == pr_author or actor.endswith("[bot]"):
            continue
        approved[actor] = review

    role_candidates: dict[str, list[str]] = {}
    roles = policy["roles"]
    for role in ROLES:
        allowed = roles[role]["allowed_logins"]
        candidates = sorted(actor for actor in allowed if actor in approved)
        _require(bool(candidates), f"no current exact-RC GitHub APPROVED review is available for role {role}")
        role_candidates[role] = candidates

    minimum = int(policy["minimum_distinct_actors"])
    sod = {tuple(pair) for pair in policy["separation_of_duties"]}
    assignment: dict[str, str] = {}

    def compatible(role: str, actor: str) -> bool:
        for other_role, other_actor in assignment.items():
            pair = tuple(sorted((role, other_role)))
            if pair in sod and other_actor == actor:
                return False
        return True

    def search(index: int) -> bool:
        if index == len(ROLES):
            return len(set(assignment.values())) >= minimum
        role = ROLES[index]
        candidates = sorted(
            role_candidates[role],
            key=lambda actor: (actor in assignment.values(), actor),
        )
        for actor in candidates:
            if not compatible(role, actor):
                continue
            assignment[role] = actor
            if search(index + 1):
                return True
            assignment.pop(role, None)
        return False

    _require(search(0), "GitHub approvals cannot satisfy minimum distinct actors and separation-of-duties policy")
    return {
        role: _approval_record(approved[assignment[role]], role=role, actor=assignment[role], rc_sha=rc_sha)
        for role in ROLES
    }


def build_authorization(
    request_path: Path,
    request: Mapping[str, Any],
    policy_path: Path,
    policy: Mapping[str, Any],
    pr_payload: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    git_sha, version, migration_head = _rc(request)
    assert isinstance(git_sha, str)
    pr = validate_pr_payload(pr_payload, expected_sha=git_sha)
    approvals = select_role_approvals(policy, reviews, rc_sha=git_sha, pr_author=pr["author"])
    release_id = str(request["release_id"])
    return {
        "schema_version": 1,
        "kind": AUTHORIZATION_KIND,
        "status": "PASS",
        "authorization_id": f"release-auth-{release_id}-{git_sha[:12]}",
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "release_id": release_id,
        "release_candidate": {
            "git_sha": git_sha.lower(),
            "version": str(version),
            "migration_head": str(migration_head),
        },
        "repository": EXPECTED_REPOSITORY,
        "pull_request": pr,
        "request_ref": _frozen(request_path),
        "approval_policy": _frozen(policy_path),
        "distinct_approver_count": len({item["actor"] for item in approvals.values()}),
        "approvals": approvals,
        "operational_handoff": dict(request["operational_handoff"]),
    }


def validate_authorization_report(
    report: Mapping[str, Any],
    *,
    expected_release_id: str | None = None,
    expected_rc: tuple[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    _require(report.get("schema_version") == 1, "release authorization schema_version must be 1")
    _require(report.get("kind") == AUTHORIZATION_KIND, "release authorization kind mismatch")
    _require(report.get("status") == "PASS", "release authorization status must be PASS")
    _require(report.get("repository") == EXPECTED_REPOSITORY, "release authorization repository mismatch")
    release_id = report.get("release_id")
    _require(_present(release_id) and bool(SAFE_ID.fullmatch(str(release_id))), "release authorization release_id invalid")
    if expected_release_id is not None:
        _require(release_id == expected_release_id, "release authorization release_id mismatch")
    rc_value = _rc(report)
    git_sha, version, migration_head = rc_value
    _require(isinstance(git_sha, str) and bool(SHA40.fullmatch(git_sha.lower())), "release authorization RC git_sha invalid")
    _require(_present(version) and _present(migration_head), "release authorization RC version/migration_head missing")
    if expected_rc is not None:
        _require(rc_value == expected_rc, "release authorization RC identity mismatch")

    policy_path = _verify_ref(report.get("approval_policy"), label="release authorization approval_policy", prefixes=("reports/final-acceptance/",))
    policy = validate_policy(_load_json(policy_path))
    request_path = _verify_ref(report.get("request_ref"), label="release authorization request_ref", prefixes=("reports/final-acceptance/",))
    request, request_policy_path, request_policy = validate_request(_load_json(request_path))
    _require(request_policy_path.resolve() == policy_path.resolve(), "release authorization request approval policy path mismatch")
    _require(request_policy == policy, "release authorization request approval policy semantic mismatch")
    _require(request.get("release_id") == release_id and _rc(request) == rc_value, "release authorization request release/RC mismatch")
    _require(request.get("operational_handoff") == report.get("operational_handoff"), "release authorization operational handoff differs from request")

    pr = report.get("pull_request")
    _require(isinstance(pr, Mapping), "release authorization pull_request missing")
    _require(pr.get("number") == EXPECTED_PR and pr.get("base_ref") == EXPECTED_BASE_REF and pr.get("head_ref") == EXPECTED_HEAD_REF, "release authorization pull request identity mismatch")
    _require(pr.get("head_sha") == git_sha.lower(), "release authorization PR head SHA mismatch")
    author = pr.get("author")
    _require(_present(author), "release authorization PR author missing")

    approvals = report.get("approvals")
    _require(isinstance(approvals, Mapping) and set(approvals) == set(ROLES), f"release authorization approvals must equal {sorted(ROLES)}")
    selected: dict[str, str] = {}
    review_ids: set[int] = set()
    for role in ROLES:
        item = approvals[role]
        _require(isinstance(item, Mapping) and item.get("status") == "APPROVED", f"release authorization role {role} is not APPROVED")
        actor = item.get("actor")
        _require(isinstance(actor, str) and actor in policy["roles"][role]["allowed_logins"], f"release authorization actor is not allowed for role {role}")
        _require(actor != author and not actor.endswith("[bot]"), f"release authorization role {role} must be approved by a human other than PR author")
        review_id = item.get("review_id")
        _require(isinstance(review_id, int) and review_id > 0, f"release authorization role {role} review_id invalid")
        _require(review_id not in review_ids, f"release authorization review id reused across roles: {review_id}")
        review_ids.add(review_id)
        review_url = item.get("review_url")
        _require(isinstance(review_url, str) and review_url.startswith(f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}"), f"release authorization role {role} review URL invalid")
        _require(item.get("commit_id") == git_sha.lower(), f"release authorization role {role} review commit does not equal RC")
        _require(_present(item.get("submitted_at")), f"release authorization role {role} submitted_at missing")
        selected[role] = actor

    _require(len(set(selected.values())) >= int(policy["minimum_distinct_actors"]), "release authorization does not satisfy minimum distinct actors")
    for left, right in policy["separation_of_duties"]:
        _require(selected[left] != selected[right], f"release authorization violates separation of duties: {left}/{right}")
    distinct = report.get("distinct_approver_count")
    _require(distinct == len(set(selected.values())), "release authorization distinct_approver_count mismatch")

    handoff = report.get("operational_handoff")
    _require(isinstance(handoff, Mapping) and set(handoff) == HANDOFF_KEYS, "release authorization operational_handoff set mismatch")
    _require(all(_present(handoff.get(key)) for key in HANDOFF_KEYS), "release authorization operational_handoff contains missing/PENDING value")

    return {
        "status": "PASS",
        "release_id": str(release_id),
        "release_candidate": {
            "git_sha": git_sha.lower(),
            "version": str(version),
            "migration_head": str(migration_head),
        },
        "approval_statuses": {role: "APPROVED" for role in ROLES},
        "actors": selected,
        "distinct_approver_count": distinct,
        "operational_handoff": dict(handoff),
        "policy": policy,
        "request_path": request_path,
        "policy_path": policy_path,
    }


def verify_live_authorization(
    report: Mapping[str, Any],
    *,
    token: str | None,
) -> dict[str, Any]:
    validated = validate_authorization_report(report)
    git_sha = validated["release_candidate"]["git_sha"]
    pr_payload = _fetch_json(
        f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/pulls/{EXPECTED_PR}",
        token=token,
        label="GitHub release PR lookup",
    )
    current_pr = validate_pr_payload(pr_payload, expected_sha=git_sha)
    _require(current_pr == report.get("pull_request"), "live GitHub PR identity differs from frozen release authorization")
    reviews = _fetch_reviews(token=token)
    by_id = {review.get("id"): review for review in reviews if isinstance(review.get("id"), int)}
    latest = latest_decisive_reviews(reviews)
    for role in ROLES:
        frozen = report["approvals"][role]
        review = by_id.get(frozen["review_id"])
        _require(isinstance(review, Mapping), f"live GitHub review missing for role {role}")
        user = review.get("user")
        actor = user.get("login") if isinstance(user, Mapping) else None
        _require(actor == frozen["actor"], f"live GitHub review actor changed for role {role}")
        _require(review.get("state") == "APPROVED", f"live GitHub review is no longer APPROVED for role {role}")
        _require(review.get("commit_id") == git_sha, f"live GitHub review is not bound to final RC for role {role}")
        _require(latest.get(str(actor), {}).get("id") == frozen["review_id"], f"frozen approval is not the latest decisive review for actor {actor}")
    return {
        "schema_version": 1,
        "kind": "LUMI_RELEASE_AUTHORIZATION_LIVE_VERIFICATION_V1",
        "status": "PASS",
        "repository": EXPECTED_REPOSITORY,
        "pull_request": EXPECTED_PR,
        "release_id": validated["release_id"],
        "release_candidate": validated["release_candidate"],
        "actors": validated["actors"],
        "distinct_approver_count": validated["distinct_approver_count"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_json(url: str, *, token: str | None, label: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lumi-node73-release-authorization",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ReleaseAuthorizationError(f"{label} failed with HTTP {exc.code}; a token with Pull Requests read permission may be required") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReleaseAuthorizationError(f"{label} failed: {exc}") from exc
    _require(isinstance(payload, dict), f"{label} returned non-object JSON")
    return payload


def _fetch_reviews(*, token: str | None) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/pulls/{EXPECTED_PR}/reviews?per_page=100&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lumi-node73-release-authorization",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ReleaseAuthorizationError(f"GitHub PR reviews lookup failed with HTTP {exc.code}; a token with Pull Requests read permission may be required") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ReleaseAuthorizationError(f"GitHub PR reviews lookup failed: {exc}") from exc
        _require(isinstance(payload, list), "GitHub PR reviews lookup returned non-array JSON")
        reviews.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return reviews
    raise ReleaseAuthorizationError("GitHub PR reviews exceed the supported 1000-review safety bound")


def capture(request_path: Path, *, token: str | None) -> dict[str, Any]:
    request, policy_path, policy = validate_request(_load_json(request_path))
    git_sha = request["release_candidate"]["git_sha"]
    pr_payload = _fetch_json(
        f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/pulls/{EXPECTED_PR}",
        token=token,
        label="GitHub release PR lookup",
    )
    reviews = _fetch_reviews(token=token)
    return build_authorization(request_path, request, policy_path, policy, pr_payload, reviews)


def self_test() -> dict[str, Any]:
    parent = ROOT / "reports" / "final-acceptance"
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="_approval-selftest-", dir=parent))
    try:
        rc_sha = "a" * 40
        policy_path = temp / "approval-policy.json"
        policy = {
            "schema_version": 1,
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
            "require_exact_rc_review_commit": True,
        }
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        request_path = temp / "authorization-request.json"
        handoff = {key: f"owner-{index}" for index, key in enumerate(sorted(HANDOFF_KEYS), start=1)}
        request = {
            "schema_version": 1,
            "kind": REQUEST_KIND,
            "release_id": "rc-auth-selftest",
            "release_candidate": {"git_sha": rc_sha, "version": "1.0.0-rc", "migration_head": "0020"},
            "repository": EXPECTED_REPOSITORY,
            "pull_request": EXPECTED_PR,
            "approval_policy": _frozen(policy_path),
            "operational_handoff": handoff,
        }
        request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        normalized_request, normalized_policy_path, normalized_policy = validate_request(request)
        pr = {
            "number": EXPECTED_PR,
            "state": "open",
            "html_url": f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}",
            "user": {"login": "pr-author"},
            "head": {"ref": EXPECTED_HEAD_REF, "sha": rc_sha, "repo": {"full_name": EXPECTED_REPOSITORY}},
            "base": {"ref": EXPECTED_BASE_REF},
        }
        reviews: list[dict[str, Any]] = []
        for index, actor in enumerate(("alice", "bob", "carol", "dave"), start=1):
            reviews.append(
                {
                    "id": index,
                    "state": "APPROVED",
                    "html_url": f"https://github.com/{EXPECTED_REPOSITORY}/pull/{EXPECTED_PR}#pullrequestreview-{index}",
                    "commit_id": rc_sha,
                    "submitted_at": f"2026-08-20T00:0{index}:00Z",
                    "user": {"login": actor},
                }
            )
        report = build_authorization(request_path, normalized_request, normalized_policy_path, normalized_policy, pr, reviews)
        clean = validate_authorization_report(report, expected_release_id="rc-auth-selftest", expected_rc=(rc_sha, "1.0.0-rc", "0020"))

        blocked = 0
        drills: list[tuple[str, callable]] = []

        def stale_review() -> None:
            changed = copy.deepcopy(reviews)
            changed[2]["commit_id"] = "b" * 40
            select_role_approvals(normalized_policy, changed, rc_sha=rc_sha, pr_author="pr-author")

        drills.append(("stale security review", stale_review))

        def bot_policy() -> None:
            changed = copy.deepcopy(policy)
            changed["roles"]["security"]["allowed_logins"] = ["security[bot]"]
            validate_policy(changed)

        drills.append(("bot role principal", bot_policy))

        def impossible_distinct() -> None:
            changed = copy.deepcopy(normalized_policy)
            changed["minimum_distinct_actors"] = 5
            select_role_approvals(changed, reviews, rc_sha=rc_sha, pr_author="pr-author")

        drills.append(("insufficient distinct actors", impossible_distinct))

        def wrong_head() -> None:
            changed = copy.deepcopy(pr)
            changed["head"]["sha"] = "b" * 40
            validate_pr_payload(changed, expected_sha=rc_sha)

        drills.append(("wrong PR head", wrong_head))

        def report_actor_swap() -> None:
            changed = copy.deepcopy(report)
            changed["approvals"]["security"]["actor"] = "alice"
            validate_authorization_report(changed)

        drills.append(("approval actor swap", report_actor_swap))

        def report_commit_swap() -> None:
            changed = copy.deepcopy(report)
            changed["approvals"]["engineering"]["commit_id"] = "b" * 40
            validate_authorization_report(changed)

        drills.append(("approval commit swap", report_commit_swap))

        def report_review_reuse() -> None:
            changed = copy.deepcopy(report)
            changed["approvals"]["operations"]["review_id"] = changed["approvals"]["product"]["review_id"]
            validate_authorization_report(changed)

        drills.append(("review id reuse", report_review_reuse))

        def policy_hash_tamper() -> None:
            original = policy_path.read_text(encoding="utf-8")
            try:
                policy_path.write_text(original + " ", encoding="utf-8")
                validate_authorization_report(report)
            finally:
                policy_path.write_text(original, encoding="utf-8")

        drills.append(("policy hash tamper", policy_hash_tamper))

        for label, drill in drills:
            try:
                drill()
            except ReleaseAuthorizationError:
                blocked += 1
                continue
            raise ReleaseAuthorizationError(f"negative authorization drill did not block: {label}")
        return {
            "status": "PASS",
            "clean_distinct_approvers": clean["distinct_approver_count"],
            "negative_drills": blocked,
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or live-verify GitHub-backed NODE-73 release authorization")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--live-output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0

    token = os.environ.get("RELEASE_APPROVAL_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.verify_report is not None:
        report_path = args.verify_report.resolve()
        report = _load_json(report_path)
        result = verify_live_authorization(report, token=token)
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.live_output is not None:
            args.live_output.parent.mkdir(parents=True, exist_ok=True)
            args.live_output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0

    _require(args.request is not None and args.output is not None, "--request and --output are required for authorization capture")
    request_path = _repo_file(_relative(args.request.resolve()), prefixes=("reports/final-acceptance/",))
    report = capture(request_path, token=token)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseAuthorizationError as exc:
        raise SystemExit(f"release authorization blocked: {exc}") from exc
