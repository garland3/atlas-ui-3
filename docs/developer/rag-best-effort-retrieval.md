# RAG Best-Effort Retrieval

Last updated: 2026-02-01

## Overview

When multiple RAG data sources are selected, the system queries **all** of them
with best-effort semantics. If an individual data source fails (timeout,
authorization error, service unavailable, etc.), the failure is logged and the
remaining sources are still queried. The LLM receives context from every source
that succeeded.

## Behavior Summary

| Scenario | Result |
|---|---|
| All sources succeed | Context from every source is injected into the LLM prompt |
| Some sources fail | Context from successful sources is used; failures noted in metadata |
| All sources fail | Falls back to plain LLM call (no RAG context) |

This applies to both `call_with_rag` (plain RAG) and `call_with_rag_and_tools`
(RAG + tool-use) code paths in `backend/modules/llm/litellm_caller.py`.

## Metadata Reporting

When partial failures occur, the response metadata footer includes a
**Failed Sources (best-effort)** section listing each source that failed and the
error message. This gives users visibility into which sources were unavailable.

## MCP-Based RAG

The MCP-based RAG aggregator (`backend/domain/rag_mcp_service.py`) already
implemented per-server best-effort semantics before this change. The work here
brings the legacy `RAGClient`-based flow to parity.

## Related

- Issue: #266
- Legacy RAG client: `backend/modules/rag/client.py`
- MCP RAG service: `backend/domain/rag_mcp_service.py`
- LLM caller: `backend/modules/llm/litellm_caller.py`
