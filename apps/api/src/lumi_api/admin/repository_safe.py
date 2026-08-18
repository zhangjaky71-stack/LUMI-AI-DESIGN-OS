from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from lumi_api.domain.ids import new_uuid7

from .contracts import FeatureFlag, PlatformAdminConflict
from .repository import PostgresPlatformAdminRepository as _BaseRepository


class PostgresPlatformAdminRepository(_BaseRepository):
    """Race-safe feature-flag writes on top of the read/control repository."""

    def upsert_feature_flag(
        self,
        *,
        actor_user_id: UUID,
        flag_key: str,
        scope: str,
        target_id: str | None,
        value: dict[str, Any],
        owner: str,
        reason: str,
        expires_at: datetime | None,
    ) -> FeatureFlag:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
        with self.transaction():
            existing = self.session.execute(
                text(
                    """
                    SELECT * FROM platform_feature_flags
                    WHERE flag_key=:key AND scope=:scope
                      AND target_id IS NOT DISTINCT FROM :target
                    FOR UPDATE
                    """
                ),
                {"key": flag_key, "scope": scope, "target": target_id},
            ).mappings().one_or_none()
            if existing is not None:
                if bool(existing["security_locked"]):
                    raise PlatformAdminConflict("ADMIN_SECURITY_FLAG_IMMUTABLE")
                row = self.session.execute(
                    text(
                        """
                        UPDATE platform_feature_flags
                        SET value_json=CAST(:value AS jsonb), owner=:owner, reason=:reason,
                            expires_at=:expires, updated_by_user_id=:actor,
                            updated_at=now(), version=version+1
                        WHERE id=:id
                        RETURNING *
                        """
                    ),
                    {
                        "value": payload,
                        "owner": owner,
                        "reason": reason,
                        "expires": expires_at,
                        "actor": actor_user_id,
                        "id": existing["id"],
                    },
                ).mappings().one()
            else:
                row = self.session.execute(
                    text(
                        """
                        INSERT INTO platform_feature_flags(
                          id,flag_key,scope,target_id,value_json,owner,reason,security_locked,
                          expires_at,created_by_user_id,updated_by_user_id,created_at,updated_at,version
                        ) VALUES(
                          :id,:key,:scope,:target,CAST(:value AS jsonb),:owner,:reason,false,
                          :expires,:actor,:actor,now(),now(),1
                        ) RETURNING *
                        """
                    ),
                    {
                        "id": new_uuid7(),
                        "key": flag_key,
                        "scope": scope,
                        "target": target_id,
                        "value": payload,
                        "owner": owner,
                        "reason": reason,
                        "expires": expires_at,
                        "actor": actor_user_id,
                    },
                ).mappings().one()
        return self._flag(row)
