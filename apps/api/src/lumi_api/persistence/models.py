# pyright: reportMissingImports=false, reportMissingModuleSource=false
from sqlalchemy import Index

from . import models_identity as _models_identity
from .models_artifacts import ArtifactEdgeModel, ArtifactVersionModel
from .models_execution import AgentRunModel, ProviderRequestModel, TaskDependencyModel, TaskModel
from .models_platform import CostLedgerModel, OutboxEventModel
from .models_projects_assets import AssetModel, ProjectModel

# Keep this referenced so linters see metadata-registration side effects as intentional.
_METADATA_MODULES = (_models_identity,)

# Query-driven indexes. Plain organization_id indexes come from TenantMixin.
Index("ix_projects_org_created", ProjectModel.organization_id, ProjectModel.created_at)
Index("ix_projects_org_status", ProjectModel.organization_id, ProjectModel.status)
Index("ix_assets_org_created", AssetModel.organization_id, AssetModel.created_at)
Index(
    "ix_artifact_versions_artifact_version",
    ArtifactVersionModel.artifact_id,
    ArtifactVersionModel.version_number,
)
Index("ix_tasks_project_status", TaskModel.project_id, TaskModel.status)
Index("ix_tasks_project_created", TaskModel.project_id, TaskModel.created_at)
Index("ix_agent_runs_project_created", AgentRunModel.project_id, AgentRunModel.created_at)
Index("ix_provider_requests_native", ProviderRequestModel.provider_request_id)
Index("ix_outbox_unpublished_created", OutboxEventModel.published_at, OutboxEventModel.created_at)
Index("ix_cost_ledger_org_occurred", CostLedgerModel.organization_id, CostLedgerModel.occurred_at)
Index("ix_artifact_edges_to", ArtifactEdgeModel.to_artifact_version_id)
Index("ix_task_dependencies_depends_on", TaskDependencyModel.depends_on_task_id)
