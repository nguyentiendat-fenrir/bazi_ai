"""What the tools run on: the account they act as, retrieval, Qwen, the glossary."""
from __future__ import annotations

from functools import cached_property
import uuid

from sqlalchemy import text

from ..answering.adapters import QwenModel, RagRetriever
from ..answering.glossary_index import GlossaryIndex
from ..answering.ports import Model, Retriever
from ..auth.service import Principal
from ..knowledge.glossary import read
from ..rag.llm import config_from


class Unavailable(Exception):
    """A tool cannot run here (not configured, account disabled); the message is for the client."""


class Backend:
    """Built from the API's state (shared engine, RAG service and CPU models) or standalone."""

    def __init__(self, engine, settings, rag_service):
        self.engine, self.settings, self.rag = engine, settings, rag_service

    def principal(self) -> Principal:
        """Looked up on every call, so disabling the account stops the tools at once."""
        email = self.settings.mcp_user_email
        if not email:
            raise Unavailable('MCP_USER_EMAIL is not configured')
        with self.engine.begin() as conn:
            user = conn.execute(text('SELECT id, email, role FROM users WHERE email = :e AND enabled'),
                                {'e': email}).mappings().first()
        if user is None:
            raise Unavailable(f'the MCP account {email} does not exist or is disabled')
        return Principal(user['id'], user['email'], user['role'], uuid.UUID(int=0), '')

    def retriever(self) -> Retriever:
        if self.rag is None:
            raise Unavailable('retrieval is not available in this process')
        return RagRetriever(self.rag, self.principal())

    def model(self) -> Model:
        config = config_from(self.settings)
        if config is None:
            raise Unavailable('the LLM is not configured (LLM_BASE_URL, LLM_MODEL)')
        return QwenModel(config)

    @cached_property
    def glossary(self) -> GlossaryIndex:
        return GlossaryIndex(self.concepts)

    @cached_property
    def concepts(self) -> list[dict]:
        return read()['concepts']
