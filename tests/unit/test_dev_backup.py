"""Host backup/restore commands of scripts/dev (T052.1/T053.1), without running Docker."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
dev = SourceFileLoader('bazi_dev', str(ROOT / 'scripts/dev')).load_module()


class BackupCommandTests(unittest.TestCase):
    def test_backup_runs_the_cli_in_the_worker_with_the_destination_mounted(self):
        with tempfile.TemporaryDirectory() as directory:
            [command] = dev.backup_commands('docker', Path(directory), 'nightly-1')
        mount = f'{Path(directory).resolve()}:/backups'
        self.assertEqual(command[:2], ['docker', 'compose'])
        self.assertNotIn('-p', command)                       # the live project
        self.assertEqual(command[command.index('-v') + 1], mount)
        self.assertEqual(command[command.index('worker'):],
                         ['worker', 'python', '-m', 'backend.app.cli', 'backup', '--dest',
                          '/backups', '--name', 'nightly-1'])

    def test_restore_only_targets_a_new_project_and_mounts_the_backup_read_only(self):
        manifest = Path('/srv/backups/nightly-1/manifest.json')
        with self.assertRaises(SystemExit):
            dev.restore_commands('docker', manifest, 'nightly-1', dev.LIVE_PROJECT)
        up, restore, login = dev.restore_commands('docker', manifest, 'nightly-1', 'bazi-restore')
        for command in (up, restore, login):
            self.assertEqual(command[command.index('-p') + 1], 'bazi-restore')
        self.assertTrue(restore[restore.index('-v') + 1].endswith(':/backup:ro'))
        self.assertEqual(restore[-4:], ['--manifest', '/backup/manifest.json', '--confirm',
                                        'nightly-1'])
        self.assertEqual(login[-1], 'create-runtime-login')
        [preflight] = dev.preflight_commands('docker', manifest)
        self.assertEqual(preflight[:6], ['docker', 'run', '--rm', '--network', 'none', '--read-only'])
        self.assertNotIn('compose', preflight)


if __name__ == '__main__':
    unittest.main()
