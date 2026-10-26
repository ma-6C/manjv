"""Controlled tests; no native app is launched by this test."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import jianying_automation as module


class Fake:
    def __init__(self, snapshots, invokes=True, raises=False):
        self.snapshots = list(snapshots)
        self.invokes = invokes
        self.raises = raises
        self.launches = 0
        self.actions = 0

    def inspect(self, *args):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def open_target(self, *args):
        self.actions += 1
        if self.raises:
            raise RuntimeError('unknown outcome')
        return self.invokes

    def launch(self, *args):
        self.launches += 1
        return {'appLaunched': True}


HOME = {'mode': 'home', 'windowId': '1', 'targetCount': 1}
OPEN = {'mode': 'target_editor', 'windowId': '1', 'pid': 10,
        'timelineVerified': True, 'projectTitleVerified': True}


class Tests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).parent / 'tmp'
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='jianying-handoff-', dir=temporary_root)
        self.folder = Path(self.temp.name)
        self.result = {'directory': str(self.folder), 'name': 'registered'}
        self.manifest = {'name': 'registered', 'editorImportedAt': 1}
        self.editor = {'editorInstalled': True, 'editorSignatureVerified': True}
        self.patchers = [patch.object(module.jianying_projects, '_open_index', return_value=(self.manifest, False)),
                         patch.object(module.jianying_projects, 'status', return_value=self.editor)]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    def run_flow(self, fake, **kwargs):
        return module.open_registered_project(self.result, backend=fake, wait_timeout=kwargs.pop('timeout', 0), **kwargs)

    def test_existing_exact_editor_is_idempotent(self):
        fake = Fake([OPEN])
        result = self.run_flow(fake)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['projectOpened'])
        self.assertFalse(result['editorValidated'])
        self.assertFalse(result['projectConfirmedByUser'])
        self.assertEqual(fake.actions + fake.launches, 0)

    def test_exact_title_and_timeline_both_required(self):
        for missing in ('timelineVerified', 'projectTitleVerified'):
            fake = Fake([{**OPEN, missing: False}])
            result = self.run_flow(fake)
            self.assertEqual(result['status'], 'waiting_action')
            self.assertFalse(result['projectOpened'])

    def test_unique_home_native_action_then_verified_editor(self):
        fake = Fake([HOME, OPEN])
        result = self.run_flow(fake, timeout=1)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(fake.actions, 1)
        self.assertEqual(fake.launches, 0)

    def test_unknown_action_outcome_observes_without_retry(self):
        fake = Fake([HOME, HOME, OPEN], raises=True)
        result = self.run_flow(fake, timeout=1)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(fake.actions, 1)

    def test_launch_alone_never_completes(self):
        fake = Fake([{'mode': 'unavailable'}])
        result = self.run_flow(fake)
        self.assertEqual(fake.launches, 1)
        self.assertTrue(result['appLaunched'])
        self.assertFalse(result['projectOpened'])
        self.assertEqual(result['status'], 'waiting_action')

    def test_do_not_touch_other_project(self):
        fake = Fake([{'mode': 'other_editor'}])
        self.assertEqual(self.run_flow(fake)['status'], 'waiting_action')
        self.assertEqual(fake.actions + fake.launches, 0)

    def test_ambiguous_or_missing_title_does_not_invoke(self):
        for snapshot in ({**HOME, 'targetCount': 0}, {**HOME, 'targetCount': 2}, {'mode': 'ambiguous'}):
            fake = Fake([snapshot])
            self.assertEqual(self.run_flow(fake)['status'], 'waiting_action')
            self.assertEqual(fake.actions + fake.launches, 0)

    def test_no_callable_native_action_waits(self):
        fake = Fake([HOME], invokes=False)
        self.assertEqual(self.run_flow(fake)['status'], 'waiting_action')
        self.assertEqual(fake.actions, 1)

    def test_invalid_signature_never_launches(self):
        self.editor['editorSignatureVerified'] = False
        fake = Fake([HOME])
        result = self.run_flow(fake)
        self.assertEqual(result['reason'], 'editor_missing')
        self.assertEqual(fake.actions + fake.launches, 0)

    def test_cancel_retains_registered_directory(self):
        event = threading.Event()
        event.set()
        fake = Fake([HOME])
        result = self.run_flow(fake, cancel_event=event)
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(self.folder.is_dir())
        self.assertEqual(fake.actions + fake.launches, 0)

    def test_manifest_name_must_match_import(self):
        with self.assertRaises(ValueError):
            module.open_registered_project({**self.result, 'name': 'another'}, backend=Fake([OPEN]))

    def test_incomplete_import_rejected(self):
        (self.folder / '未完成导入.txt').write_text('fixture', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_flow(Fake([OPEN]))

    def test_parallel_native_handoff_not_dispatched_twice(self):
        module._OPEN_LOCK.acquire()
        try:
            fake = Fake([HOME])
            self.assertEqual(self.run_flow(fake)['reason'], 'editor_busy')
            self.assertEqual(fake.actions + fake.launches, 0)
        finally:
            module._OPEN_LOCK.release()

    def test_project_title_requires_reserved_identity(self):
        class Control:
            Name = 'registered'
            AutomationId = 'media.filename'

            def GetPropertyValue(self, _):
                return ''
        control = Control()
        self.assertFalse(module._editor_title(control, 'registered'))
        control.AutomationId = 'editor.title'
        self.assertTrue(module._editor_title(control, 'registered'))
        self.assertFalse(module._editor_title(control, 'registered-other'))

    def test_description_match_is_exact(self):
        class Control:
            Name = ''
            AutomationId = ''

            def GetPropertyValue(self, _):
                return 'MainWindowTitleBarDraftName:registered'
        self.assertTrue(module._editor_title(Control(), 'registered'))
        self.assertFalse(module._editor_title(Control(), 'register'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
