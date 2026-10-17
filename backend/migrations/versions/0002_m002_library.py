"""M002 objects, authors, books, versions and access grants.

Revision ID: 0002_m002_library
Revises: 0001_m001_identity
"""
from alembic import op

revision = '0002_m002_library'
down_revision = '0001_m001_identity'
branch_labels = None
depends_on = None


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


def upgrade() -> None:
    create_table('objects', """
        sha256 sha256_hex NOT NULL UNIQUE,
        storage_backend text NOT NULL CHECK (storage_backend IN ('local', 's3')),
        object_key text NOT NULL UNIQUE,
        size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
        detected_mime text NOT NULL,
        state text NOT NULL CHECK (state IN ('staging', 'ready', 'quarantined', 'deleting')),
        encrypted boolean NOT NULL DEFAULT false
    """)
    run("""
    CREATE TRIGGER objects_immutable BEFORE UPDATE ON objects
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable(
            'sha256', 'storage_backend', 'object_key', 'size_bytes');
    """)

    create_table('authors', """
        name text NOT NULL,
        normalized_name text NOT NULL,
        notes text
    """)
    run('CREATE INDEX authors_normalized_name_idx ON authors (normalized_name);')

    create_table('books', """
        title text NOT NULL,
        normalized_title text NOT NULL,
        language text NOT NULL,
        description text,
        revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
        created_by uuid NOT NULL REFERENCES users,
        deleted_at timestamptz
    """)
    run("""
    CREATE INDEX books_normalized_title_trgm_idx ON books
        USING gin (normalized_title gin_trgm_ops);
    CREATE INDEX books_created_by_idx ON books (created_by);
    """)

    create_table('book_authors', """
        book_id uuid NOT NULL REFERENCES books,
        author_id uuid NOT NULL REFERENCES authors,
        role text NOT NULL CHECK (role IN ('author', 'commentator', 'translator', 'editor')),
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        UNIQUE (book_id, author_id, role)
    """)
    run('CREATE INDEX book_authors_author_id_idx ON book_authors (author_id);')

    create_table('book_versions', """
        book_id uuid NOT NULL REFERENCES books,
        object_id uuid NOT NULL REFERENCES objects,
        edition_label text NOT NULL,
        version_no integer NOT NULL CHECK (version_no >= 1),
        rights_status text NOT NULL CHECK (rights_status IN
            ('unknown', 'private_reference', 'licensed', 'public_domain', 'restricted')),
        external_processing_allowed boolean NOT NULL DEFAULT false,
        status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn')),
        uploaded_by uuid NOT NULL REFERENCES users,
        withdrawn_at timestamptz,
        CHECK ((status = 'withdrawn') = (withdrawn_at IS NOT NULL)),
        UNIQUE (book_id, version_no),
        UNIQUE (book_id, object_id)
    """)
    run("""
    CREATE INDEX book_versions_object_id_idx ON book_versions (object_id);
    CREATE INDEX book_versions_uploaded_by_idx ON book_versions (uploaded_by);
    CREATE TRIGGER book_versions_immutable BEFORE UPDATE ON book_versions
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable('book_id', 'object_id', 'version_no');
    """)

    create_table('book_access', """
        book_id uuid NOT NULL REFERENCES books,
        user_id uuid REFERENCES users,
        role_scope text CHECK (role_scope IN ('reader', 'reviewer', 'admin')),
        permission text NOT NULL CHECK (permission IN ('read', 'review', 'manage')),
        CHECK (num_nonnulls(user_id, role_scope) = 1),
        UNIQUE NULLS NOT DISTINCT (book_id, user_id, role_scope, permission)
    """)
    run('CREATE INDEX book_access_user_id_idx ON book_access (user_id);')


def downgrade() -> None:
    run('DROP TABLE book_access, book_versions, book_authors, books, authors, objects;')
