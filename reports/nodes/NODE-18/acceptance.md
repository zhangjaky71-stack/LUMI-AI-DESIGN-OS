# NODE-18 — Asset Storage Acceptance

Status: **IMPLEMENTED / VALIDATING**  
Hosted status: **pending actual runner execution**

## Implemented

- S3-compatible `ObjectStore` boundary and deterministic Memory adapter.
- Dependency-free SigV4 short-lived signed PUT/GET, HEAD, multipart, copy and delete-candidate operations.
- Canonical tenant/project/asset/file object-key strategy.
- Browser-direct upload REST contract; no FastAPI binary `UploadFile` route.
- UploadSession lifecycle with single PUT and multipart modes.
- Pre-sign file-size and organization-quota checks.
- Complete-upload object existence/length/storage-checksum checks.
- Worker-side streaming SHA-256 over actual stored bytes.
- Magic-byte MIME sniffing independent of extension and declared Content-Type.
- PNG/JPEG/WebP, SVG, PDF, MP4/MOV/WebM and TTF/OTF/WOFF2 P0 recognition.
- Strict SVG active-content rejection and sanitized derived file.
- FileScanner boundary, ClamAV command adapter and clamd INSTREAM adapter.
- Scanner-unavailable fail-closed policy.
- Safe image/video metadata extraction; raw EXIF/GPS is not exposed by default.
- Preview pipeline contract plus ffmpeg and deterministic adapters.
- READY-only authorized signed downloads with short TTL.
- `USER_OWNED | LICENSED | UNKNOWN` rights assertion separate from commercial-use permission.
- Orphan upload TTL cleanup and multipart abort boundary.
- Frozen Asset Storage event names and repository audit boundary.
- Forward migration `20260816_0004` on NODE-17 `0003`.
- `asset_upload_sessions` and append-only `asset_validation_reports`.
- Asset/File/Preview/Rights metadata upgrade.
- RLS and canonical-key/same-tenant database triggers.
- Security/unit/HTTP/PostgreSQL test harnesses.
- Real MinIO round-trip and real clamd/EICAR test scripts.
- Eight machine-readable JSON Schema exports.
- Local Compose optional ClamAV security profile.

## Canonical validation required

```bash
uv sync --all-packages --frozen
PYTHONPATH=apps/api/src uv run python tools/node18/validate_asset_storage.py
PYTHONPATH=apps/api/src uv run pytest -q \
  apps/api/tests/test_asset_storage_contract.py \
  apps/api/tests/test_asset_security_contract.py \
  apps/api/tests/test_asset_http_contract.py \
  apps/api/tests/test_api_v1_contract.py
PYTHONPATH=apps/api/src uv run python tools/node18/export_asset_schemas.py
```

The hosted gate must additionally execute a real local-infrastructure path:

```text
start PostgreSQL + MinIO + ClamAV security profile
initialize lumi-assets bucket
upgrade Alembic through 0003 and load deterministic two-tenant fixture
upgrade 0004
run NODE-10 baseline DB invariants at current head
run tools/node18/test_asset_database.py
run tools/node18/test_minio_roundtrip.py
run tools/node18/test_clamd.py
rollback to 0003 and verify NODE-17 survives
reapply 0004 and rerun NODE-18 DB invariants
Ruff + Pyright
```

## Required evidence before COMPLETE

- Python 3.12 frozen dependency install actually succeeds.
- Asset validator executes green.
- Unit/security/HTTP tests execute green.
- Eight exported schemas parse successfully.
- Ruff executes green.
- Pyright executes green.
- MinIO signed upload/download/copy/delete round trip executes green.
- clamd clean + EICAR detection executes green.
- PostgreSQL `0004` upgrade/RLS/guards/append-only/downgrade/reapply execute green.
- Repository CI/security gates execute green.
- NODE-09 through NODE-17 stacked dependencies resolve.

## Explicit gaps

See `reports/nodes/NODE-18/gap-ledger.json`.

In particular, an application-wired async PostgreSQL `AssetRepository` and queue-backed validation/preview execution are not claimed by the existence of the schema and pure service contract. NODE-19 owns queue/event runtime integration.

## Completion rule

A workflow file, static review, or GitHub job that never received a runner is not PASS. `runner_id=0 / steps=[]` must be classified `BLOCKED_EXTERNAL`.

Next: **NODE-19 — Queue / Event Runtime**.
