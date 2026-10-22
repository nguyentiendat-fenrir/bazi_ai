"""Owner-side commands of the RAG pilot (run through ``python -m backend.app.cli``).

* ``fetch-models``  — download the pinned models into the model cache (run once, as
  root, with network, on a writable mount: ``docker run --rm --user 0 -v
  bazi-ai_model_cache:/models -e HF_HUB_OFFLINE=0 bazi-ai-app:local …`` — the compose
  services mount the cache read-only);
  SenOCR-Vi gets a PaddleX-ready directory (its single shard linked as
  ``model.safetensors``, which PaddleX's transformers engine looks for).
* ``rag-setup``     — local-jina embedding profile (1024-d) + provisioned collection with
  HNSW + the pipeline profile books are processed with. Idempotent.
* ``ingest-folder`` — every PDF/DOCX under a folder becomes a book; the folder name gives
  the school (``Manh Phái`` → manh_phai, ``Vượng suy`` → tu_binh). The school scope is
  created and approved by the named admin (an explicit, audited review), and the batch
  auto-publishes when no page needs a person.
* ``judge-password`` — Argon2 hash for ``JUDGE_PASSWORD_HASH``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from sqlalchemy import create_engine, pool, text

from ..auth.passwords import hash_password
from ..auth.service import Principal
from ..core.config import load_settings
from ..documents.text import fold

FOLDER_SCHOOLS = {'manh phai': 'manh_phai', 'vuong suy': 'tu_binh', 'tu binh': 'tu_binh'}
SENOCR_DIR = Path('/models/senocr-vi')
EXTENSIONS = {'.pdf', '.docx'}


def fetch_models(settings=None, ocr_only: bool = False) -> dict:
    """``ocr_only``: just SenOCR-Vi + the layout model (a remote OCR server needs no Jina)."""
    from huggingface_hub import snapshot_download
    settings = settings or load_settings()
    out = {}
    rag_models = () if ocr_only else (
        (settings.rag_embedding_model, settings.rag_embedding_revision),
        (settings.rag_reranker_model, settings.rag_reranker_revision))
    for name, revision in rag_models:
        out[name] = snapshot_download(name, revision=revision)
    snapshot = Path(snapshot_download(settings.ocr_model, revision=settings.ocr_revision))
    target = SENOCR_DIR / snapshot.name[:12]
    target.mkdir(parents=True, exist_ok=True)
    for item in snapshot.iterdir():
        if item.name in ('model.safetensors.index.json', 'banner.png', 'README.md'):
            continue
        link = target / ('model.safetensors' if item.name.endswith('-of-00001.safetensors')
                         else item.name)
        if not link.exists():
            link.symlink_to(item.resolve())
    current = SENOCR_DIR / 'current'
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(target.name)
    out[settings.ocr_model] = str(target)
    try:
        # The layout model (PP-DocLayoutV3) is fetched by PaddleX on first use.
        from paddlex import create_model
        create_model('PP-DocLayoutV3', device='cpu')
        out['PP-DocLayoutV3'] = 'cached'
    except Exception as exc:  # noqa: BLE001 - report, the worker will retry on first OCR
        out['PP-DocLayoutV3'] = f'not cached: {type(exc).__name__}'
    for root, dirs, files in os.walk('/models'):
        for entry in dirs + files:
            path = os.path.join(root, entry)
            if not os.path.islink(path):
                os.chmod(path, 0o755 if os.path.isdir(path) else 0o644)
    return out


def rag_setup(settings=None) -> dict:
    import psycopg

    from ..ingestion.docx import renderer_version
    from ..ingestion.profiles import create_pipeline_profile
    from ..retrieval.models import create_ann_index, provision_collection, register_profile
    settings = settings or load_settings()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        profile = register_profile(conn, 'local-jina', settings.rag_embedding_model,
                                   settings.rag_embedding_revision, 1024,
                                   {'locality': 'local', 'threads': settings.rag_cpu_threads},
                                   None)
    owner = settings.database_url
    with psycopg.connect(host=owner.host, port=owner.port, dbname=owner.database,
                         user=owner.username, password=owner.password, autocommit=True) as conn:
        table = provision_collection(conn, profile, 'cosine')
        create_ann_index(conn, profile)
    with engine.begin() as conn:
        pipeline_id, created = create_pipeline_profile(
            conn, 'RAG pilot (SenOCR-Vi + chunker-3 + jina-v5)', uuid.UUID(profile.id), None,
            renderer_version())
    return {'embedding_profile': profile.id, 'collection': table,
            'pipeline_profile': str(pipeline_id), 'created': created}


def judge_password_hash(password: str) -> str:
    return hash_password(password)


def _school_key(folder: str) -> str | None:
    return FOLDER_SCHOOLS.get(' '.join(fold(folder).lower().split()))


def ingest_folder(root: Path, admin_email: str, pipeline_profile_id: str | None = None,
                  only: list[str] | None = None, auto_publish: bool = True,
                  settings=None) -> dict:
    from ..documents.uploads import (UploadForm, UploadRejected, accept_upload, create_batch,
                                     record_rejection)
    from ..knowledge.decisions import decide
    from ..knowledge.scopes import create_scope
    from ..storage import build_store
    settings = settings or load_settings()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    store = build_store(settings)
    with engine.begin() as conn:
        user = conn.execute(text("SELECT id, email, role FROM users WHERE lower(email) = lower(:e)"
                                 " AND role = 'admin'"), {'e': admin_email}).first()
        if user is None:
            raise SystemExit(f'no admin account {admin_email}')
        principal = Principal(user.id, user.email, user.role, uuid.uuid4(), '')
        if pipeline_profile_id is None:
            pipeline_profile_id = conn.execute(text(
                "SELECT id FROM pipeline_profiles WHERE name LIKE 'RAG pilot%'"
                ' ORDER BY created_at DESC LIMIT 1')).scalar()
        if pipeline_profile_id is None:
            raise SystemExit('no RAG pilot pipeline profile; run rag-setup first')
        schools = dict(conn.execute(text('SELECT key, id FROM schools')).all())
        batch = create_batch(conn, principal, f'ingest-folder {root.name}',
                             uuid.UUID(str(pipeline_profile_id)), auto_publish)
    files = sorted(p for p in root.rglob('*') if p.suffix.lower() in EXTENSIONS and p.is_file())
    if only:
        files = [p for p in files if any(o.lower() in p.name.lower() for o in only)]
    report = []
    for path in files:
        school_key = _school_key(path.parent.name)
        entry = {'file': str(path.relative_to(root)), 'school': school_key}
        form = UploadForm(batch['id'], 'pilot', 'private_reference', False, None, None, 'vi')
        try:
            with engine.begin() as conn, path.open('rb') as stream:
                conn.execute(text("SELECT set_config('app.user_id', :u, true)"),
                             {'u': str(principal.user_id)})
                result = accept_upload(conn, store, principal, form, stream, path.name)
                entry.update(outcome=result['outcome'], version_id=result.get('version_id'),
                             job_id=result.get('job_id'))
                if result['outcome'] == 'accepted' and school_key in schools:
                    scope = create_scope(conn, principal, uuid.UUID(result['version_id']),
                                         schools[school_key], None, None,
                                         f'Thư mục nguồn "{path.parent.name}" (ingest-folder)')
                    decide(conn, principal, 'school_scope', uuid.UUID(scope['id']), 'approve', 1,
                           'Trường phái theo thư mục sách (RAG pilot, ingest-folder)', None)
        except UploadRejected as exc:
            record_rejection(engine, principal, batch['id'], path.name, exc.code)
            entry.update(outcome='rejected', error=exc.code)
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    return {'batch_id': str(batch['id']), 'files': len(report),
            'accepted': sum(1 for r in report if r.get('outcome') == 'accepted')}
