from __future__ import annotations

from collections import defaultdict

from lumi_agent_runtime.agent_registry.semver import SemVer, select_highest

from .contracts import (
    RecipeDefinition,
    RecipeReleaseManifest,
    RecipeReleaseRecord,
    RecipeReleaseStatus,
    ResolvedRecipe,
)
from .errors import RecipeNotFoundError, RecipeReleaseError, RecipeVersionResolutionError


class RecipeRegistry:
    def __init__(
        self,
        definitions: tuple[RecipeDefinition, ...],
        manifest: RecipeReleaseManifest,
    ) -> None:
        self._by_key = {item.identity: item for item in definitions}
        if len(self._by_key) != len(definitions):
            raise RecipeReleaseError("duplicate exact Recipe version")
        self.manifest = manifest
        self._validate_manifest()

    def definitions(self) -> tuple[RecipeDefinition, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))

    def resolve(self, requested_ref: str) -> ResolvedRecipe:
        recipe_id, selector = _split(requested_ref)
        version, release = self._resolve_version(recipe_id, selector)
        definition = self._by_key.get(f"{recipe_id}@{version}")
        if definition is None:
            raise RecipeNotFoundError(f"Recipe not found: {recipe_id}@{version}")
        return ResolvedRecipe(
            definition=definition,
            release_status=release.status,
            requested_ref=requested_ref,
            manifest_revision=self.manifest.revision,
        )

    def resolve_exact_for_resume(self, recipe_id: str, exact_version: str) -> ResolvedRecipe:
        SemVer.parse(exact_version)
        return self.resolve(f"{recipe_id}@{exact_version}")

    def _resolve_version(
        self,
        recipe_id: str,
        selector: str,
    ) -> tuple[str, RecipeReleaseRecord]:
        alias = self.manifest.aliases.get(recipe_id, {}).get(selector)
        if alias is not None:
            release = self._release(recipe_id, alias)
            if selector == "production" and release.status != RecipeReleaseStatus.PRODUCTION:
                raise RecipeReleaseError("Recipe production alias must target PRODUCTION")
            if release.status == RecipeReleaseStatus.DISABLED:
                raise RecipeReleaseError("Recipe alias targets DISABLED")
            return alias, release
        try:
            SemVer.parse(selector)
        except ValueError:
            versions = tuple(
                row.version
                for row in self.manifest.releases
                if row.recipe_id == recipe_id
                and row.status == RecipeReleaseStatus.PRODUCTION
            )
            try:
                version = select_highest(versions, selector)
            except ValueError as exc:
                raise RecipeVersionResolutionError(str(exc)) from exc
            if version is None:
                raise RecipeVersionResolutionError(
                    f"no production Recipe matches: {recipe_id}@{selector}"
                )
            return version, self._release(recipe_id, version)
        release = self._release(recipe_id, selector)
        if release.status in {RecipeReleaseStatus.DRAFT, RecipeReleaseStatus.DISABLED}:
            raise RecipeReleaseError(
                f"Recipe exact version is not runnable: {recipe_id}@{selector}"
            )
        return selector, release

    def _release(self, recipe_id: str, version: str) -> RecipeReleaseRecord:
        row = next(
            (
                item
                for item in self.manifest.releases
                if item.recipe_id == recipe_id and item.version == version
            ),
            None,
        )
        if row is None:
            raise RecipeReleaseError(
                f"Recipe release metadata missing: {recipe_id}@{version}"
            )
        return row

    def _validate_manifest(self) -> None:
        if self.manifest.schema != "lumi.recipe-registry.release.v1" or self.manifest.revision < 1:
            raise RecipeReleaseError("Recipe release manifest schema/revision invalid")
        definitions = set(self._by_key)
        releases = {
            f"{item.recipe_id}@{item.version}"
            for item in self.manifest.releases
        }
        if definitions != releases:
            raise RecipeReleaseError("Recipe release/definition set mismatch")
        production: dict[str, int] = defaultdict(int)
        for row in self.manifest.releases:
            if row.status == RecipeReleaseStatus.PRODUCTION:
                production[row.recipe_id] += 1
        if any(count > 1 for count in production.values()):
            raise RecipeReleaseError("multiple PRODUCTION versions for one Recipe")
        for recipe_id, aliases in self.manifest.aliases.items():
            for name, version in aliases.items():
                release = self._release(recipe_id, version)
                if release.status == RecipeReleaseStatus.DISABLED:
                    raise RecipeReleaseError("Recipe alias targets DISABLED")
                if name == "production" and release.status != RecipeReleaseStatus.PRODUCTION:
                    raise RecipeReleaseError(
                        "Recipe production alias targets non-production"
                    )


def _split(value: str) -> tuple[str, str]:
    if "@" not in value:
        raise RecipeVersionResolutionError("Recipe reference must include @selector")
    recipe_id, selector = value.rsplit("@", 1)
    if not recipe_id or not selector:
        raise RecipeVersionResolutionError("Recipe reference incomplete")
    return recipe_id, selector
