from __future__ import annotations

import math

from .model import AssetAnalysisRecord, DuplicateEvidence, DuplicatePolicy


class DuplicateContractError(ValueError):
    pass


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise DuplicateContractError("EMBEDDING_SPACE_MISMATCH")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def perceptual_hamming(left: str, right: str) -> int:
    if len(left) != len(right) or not left:
        raise DuplicateContractError("PERCEPTUAL_HASH_SPACE_MISMATCH")
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError as exc:
        raise DuplicateContractError("INVALID_PERCEPTUAL_HASH") from exc


def classify_similarity(
    source: AssetAnalysisRecord,
    candidate: AssetAnalysisRecord,
    policy: DuplicatePolicy,
) -> tuple[DuplicateEvidence, ...]:
    if source.organization_id != candidate.organization_id:
        raise DuplicateContractError("DUPLICATE_TENANT_MISMATCH")
    if source.index_id != candidate.index_id:
        raise DuplicateContractError("DUPLICATE_INDEX_SPACE_MISMATCH")
    if source.asset_id == candidate.asset_id and source.asset_version == candidate.asset_version:
        return ()
    result: list[DuplicateEvidence] = []
    if source.checksum_sha256 == candidate.checksum_sha256:
        result.append(DuplicateEvidence(
            source.asset_id, candidate.asset_id, "EXACT", 1.0, policy.version,
            "sha256 checksum match",
        ))
    if source.perceptual_hash and candidate.perceptual_hash:
        distance = perceptual_hamming(source.perceptual_hash, candidate.perceptual_hash)
        bit_count = len(source.perceptual_hash) * 4
        score = 1.0 - distance / bit_count
        if distance <= policy.perceptual_max_hamming:
            result.append(DuplicateEvidence(
                source.asset_id, candidate.asset_id, "PERCEPTUAL_NEAR_DUPLICATE", score,
                policy.version, f"perceptual hamming distance={distance}",
            ))
    if source.embedding is not None and candidate.embedding is not None:
        semantic = cosine_similarity(source.embedding, candidate.embedding)
        if semantic >= policy.semantic_similarity_floor:
            result.append(DuplicateEvidence(
                source.asset_id, candidate.asset_id, "SEMANTIC_SIMILAR", semantic,
                policy.version,
                "embedding similarity only; never an automatic deletion signal",
            ))
    order = {"EXACT": 0, "PERCEPTUAL_NEAR_DUPLICATE": 1, "SEMANTIC_SIMILAR": 2}
    return tuple(sorted(result, key=lambda item: (order[item.tier], -item.score)))
