"""Row-level security as the runtime role (M008): owners only, fail closed, no bypass."""
import unittest
import uuid

import psycopg
from psycopg import errors

from tests.integration.db import (create_runtime_login, database_url, drop_database, drop_role,
                                  migrated_database)

DB_NAME = ROLE = RUNTIME = None


def setUpModule():
    global DB_NAME, ROLE, RUNTIME
    DB_NAME = migrated_database('head')
    try:
        ROLE, RUNTIME = create_runtime_login(DB_NAME)
    except BaseException:
        drop_database(DB_NAME)
        raise


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)
    if ROLE:
        drop_role(ROLE)


def owner_exec(query, *params):
    with psycopg.connect(database_url(DB_NAME), autocommit=True) as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchone()[0] if cursor.description else None


def new_user(role='reader'):
    return owner_exec("INSERT INTO users (email, password_hash, role) VALUES (%s, 'x', %s)"
                      ' RETURNING id', f'{uuid.uuid4().hex}@example.test', role)


class RlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice, cls.bob, cls.admin = new_user(), new_user(), new_user('admin')
        config = '{"day_boundary": "00:00"}'
        cls.policy = owner_exec("INSERT INTO calculation_policies (key, revision, config,"
                                ' manifest_hash) VALUES (%s, 1, %s::jsonb,'
                                ' bazi_sha256_text(%s::jsonb::text)) RETURNING id',
                                uuid.uuid4().hex, config, config)

    def setUp(self):
        self.conn = psycopg.connect(RUNTIME)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)

    def act_as(self, user_id):
        self.conn.execute("SELECT set_config('app.user_id', %s, true)",
                          (str(user_id) if user_id else '',))

    def chart_for(self, owner):
        self.act_as(owner)
        facts = '{"pillars": {}}'
        return self.conn.execute(
            'INSERT INTO bazi_charts (owner_id, policy_id, input_snapshot_encrypted, facts,'
            " facts_hash, engine_manifest, validation_status) VALUES (%s, %s, '\\x00', %s::jsonb,"
            " bazi_sha256_text(%s::jsonb::text), '{}', 'valid') RETURNING id",
            (owner, self.policy, facts, facts)).fetchone()[0]

    def visible_charts(self, user_id):
        self.act_as(user_id)
        return {r[0] for r in self.conn.execute('SELECT id FROM bazi_charts')}

    def test_runtime_role_cannot_bypass(self):
        flags = self.conn.execute('SELECT rolsuper, rolbypassrls FROM pg_roles'
                                  ' WHERE rolname = current_user').fetchone()
        self.assertEqual(flags, (False, False))
        self.conn.execute('SET row_security = off')
        with self.assertRaises(errors.InsufficientPrivilege):
            self.conn.execute('SELECT * FROM bazi_charts')

    def test_owner_sees_only_own_charts_admin_included(self):
        alice_chart = self.chart_for(self.alice)
        bob_chart = self.chart_for(self.bob)
        self.assertEqual(self.visible_charts(self.alice), {alice_chart})
        self.assertEqual(self.visible_charts(self.bob), {bob_chart})
        # An application admin has no implicit read access to private charts.
        self.assertEqual(self.visible_charts(self.admin), set())

    def test_unset_principal_sees_nothing(self):
        self.chart_for(self.alice)
        self.assertEqual(self.visible_charts(None), set())

    def test_cannot_write_rows_for_another_owner(self):
        self.act_as(self.bob)
        with self.assertRaises(errors.InsufficientPrivilege):
            self.conn.execute("INSERT INTO birth_profiles (owner_id, label, birth_input_encrypted,"
                              " crypto_key_version) VALUES (%s, 'x', '\\x00', 'v1')", (self.alice,))

    def test_cannot_update_or_delete_others_rows(self):
        chart = self.chart_for(self.alice)
        self.act_as(self.bob)
        updated = self.conn.execute("UPDATE bazi_charts SET validation_status = 'invalid'"
                                    ' WHERE id = %s', (chart,)).rowcount
        deleted = self.conn.execute('DELETE FROM bazi_charts WHERE id = %s', (chart,)).rowcount
        self.assertEqual((updated, deleted), (0, 0))

    def test_messages_follow_conversation_owner(self):
        self.act_as(self.alice)
        conversation = self.conn.execute('INSERT INTO conversations (owner_id) VALUES (%s)'
                                         ' RETURNING id', (self.alice,)).fetchone()[0]
        self.conn.execute("INSERT INTO messages (conversation_id, seq, role, content, status)"
                          " VALUES (%s, 1, 'user', 'giờ sinh riêng tư', 'completed')",
                          (conversation,))
        self.act_as(self.bob)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        with self.assertRaises(errors.InsufficientPrivilege):
            self.conn.execute("INSERT INTO messages (conversation_id, seq, role, status)"
                              " VALUES (%s, 2, 'user', 'completed')", (conversation,))

    def test_system_settings_shared_user_settings_private(self):
        owner_exec("INSERT INTO settings (scope, key, value) VALUES ('system', %s, '1')",
                   uuid.uuid4().hex)
        self.act_as(self.alice)
        self.conn.execute("INSERT INTO settings (scope, owner_id, key, value)"
                          " VALUES ('user', %s, 'theme', '\"dark\"')", (self.alice,))
        self.act_as(self.bob)
        scopes = {r[0] for r in self.conn.execute('SELECT scope FROM settings')}
        self.assertEqual(scopes, {'system'})

    def test_runtime_cannot_change_migration_metadata(self):
        for statement in ("UPDATE alembic_version SET version_num = 'x'",
                          "INSERT INTO entity_registry VALUES ('evil', 'users')"):
            with self.assertRaises(errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.conn.execute(statement)

    def test_reference_guard_sees_all_owners(self):
        prosecdef = self.conn.execute("SELECT prosecdef FROM pg_proc"
                                      " WHERE proname = 'bazi_guard_referenced_delete'").fetchone()
        self.assertEqual(prosecdef, (True,))

    def test_erasure_bypass_cannot_be_forged_by_the_runtime(self):
        # The delete guard only stands aside for bazi_erase_owner's own transaction (M015).
        for statement in ('INSERT INTO erasure_tokens VALUES (txid_current())',
                          'SELECT count(*) FROM erasure_tokens',
                          'SELECT count(*) FROM deletion_ledger'):
            with self.subTest(statement=statement):
                with self.assertRaises(errors.InsufficientPrivilege):
                    with self.conn.transaction():
                        self.conn.execute(statement)
        source = self.conn.execute("SELECT prosrc FROM pg_proc"
                                   " WHERE proname = 'bazi_guard_referenced_delete'").fetchone()[0]
        self.assertIn('erasure_tokens', source)
        self.assertNotIn('current_setting', source)

    def test_shared_library_tables_readable(self):
        self.act_as(self.bob)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM concepts WHERE canonical_key LIKE 'can.%%'").fetchone()[0], 10)


if __name__ == '__main__':
    unittest.main()
