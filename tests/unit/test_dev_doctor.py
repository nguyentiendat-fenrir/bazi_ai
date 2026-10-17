"""Behavioral checks for T002 doctor without a live Docker installation."""
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
dev = SourceFileLoader('bazi_dev', str(ROOT / 'scripts/dev')).load_module()


class DoctorTests(unittest.TestCase):
    def test_windows_development_does_not_require_wsl_docker_or_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'infra').mkdir()
            for name in ('.env.example', 'uv.lock', 'infra/compose.yaml'):
                (root / name).touch()
            with patch.object(dev.platform, 'system', return_value='Windows'), \
                 patch.object(dev.sys, 'version_info', (3, 12)), \
                 patch.object(dev, 'docker_executable', return_value=None), \
                 patch.object(dev, 'dependency_reachable', return_value=False):
                result = dev.doctor(root, target='dev')
                server = dev.doctor(root, target='deploy')
            self.assertEqual(result['status'], 'READY')
            self.assertEqual(server['status'], 'BLOCKED')
            self.assertIn('linux_environment', server['essential_failures'])
            self.assertIn('docker_cli', server['essential_failures'])
            self.assertIn('env_postgres_password', server['essential_failures'])

    def test_missing_prerequisites_block_without_leaking_env_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('POSTGRES_PASSWORD=\n', encoding='utf-8')
            (root / '.env').write_text('POSTGRES_PASSWORD="DO_NOT_PRINT_THIS_SECRET"\n', encoding='utf-8')
            with patch.object(dev, 'dependency_reachable', return_value=False), \
                 patch.object(dev, 'memory_bytes', return_value=32 * 1024**3), \
                 patch.object(dev, 'docker_executable', return_value=None):
                result = dev.doctor(root, target='deploy')
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertIn('docker_cli', result['essential_failures'])
            self.assertIn('network_pypi_org', result['degraded'])
            self.assertTrue(result['checks']['env_postgres_password']['ok'])
            self.assertNotIn('DO_NOT_PRINT_THIS_SECRET', json.dumps(result))

    def test_cli_exit_matches_readiness(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/dev'), 'doctor'],
                                capture_output=True, text=True, timeout=30)
        output = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if output['status'] == 'READY' else 1)
        self.assertEqual(output['status'] == 'BLOCKED', bool(output['essential_failures']))
        self.assertNotIn('DO_NOT_PRINT_THIS_SECRET', result.stdout)


if __name__ == '__main__':
    unittest.main()
