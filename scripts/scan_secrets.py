"""Local static T001 secrets scan; prints rule/line only, never secret values.

Scan first-party text and preserved source. Raw inputs, installed tooling and
Git internals are excluded explicitly, not claimed scanned. This is a bounded
pattern scan, not a replacement for release security/dependency scans in T049.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.tools', '.venv', '__pycache__', '.pytest_cache',
        '.cache', '.artifacts', '.next', 'node_modules', 'inputs'}
TEXT_SUFFIXES = {'.py', '.md', '.json', '.txt', '.toml', '.yaml', '.yml',
                 '.js', '.ts', '.tsx', '.html', '.css', '.sh', '.ps1'}
RULES = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'provider_token': re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9-]{20,})\b'),
    'credential_url': re.compile(r'(?i)(?:postgres(?:ql)?|mysql|redis|https?)://[^\s/:]+:[^\s/@]+@'),
    'literal_credential': re.compile(r'''(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*["'][A-Za-z0-9_+/=.-]{12,}["']'''),
}


def findings(text):
    return [{'rule': name, 'line': text.count('\n', 0, match.start()) + 1}
            for name, pattern in RULES.items() for match in pattern.finditer(text)]


def ignored_local_env(root):
    safe = '-c'
    directory = 'safe.directory=' + str(root.resolve()).replace('\\', '/')
    base = ['git', safe, directory]
    try:
        ignored = subprocess.run(base + ['check-ignore', '-q', '--', '.env'],
                                 cwd=root, capture_output=True, check=False)
        tracked = subprocess.run(base + ['ls-files', '--error-unmatch', '--', '.env'],
                                 cwd=root, capture_output=True, check=False)
    except OSError:
        return False
    return ignored.returncode == 0 and tracked.returncode == 1


def scan(root):
    matches, errors, count, local_secret_files = [], [], 0, []
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (Path(parent) / d).is_symlink())
        for name in sorted(files):
            path = Path(parent) / name
            if path.is_symlink():
                errors.append('SYMLINK_NOT_SCANNED')
                continue
            relative = path.relative_to(root).as_posix()
            if name == '.env' or name.startswith('.env.') and name != '.env.example':
                # Never read local secrets. Accept only the root .env when Git
                # confirms it is ignored and not tracked.
                if relative == '.env' and ignored_local_env(root):
                    local_secret_files.append(relative)
                else:
                    matches.append({'path': relative, 'rule': 'secret_file_present', 'line': 0})
                continue
            if path.suffix not in TEXT_SUFFIXES and name != '.gitignore':
                continue
            try:
                content = path.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError):
                errors.append('UNREADABLE_TEXT: ' + relative)
                continue
            count += 1
            matches.extend({'path': relative, **hit} for hit in findings(content))
    return {'status': 'PASS' if not matches and not errors else 'FAIL',
            'kind': 'static_pattern_scan', 'files_scanned': count,
            'excluded_directories': sorted(SKIP), 'rules': sorted(RULES),
            'findings': matches, 'errors': errors,
            'ignored_local_secret_files': local_secret_files}


if __name__ == '__main__':
    result = scan(ROOT)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)
