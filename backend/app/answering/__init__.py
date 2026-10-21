"""Answering harness: steps 3–8 of the answering rules (docs/09 · Answering harness).

One question goes through: risk guard → chart facts (``calc.pillar_facts``) → the
needs to know (concepts from the reviewed glossary, sub-questions, chart analysis
B3–B7 per school, the question itself) → an evidence loop (retrieve per need,
the model judges each need with verbatim quotes, code verifies the quotes,
targeted re-queries for what is missing; at most 7 rounds, early stops) →
analysis per school → synthesis with "góc nhìn khác" → per-claim validation →
an answer built by code from the claims that survived, plus a full trace.

The harness only talks to two ports (``ports.Model``, ``ports.Retriever``), so the
whole flow runs in tests with scripted fakes; ``adapters`` binds them to Qwen
(OpenAI-compatible) and to the RAG pilot's retrieval.
"""
