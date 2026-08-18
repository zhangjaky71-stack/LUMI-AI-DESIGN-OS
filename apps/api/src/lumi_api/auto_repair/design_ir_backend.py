from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Iterator, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lumi_api.artifact_engine.contracts import VersionCreateCommand
from lumi_api.artifact_engine.ports import ArtifactRuntimeRepository
from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.artifacts.models import ArtifactFile, ArtifactType, CreatedByType, LineageEdgeType
from lumi_api.design_ir.document import DesignIRDocument, content_hash_sha256, node_index
from lumi_api.design_ir.engine import apply_batch
from lumi_api.design_ir.nodes import ImageNode, TextNode
from lumi_api.design_ir.operations import (
    ActorRef,
    DesignOperation,
    DesignOperationBatch,
    RenameNodeOp,
    SetAppearanceOp,
    SetFillOp,
    SetImageAssetOp,
    SetLockOp,
    SetSizeOp,
    SetTextOp,
    SetTextStyleOp,
    SetTransformOp,
)
from lumi_api.design_ir.primitives import RgbaColor, Size2D, SolidPaint
from lumi_api.domain.ids import new_uuid7
from lumi_api.persistence.models_artifacts import (
    DesignDocumentModel,
    DesignDocumentVersionModel,
)
from lumi_auto_repair import AutoRepairJob, RepairCandidate, RepairPlan


class DesignPreviewRenderPort(Protocol):
    """Render one exact DesignIR snapshot and persist its preview object."""

    async def render_preview(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_id: str,
        design_document_version_id: str,
        document: DesignIRDocument,
    ) -> ArtifactFile: ...


class Node38StructuralRepairBackend:
    """Apply allowlisted NODE-38 operations and create an immutable repair version.

    The SQLAlchemy Session is dedicated to DesignDocumentVersion allocation. The
    Artifact Engine owns a separate repository/session for NODE-42 transactions.
    The design document's canonical head is intentionally NOT advanced: repair
    candidates stay isolated until NODE-51 promotes the ArtifactVersion.
    """

    def __init__(
        self,
        *,
        session: Session,
        artifacts: ArtifactEngineService,
        artifact_repository: ArtifactRuntimeRepository,
        preview_renderer: DesignPreviewRenderPort,
    ) -> None:
        self.session = session
        self.artifacts = artifacts
        self.artifact_repository = artifact_repository
        self.preview_renderer = preview_renderer

    async def execute_design_ops(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        repair_branch_id: str,
    ) -> RepairCandidate:
        source = job.working_source
        if source.artifact_type != ArtifactType.DESIGN_DOCUMENT.value:
            raise ValueError("REPAIR_STRUCTURAL_DESIGN_DOCUMENT_REQUIRED")
        if source.design_document_id is None or source.design_document_version_id is None:
            raise ValueError("REPAIR_DESIGN_DOCUMENT_VERSION_REQUIRED")

        source_row = self.session.get(
            DesignDocumentVersionModel,
            UUID(source.design_document_version_id),
        )
        if source_row is None:
            raise KeyError("REPAIR_DESIGN_DOCUMENT_VERSION_NOT_FOUND")
        if str(source_row.organization_id) != job.spec.organization_id:
            raise PermissionError("REPAIR_DESIGN_DOCUMENT_ORG_MISMATCH")
        if str(source_row.design_document_id) != source.design_document_id:
            raise ValueError("REPAIR_DESIGN_DOCUMENT_ID_MISMATCH")

        document = DesignIRDocument.model_validate(dict(source_row.content_json))
        if content_hash_sha256(document) != source_row.content_hash:
            raise ValueError("REPAIR_DESIGN_DOCUMENT_HASH_MISMATCH")
        operations = self._compile_operations(document, plan)
        batch = DesignOperationBatch(
            operation_id=new_uuid7(),
            document_id=document.document_id,
            base_revision=document.revision,
            actor=ActorRef(kind="system"),
            correlation_id=f"repair:{job.job_id}:{plan.iteration}"[:128],
            operations=operations,
        )
        applied = apply_batch(document, batch)
        if applied.content_hash == source_row.content_hash:
            raise ValueError("REPAIR_STRUCTURAL_NO_SEMANTIC_CHANGE")

        design_version_id = self._persist_candidate_design_version(
            organization_id=UUID(job.spec.organization_id),
            design_document_id=source_row.design_document_id,
            parent_version_id=source_row.id,
            document=applied.document,
            content_hash=applied.content_hash,
        )
        preview = await self.preview_renderer.render_preview(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            artifact_id=source.artifact_id,
            design_document_version_id=str(design_version_id),
            document=applied.document,
        )
        preview = self._normalize_preview(preview, job)

        source_artifact_version = self.artifact_repository.get_version(
            UUID(source.artifact_version_id)
        )
        source_artifact = self.artifact_repository.get_artifact(
            source_artifact_version.artifact_id
        )
        if source_artifact.type is not ArtifactType.DESIGN_DOCUMENT:
            raise ValueError("REPAIR_STRUCTURAL_ARTIFACT_TYPE_MISMATCH")
        envelope = self.artifact_repository.get_provenance_envelope(
            source_artifact_version.id
        )
        record = envelope.record.model_copy(
            update={
                "agent_run_id": None,
                "task_id": UUID(job.spec.task_id),
                "generation_id": None,
                "provider": None,
                "model": None,
                "provider_request_id": None,
                "prompt_hash": None,
                "prompt_ref": None,
                "prompt_template_version": None,
                "input_artifact_version_ids": tuple(
                    dict.fromkeys(
                        (
                            *envelope.record.input_artifact_version_ids,
                            source_artifact_version.id,
                        )
                    )
                ),
                "design_ir_schema_version": applied.document.spec_version,
                "constraint_snapshot_hash": source.constraint_snapshot_hash,
                "recipe_version": "auto-repair/1.0",
            }
        )
        provenance = envelope.model_copy(
            update={
                "record": record,
                "agent_version": "auto-repair/1.0.0",
            }
        )
        branch = self.artifact_repository.get_branch(UUID(repair_branch_id))
        if branch.head_version_id != source_artifact_version.id:
            raise ValueError("REPAIR_STRUCTURAL_BRANCH_HEAD_MISMATCH")
        candidate, _ = self.artifacts.create_version(
            VersionCreateCommand(
                branch_id=branch.id,
                expected_head_version_id=source_artifact_version.id,
                content_hash=applied.content_hash,
                files=(preview,),
                provenance=provenance,
                rights=source_artifact_version.rights,
                created_by_type=CreatedByType.SYSTEM,
                created_by_id=f"auto-repair:{job.job_id}"[:200],
                created_at=datetime.now(UTC),
                primary_file_id=preview.id,
                design_document_version_id=design_version_id,
                quality_score=None,
                constraint_snapshot_hash=source.constraint_snapshot_hash,
                lineage_sources=(
                    (source_artifact_version.id, LineageEdgeType.EDITED_FROM),
                ),
            )
        )
        return RepairCandidate(
            artifact_version_id=str(candidate.id),
            artifact_content_hash=candidate.content_hash,
            repair_branch_id=str(candidate.branch_id),
            changed_node_ids=tuple(str(item) for item in applied.changed_node_ids),
            metadata={
                "design_document_version_id": str(design_version_id),
                "design_operation_id": str(applied.operation_id),
                "design_revision": applied.new_revision,
            },
        )

    def _persist_candidate_design_version(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
        parent_version_id: UUID,
        document: DesignIRDocument,
        content_hash: str,
    ) -> UUID:
        with self._transaction():
            design = self.session.scalar(
                select(DesignDocumentModel)
                .where(
                    DesignDocumentModel.id == design_document_id,
                    DesignDocumentModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if design is None:
                raise KeyError("REPAIR_DESIGN_DOCUMENT_NOT_FOUND")
            max_version = self.session.scalar(
                select(func.max(DesignDocumentVersionModel.version_number)).where(
                    DesignDocumentVersionModel.design_document_id == design_document_id,
                    DesignDocumentVersionModel.organization_id == organization_id,
                )
            )
            version_id = new_uuid7()
            self.session.add(
                DesignDocumentVersionModel(
                    id=version_id,
                    organization_id=organization_id,
                    design_document_id=design_document_id,
                    version_number=int(max_version or 0) + 1,
                    parent_version_id=parent_version_id,
                    content_json=document.model_dump(mode="json"),
                    content_hash=content_hash,
                    created_by=None,
                )
            )
            self.session.flush()
        return version_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    @staticmethod
    def _normalize_preview(
        preview: ArtifactFile,
        job: AutoRepairJob,
    ) -> ArtifactFile:
        if not preview.mime_type.startswith("image/"):
            raise ValueError("REPAIR_PREVIEW_IMAGE_REQUIRED")
        metadata = dict(preview.metadata)
        metadata["repair_job_id"] = job.job_id
        metadata["repair_preview"] = "true"
        for ref in job.original_source.protected_refs:
            existing = metadata.get("protected_refs", "")
            values = {item for item in existing.split(",") if item}
            values.add(ref)
            metadata["protected_refs"] = ",".join(sorted(values))
        return preview.model_copy(
            update={
                "id": new_uuid7(),
                "metadata": tuple(sorted(metadata.items())),
            }
        )

    def _compile_operations(
        self,
        document: DesignIRDocument,
        plan: RepairPlan,
    ) -> tuple[DesignOperation, ...]:
        nodes = node_index(document)
        operations: list[DesignOperation] = []
        for directive in plan.directives:
            try:
                node_id = UUID(directive.target)
            except ValueError as exc:
                raise ValueError("REPAIR_STRUCTURAL_TARGET_UUID_REQUIRED") from exc
            node = nodes.get(node_id)
            if node is None:
                raise ValueError("REPAIR_STRUCTURAL_TARGET_NOT_FOUND")
            params = directive.parameters
            action = directive.action_type
            if action == "REPLACE_TEXT":
                if not isinstance(node, TextNode):
                    raise ValueError("REPAIR_REPLACE_TEXT_TARGET_INVALID")
                operations.append(
                    SetTextOp(node_id=node_id, text=str(params["text"]))
                )
            elif action == "RESIZE_NODE":
                operations.append(
                    SetSizeOp(
                        node_id=node_id,
                        size=Size2D(
                            width=float(params["width"]),
                            height=float(params["height"]),
                        ),
                    )
                )
            elif action == "MOVE_NODE":
                updates = {}
                for key in ("x", "y", "rotation_deg"):
                    if key in params:
                        updates[key] = float(params[key])
                if not updates:
                    raise ValueError("REPAIR_MOVE_NODE_COORDINATES_REQUIRED")
                operations.append(
                    SetTransformOp(
                        node_id=node_id,
                        transform=node.transform.model_copy(update=updates),
                    )
                )
            elif action == "SET_FONT":
                if not isinstance(node, TextNode):
                    raise ValueError("REPAIR_SET_FONT_TARGET_INVALID")
                style_updates = {
                    key: params[key]
                    for key in (
                        "font_family",
                        "font_size",
                        "font_weight",
                        "italic",
                        "line_height",
                        "letter_spacing",
                        "align",
                        "vertical_align",
                    )
                    if key in params
                }
                if not style_updates:
                    raise ValueError("REPAIR_SET_FONT_FIELDS_REQUIRED")
                operations.append(
                    SetTextStyleOp(
                        node_id=node_id,
                        style=node.style.model_copy(update=style_updates),
                    )
                )
            elif action == "SET_SPACING":
                if not isinstance(node, TextNode):
                    raise ValueError("REPAIR_SET_SPACING_TARGET_INVALID")
                spacing = {
                    key: float(params[key])
                    for key in ("line_height", "letter_spacing")
                    if key in params
                }
                if not spacing:
                    raise ValueError("REPAIR_SET_SPACING_FIELDS_REQUIRED")
                operations.append(
                    SetTextStyleOp(
                        node_id=node_id,
                        style=node.style.model_copy(update=spacing),
                    )
                )
            elif action == "SET_COLOR":
                color = _color(params)
                if isinstance(node, TextNode):
                    operations.append(
                        SetTextStyleOp(
                            node_id=node_id,
                            style=node.style.model_copy(update={"color": color}),
                        )
                    )
                else:
                    operations.append(
                        SetFillOp(node_id=node_id, fill=SolidPaint(color=color))
                    )
            elif action == "REPLACE_ASSET":
                if not isinstance(node, ImageNode):
                    raise ValueError("REPAIR_REPLACE_ASSET_TARGET_INVALID")
                if "asset_id" not in params:
                    raise ValueError("REPAIR_REPLACE_ASSET_ID_REQUIRED")
                operations.append(
                    SetImageAssetOp(
                        node_id=node_id,
                        asset_id=UUID(str(params["asset_id"])),
                    )
                )
            elif action == "SET_PROPERTY":
                operations.extend(self._compile_property(node_id, node, params))
            else:
                raise ValueError(f"REPAIR_STRUCTURAL_ACTION_UNSUPPORTED:{action}")
        if not operations:
            raise ValueError("REPAIR_STRUCTURAL_OPERATIONS_REQUIRED")
        return tuple(operations)

    @staticmethod
    def _compile_property(
        node_id: UUID,
        node,
        params: dict,
    ) -> tuple[DesignOperation, ...]:
        prop = str(params.get("property", ""))
        value = params.get("value")
        if prop == "visible":
            if not isinstance(value, bool):
                raise ValueError("REPAIR_VISIBLE_BOOL_REQUIRED")
            return (SetAppearanceOp(node_id=node_id, visible=value),)
        if prop == "opacity":
            return (SetAppearanceOp(node_id=node_id, opacity=float(value)),)
        if prop == "locked":
            if not isinstance(value, bool):
                raise ValueError("REPAIR_LOCKED_BOOL_REQUIRED")
            return (SetLockOp(node_id=node_id, locked=value),)
        if prop == "name":
            return (RenameNodeOp(node_id=node_id, name=str(value)),)
        if prop in {"x", "y", "rotation_deg"}:
            return (
                SetTransformOp(
                    node_id=node_id,
                    transform=node.transform.model_copy(
                        update={prop: float(value)}
                    ),
                ),
            )
        raise ValueError(f"REPAIR_SET_PROPERTY_NOT_ALLOWLISTED:{prop}")


def _color(params: dict) -> RgbaColor:
    value = params.get("color")
    if isinstance(value, dict):
        return RgbaColor.model_validate(value)
    if isinstance(value, str) and value.startswith("#"):
        raw = value[1:]
        if len(raw) not in {6, 8}:
            raise ValueError("REPAIR_COLOR_HEX_INVALID")
        try:
            channels = [int(raw[index : index + 2], 16) for index in range(0, len(raw), 2)]
        except ValueError as exc:
            raise ValueError("REPAIR_COLOR_HEX_INVALID") from exc
        if len(channels) == 3:
            channels.append(255)
        return RgbaColor(
            r=channels[0] / 255,
            g=channels[1] / 255,
            b=channels[2] / 255,
            a=channels[3] / 255,
        )
    raise ValueError("REPAIR_COLOR_REQUIRED")
