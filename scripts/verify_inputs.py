"""T001: inspect audited inputs and preserve legacy bytes, never execute them.

--check reads inputs and legacy only. --extract stages verified files and renames
the complete directory into place; an existing legacy tree is never overwritten.
No dependency is needed to report missing inputs. RAR reading needs rarfile 4.2.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_ENTRIES = 10000
EXCLUDED_DIRS = {'.venv', 'venv', '.git', '__pycache__', '.cache',
                 '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.exe', '.dll', '.pyd', '.so', '.dylib',
                     '.o', '.obj', '.a', '.lib', '.class'}
RESERVED = re.compile(r'^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)', re.I)


class VerificationError(Exception):
    """A sanitized diagnostic; do not include input contents or external paths."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_member(name: str, directory: bool = False) -> str:
    """Reject ambiguous Windows AND POSIX paths before any member is read."""
    name = name.replace('\\', '/')
    if directory and name.endswith('/'):
        name = name[:-1]
    parts = name.split('/')
    if (not name or len(name) > 240 or any(
        not p or p in {'.', '..'} or p[-1:] in {' ', '.'}
        or RESERVED.match(p) or any(ord(c) < 32 or c in ':*?"<>|\x7f' for c in p)
        for p in parts
    )):
        raise VerificationError('UNSAFE_ARCHIVE_PATH')
    return '/'.join(parts)


def excluded(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (any(p.casefold() in EXCLUDED_DIRS for p in parts)
            or PurePosixPath(path).suffix.casefold() in EXCLUDED_SUFFIXES)


def local_path(root: Path, relative: str) -> Path:
    """Disallow symlinks, Windows junctions/reparse points and hardlinked files."""
    path = root
    for part in PurePosixPath(safe_member(relative)).parts:
        path = path / part
        try:
            st = path.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(st.st_mode)
            or getattr(st, 'st_file_attributes', 0) & 0x400
            or (stat.S_ISREG(st.st_mode) and st.st_nlink != 1)):
            raise VerificationError('UNSAFE_LOCAL_LINK')
    return path


def file_record(path: Path) -> dict:
    sha = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
            size += len(block)
    return {'size_bytes': size, 'sha256': sha.hexdigest()}


def load_contract(root: Path) -> tuple[list[dict], dict, dict, list[str]]:
    audit = (root / 'docs/02_SOURCE_CODE_AUDIT.md').read_text(encoding='utf-8')
    inputs = []
    for name, size, sha in re.findall(
        r'^\| ([^|]+) \| ([\d.]+) \| `([a-f0-9]{64})` \|$', audit, re.M
    ):
        folder = 'source' if name == 'bazi.rar' else 'books'
        path = safe_member(f'inputs/{folder}/{name}')
        inputs.append({'path': path, 'size_bytes': int(size.replace('.', '')), 'sha256': sha})
    if not any(x['path'] == 'inputs/source/bazi.rar' for x in inputs):
        raise VerificationError('MISSING_ARCHIVE_CONTRACT')
    metrics = json.loads((root / 'evidence/pdf_metrics.json').read_text(encoding='utf-8'))
    hashes = {x['path']: x['sha256'] for x in inputs}
    issues = []
    for row in metrics:
        if hashes.get('inputs/books/' + row['name']) != row['sha256']:
            issues.append('SPEC_CONFLICT_PDF_HASH')
    sources = {}
    for row in json.loads((root / 'evidence/source_manifest.json').read_text(encoding='utf-8')):
        path = safe_member(row['relative_path'])
        if path.startswith('dependency/') or excluded(path):
            continue
        if path in sources or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise VerificationError('INVALID_SOURCE_MANIFEST')
        sources[path] = {'size_bytes': row['size_bytes'], 'sha256': row['sha256']}
    count = re.search(r'source nghiệp vụ \((\d+) tệp gồm', audit)
    if not count or int(count[1]) != len(sources):
        issues.append('SPEC_CONFLICT_SOURCE_COUNT')
    totals = re.search(r'RAR có ([\d.]+) entries.*?([\d.]+) bytes tổng uncompressed', audit)
    if not totals:
        raise VerificationError('MISSING_ARCHIVE_TOTALS')
    archive = {'entries': int(totals[1].replace('.', '')),
               'expanded_bytes': int(totals[2].replace('.', ''))}
    return inputs, sources, archive, sorted(set(issues))


def archive_payloads(data: bytes, expected: dict, totals: dict | None = None) -> tuple[dict, list]:
    """Preflight ALL RAR paths, then read only audited source into bounded memory.

    rarfile parses metadata; its open() streams bytes (no extract/extractall).
    The immutable byte snapshot closes the hash/list/extraction race on the RAR.
    """
    try:
        import rarfile
    except ImportError as exc:
        raise VerificationError('RAR_READER_MISSING: install scripts/requirements-t001.txt') from exc
    if len(data) > MAX_ARCHIVE:
        raise VerificationError('ARCHIVE_SIZE_LIMIT')
    try:
        with rarfile.RarFile(io.BytesIO(data), errors='strict') as archive:
            infos = archive.infolist()
            if archive.needs_password() or len(archive.volumelist()) > 1:
                raise VerificationError('ENCRYPTED_OR_MULTIVOLUME_ARCHIVE')
            if not infos or len(infos) > MAX_ENTRIES:
                raise VerificationError('ARCHIVE_ENTRY_LIMIT')
            inventory, names, selected = [], {}, {}
            expanded = 0
            for entry in infos:
                path = safe_member(entry.filename, entry.isdir())
                key = unicodedata.normalize('NFC', path).casefold()
                if key in names:
                    raise VerificationError('DUPLICATE_ARCHIVE_PATH')
                names[key] = entry.isdir()
                if (entry.is_symlink() or entry.file_redir is not None
                    or entry.flags & (rarfile.RAR_FILE_SPLIT_BEFORE | rarfile.RAR_FILE_SPLIT_AFTER)
                    or (not entry.isdir() and not entry.is_file())
                    or (entry.host_os == rarfile.RAR_OS_UNIX
                        and stat.S_IFMT(entry.mode) not in {stat.S_IFREG, stat.S_IFDIR})):
                    raise VerificationError('ARCHIVE_LINK_OR_SPECIAL_FILE')
                if entry.file_size < 0:
                    raise VerificationError('INVALID_MEMBER_SIZE')
                expanded += entry.file_size
                if expanded > MAX_EXPANDED:
                    raise VerificationError('ARCHIVE_EXPANSION_LIMIT')
                if path != 'bazi' and not path.startswith('bazi/'):
                    raise VerificationError('UNEXPECTED_ARCHIVE_ROOT')
                relative = path.removeprefix('bazi/')
                action = 'directory' if entry.isdir() else 'excluded' if excluded(relative) else 'source'
                if action == 'source':
                    if relative not in expected:
                        raise VerificationError('UNEXPECTED_SOURCE_FILE')
                    if entry.file_size != expected[relative]['size_bytes']:
                        raise VerificationError('SOURCE_SIZE_MISMATCH')
                    selected[relative] = entry
                inventory.append({'path': path, 'size_bytes': entry.file_size, 'action': action})
            for key in names:
                for parent in PurePosixPath(key).parents:
                    if names.get(str(parent)) is False:
                        raise VerificationError('ARCHIVE_FILE_DIRECTORY_COLLISION')
            if totals and (len(infos) != totals['entries'] or expanded != totals['expanded_bytes']):
                raise VerificationError('ARCHIVE_TOTALS_MISMATCH')
            if set(selected) != set(expected):
                raise VerificationError('MISSING_SOURCE_MEMBERS')
            payloads = {}
            for path, entry in selected.items():
                with archive.open(entry) as stream:
                    content = stream.read(expected[path]['size_bytes'] + 1)
                if len(content) != expected[path]['size_bytes'] or digest(content) != expected[path]['sha256']:
                    raise VerificationError('SOURCE_HASH_MISMATCH')
                payloads[path] = content
            return payloads, inventory
    except rarfile.Error as exc:
        raise VerificationError('RAR_READ_FAILED: ' + type(exc).__name__) from exc


def verify_legacy(root: Path, expected: dict) -> bool:
    destination = local_path(root, 'legacy/bazi')
    if not destination.exists():
        return False
    if not destination.is_dir():
        raise VerificationError('LEGACY_NOT_DIRECTORY')
    actual = set()
    allowed_dirs = {str(parent) for path in expected for parent in PurePosixPath(path).parents}
    for parent, dirs, files in os.walk(destination, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            local_path(root, path.relative_to(root).as_posix())
            relative = path.relative_to(destination).as_posix()
            if name in dirs and relative not in allowed_dirs:
                raise VerificationError('UNEXPECTED_LEGACY_DIRECTORY')
            if name in files:
                if relative not in expected or not path.is_file():
                    raise VerificationError('UNEXPECTED_LEGACY_FILE')
                actual.add(relative)
                if file_record(path) != expected[relative]:
                    raise VerificationError('LEGACY_HASH_MISMATCH')
    if actual != set(expected):
        raise VerificationError('INCOMPLETE_LEGACY')
    return True


def preserve(root: Path, payloads: dict, expected: dict) -> str:
    if set(payloads) != set(expected):
        raise VerificationError('PAYLOAD_MANIFEST_MISMATCH')
    for relative, content in payloads.items():
        safe_member(relative)
        if len(content) != expected[relative]['size_bytes'] or digest(content) != expected[relative]['sha256']:
            raise VerificationError('PAYLOAD_HASH_MISMATCH')
    if verify_legacy(root, expected):
        return 'ALREADY_VERIFIED'
    destination = local_path(root, 'legacy/bazi')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage inside legacy, on the same volume. TemporaryDirectory only removes
    # the private staging directory it created; it never removes user source.
    with tempfile.TemporaryDirectory(prefix='.t001-', dir=destination.parent) as tmp:
        stage = Path(tmp) / 'bazi'
        stage.mkdir()
        for relative, content in payloads.items():
            target = local_path(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(content)
        # Check staged bytes before publication, never repair existing source.
        for relative, record in expected.items():
            if file_record(local_path(stage, relative)) != record:
                raise VerificationError('STAGED_HASH_MISMATCH')
        local_path(root, 'legacy/bazi')
        if destination.exists():
            raise VerificationError('LEGACY_APPEARED_DURING_EXTRACTION')
        stage.rename(destination)
    return 'EXTRACTED_VERIFIED'


def verify(root: Path, extract: bool = False) -> dict:
    inputs, sources, totals, conflicts = load_contract(root)
    report = {'task': 'T001', 'mode': 'extract' if extract else 'check',
              'status': 'BLOCKED', 'inputs': [], 'issues': conflicts,
              'source_count_in_manifest': len(sources), 'archive': 'NOT_CHECKED',
              'legacy': 'NOT_CHECKED'}
    rar_record = None
    for expected in inputs:
        path = local_path(root, expected['path'])
        row = {'path': expected['path'], 'expected': {k: v for k, v in expected.items() if k != 'path'}}
        if not path.exists():
            row['status'] = 'MISSING'
        elif not path.is_file():
            row['status'] = 'NOT_REGULAR_FILE'
        else:
            row['actual'] = file_record(path)
            row['status'] = 'PASS' if row['actual'] == row['expected'] else 'MISMATCH'
        report['inputs'].append(row)
        if expected['path'] == 'inputs/source/bazi.rar':
            rar_record = row
        elif row['status'] not in {'PASS', 'MISSING'}:
            report['issues'].append('PDF_HASH_MISMATCH')
    if rar_record['status'] != 'PASS':
        report['issues'].append('SOURCE_ARCHIVE_' + rar_record['status'])
    # Always inspect existing legacy, even when original input is missing.
    report['legacy'] = 'VERIFIED' if verify_legacy(root, sources) else 'MISSING'
    if not report['issues']:
        path = local_path(root, 'inputs/source/bazi.rar')
        with path.open('rb') as stream:
            data = stream.read(MAX_ARCHIVE + 1)
        if len(data) != rar_record['expected']['size_bytes'] or digest(data) != rar_record['expected']['sha256']:
            raise VerificationError('ARCHIVE_CHANGED_DURING_CHECK')
        payloads, inventory = archive_payloads(data, sources, totals)
        report['archive'] = 'VERIFIED'
        report['archive_entries'] = inventory
        if extract:
            report['legacy'] = preserve(root, payloads, sources)
    if report['legacy'] == 'MISSING':
        report['issues'].append('LEGACY_MISSING')
    report['status'] = 'BLOCKED' if report['issues'] else 'PASS'
    report['missing_books_optional_for_T001'] = [
        row['path'] for row in report['inputs']
        if row['path'].startswith('inputs/books/') and row['status'] == 'MISSING'
    ]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--extract', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = verify(ROOT, args.extract)
    except (VerificationError, OSError, ValueError, KeyError) as exc:
        # No raw filesystem/parser errors: they may contain private paths/data.
        report = {'task': 'T001', 'status': 'BLOCKED', 'issues': [
            str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
        ]}
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
