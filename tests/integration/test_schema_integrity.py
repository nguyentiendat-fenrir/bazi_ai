"""M004–M007 integrity at head: review lifecycle, registry, chat cycle, jobs, seed.

Raw SQL against PostgreSQL; needs ``BAZI_TEST_DATABASE_URL`` (tests/integration/db.py).
"""
import json
from pathlib import Path
import re
import unittest
import uuid

import psycopg
from psycopg import errors

from tests.integration.db import (ROOT, alembic, create_database, database_url, drop_database,
                                  migrated_database, sha)
from tests.integration.factories import Factory

DB_NAME = None
SPEC = ROOT / 'docs' / '04_DATABASE_SCHEMA.md'
INTERNAL_TABLES = {'alembic_version', 'entity_registry'}


def setUpModule():
    global DB_NAME
    DB_NAME = migrated_database('head')


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)


class Knowledge(Factory):
    def school(self, key='manh_phai'):
        return self.one('SELECT id FROM schools WHERE key = %s', key)

    def review(self, kind, entity, decision='approve', reviewer=None):
        return self.one('INSERT INTO reviews (entity_kind, entity_id, reviewer_id, decision, reason,'
                        " base_revision) VALUES (%s, %s, %s, %s, 'checked', 1) RETURNING id",
                        kind, entity, reviewer or self.user(), decision)

    def approve(self, table, kind, entity):
        self.conn.execute(f"UPDATE {table} SET state = 'in_review' WHERE id = %s", (entity,))
        self.review(kind, entity)
        self.conn.execute(f"UPDATE {table} SET state = 'approved' WHERE id = %s", (entity,))

    def method(self, school=None, approved=True):
        school = school or self.school()
        method = self.one("INSERT INTO methods (school_id, key, revision, description)"
                          " VALUES (%s, %s, 1, 'm') RETURNING id", school, uuid.uuid4().hex)
        if approved:
            self.approve('methods', 'method', method)
        return method

    def evidence(self, start=0, end=5):
        version = self.book_version()
        revision = self.revision(self.page(version))
        block = self.block(revision, start=0, end=10)
        text = self.one('SELECT normalized_text FROM page_revisions WHERE id = %s', revision)
        evidence = self.one('INSERT INTO evidence_spans (book_version_id, page_revision_id,'
                            ' block_id, start_offset, end_offset, quote_hash, speaker_layer, origin)'
                            " VALUES (%s, %s, %s, %s, %s, %s, 'original_author', 'source_explicit')"
                            ' RETURNING id', version, revision, block, start, end,
                            sha(text[start:end]))
        return dict(evidence=evidence, version=version, revision=revision, block=block)

    def rule(self, method=None, school=None):
        school = school or self.school()
        method = method or self.method(school)
        dsl = json.dumps({'when': {'fact': 'pillars.day.stem'}, 'emit': 'x'})
        return self.one('INSERT INTO knowledge_rules (rule_key, revision, school_id, method_id,'
                        ' dsl, dsl_hash, fact_schema_version, author_id) VALUES (%s, 1, %s, %s,'
                        " %s::jsonb, bazi_sha256_text(%s::jsonb::text), 'chart-facts/1', %s)"
                        ' RETURNING id', uuid.uuid4().hex, school, method, dsl, dsl, self.user())

    def conversation(self, owner=None):
        owner = owner or self.user()
        conversation = self.one('INSERT INTO conversations (owner_id) VALUES (%s) RETURNING id',
                                owner)
        return owner, conversation

    def message(self, conversation, seq, role, status='completed'):
        return self.one('INSERT INTO messages (conversation_id, seq, role, status)'
                        ' VALUES (%s, %s, %s, %s) RETURNING id', conversation, seq, role, status)


class SchemaTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(database_url(DB_NAME))
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.f = Knowledge(self.conn)

    def rejects(self, error, query, *params):
        with self.assertRaises(error):
            with self.conn.transaction():
                self.conn.execute(query, params)


class ContractTests(SchemaTestCase):
    def test_every_documented_table_exists(self):
        documented = set(re.findall(r'^### `([a-z_]+)`$', SPEC.read_text('utf-8'), re.M))
        tables = {r[0] for r in self.conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        # embeddings_<collection> are provisioned per profile by the registry (T016).
        self.assertEqual(documented, tables - INTERNAL_TABLES)

    def test_every_foreign_key_is_indexed(self):
        missing = self.conn.execute("""
            SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c
            WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace AND NOT EXISTS (
                SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid
                  AND (i.indkey::int2[])[0] = c.conkey[1])""").fetchall()
        self.assertEqual(missing, [])

    def test_seed_is_structural_only(self):
        counts = self.conn.execute("""
            SELECT (SELECT count(*) FROM knowledge_rules), (SELECT count(*) FROM assertions),
                   (SELECT count(*) FROM evidence_spans), (SELECT count(*) FROM cases),
                   (SELECT count(*) FROM concepts c JOIN schools s ON s.id = c.school_id
                    WHERE s.key <> 'tu_tru'),
                   (SELECT count(*) FROM concepts WHERE state = 'approved'),
                   (SELECT string_agg(key, ',' ORDER BY key) FROM schools),
                   (SELECT state FROM ontology_releases WHERE version = 'seed-1')""").fetchone()
        self.assertEqual(counts, (0, 0, 0, 0, 0, 27, 'manh_phai,tu_binh,tu_tru', 'published'))
        terms = {r[0] for r in self.conn.execute(
            "SELECT t.form_nfc FROM terms t JOIN concepts c ON c.id = t.concept_id"
            " WHERE c.canonical_key = 'can.giap'")}
        self.assertEqual(terms, {'Giáp', '甲'})
        folded = self.f.one("SELECT form_folded FROM terms WHERE form_nfc = 'Đinh'")
        self.assertEqual(folded, 'dinh')


class ReviewLifecycleTests(SchemaTestCase):
    def test_rules_cannot_be_born_approved(self):
        school = self.f.school()
        method = self.f.method(school)
        self.rejects(errors.CheckViolation, 'INSERT INTO knowledge_rules (rule_key, revision,'
                     " school_id, method_id, dsl, dsl_hash, fact_schema_version, state, author_id)"
                     " VALUES ('r', 1, %s, %s, '{}', bazi_sha256_text('{}'), 'v', 'approved', %s)",
                     school, method, self.f.user())

    def test_approval_needs_review_and_source(self):
        rule = self.f.rule()
        self.conn.execute("UPDATE knowledge_rules SET state = 'in_review' WHERE id = %s", (rule,))
        self.rejects(errors.CheckViolation,
                     "UPDATE knowledge_rules SET state = 'approved' WHERE id = %s", rule)
        self.f.review('rule', rule)
        # Reviewed but without source evidence: still refused.
        self.rejects(errors.CheckViolation,
                     "UPDATE knowledge_rules SET state = 'approved' WHERE id = %s", rule)

    def test_reviewed_rule_with_source_is_approved_and_frozen(self):
        rule = self.f.rule()
        evidence = self.f.evidence()['evidence']
        self.conn.execute('INSERT INTO rule_sources (rule_id, evidence_id) VALUES (%s, %s)',
                          (rule, evidence))
        self.f.approve('knowledge_rules', 'rule', rule)
        self.rejects(errors.RestrictViolation,
                     "UPDATE knowledge_rules SET fact_schema_version = 'v2' WHERE id = %s", rule)
        self.rejects(errors.RestrictViolation, 'DELETE FROM rule_sources WHERE rule_id = %s', rule)
        self.rejects(errors.CheckViolation,
                     "UPDATE knowledge_rules SET state = 'draft' WHERE id = %s", rule)
        self.rejects(errors.CheckViolation,
                     "UPDATE knowledge_rules SET state = 'revoked' WHERE id = %s", rule)
        self.f.review('rule', rule, decision='revoke')
        self.conn.execute("UPDATE knowledge_rules SET state = 'revoked' WHERE id = %s", (rule,))

    def test_dsl_hash_must_match(self):
        self.rejects(errors.CheckViolation, 'INSERT INTO knowledge_rules (rule_key, revision,'
                     ' school_id, method_id, dsl, dsl_hash, fact_schema_version, author_id)'
                     " VALUES ('r', 1, %s, %s, '{\"a\": 1}', %s, 'v', %s)",
                     self.f.school(), self.f.method(), sha('other'), self.f.user())

    def test_method_school_must_match_assertion_school(self):
        method = self.f.method(self.f.school('manh_phai'))
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO assertions (assertion_key, revision,'
                     " school_id, method_id, statement, origin, author_id) VALUES ('a', 1, %s, %s,"
                     " 's', 'source_explicit', %s)", self.f.school('tu_binh'), method, self.f.user())

    def test_rule_dependencies_stay_acyclic(self):
        method = self.f.method()
        a, b, c = (self.f.rule(method=method) for _ in range(3))
        for rule, requires in ((a, b), (b, c)):
            self.conn.execute('INSERT INTO rule_dependencies (rule_id, requires_id)'
                              ' VALUES (%s, %s)', (rule, requires))
        self.rejects(errors.CheckViolation, 'INSERT INTO rule_dependencies (rule_id, requires_id)'
                     ' VALUES (%s, %s)', c, a)

    def test_ruleset_takes_only_approved_rules_of_its_method(self):
        school = self.f.school()
        method = self.f.method(school)
        ruleset = self.f.one('INSERT INTO rulesets (school_id, method_id, version)'
                             " VALUES (%s, %s, 'v1') RETURNING id", school, method)
        draft = self.f.rule(method=method, school=school)
        self.rejects(errors.CheckViolation, 'INSERT INTO ruleset_members (ruleset_id, rule_id,'
                     ' ordinal) VALUES (%s, %s, 0)', ruleset, draft)


class RegistryTests(SchemaTestCase):
    def test_unknown_kind_and_missing_target_rejected(self):
        reviewer = self.f.user()
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO reviews (entity_kind, entity_id,'
                     " reviewer_id, decision, reason, base_revision) VALUES ('spaceship', %s, %s,"
                     " 'approve', 'x', 1)", uuid.uuid4(), reviewer)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO reviews (entity_kind, entity_id,'
                     " reviewer_id, decision, reason, base_revision) VALUES ('rule', %s, %s,"
                     " 'approve', 'x', 1)", uuid.uuid4(), reviewer)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO review_items (entity_kind, entity_id,'
                     " reason_code, severity) VALUES ('concept', %s, 'x', 'low')", uuid.uuid4())

    def test_referenced_entity_cannot_be_deleted(self):
        concept = self.f.one("SELECT id FROM concepts WHERE canonical_key = 'chi.ty'")
        self.f.review('concept', concept, decision='reject')
        self.rejects(errors.ForeignKeyViolation, 'DELETE FROM concepts WHERE id = %s', concept)

    def test_reviews_and_audit_are_append_only(self):
        review = self.f.review('concept', self.f.one(
            "SELECT id FROM concepts WHERE canonical_key = 'can.at'"), decision='reject')
        self.rejects(errors.RestrictViolation, "UPDATE reviews SET reason = 'edited' WHERE id = %s",
                     review)
        audit = self.f.one("INSERT INTO audit_logs (action, trace_id, outcome)"
                           " VALUES ('login', 't', 'success') RETURNING id")
        self.rejects(errors.RestrictViolation, 'DELETE FROM audit_logs WHERE id = %s', audit)
        with self.conn.transaction():
            self.conn.execute("SET LOCAL bazi.retention = 'on'")
            self.conn.execute('DELETE FROM audit_logs WHERE id = %s', (audit,))

    def test_school_tree_has_no_cycles(self):
        root = self.f.school('tu_tru')
        child = self.f.school('manh_phai')
        self.rejects(errors.CheckViolation, 'UPDATE schools SET parent_id = %s WHERE id = %s',
                     child, root)


class EvidenceAndCitationTests(SchemaTestCase):
    def test_quote_hash_must_match_revision_text(self):
        e = self.f.evidence()
        self.rejects(errors.CheckViolation, 'INSERT INTO evidence_spans (book_version_id,'
                     ' page_revision_id, block_id, start_offset, end_offset, quote_hash,'
                     " speaker_layer, origin) VALUES (%s, %s, %s, 0, 5, %s, 'original_author',"
                     " 'source_explicit')", e['version'], e['revision'], e['block'], sha('bịa'))

    def test_evidence_revision_must_belong_to_version(self):
        e = self.f.evidence()
        text = self.f.one('SELECT normalized_text FROM page_revisions WHERE id = %s', e['revision'])
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO evidence_spans (book_version_id,'
                     ' page_revision_id, block_id, start_offset, end_offset, quote_hash,'
                     " speaker_layer, origin) VALUES (%s, %s, %s, 0, 5, %s, 'original_author',"
                     " 'source_explicit')", self.f.book_version(), e['revision'], e['block'],
                     sha(text[0:5]))

    def test_citation_must_come_from_the_release(self):
        e = self.f.evidence()
        collection = self.f.one('INSERT INTO embedding_collections (profile_id, dimension, distance,'
                                " physical_table, state) VALUES (%s, 4, 'cosine', %s, 'ready')"
                                ' RETURNING id', self.f.embedding_profile(),
                                f'embeddings_{uuid.uuid4().hex[:8]}')
        release = self.f.one('INSERT INTO corpus_releases (embedding_collection_id,'
                             " ontology_release_id, lexical_profile_version) SELECT %s, id, 'fts1'"
                             " FROM ontology_releases WHERE version = 'seed-1' RETURNING id",
                             collection)
        owner, conversation = self.f.conversation()
        message = self.f.message(conversation, 1, 'assistant')
        claim = self.f.one('INSERT INTO claims (message_id, local_key, text, kind, support_status,'
                           " inference_level) VALUES (%s, 'c1', 't', 'source_statement',"
                           " 'validated', 'direct') RETURNING id", message)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO citations (claim_id, evidence_id,'
                     " corpus_release_id, validation, display_snapshot) VALUES (%s, %s, %s, '{}',"
                     " '{}')", claim, e['evidence'], release)


class ChatTests(SchemaTestCase):
    def run_sql(self, conversation, owner, user_msg, assistant_msg):
        return ('INSERT INTO chat_runs (conversation_id, user_message_id, assistant_message_id,'
                " owner_id, mode, context_snapshot, prompt_version) VALUES (%s, %s, %s, %s,"
                " 'research', '{}', 'p1') RETURNING id", conversation, user_msg, assistant_msg, owner)

    def test_run_and_messages_created_together(self):
        owner, conversation = self.f.conversation()
        run_id, user_msg, assistant_msg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        # Run first, messages after: the deferred FKs accept the cycle at commit.
        self.conn.execute('INSERT INTO chat_runs (id, conversation_id, user_message_id,'
                          ' assistant_message_id, owner_id, mode, context_snapshot, prompt_version)'
                          " VALUES (%s, %s, %s, %s, %s, 'research', '{}', 'p1')",
                          (run_id, conversation, user_msg, assistant_msg, owner))
        for seq, (mid, role) in enumerate(((user_msg, 'user'), (assistant_msg, 'assistant')), 1):
            self.conn.execute('INSERT INTO messages (id, conversation_id, seq, role, status, run_id)'
                              " VALUES (%s, %s, %s, %s, 'pending', %s)",
                              (mid, conversation, seq, role, run_id))
        self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_swapped_roles_fail_at_commit(self):
        owner, conversation = self.f.conversation()
        user_msg = self.f.message(conversation, 1, 'user')
        assistant_msg = self.f.message(conversation, 2, 'assistant')
        query, *params = self.run_sql(conversation, owner, assistant_msg, user_msg)
        with self.assertRaises(errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(query, params)
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_messages_from_another_conversation_rejected(self):
        owner, conversation = self.f.conversation()
        _, other = self.f.conversation(owner)
        user_msg = self.f.message(other, 1, 'user')
        assistant_msg = self.f.message(conversation, 1, 'assistant')
        with self.assertRaises(errors.ForeignKeyViolation):
            with self.conn.transaction():
                query, *params = self.run_sql(conversation, owner, user_msg, assistant_msg)
                self.conn.execute(query, params)
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_run_owner_must_own_conversation(self):
        _, conversation = self.f.conversation()
        user_msg = self.f.message(conversation, 1, 'user')
        assistant_msg = self.f.message(conversation, 2, 'assistant')
        query, *params = self.run_sql(conversation, self.f.user(), user_msg, assistant_msg)
        self.rejects(errors.ForeignKeyViolation, query, *params)

    def test_feedback_only_on_own_messages(self):
        owner, conversation = self.f.conversation()
        message = self.f.message(conversation, 1, 'assistant')
        self.rejects(errors.InsufficientPrivilege, 'INSERT INTO feedback (user_id, message_id,'
                     ' rating) VALUES (%s, %s, 1)', self.f.user(), message)
        self.conn.execute('INSERT INTO feedback (user_id, message_id, rating) VALUES (%s, %s, 1)',
                          (owner, message))


class JobTests(SchemaTestCase):
    def job_sql(self, g, user):
        return ('INSERT INTO ingestion_jobs (book_version_id, generation_id, pipeline_profile_id,'
                ' requested_by) SELECT %s, id, pipeline_profile_id, %s FROM generations'
                ' WHERE id = %s RETURNING id', g['version'], user, g['generation'])

    def test_one_active_job_per_version_and_profile(self):
        g = self.f.built_generation()
        user = self.f.user()
        query, *params = self.job_sql(g, user)
        job = self.f.one(query, *params)
        self.rejects(errors.UniqueViolation, query, *params)
        self.conn.execute("UPDATE ingestion_jobs SET state = 'running' WHERE id = %s", (job,))
        self.conn.execute("UPDATE ingestion_jobs SET state = 'failed' WHERE id = %s", (job,))
        self.f.one(query, *params)  # a retry job is allowed once the first is terminal
        self.rejects(errors.CheckViolation,
                     "UPDATE ingestion_jobs SET state = 'running' WHERE id = %s", job)

    def test_job_profile_must_match_generation(self):
        g = self.f.built_generation()
        other_profile = self.f.one('INSERT INTO pipeline_profiles (name, parser_version,'
                                   " chunker_version, normalizer_version, embedding_profile_id,"
                                   " config_hash) VALUES ('p2', '1', '1', '1', %s, %s) RETURNING id",
                                   self.f.embedding_profile(), sha(uuid.uuid4().hex))
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO ingestion_jobs (book_version_id,'
                     ' generation_id, pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s)',
                     g['version'], g['generation'], other_profile, self.f.user())

    def test_stage_idempotency_and_fencing(self):
        g = self.f.built_generation()
        query, *params = self.job_sql(g, self.f.user())
        job = self.f.one(query, *params)
        key = sha('stage-key')
        stage_sql = ('INSERT INTO job_stages (job_id, stage, unit_key, input_hash, idempotency_key)'
                     " VALUES (%s, 'extract', 'page:1', %s, %s) RETURNING id")
        stage = self.f.one(stage_sql, job, sha('in'), key)
        self.rejects(errors.UniqueViolation, stage_sql, job, sha('in'), key)
        self.conn.execute("UPDATE job_stages SET state = 'running', lease_until = now(),"
                          " worker_id = 'w1', fencing_token = 5 WHERE id = %s", (stage,))
        self.rejects(errors.CheckViolation,
                     'UPDATE job_stages SET fencing_token = 4 WHERE id = %s', stage)


class MigrationTests(unittest.TestCase):
    def test_downgrade_to_m003_and_back(self):
        name = create_database()
        try:
            alembic(name, 'upgrade', 'head')
            alembic(name, 'downgrade', '0003_m003_documents')
            with psycopg.connect(database_url(name)) as conn:
                version = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
                leftovers = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
                                         " AND tablename IN ('schools', 'entity_registry',"
                                         " 'chat_runs', 'audit_logs')").fetchone()[0]
            self.assertEqual((version, leftovers), ('0003_m003_documents', 0))
            alembic(name, 'upgrade', 'head')
            alembic(name, 'upgrade', 'head')  # idempotent at head
        finally:
            drop_database(name)


if __name__ == '__main__':
    unittest.main()
