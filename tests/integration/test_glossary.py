"""Loading the reviewed term list: approved through reviews, revisions for the seed, re-runnable."""
import uuid

from sqlalchemy import text

from backend.app.auth.service import Principal
from backend.app.knowledge import glossary, ontology_release
from tests.integration.env import PipelineTestCase


class GlossaryTests(PipelineTestCase):
    def load(self, data):
        with self.owner_engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {'u': self.user})
            role = conn.execute(text('SELECT email, role FROM users WHERE id = :u'),
                                {'u': self.user}).one()
            principal = Principal(uuid.UUID(self.user), role[0], role[1], uuid.UUID(int=0), '')
            return glossary.load(conn, principal, data).as_dict(), conn

    def test_reviewed_list_loads_as_approved_concepts(self):
        data = glossary.read()
        report, _ = self.load(data)
        seed = 27                                       # Can, Chi, Ngũ Hành already approved
        self.assertEqual(report['missing_schools'], [])
        self.assertEqual(report['concepts_created'] + report['concepts_revised'],
                         len(data['concepts']))
        self.assertGreaterEqual(report['concepts_revised'], 22)
        self.assertLessEqual(report['concepts_revised'], seed)

        # every concept and alias of the list is approved, each with a review by the loader
        not_approved = self.sql(
            "SELECT count(*) FROM concepts c WHERE c.state <> 'approved' AND c.revision ="
            " (SELECT max(revision) FROM concepts o WHERE o.school_id = c.school_id"
            "  AND o.canonical_key = c.canonical_key)")[0][0]
        self.assertEqual(not_approved, 0)
        self.assertEqual(self.sql("SELECT count(*) FROM terms WHERE state = 'draft'")[0][0], 0)
        reviewed = self.sql(
            "SELECT count(DISTINCT c.id) FROM concepts c JOIN reviews r ON r.entity_kind = 'concept'"
            " AND r.entity_id = c.id AND r.decision = 'approve' AND r.reviewer_id = %s"
            " AND r.reason LIKE 'Danh sách thuật ngữ glossary-%%'", self.user)[0][0]
        self.assertEqual(reviewed, len(data['concepts']))

        # the seed stem got the reviewed description as revision 2 and kept its Hán alias
        rows = self.sql(
            "SELECT c.revision, c.description, array_agg(t.form_nfc ORDER BY t.form_nfc)"
            " FROM concepts c JOIN terms t ON t.concept_id = c.id AND t.state = 'approved'"
            " WHERE c.canonical_key = 'can.giap' AND c.state = 'approved'"
            " GROUP BY c.id ORDER BY c.revision DESC LIMIT 1")
        revision, description, forms = rows[0]
        self.assertEqual(revision, 2)
        self.assertIn('Lộc tại Dần', description)
        self.assertTrue({'Giáp', '甲', 'Giáp mộc', 'dương mộc'} <= set(forms))

        # same written form, two schools, two concepts (Manh phái keeps its own meaning)
        schools = self.sql(
            "SELECT s.key FROM concepts c JOIN schools s ON s.id = c.school_id"
            " WHERE c.label = 'Mộ' AND c.state = 'approved' ORDER BY s.key")
        self.assertEqual([r[0] for r in schools], ['manh_phai', 'tu_tru'])
        # no hợp hóa concept was loaded
        self.assertEqual(self.sql("SELECT count(*) FROM concepts WHERE label ILIKE %s"
                                  " OR label ILIKE %s", '%hợp hóa%', '%hóa thổ%')[0][0], 0)

        again, _ = self.load(data)
        self.assertEqual((again['concepts_created'], again['concepts_revised'],
                          again['aliases_added']), (0, 0, 0))
        self.assertEqual(again['concepts_unchanged'], len(data['concepts']))

        with self.owner_engine.begin() as conn:
            published = ontology_release.publish(conn, uuid.UUID(self.user), 'glossary-1', None)
        self.assertEqual(published['release']['state'], 'published')
        # the list plus the seed codes it did not revise
        self.assertEqual(published['release']['concepts'],
                         len(data['concepts']) + seed - report['concepts_revised'])
