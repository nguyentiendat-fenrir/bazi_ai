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
    def test_missing_prerequisites_block_without_leaking_env_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('POSTGRES_PASSWORD=\n', encoding='utf-8')
            (root / '.env').write_text('POSTGRES_PASSWORD="DO_NOT_PRINT_THIS_SECRET"\n', encoding='utf-8')
            with patch.object(dev, 'dependency_reachable', return_value=False), \
                 patch.object(dev, 'port_available', return_value=True), \
                 patch.object(dev, 'memory_bytes', return_value=32 * 1024**3), \
                 patch.object(dev.shutil, 'which', return_value=None):
                result = dev.doctor(root)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertIn('docker_cli', result['essential_failures'])
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
