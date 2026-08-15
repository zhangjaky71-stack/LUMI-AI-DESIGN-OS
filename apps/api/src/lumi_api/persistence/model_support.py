# pyright: reportMissingImports=false, reportMissingModuleSource=false
from sqlalchemy import text

JSON_OBJECT_DEFAULT = text("'{}'::jsonb")
JSON_ARRAY_DEFAULT = text("'[]'::jsonb")
