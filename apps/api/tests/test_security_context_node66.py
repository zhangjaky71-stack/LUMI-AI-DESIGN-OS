from __future__ import annotations

import pytest

from lumi_api.security import ContextEnvelope, ContextTrust


def _envelope(**kwargs):
    return ContextEnvelope.from_text(
        trust=ContextTrust.EXTERNAL_UNTRUSTED,
        source_type="web_page",
        source_ref="https://example.test/research?utm_source=fixture#section",
        text="untrusted fixture body",
        **kwargs,
    )


def test_context_source_ref_drops_nonessential_url_query_and_fragment() -> None:
    envelope = _envelope(metadata={"mime_type": "text/html", "status": 200})
    assert envelope.source_ref == "https://example.test/research"
    assert envelope.metadata == {"mime_type": "text/html", "status": 200}


def test_context_metadata_rejects_raw_prompt_or_document_content() -> None:
    with pytest.raises(ValueError, match="METADATA_SENSITIVE_KEY_FORBIDDEN"):
        _envelope(metadata={"raw_content": "customer document"})
    with pytest.raises(ValueError, match="METADATA_SENSITIVE_KEY_FORBIDDEN"):
        _envelope(metadata={"nested": {"system_prompt": "ignore policy"}})


def test_context_metadata_rejects_secret_shaped_values_even_under_innocent_key() -> None:
    with pytest.raises(ValueError, match="METADATA_SECRET_VALUE_FORBIDDEN"):
        _envelope(metadata={"note": "Bearer raw-access-token"})
    with pytest.raises(ValueError, match="METADATA_SECRET_VALUE_FORBIDDEN"):
        _envelope(metadata={"note": "sk-live-secret"})


def test_context_metadata_has_depth_item_and_string_bounds() -> None:
    with pytest.raises(ValueError, match="METADATA_ITEMS_EXCEEDED"):
        _envelope(metadata={f"k{index}": index for index in range(33)})
    with pytest.raises(ValueError, match="METADATA_VALUE_TOO_LONG"):
        _envelope(metadata={"label": "x" * 513})
    with pytest.raises(ValueError, match="METADATA_DEPTH_EXCEEDED"):
        _envelope(metadata={"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}})


def test_context_metadata_rejects_binary_and_unknown_object_types() -> None:
    with pytest.raises(ValueError, match="METADATA_BINARY_FORBIDDEN"):
        _envelope(metadata={"blob": b"secret"})
    with pytest.raises(ValueError, match="METADATA_TYPE_FORBIDDEN"):
        _envelope(metadata={"object": object()})
