# ruff: noqa: E501
from __future__ import annotations

from .models import ConstraintType, EvaluatorContract

_LOCK_OBSERVATION = "lock_integrity"

EVALUATOR_CONTRACTS: dict[ConstraintType, EvaluatorContract] = {
    "LOCK_POSITION": EvaluatorContract(constraint_type="LOCK_POSITION", stages=("preflight", "postflight"), preflight_facets=("position",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_SIZE": EvaluatorContract(constraint_type="LOCK_SIZE", stages=("preflight", "postflight"), preflight_facets=("size",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_ROTATION": EvaluatorContract(constraint_type="LOCK_ROTATION", stages=("preflight", "postflight"), preflight_facets=("rotation",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_TRANSFORM": EvaluatorContract(constraint_type="LOCK_TRANSFORM", stages=("preflight", "postflight"), preflight_facets=("transform", "position", "rotation"), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_ASPECT_RATIO": EvaluatorContract(constraint_type="LOCK_ASPECT_RATIO", stages=("preflight", "postflight"), preflight_facets=("aspect_ratio",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_LAYER_ORDER": EvaluatorContract(constraint_type="LOCK_LAYER_ORDER", stages=("preflight", "postflight"), preflight_facets=("layer_order",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_PARENT": EvaluatorContract(constraint_type="LOCK_PARENT", stages=("preflight", "postflight"), preflight_facets=("parent",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_CONTENT": EvaluatorContract(constraint_type="LOCK_CONTENT", stages=("preflight", "postflight"), preflight_facets=("content",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_TEXT": EvaluatorContract(constraint_type="LOCK_TEXT", stages=("preflight", "postflight"), preflight_facets=("text",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_ASSET": EvaluatorContract(constraint_type="LOCK_ASSET", stages=("preflight", "postflight"), preflight_facets=("asset",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_IDENTITY": EvaluatorContract(constraint_type="LOCK_IDENTITY", stages=("preflight", "postflight"), preflight_facets=("identity",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_STYLE": EvaluatorContract(constraint_type="LOCK_STYLE", stages=("preflight", "postflight"), preflight_facets=("style",), postflight_observation_kind=_LOCK_OBSERVATION),
    "LOCK_BRAND": EvaluatorContract(constraint_type="LOCK_BRAND", stages=("preflight", "postflight"), preflight_facets=("brand", "style"), postflight_observation_kind=_LOCK_OBSERVATION),
    "PROTECT_REGION": EvaluatorContract(constraint_type="PROTECT_REGION", stages=("postflight",), postflight_observation_kind="protected_region"),
    "MUST_STAY_INSIDE": EvaluatorContract(constraint_type="MUST_STAY_INSIDE", stages=("postflight",), postflight_observation_kind="geometry"),
    "MUST_NOT_OVERLAP": EvaluatorContract(constraint_type="MUST_NOT_OVERLAP", stages=("postflight",), postflight_observation_kind="geometry"),
    "MIN_MARGIN": EvaluatorContract(constraint_type="MIN_MARGIN", stages=("postflight",), postflight_observation_kind="geometry"),
    "SAFE_AREA": EvaluatorContract(constraint_type="SAFE_AREA", stages=("postflight",), postflight_observation_kind="geometry"),
    "REQUIRE_CONTRAST": EvaluatorContract(constraint_type="REQUIRE_CONTRAST", stages=("postflight",), postflight_observation_kind="contrast"),
    "REQUIRE_SCANNABILITY": EvaluatorContract(constraint_type="REQUIRE_SCANNABILITY", stages=("postflight",), postflight_observation_kind="qr_scannability"),
    "REQUIRE_TEXT_READABILITY": EvaluatorContract(constraint_type="REQUIRE_TEXT_READABILITY", stages=("postflight",), postflight_observation_kind="text_readability"),
    "REQUIRE_BRAND_COMPLIANCE": EvaluatorContract(constraint_type="REQUIRE_BRAND_COMPLIANCE", stages=("postflight",), postflight_observation_kind="brand_compliance"),
    "REQUIRE_RESOLUTION": EvaluatorContract(constraint_type="REQUIRE_RESOLUTION", stages=("postflight",), postflight_observation_kind="resolution"),
    "REQUIRE_IDENTITY_SCORE": EvaluatorContract(constraint_type="REQUIRE_IDENTITY_SCORE", stages=("postflight",), postflight_observation_kind="identity_score"),
}
