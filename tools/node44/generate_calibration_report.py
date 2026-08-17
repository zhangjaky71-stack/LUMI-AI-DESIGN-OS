from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from lumi_api.identity_engine.calibration import calibrate_threshold
from lumi_api.identity_engine.contracts import (
    CalibrationSample,
    IdentityType,
    SampleLabel,
    SignalScore,
)


def _label(case: dict[str, object]) -> SampleLabel | None:
    name = str(case["case"])
    if "low-quality" in name or "low-crop" in name:
        return None
    if bool(case["expected_pass"]):
        return SampleLabel.POSITIVE
    if "near" in name:
        return SampleLabel.NEAR_MISS
    return SampleLabel.NEGATIVE


def main() -> None:
    fixture = json.loads(
        Path("evals/node44/identity-benchmark.json").read_text(encoding="utf-8")
    )
    reports = []
    for identity_type, report_id in (
        (IdentityType.LOGO, UUID("74444444-4444-7444-8444-444444444444")),
        (IdentityType.PRODUCT, UUID("75555555-5555-7555-8555-555555555555")),
    ):
        samples = []
        for case in fixture["cases"]:
            if case["identity_type"] != identity_type.value:
                continue
            label = _label(case)
            if label is None:
                continue
            samples.append(
                CalibrationSample(
                    sample_id=case["case"],
                    identity_type=identity_type,
                    scenario="node44-contract-benchmark",
                    label=label,
                    signal_scores=tuple(
                        SignalScore.model_validate(value) for value in case["signals"]
                    ),
                    crop_quality=float(case["region_quality"]),
                )
            )
        report = calibrate_threshold(
            report_id=report_id,
            organization_id=UUID("11111111-1111-4111-8111-111111111111"),
            identity_type=identity_type,
            profile_key="node44-contract-benchmark",
            version=1,
            samples=tuple(samples),
            target_precision=0.95,
            created_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        )
        reports.append(report.model_dump(mode="json"))
    output = {
        "schema_version": "lumi.identity-calibration-report/1.0",
        "qualification": (
            "Deterministic contract fixture only; not production model accuracy evidence."
        ),
        "reports": reports,
    }
    Path("reports/nodes/NODE-44/calibration-report.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for report in reports:
        print(
            "NODE44_CALIBRATION_REPORT",
            report["identity_type"],
            f"threshold={report['selected_threshold']}",
            f"precision={report['metrics']['precision']:.3f}",
            f"recall={report['metrics']['recall']:.3f}",
        )


if __name__ == "__main__":
    main()
