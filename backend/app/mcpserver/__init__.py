"""MCP server of the RAG ("bazi-rag"): the library, the answering harness, chart facts and the
reviewed glossary as read-only tools for any MCP client (docs/09 · MCP).

Two ways in, same tools:

* HTTP, inside the API: ``POST /api/v1/mcp/`` (Streamable HTTP, stateless, JSON responses),
  ``Authorization: Bearer <MCP_TOKEN>``; off unless ``MCP_TOKEN`` and ``MCP_USER_EMAIL`` are set.
* stdio, for a local client (Claude Code/Desktop): ``python -m backend.app.mcpserver``.

The tools act as ``MCP_USER_EMAIL``: row-level security and the library's visibility rules
apply to that account exactly as in the web app.
"""
