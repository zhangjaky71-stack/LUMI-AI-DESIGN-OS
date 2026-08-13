from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True, order=True, slots=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease_rank: tuple[tuple[int, int | str], ...] = ()
    text: str = ""

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = _SEMVER.fullmatch(value)
        if match is None:
            raise ValueError(f"AGENT_SEMVER_INVALID:{value}")
        prerelease = match.group(4)
        # Stable releases sort after prereleases for the same core version.
        if prerelease is None:
            rank: tuple[tuple[int, int | str], ...] = ((2, 0),)
        else:
            parts: list[tuple[int, int | str]] = [(1, 0)]
            for item in prerelease.split("."):
                parts.append((0, int(item)) if item.isdigit() else (1, item))
            rank = tuple(parts)
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease_rank=rank,
            text=value,
        )


def matches(version: SemVer, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        raise ValueError("AGENT_SEMVER_SELECTOR_EMPTY")
    if _SEMVER.fullmatch(selector):
        return version.text == selector
    if selector.endswith(".x"):
        prefix = selector[:-2]
        if not prefix.isdigit():
            raise ValueError(f"AGENT_SEMVER_SELECTOR_INVALID:{selector}")
        return version.major == int(prefix)
    if selector.startswith("^"):
        base = _parse_partial(selector[1:], selector)
        lower = _lower_bound(base)
        upper = _caret_upper(base)
        return lower <= version < upper
    if selector.startswith("~"):
        base = _parse_partial(selector[1:], selector)
        lower = _lower_bound(base)
        upper = SemVer(base[0], base[1] + 1, 0, ((2, 0),), f"{base[0]}.{base[1] + 1}.0")
        return lower <= version < upper
    raise ValueError(f"AGENT_SEMVER_SELECTOR_INVALID:{selector}")


def select_highest(versions: tuple[str, ...], selector: str) -> str | None:
    candidates = [SemVer.parse(value) for value in versions]
    matched = [item for item in candidates if matches(item, selector)]
    if not matched:
        return None
    return max(matched).text


def _parse_partial(value: str, selector: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"AGENT_SEMVER_SELECTOR_INVALID:{selector}")
    numbers = [int(part) for part in parts]
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2]


def _lower_bound(base: tuple[int, int, int]) -> SemVer:
    major, minor, patch = base
    return SemVer(major, minor, patch, ((2, 0),), f"{major}.{minor}.{patch}")


def _caret_upper(base: tuple[int, int, int]) -> SemVer:
    major, minor, patch = base
    if major > 0:
        return SemVer(major + 1, 0, 0, ((2, 0),), f"{major + 1}.0.0")
    if minor > 0:
        return SemVer(0, minor + 1, 0, ((2, 0),), f"0.{minor + 1}.0")
    return SemVer(0, 0, patch + 1, ((2, 0),), f"0.0.{patch + 1}")
