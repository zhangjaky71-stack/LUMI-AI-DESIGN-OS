from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/image-edit/src"))

from lumi_image_edit import (  # noqa: E402
    EditIntent,
    ImageEditSpec,
    MaskSpec,
    PixelRect,
    ProtectedRegion,
    SourceImageRef,
    plan_edit,
)

SHA = "a" * 64
GIT = "b" * 40


def _source() -> SourceImageRef:
    return SourceImageRef(
        "org",
        "project",
        "artifact",
        "v3",
        "asset",
        "7",
        "bucket/source.png",
        SHA,
        1000,
        1000,
        "image/png",
        "owned",
        True,
    )


def _spec(case: dict[str, object]) -> ImageEditSpec:
    source = _source()
    if case["route"] == "STRUCTURAL_IR_EDIT":
        return ImageEditSpec(
            "org",
            "project",
            "task",
            str(case["id"]),
            source,
            EditIntent(
                "RESIZE_TEXT",
                "resize title",
                ("title",),
                {"width": 500, "height": 100},
            ),
            (),
            (),
            None,
            None,
            (),
            Decimal("1"),
            GIT,
            "doc",
            3,
        )

    protected = ()
    role = case.get("protected")
    if role:
        kwargs: dict[str, object] = {}
        if role == "QR":
            kwargs["expected_qr_payload"] = "https://example.test"
        protected = (
            ProtectedRegion(
                str(case["id"]),
                str(role),  # type: ignore[arg-type]
                PixelRect(600, 100, 100, 100),
                "HARD",
                SHA,
                **kwargs,
            ),
        )
    mask = MaskSpec(
        "mask",
        "1",
        "USER_BRUSH",
        "asset",
        "7",
        SHA,
        1000,
        1000,
        PixelRect(0, 0, 400, 1000),
        "c" * 64,
        "bucket/mask.png",
    )
    return ImageEditSpec(
        "org",
        "project",
        "task",
        str(case["id"]),
        source,
        EditIntent("BACKGROUND_REPLACE", "background black"),
        (),
        protected,
        mask,
        None,
        (),
        Decimal("1"),
        GIT,
    )


def main() -> None:
    corpus_path = ROOT / "evals/node47/local-edit-corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    per_scenario = int(corpus["cases_per_scenario"])
    scenarios = corpus["scenarios"]
    cases = [
        {**scenario, "id": f"{scenario['name']}-{index:02d}"}
        for scenario in scenarios
        for index in range(per_scenario)
    ]
    assert len(cases) >= 100
    for case in cases:
        plan = plan_edit(_spec(case))
        assert plan.route == case["route"]
        if case["expect"] == "NO_MODEL":
            assert not plan.requires_provider
        else:
            assert plan.requires_provider
    print(f"NODE47_LOCAL_EDIT_EVAL_PASS cases={len(cases)}")
    print("visual_quality_claimed=false")


if __name__ == "__main__":
    main()
