"""Tests for best-effort RAG retrieval across multiple data sources.

Verifies that when one or more RAG data sources fail, the system still
queries the remaining sources and returns the best available result
(issue #266).
"""

import os
import sys
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.rag.client import RAGResponse, RAGMetadata, DocumentMetadata


def _make_rag_response(source_name: str) -> RAGResponse:
    """Build a minimal RAGResponse for testing."""
    return RAGResponse(
        content=f"Context from {source_name}",
        metadata=RAGMetadata(
            query_processing_time_ms=10,
            total_documents_searched=5,
            documents_found=[
                DocumentMetadata(
                    source=source_name,
                    content_type="text",
                    confidence_score=0.9,
                )
            ],
            data_source_name=source_name,
            retrieval_method="vector",
        ),
    )


class FakeRAGClient:
    """RAG client stub that can be configured to fail on specific sources."""

    def __init__(self, failing_sources: List[str] | None = None):
        self.failing_sources = set(failing_sources or [])
        self.queried_sources: List[str] = []

    async def query_rag(self, user_name: str, data_source: str, messages: List[Dict]) -> RAGResponse:
        self.queried_sources.append(data_source)
        if data_source in self.failing_sources:
            raise Exception(f"Simulated failure for {data_source}")
        return _make_rag_response(data_source)


@pytest.fixture
def caller():
    """Create a LiteLLMCaller with mocked config."""
    fake_model_config = type("M", (), {
        "model_name": "test-model",
        "model_url": "https://api.openai.com/v1",
        "max_tokens": 100,
        "temperature": 0.7,
        "api_key": "fake-key",
        "extra_headers": None,
    })()
    fake_llm_config = type("C", (), {"models": {"test-model": fake_model_config}})()

    from modules.llm.litellm_caller import LiteLLMCaller
    return LiteLLMCaller(llm_config=fake_llm_config, debug_mode=False)


# ---------------------------------------------------------------------------
# call_with_rag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_with_rag_all_sources_succeed(caller):
    """All sources succeed - context from each should be included."""
    rag = FakeRAGClient()
    with patch.object(caller, "call_plain", new_callable=AsyncMock, return_value="LLM answer"):
        result = await caller.call_with_rag(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a", "src_b", "src_c"],
            user_email="user@test.com",
            rag_client=rag,
        )

    assert rag.queried_sources == ["src_a", "src_b", "src_c"]
    # The LLM response should be present
    assert "LLM answer" in result
    # RAG metadata section should be present (one entry per source)
    assert "RAG Sources & Processing Info" in result


@pytest.mark.asyncio
async def test_call_with_rag_partial_failure(caller):
    """One source fails, others succeed - result still includes successful context."""
    rag = FakeRAGClient(failing_sources=["src_b"])
    with patch.object(caller, "call_plain", new_callable=AsyncMock, return_value="LLM answer") as mock_plain:
        result = await caller.call_with_rag(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a", "src_b", "src_c"],
            user_email="user@test.com",
            rag_client=rag,
        )

    # All three sources were attempted
    assert rag.queried_sources == ["src_a", "src_b", "src_c"]
    # call_plain was invoked (not the fallback without RAG context)
    mock_plain.assert_called_once()
    # The messages passed to call_plain should have context from src_a and src_c
    call_messages = mock_plain.call_args[0][1]
    context_msgs = [m for m in call_messages if m["role"] == "system" and "Retrieved context" in m["content"]]
    assert len(context_msgs) == 2
    source_names = [m["content"] for m in context_msgs]
    assert any("src_a" in s for s in source_names)
    assert any("src_c" in s for s in source_names)
    # Failed source info should appear in the metadata footer
    assert "src_b" in result
    assert "Failed Sources" in result


@pytest.mark.asyncio
async def test_call_with_rag_all_sources_fail(caller):
    """All sources fail - falls back to plain LLM call."""
    rag = FakeRAGClient(failing_sources=["src_a", "src_b"])
    with patch.object(caller, "call_plain", new_callable=AsyncMock, return_value="plain fallback") as mock_plain:
        result = await caller.call_with_rag(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a", "src_b"],
            user_email="user@test.com",
            rag_client=rag,
        )

    assert rag.queried_sources == ["src_a", "src_b"]
    assert result == "plain fallback"
    # call_plain should have been called with original messages (no RAG context)
    call_messages = mock_plain.call_args[0][1]
    assert not any("Retrieved context" in m.get("content", "") for m in call_messages)


@pytest.mark.asyncio
async def test_call_with_rag_single_source_still_works(caller):
    """Backward-compatible: single source behaves like before."""
    rag = FakeRAGClient()
    with patch.object(caller, "call_plain", new_callable=AsyncMock, return_value="answer"):
        result = await caller.call_with_rag(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["only_one"],
            user_email="user@test.com",
            rag_client=rag,
        )

    assert rag.queried_sources == ["only_one"]
    assert "answer" in result


@pytest.mark.asyncio
async def test_call_with_rag_empty_sources_calls_plain(caller):
    """Empty data_sources list should call plain LLM directly."""
    with patch.object(caller, "call_plain", new_callable=AsyncMock, return_value="plain") as mock_plain:
        result = await caller.call_with_rag(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=[],
            user_email="user@test.com",
        )
    assert result == "plain"
    mock_plain.assert_called_once()


# ---------------------------------------------------------------------------
# call_with_rag_and_tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_with_rag_and_tools_partial_failure(caller):
    """RAG+tools: partial source failure still enriches context."""
    from modules.llm.models import LLMResponse

    rag = FakeRAGClient(failing_sources=["src_b"])
    fake_llm_resp = LLMResponse(content="tool answer", model_used="test-model")

    with patch.object(caller, "call_with_tools", new_callable=AsyncMock, return_value=fake_llm_resp) as mock_tools:
        result = await caller.call_with_rag_and_tools(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a", "src_b"],
            tools_schema=[{"type": "function", "function": {"name": "test"}}],
            user_email="user@test.com",
            rag_client=rag,
        )

    assert rag.queried_sources == ["src_a", "src_b"]
    mock_tools.assert_called_once()
    # Messages passed should have context from src_a only
    call_messages = mock_tools.call_args[0][1]
    context_msgs = [m for m in call_messages if m["role"] == "system" and "Retrieved context" in m["content"]]
    assert len(context_msgs) == 1
    assert "src_a" in context_msgs[0]["content"]
    # Failed source info in metadata
    assert "src_b" in result.content
    assert "Failed Sources" in result.content


@pytest.mark.asyncio
async def test_call_with_rag_and_tools_all_fail(caller):
    """RAG+tools: all sources fail - falls back to tools-only call."""
    from modules.llm.models import LLMResponse

    rag = FakeRAGClient(failing_sources=["src_a", "src_b"])
    fake_llm_resp = LLMResponse(content="tools only", model_used="test-model")

    with patch.object(caller, "call_with_tools", new_callable=AsyncMock, return_value=fake_llm_resp) as mock_tools:
        result = await caller.call_with_rag_and_tools(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a", "src_b"],
            tools_schema=[{"type": "function", "function": {"name": "test"}}],
            user_email="user@test.com",
            rag_client=rag,
        )

    # Fallback: original messages without RAG context
    call_messages = mock_tools.call_args[0][1]
    assert not any("Retrieved context" in m.get("content", "") for m in call_messages)
    assert result.content == "tools only"


@pytest.mark.asyncio
async def test_call_with_rag_and_tools_no_metadata_when_tool_calls(caller):
    """RAG+tools: metadata not appended when response has tool calls."""
    from modules.llm.models import LLMResponse

    rag = FakeRAGClient()
    fake_llm_resp = LLMResponse(
        content="calling tool",
        tool_calls=[{"id": "1", "function": {"name": "test", "arguments": "{}"}}],
        model_used="test-model",
    )

    with patch.object(caller, "call_with_tools", new_callable=AsyncMock, return_value=fake_llm_resp):
        result = await caller.call_with_rag_and_tools(
            model_name="test-model",
            messages=[{"role": "user", "content": "hello"}],
            data_sources=["src_a"],
            tools_schema=[{"type": "function", "function": {"name": "test"}}],
            user_email="user@test.com",
            rag_client=rag,
        )

    # No metadata appended when tool calls are present
    assert "RAG Sources" not in result.content
