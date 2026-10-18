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
        self.assertEqual(preflight[6:8], ['-e', 'BACKUP_ENCRYPTION_KEY'])   # by name, no value
        self.assertNotIn('compose', preflight)

    def test_deletion_ledger_is_exported_and_passed_read_only_to_a_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            [export] = dev.ledger_commands('docker', Path(directory))
        self.assertNotIn('-p', export)                        # read from the live project
        self.assertEqual(export[-3:], ['deletion-ledger', '--out', '/backups/deletion-ledger.json'])
        ledger = Path('/srv/backups/deletion-ledger.json')
        _, restore, _ = dev.restore_commands('docker', Path('/srv/backups/n/manifest.json'), 'n',
                                             'bazi-restore', ledger=ledger)
        self.assertIn(f'{ledger.resolve()}:/ledger.json:ro', restore)
        self.assertEqual(restore[-2:], ['--deletion-ledger', '/ledger.json'])

    def test_a_drill_restores_into_its_own_project_and_removes_only_that(self):
        steps, teardown = dev.drill_commands('docker', Path('/srv/b/n/manifest.json'), 'n')
        for command in (*steps, teardown):
            self.assertEqual(command[command.index('-p') + 1], dev.DRILL_PROJECT)
        self.assertNotEqual(dev.DRILL_PROJECT, dev.LIVE_PROJECT)
        self.assertEqual(teardown[-5:], ['--profile', 'app', 'down', '-v', '--remove-orphans'])
        self.assertIn('restore', steps[1])


if __name__ == '__main__':
    unittest.main()
