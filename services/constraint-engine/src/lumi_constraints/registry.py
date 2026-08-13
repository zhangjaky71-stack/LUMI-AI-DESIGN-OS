from __future__ import annotations

from dataclasses import dataclass

SOURCE_PRECEDENCE = {
    "SAFETY_SYSTEM": 700,
    "USER_EXPLICIT": 600,
    "APPROVED_BRAND_RULE": 500,
    "PROJECT_RULE": 400,
    "RECIPE_RULE": 300,
    "AGENT_INFERRED": 200,
    "STYLE_PREFERENCE": 100,
}

CONSTRAINT_TYPES = frozenset(
    {
        "LOCK_POSITION",
        "LOCK_SIZE",
        "LOCK_ROTATION",
        "LOCK_TRANSFORM",
        "LOCK_ASPECT_RATIO",
        "LOCK_LAYER_ORDER",
        "LOCK_PARENT",
        "LOCK_CONTENT",
        "LOCK_TEXT",
        "LOCK_ASSET",
        "LOCK_IDENTITY",
        "LOCK_STYLE",
        "LOCK_BRAND",
        "PROTECT_REGION",
        "MUST_STAY_INSIDE",
        "MUST_NOT_OVERLAP",
        "MIN_MARGIN",
        "SAFE_AREA",
        "REQUIRE_CONTRAST",
        "REQUIRE_SCANNABILITY",
        "REQUIRE_TEXT_READABILITY",
        "REQUIRE_BRAND_COMPLIANCE",
        "REQUIRE_RESOLUTION",
        "REQUIRE_IDENTITY_SCORE",
    }
)


@dataclass(frozen=True, slots=True)
class EvaluatorSpec:
    phase: str
    evaluator: str
    properties: frozenset[str] = frozenset()
    evidence: str | None = None


EVALUATORS = {
    "LOCK_POSITION": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"position"})),
    "LOCK_SIZE": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"size"})),
    "LOCK_ROTATION": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"rotation"})),
    "LOCK_TRANSFORM": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"position", "size", "rotation", "transform"})),
    "LOCK_ASPECT_RATIO": EvaluatorSpec("PREFLIGHT", "aspect_ratio", frozenset({"size"})),
    "LOCK_LAYER_ORDER": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"layer_order", "parent"})),
    "LOCK_PARENT": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"parent"})),
    "LOCK_CONTENT": EvaluatorSpec("BOTH", "lock_content", frozenset({"content", "text", "asset", "existence"}), "content_identity"),
    "LOCK_TEXT": EvaluatorSpec("BOTH", "lock_property", frozenset({"text", "content"}), "text_match"),
    "LOCK_ASSET": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"asset", "content"})),
    "LOCK_IDENTITY": EvaluatorSpec("BOTH", "lock_property", frozenset({"asset", "content", "existence"}), "identity"),
    "LOCK_STYLE": EvaluatorSpec("PREFLIGHT", "lock_property", frozenset({"style"})),
    "LOCK_BRAND": EvaluatorSpec("BOTH", "lock_property", frozenset({"style", "brand"}), "brand_compliance"),
    "PROTECT_REGION": EvaluatorSpec("BOTH", "protected_region", frozenset({"position", "size", "rotation", "content", "asset", "style"}), "protected_region_diff"),
    "MUST_STAY_INSIDE": EvaluatorSpec("PREFLIGHT", "inside_region", frozenset({"position", "size", "parent"})),
    "MUST_NOT_OVERLAP": EvaluatorSpec("PREFLIGHT", "non_overlap", frozenset({"position", "size", "parent"})),
    "MIN_MARGIN": EvaluatorSpec("PREFLIGHT", "min_margin", frozenset({"position", "size", "parent"})),
    "SAFE_AREA": EvaluatorSpec("PREFLIGHT", "inside_region", frozenset({"position", "size", "parent"})),
    "REQUIRE_CONTRAST": EvaluatorSpec("POSTFLIGHT", "evidence_threshold", evidence="contrast"),
    "REQUIRE_SCANNABILITY": EvaluatorSpec("POSTFLIGHT", "qr_scannability", evidence="qr"),
    "REQUIRE_TEXT_READABILITY": EvaluatorSpec("POSTFLIGHT", "evidence_threshold", evidence="text_readability"),
    "REQUIRE_BRAND_COMPLIANCE": EvaluatorSpec("POSTFLIGHT", "evidence_threshold", evidence="brand_compliance"),
    "REQUIRE_RESOLUTION": EvaluatorSpec("POSTFLIGHT", "resolution", evidence="resolution"),
    "REQUIRE_IDENTITY_SCORE": EvaluatorSpec("POSTFLIGHT", "evidence_threshold", evidence="identity"),
}

assert set(EVALUATORS) == CONSTRAINT_TYPES
