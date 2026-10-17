"""M004 ontology, evidence, assertions, rules, reviews and cases.

Review lifecycle (docs/06): rows are inserted as ``draft``; moving to
approved/rejected/revoked needs a ``reviews`` row with the matching decision in
the same transaction, and content columns freeze once a row leaves draft. Only
the migration seed (``SET LOCAL bazi.seed = 'on'``) may insert approved rows,
and it seeds structural codes only, never interpretations or rules.

Polymorphic references (reviews, review_items, later analysis_dependencies) go
through ``entity_registry``: unknown kinds and missing targets are rejected and
referenced targets cannot be deleted.

Revision ID: 0004_m004_knowledge
Revises: 0003_m003_documents
"""
from alembic import op

revision = '0004_m004_knowledge'
down_revision = '0003_m003_documents'
branch_labels = None
depends_on = None

SPEAKER = "('original_author', 'commentator', 'translator', 'editor', 'unknown')"
LIFECYCLE = "('draft', 'in_review', 'approved', 'rejected', 'revoked')"
# Kinds registered here; later migrations add their own.
KINDS = {
    'book_version': 'book_versions', 'page_revision': 'page_revisions',
    'generation': 'generations', 'chunk': 'chunks', 'corpus_release': 'corpus_releases',
    'model_profile': 'model_profiles', 'school': 'schools', 'method': 'methods',
    'topic': 'topics', 'concept': 'concepts', 'term': 'terms',
    'ontology_release': 'ontology_releases', 'evidence': 'evidence_spans',
    'assertion': 'assertions', 'assertion_relation': 'assertion_relations',
    'rule': 'knowledge_rules', 'case_revision': 'case_revisions',
}

STEMS = [('giap', 'Giáp', '甲'), ('at', 'Ất', '乙'), ('binh', 'Bính', '丙'), ('dinh', 'Đinh', '丁'),
         ('mau', 'Mậu', '戊'), ('ky', 'Kỷ', '己'), ('canh', 'Canh', '庚'), ('tan', 'Tân', '辛'),
         ('nham', 'Nhâm', '壬'), ('quy', 'Quý', '癸')]
BRANCHES = [('ty', 'Tý', '子'), ('suu', 'Sửu', '丑'), ('dan', 'Dần', '寅'), ('mao', 'Mão', '卯'),
            ('thin', 'Thìn', '辰'), ('ti', 'Tỵ', '巳'), ('ngo', 'Ngọ', '午'), ('mui', 'Mùi', '未'),
            ('than', 'Thân', '申'), ('dau', 'Dậu', '酉'), ('tuat', 'Tuất', '戌'), ('hoi', 'Hợi', '亥')]
ELEMENTS = [('moc', 'Mộc', '木'), ('hoa', 'Hỏa', '火'), ('tho', 'Thổ', '土'), ('kim', 'Kim', '金'),
            ('thuy', 'Thủy', '水')]
TOPICS = [('can_chi', 'Can Chi'), ('ngu_hanh', 'Ngũ Hành'), ('thap_than', 'Thập Thần'),
          ('van_han', 'Đại Vận và Lưu Niên'), ('menh_le', 'Mệnh lệ')]


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def create_table(name: str, columns: str) -> None:
    run(f"""
    CREATE TABLE {name} (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        {columns}
    );
    CREATE TRIGGER {name}_touch BEFORE UPDATE ON {name}
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    """)


def immutable(table: str, *columns: str) -> None:
    cols = ', '.join(f"'{c}'" for c in columns)
    run(f"""
    CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable({cols});
    """)


def lifecycle(table: str, kind: str, *content: str) -> None:
    cols = ', '.join(f"'{c}'" for c in (kind, *content))
    run(f"""
    CREATE TRIGGER {table}_lifecycle BEFORE INSERT OR UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION bazi_review_lifecycle({cols});
    """)


def no_cycle(table: str) -> None:
    run(f"""
    CREATE TRIGGER {table}_no_cycle BEFORE INSERT OR UPDATE OF parent_id ON {table}
        FOR EACH ROW EXECUTE FUNCTION bazi_no_parent_cycle();
    """)


def q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    run("""
    CREATE TABLE entity_registry (
        kind text PRIMARY KEY CHECK (kind ~ '^[a-z_]{1,40}$'),
        table_name text NOT NULL UNIQUE
    );

    CREATE FUNCTION bazi_entity_exists(entity_kind text, entity_id uuid) RETURNS boolean
        LANGUAGE plpgsql STABLE AS $$
    DECLARE
        target text;
        found boolean;
    BEGIN
        SELECT table_name INTO target FROM entity_registry WHERE kind = entity_kind;
        IF target IS NULL THEN
            RAISE EXCEPTION 'unknown entity kind %', entity_kind
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', target)
            INTO found USING entity_id;
        RETURN found;
    END $$;

    -- Usage: EXECUTE FUNCTION bazi_check_polymorphic('kind_column', 'id_column').
    CREATE FUNCTION bazi_check_polymorphic() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        row_data jsonb := to_jsonb(NEW);
        entity_kind text := row_data ->> TG_ARGV[0];
        entity_id uuid := row_data ->> TG_ARGV[1];
    BEGIN
        IF entity_id IS NOT NULL AND NOT bazi_entity_exists(entity_kind, entity_id) THEN
            RAISE EXCEPTION '% % does not exist', entity_kind, entity_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        RETURN NEW;
    END $$;

    -- Delete guard for registered tables; reference tables are looked up lazily
    -- because analysis_dependencies arrives in M006.
    CREATE FUNCTION bazi_guard_referenced_delete() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        ref record;
        referenced boolean;
    BEGIN
        FOR ref IN SELECT * FROM (VALUES ('reviews', 'entity_kind', 'entity_id'),
                                         ('review_items', 'entity_kind', 'entity_id'),
                                         ('analysis_dependencies', 'dependency_kind',
                                          'dependency_id')) AS r(tbl, kind_col, id_col)
        LOOP
            CONTINUE WHEN to_regclass(ref.tbl) IS NULL;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE %I = $1 AND %I = $2)',
                           ref.tbl, ref.kind_col, ref.id_col)
                INTO referenced USING TG_ARGV[0], OLD.id;
            IF referenced THEN
                RAISE EXCEPTION '% % is referenced by %', TG_ARGV[0], OLD.id, ref.tbl
                    USING ERRCODE = 'foreign_key_violation';
            END IF;
        END LOOP;
        RETURN OLD;
    END $$;

    CREATE FUNCTION bazi_no_parent_cycle() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        cyclic boolean;
    BEGIN
        IF NEW.parent_id IS NULL THEN
            RETURN NEW;
        END IF;
        EXECUTE format($q$
            WITH RECURSIVE up(id) AS (
                SELECT $1
                UNION SELECT t.parent_id FROM %I t JOIN up ON t.id = up.id
                WHERE t.parent_id IS NOT NULL)
            SELECT EXISTS (SELECT 1 FROM up WHERE id = $2)$q$, TG_TABLE_NAME)
            INTO cyclic USING NEW.parent_id, NEW.id;
        IF cyclic THEN
            RAISE EXCEPTION '% parent cycle at %', TG_TABLE_NAME, NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;

    -- Usage: bazi_review_lifecycle('entity_kind', 'content_col', ...).
    CREATE FUNCTION bazi_review_lifecycle() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        col text;
        needed text;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.state <> 'draft' AND current_setting('bazi.seed', true)
                    IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION '% must be created as draft', TG_TABLE_NAME
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state THEN
            IF (OLD.state, NEW.state) NOT IN (
                    ('draft', 'in_review'), ('in_review', 'draft'), ('in_review', 'approved'),
                    ('in_review', 'rejected'), ('approved', 'revoked')) THEN
                RAISE EXCEPTION '% state % -> % is not allowed', TG_TABLE_NAME,
                    OLD.state, NEW.state USING ERRCODE = 'check_violation';
            END IF;
            needed := CASE NEW.state WHEN 'approved' THEN 'approve'
                WHEN 'rejected' THEN 'reject' WHEN 'revoked' THEN 'revoke' END;
            IF needed IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM reviews r WHERE r.entity_kind = TG_ARGV[0] AND r.entity_id = NEW.id
                    AND r.decision = needed AND r.created_at = now()) THEN
                RAISE EXCEPTION '% % needs a % review in the same transaction',
                    TG_ARGV[0], NEW.id, needed USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        IF OLD.state <> 'draft' THEN
            FOREACH col IN ARRAY TG_ARGV[1:] LOOP
                IF to_jsonb(NEW) -> col IS DISTINCT FROM to_jsonb(OLD) -> col THEN
                    RAISE EXCEPTION '%.% is frozen outside draft; create a new revision',
                        TG_TABLE_NAME, col USING ERRCODE = 'restrict_violation';
                END IF;
            END LOOP;
        END IF;
        RETURN NEW;
    END $$;
    """)

    # ---- taxonomy -----------------------------------------------------------------
    create_table('schools', """
        key text NOT NULL UNIQUE,
        label text NOT NULL,
        parent_id uuid REFERENCES schools,
        description text NOT NULL DEFAULT ''
    """)
    no_cycle('schools')
    run('CREATE INDEX schools_parent_id_idx ON schools (parent_id);')

    create_table('methods', f"""
        school_id uuid NOT NULL REFERENCES schools,
        key text NOT NULL,
        revision integer NOT NULL CHECK (revision >= 1),
        description text NOT NULL,
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        UNIQUE (school_id, key, revision),
        UNIQUE (id, school_id)
    """)
    immutable('methods', 'school_id', 'key', 'revision')
    lifecycle('methods', 'method', 'description')

    create_table('topics', """
        key text NOT NULL UNIQUE,
        label text NOT NULL,
        parent_id uuid REFERENCES topics
    """)
    no_cycle('topics')
    run('CREATE INDEX topics_parent_id_idx ON topics (parent_id);')

    create_table('concepts', f"""
        school_id uuid NOT NULL REFERENCES schools,
        canonical_key text NOT NULL,
        label text NOT NULL,
        description text NOT NULL DEFAULT '',
        revision integer NOT NULL CHECK (revision >= 1),
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        UNIQUE (school_id, canonical_key, revision),
        UNIQUE (id, school_id)
    """)
    immutable('concepts', 'school_id', 'canonical_key', 'revision')
    lifecycle('concepts', 'concept', 'label', 'description')

    # ---- evidence -----------------------------------------------------------------
    create_table('evidence_spans', f"""
        book_version_id uuid NOT NULL REFERENCES book_versions,
        page_revision_id uuid NOT NULL,
        block_id uuid NOT NULL,
        start_offset integer NOT NULL,
        end_offset integer NOT NULL,
        bbox jsonb CHECK (bazi_valid_bbox(bbox)),
        quote_hash sha256_hex NOT NULL,
        speaker_layer text NOT NULL CHECK (speaker_layer IN {SPEAKER}),
        origin text NOT NULL CHECK (origin IN
            ('source_explicit', 'editor_interpretation', 'ai_inferred')),
        FOREIGN KEY (block_id, page_revision_id) REFERENCES blocks (id, page_revision_id),
        CHECK (0 <= start_offset AND start_offset < end_offset)
    """)
    immutable('evidence_spans', 'book_version_id', 'page_revision_id', 'block_id', 'start_offset',
              'end_offset', 'bbox', 'quote_hash', 'speaker_layer', 'origin')
    run("""
    CREATE INDEX evidence_spans_version_revision_idx
        ON evidence_spans (book_version_id, page_revision_id);
    CREATE INDEX evidence_spans_page_revision_id_idx ON evidence_spans (page_revision_id);
    CREATE INDEX evidence_spans_block_id_idx ON evidence_spans (block_id);

    -- The quote is whatever the revision says at those offsets; it cannot be rewritten.
    CREATE FUNCTION bazi_check_evidence_span() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        blk blocks;
        source_text text;
        source_version uuid;
    BEGIN
        SELECT * INTO blk FROM blocks WHERE id = NEW.block_id;
        SELECT r.normalized_text, p.book_version_id INTO source_text, source_version
            FROM page_revisions r JOIN pages p ON p.id = r.page_id
            WHERE r.id = NEW.page_revision_id;
        IF source_version IS DISTINCT FROM NEW.book_version_id THEN
            RAISE EXCEPTION 'evidence page revision is not in book version %',
                NEW.book_version_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF NEW.start_offset < blk.start_offset OR NEW.end_offset > blk.end_offset THEN
            RAISE EXCEPTION 'evidence [%,%) is outside block [%,%)', NEW.start_offset,
                NEW.end_offset, blk.start_offset, blk.end_offset USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.quote_hash <> bazi_sha256_text(
                substr(source_text, NEW.start_offset + 1, NEW.end_offset - NEW.start_offset)) THEN
            RAISE EXCEPTION 'quote_hash does not match the revision text at [%,%)',
                NEW.start_offset, NEW.end_offset USING ERRCODE = 'check_violation';
        END IF;
        IF blk.speaker_layer <> NEW.speaker_layer THEN
            RAISE EXCEPTION 'evidence speaker % differs from block speaker %',
                NEW.speaker_layer, blk.speaker_layer USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER evidence_spans_check BEFORE INSERT ON evidence_spans
        FOR EACH ROW EXECUTE FUNCTION bazi_check_evidence_span();
    """)

    create_table('terms', f"""
        concept_id uuid NOT NULL REFERENCES concepts,
        form_nfc text NOT NULL,
        form_folded text NOT NULL,
        language text NOT NULL,
        alias_kind text NOT NULL CHECK (alias_kind IN
            ('canonical', 'same_concept', 'translation_variant', 'related', 'contrasts_with')),
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        evidence_id uuid REFERENCES evidence_spans,
        UNIQUE (concept_id, form_nfc, language, alias_kind)
    """)
    immutable('terms', 'concept_id', 'form_nfc', 'language', 'alias_kind')
    lifecycle('terms', 'term', 'form_folded', 'evidence_id')
    run("""
    CREATE INDEX terms_form_folded_trgm_idx ON terms USING gin (form_folded gin_trgm_ops);
    CREATE INDEX terms_evidence_id_idx ON terms (evidence_id);
    """)

    create_table('ontology_releases', """
        version text NOT NULL UNIQUE,
        state text NOT NULL DEFAULT 'building' CHECK (state IN ('building', 'published', 'retired')),
        manifest_hash sha256_hex,
        CHECK (state = 'building' OR manifest_hash IS NOT NULL)
    """)
    run("""
    CREATE FUNCTION bazi_ontology_release_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
                ('building', 'published'), ('building', 'retired'), ('published', 'retired')) THEN
            RAISE EXCEPTION 'ontology release state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state <> 'building' AND (NEW.manifest_hash IS DISTINCT FROM OLD.manifest_hash
                OR NEW.version IS DISTINCT FROM OLD.version) THEN
            RAISE EXCEPTION 'ontology release is frozen after building'
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER ontology_releases_transition BEFORE UPDATE ON ontology_releases
        FOR EACH ROW EXECUTE FUNCTION bazi_ontology_release_transition();
    """)

    create_table('ontology_members', """
        release_id uuid NOT NULL REFERENCES ontology_releases,
        concept_id uuid NOT NULL REFERENCES concepts,
        term_id uuid REFERENCES terms,
        method_id uuid REFERENCES methods,
        UNIQUE NULLS NOT DISTINCT (release_id, concept_id, term_id, method_id)
    """)
    immutable('ontology_members', 'release_id', 'concept_id', 'term_id', 'method_id')
    run("""
    CREATE INDEX ontology_members_concept_id_idx ON ontology_members (concept_id);
    CREATE INDEX ontology_members_term_id_idx ON ontology_members (term_id);
    CREATE INDEX ontology_members_method_id_idx ON ontology_members (method_id);

    CREATE FUNCTION bazi_check_ontology_member() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target ontology_members := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        concept_row concepts;
    BEGIN
        IF (SELECT state FROM ontology_releases WHERE id = target.release_id FOR SHARE)
                IS DISTINCT FROM 'building' THEN
            RAISE EXCEPTION 'ontology release % is frozen', target.release_id
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        SELECT * INTO concept_row FROM concepts WHERE id = NEW.concept_id;
        IF concept_row.state <> 'approved' THEN
            RAISE EXCEPTION 'concept % is not approved', NEW.concept_id
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.term_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM terms WHERE id = NEW.term_id
                AND concept_id = NEW.concept_id AND state = 'approved') THEN
            RAISE EXCEPTION 'term % is not an approved alias of concept %', NEW.term_id,
                NEW.concept_id USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.method_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM methods WHERE id = NEW.method_id
                AND school_id = concept_row.school_id AND state = 'approved') THEN
            RAISE EXCEPTION 'method % is not an approved method of the concept school',
                NEW.method_id USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER ontology_members_check BEFORE INSERT OR UPDATE OR DELETE ON ontology_members
        FOR EACH ROW EXECUTE FUNCTION bazi_check_ontology_member();
    """)

    create_table('chunk_classifications', """
        chunk_id uuid NOT NULL REFERENCES chunks,
        generation_id uuid NOT NULL,
        school_id uuid REFERENCES schools,
        topic_id uuid REFERENCES topics,
        concept_id uuid REFERENCES concepts,
        status text NOT NULL CHECK (status IN ('proposed', 'reviewed', 'rejected')),
        confidence numeric CHECK (confidence BETWEEN 0 AND 1),
        classification_version text NOT NULL,
        FOREIGN KEY (generation_id, chunk_id) REFERENCES generation_chunks (generation_id, chunk_id),
        CHECK (num_nonnulls(school_id, topic_id, concept_id) >= 1)
    """)
    run("""
    CREATE INDEX chunk_classifications_generation_chunk_idx
        ON chunk_classifications (generation_id, chunk_id);
    CREATE INDEX chunk_classifications_chunk_id_idx ON chunk_classifications (chunk_id);
    CREATE INDEX chunk_classifications_school_id_idx ON chunk_classifications (school_id);
    CREATE INDEX chunk_classifications_topic_id_idx ON chunk_classifications (topic_id);
    CREATE INDEX chunk_classifications_concept_id_idx ON chunk_classifications (concept_id);

    CREATE FUNCTION bazi_check_classification() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target uuid := CASE WHEN TG_OP = 'DELETE' THEN OLD.generation_id ELSE NEW.generation_id END;
    BEGIN
        IF (SELECT state FROM generations WHERE id = target FOR SHARE)
                IN ('published', 'superseded', 'withdrawn') THEN
            RAISE EXCEPTION 'classifications of published generation % are frozen', target
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END $$;
    CREATE TRIGGER chunk_classifications_frozen BEFORE INSERT OR UPDATE OR DELETE
        ON chunk_classifications FOR EACH ROW EXECUTE FUNCTION bazi_check_classification();
    """)

    # ---- assertions and rules -----------------------------------------------------
    create_table('assertions', f"""
        assertion_key text NOT NULL,
        revision integer NOT NULL CHECK (revision >= 1),
        school_id uuid NOT NULL REFERENCES schools,
        method_id uuid,
        concept_id uuid,
        statement text NOT NULL,
        applicability jsonb NOT NULL DEFAULT '{{}}',
        exception_text text,
        origin text NOT NULL CHECK (origin IN
            ('source_explicit', 'editor_interpretation', 'ai_inferred')),
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        author_id uuid NOT NULL REFERENCES users,
        UNIQUE (assertion_key, revision),
        FOREIGN KEY (method_id, school_id) REFERENCES methods (id, school_id),
        FOREIGN KEY (concept_id, school_id) REFERENCES concepts (id, school_id)
    """)
    immutable('assertions', 'assertion_key', 'revision', 'school_id', 'author_id')
    lifecycle('assertions', 'assertion', 'method_id', 'concept_id', 'statement',
              'applicability', 'exception_text', 'origin')
    run("""
    CREATE INDEX assertions_school_id_idx ON assertions (school_id);
    CREATE INDEX assertions_method_id_idx ON assertions (method_id);
    CREATE INDEX assertions_concept_id_idx ON assertions (concept_id);
    CREATE INDEX assertions_author_id_idx ON assertions (author_id);
    """)

    create_table('assertion_sources', """
        assertion_id uuid NOT NULL REFERENCES assertions,
        evidence_id uuid NOT NULL REFERENCES evidence_spans,
        relation text NOT NULL CHECK (relation IN ('states', 'supports', 'contrasts')),
        UNIQUE (assertion_id, evidence_id, relation)
    """)
    immutable('assertion_sources', 'assertion_id', 'evidence_id', 'relation')
    run('CREATE INDEX assertion_sources_evidence_id_idx ON assertion_sources (evidence_id);')

    create_table('assertion_relations', f"""
        from_id uuid NOT NULL REFERENCES assertions,
        to_id uuid NOT NULL REFERENCES assertions,
        relation text NOT NULL CHECK (relation IN
            ('supports', 'disputes', 'qualifies', 'exception_to', 'derives_from')),
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        UNIQUE (from_id, to_id, relation),
        CHECK (from_id <> to_id)
    """)
    immutable('assertion_relations', 'from_id', 'to_id', 'relation')
    lifecycle('assertion_relations', 'assertion_relation')
    run('CREATE INDEX assertion_relations_to_id_idx ON assertion_relations (to_id);')

    create_table('knowledge_rules', f"""
        rule_key text NOT NULL,
        revision integer NOT NULL CHECK (revision >= 1),
        school_id uuid NOT NULL REFERENCES schools,
        method_id uuid NOT NULL,
        assertion_id uuid REFERENCES assertions,
        dsl jsonb NOT NULL,
        dsl_hash sha256_hex NOT NULL,
        fact_schema_version text NOT NULL,
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        author_id uuid NOT NULL REFERENCES users,
        UNIQUE (rule_key, revision),
        UNIQUE (id, school_id, method_id),
        FOREIGN KEY (method_id, school_id) REFERENCES methods (id, school_id),
        CHECK (dsl_hash = bazi_sha256_text(dsl::text))
    """)
    immutable('knowledge_rules', 'rule_key', 'revision', 'school_id', 'method_id', 'author_id')
    lifecycle('knowledge_rules', 'rule', 'assertion_id', 'dsl', 'dsl_hash', 'fact_schema_version')
    run("""
    CREATE INDEX knowledge_rules_school_id_idx ON knowledge_rules (school_id);
    CREATE INDEX knowledge_rules_method_id_idx ON knowledge_rules (method_id);
    CREATE INDEX knowledge_rules_assertion_id_idx ON knowledge_rules (assertion_id);
    CREATE INDEX knowledge_rules_author_id_idx ON knowledge_rules (author_id);
    """)

    create_table('rule_sources', """
        rule_id uuid NOT NULL REFERENCES knowledge_rules,
        evidence_id uuid NOT NULL REFERENCES evidence_spans,
        UNIQUE (rule_id, evidence_id)
    """)
    immutable('rule_sources', 'rule_id', 'evidence_id')
    run('CREATE INDEX rule_sources_evidence_id_idx ON rule_sources (evidence_id);')

    create_table('rule_dependencies', """
        rule_id uuid NOT NULL REFERENCES knowledge_rules,
        requires_id uuid NOT NULL REFERENCES knowledge_rules,
        UNIQUE (rule_id, requires_id),
        CHECK (rule_id <> requires_id)
    """)
    immutable('rule_dependencies', 'rule_id', 'requires_id')
    run("""
    CREATE INDEX rule_dependencies_requires_id_idx ON rule_dependencies (requires_id);

    -- Sources and dependencies are part of rule content: only editable in draft.
    CREATE FUNCTION bazi_rule_part_editable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target uuid := CASE WHEN TG_OP = 'DELETE' THEN OLD.rule_id ELSE NEW.rule_id END;
    BEGIN
        IF (SELECT state FROM knowledge_rules WHERE id = target FOR SHARE) <> 'draft' THEN
            RAISE EXCEPTION 'rule % is not a draft; % are frozen', target, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END $$;
    CREATE TRIGGER rule_sources_editable BEFORE INSERT OR UPDATE OR DELETE ON rule_sources
        FOR EACH ROW EXECUTE FUNCTION bazi_rule_part_editable();
    CREATE TRIGGER rule_dependencies_editable BEFORE INSERT OR UPDATE OR DELETE
        ON rule_dependencies FOR EACH ROW EXECUTE FUNCTION bazi_rule_part_editable();

    CREATE FUNCTION bazi_rule_dependency_acyclic() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (WITH RECURSIVE reach(id) AS (
                       SELECT NEW.requires_id
                       UNION SELECT d.requires_id FROM rule_dependencies d
                       JOIN reach ON d.rule_id = reach.id)
                   SELECT 1 FROM reach WHERE id = NEW.rule_id) THEN
            RAISE EXCEPTION 'rule dependency % -> % creates a cycle', NEW.rule_id, NEW.requires_id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER rule_dependencies_acyclic BEFORE INSERT ON rule_dependencies
        FOR EACH ROW EXECUTE FUNCTION bazi_rule_dependency_acyclic();

    -- docs/04: an approved rule has at least one source evidence span.
    CREATE FUNCTION bazi_rule_needs_source() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state = 'approved' AND OLD.state <> 'approved'
                AND NOT EXISTS (SELECT 1 FROM rule_sources WHERE rule_id = NEW.id) THEN
            RAISE EXCEPTION 'rule % cannot be approved without source evidence', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER knowledge_rules_source BEFORE UPDATE OF state ON knowledge_rules
        FOR EACH ROW EXECUTE FUNCTION bazi_rule_needs_source();
    """)

    # ---- reviews ------------------------------------------------------------------
    create_table('reviews', """
        entity_kind text NOT NULL REFERENCES entity_registry,
        entity_id uuid NOT NULL,
        reviewer_id uuid NOT NULL REFERENCES users,
        decision text NOT NULL CHECK (decision IN ('approve', 'reject', 'revoke')),
        reason text NOT NULL,
        base_revision integer NOT NULL CHECK (base_revision >= 1)
    """)
    run("""
    CREATE INDEX reviews_entity_idx ON reviews (entity_kind, entity_id, created_at);
    CREATE INDEX reviews_reviewer_id_idx ON reviews (reviewer_id);

    CREATE FUNCTION bazi_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END $$;
    CREATE TRIGGER reviews_append_only BEFORE UPDATE OR DELETE ON reviews
        FOR EACH ROW EXECUTE FUNCTION bazi_append_only();
    CREATE TRIGGER reviews_target BEFORE INSERT ON reviews
        FOR EACH ROW EXECUTE FUNCTION bazi_check_polymorphic('entity_kind', 'entity_id');
    """)

    create_table('review_items', """
        generation_id uuid REFERENCES generations,
        page_revision_id uuid REFERENCES page_revisions,
        entity_kind text REFERENCES entity_registry,
        entity_id uuid,
        reason_code text NOT NULL,
        severity text NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
        state text NOT NULL DEFAULT 'open' CHECK (state IN
            ('open', 'in_progress', 'resolved', 'dismissed')),
        assigned_to uuid REFERENCES users,
        resolution jsonb,
        CHECK (num_nonnulls(generation_id, page_revision_id, entity_id) >= 1),
        CHECK ((entity_kind IS NULL) = (entity_id IS NULL))
    """)
    run("""
    CREATE INDEX review_items_queue_idx ON review_items (state, severity, created_at);
    CREATE INDEX review_items_open_idx ON review_items (severity, created_at)
        WHERE state IN ('open', 'in_progress');
    CREATE INDEX review_items_generation_id_idx ON review_items (generation_id);
    CREATE INDEX review_items_page_revision_id_idx ON review_items (page_revision_id);
    CREATE INDEX review_items_entity_idx ON review_items (entity_kind, entity_id);
    CREATE INDEX review_items_assigned_to_idx ON review_items (assigned_to);
    CREATE TRIGGER review_items_target BEFORE INSERT OR UPDATE OF entity_kind, entity_id
        ON review_items FOR EACH ROW EXECUTE FUNCTION bazi_check_polymorphic('entity_kind', 'entity_id');
    """)

    # ---- cases --------------------------------------------------------------------
    create_table('cases', """
        case_key text NOT NULL UNIQUE,
        owner_id uuid REFERENCES users,
        origin text NOT NULL CHECK (origin IN ('book_case', 'user_case', 'synthetic_test')),
        visibility text NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'library')),
        deleted_at timestamptz,
        CHECK (origin <> 'user_case' OR (owner_id IS NOT NULL AND visibility = 'private'))
    """)
    run('CREATE INDEX cases_owner_id_idx ON cases (owner_id);')

    create_table('case_revisions', f"""
        case_id uuid NOT NULL REFERENCES cases,
        revision integer NOT NULL CHECK (revision >= 1),
        school_id uuid NOT NULL REFERENCES schools,
        method_id uuid,
        chart_payload jsonb NOT NULL CHECK (jsonb_typeof(chart_payload) = 'object'),
        narrative text NOT NULL,
        claimed_events jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(claimed_events) = 'array'),
        state text NOT NULL DEFAULT 'draft' CHECK (state IN {LIFECYCLE}),
        quality jsonb NOT NULL DEFAULT '{{}}',
        UNIQUE (case_id, revision),
        FOREIGN KEY (method_id, school_id) REFERENCES methods (id, school_id)
    """)
    immutable('case_revisions', 'case_id', 'revision')
    lifecycle('case_revisions', 'case_revision', 'school_id', 'method_id', 'chart_payload',
              'narrative', 'claimed_events')
    run("""
    CREATE INDEX case_revisions_school_id_idx ON case_revisions (school_id);
    CREATE INDEX case_revisions_method_id_idx ON case_revisions (method_id);
    """)

    create_table('case_sources', """
        case_revision_id uuid NOT NULL REFERENCES case_revisions,
        evidence_id uuid NOT NULL REFERENCES evidence_spans,
        UNIQUE (case_revision_id, evidence_id)
    """)
    immutable('case_sources', 'case_revision_id', 'evidence_id')
    run('CREATE INDEX case_sources_evidence_id_idx ON case_sources (evidence_id);')

    # ---- deferred FKs from M003 and the registry ----------------------------------
    run("""
    ALTER TABLE sections ADD CONSTRAINT sections_school_id_fkey
        FOREIGN KEY (school_id) REFERENCES schools;
    ALTER TABLE corpus_releases ADD CONSTRAINT corpus_releases_ontology_release_id_fkey
        FOREIGN KEY (ontology_release_id) REFERENCES ontology_releases;
    """)
    register(KINDS)
    seed()


def register(kinds: dict[str, str]) -> None:
    for kind, table in kinds.items():
        run(f"""
        INSERT INTO entity_registry (kind, table_name) VALUES ({q(kind)}, {q(table)});
        CREATE TRIGGER {table}_referenced_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION bazi_guard_referenced_delete({q(kind)});
        """)


def seed() -> None:
    """Structural taxonomy only: schools, codes and topics. Idempotent."""
    rows = []
    for prefix, items in (('can', STEMS), ('chi', BRANCHES), ('ngu_hanh', ELEMENTS)):
        for key, label, han in items:
            rows.append((f'{prefix}.{key}', label, han))
    concepts = ',\n'.join(f'({q(k)}, {q(label)}, {q(han)})' for k, label, han in rows)
    topics = ',\n'.join(f'({q(k)}, {q(label)})' for k, label in TOPICS)
    run(f"""
    SET LOCAL bazi.seed = 'on';
    INSERT INTO schools (key, label, description) VALUES
        ('tu_tru', 'Tứ Trụ (Bát Tự)', 'Gốc chung: mã Can/Chi/Ngũ Hành dùng cho mọi trường phái')
        ON CONFLICT (key) DO NOTHING;
    INSERT INTO schools (key, label, parent_id, description)
        SELECT v.key, v.label, s.id, '' FROM (VALUES
            ('manh_phai', 'Manh Phái'), ('tu_binh', 'Tử Bình')) AS v(key, label)
        CROSS JOIN schools s WHERE s.key = 'tu_tru'
        ON CONFLICT (key) DO NOTHING;
    INSERT INTO topics (key, label) VALUES {topics} ON CONFLICT (key) DO NOTHING;

    WITH root AS (SELECT id FROM schools WHERE key = 'tu_tru'),
    codes(canonical_key, label, han) AS (VALUES {concepts}),
    new_concepts AS (
        INSERT INTO concepts (school_id, canonical_key, label, description, revision, state)
        SELECT root.id, c.canonical_key, c.label, 'Mã cấu trúc lịch pháp', 1, 'approved'
        FROM codes c CROSS JOIN root
        ON CONFLICT (school_id, canonical_key, revision) DO NOTHING
        RETURNING id, canonical_key, label)
    INSERT INTO terms (concept_id, form_nfc, form_folded, language, alias_kind, state)
    SELECT n.id, t.form, t.folded, t.lang, t.kind, 'approved'
    FROM new_concepts n JOIN codes c USING (canonical_key)
    CROSS JOIN LATERAL (VALUES
        (n.label, lower(unaccent(replace(replace(n.label, 'Đ', 'D'), 'đ', 'd'))), 'vi', 'canonical'),
        (c.han, c.han, 'zh', 'translation_variant')) AS t(form, folded, lang, kind)
    ON CONFLICT DO NOTHING;

    INSERT INTO ontology_releases (version) VALUES ('seed-1') ON CONFLICT (version) DO NOTHING;
    INSERT INTO ontology_members (release_id, concept_id, term_id)
    SELECT r.id, c.id, t.id FROM ontology_releases r
    JOIN concepts c ON c.state = 'approved'
    JOIN terms t ON t.concept_id = c.id AND t.state = 'approved'
    WHERE r.version = 'seed-1' AND r.state = 'building'
    ON CONFLICT DO NOTHING;
    UPDATE ontology_releases SET state = 'published', manifest_hash = (
        SELECT bazi_sha256_text(string_agg(c.canonical_key || '|' || t.form_nfc || '|'
                                           || t.alias_kind, E'\\n' ORDER BY c.canonical_key,
                                           t.form_nfc, t.alias_kind))
        FROM ontology_members m JOIN concepts c ON c.id = m.concept_id
        JOIN terms t ON t.id = m.term_id WHERE m.release_id = ontology_releases.id)
    WHERE version = 'seed-1' AND state = 'building';
    """)


def downgrade() -> None:
    run("""
    ALTER TABLE corpus_releases DROP CONSTRAINT corpus_releases_ontology_release_id_fkey;
    ALTER TABLE sections DROP CONSTRAINT sections_school_id_fkey;
    """)
    for table in ('book_versions', 'page_revisions', 'generations', 'chunks', 'corpus_releases',
                  'model_profiles'):
        run(f'DROP TRIGGER {table}_referenced_delete ON {table};')
    run("""
    DROP TABLE case_sources, case_revisions, cases, review_items, reviews, rule_dependencies,
        rule_sources, knowledge_rules, assertion_relations, assertion_sources, assertions,
        chunk_classifications, ontology_members, ontology_releases, terms, evidence_spans,
        concepts, topics, methods, schools, entity_registry;
    DROP FUNCTION bazi_append_only(), bazi_rule_needs_source(), bazi_rule_dependency_acyclic(),
        bazi_rule_part_editable(), bazi_check_classification(), bazi_check_ontology_member(),
        bazi_ontology_release_transition(), bazi_check_evidence_span(), bazi_review_lifecycle(),
        bazi_no_parent_cycle(), bazi_guard_referenced_delete(), bazi_check_polymorphic(),
        bazi_entity_exists(text, uuid);
    """)
