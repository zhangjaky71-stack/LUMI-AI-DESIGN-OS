# LUMI Export Engine — NODE-49

Exact-version export control plane for approved ArtifactVersions.

NODE-49 owns export planning, exact immutable snapshots, renderer selection, deterministic package/manifest creation, checksum verification and download-grant lifecycle. NODE-42 remains Artifact truth, NODE-19 remains durable worker truth, and object storage remains the binary authority.

Export requests never resolve `latest`, branch head, or mutable Artifact state after planning. Short-lived download URLs/tokens are response-only and must never be persisted in job, manifest, logs or database rows.
