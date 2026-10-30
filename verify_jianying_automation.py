"""Controlled tests; no native app is launched by this test."""
import tempfile
import json
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


class FirstDraftFake(Fake):
    def __init__(self,snapshots,raises=False):
        super().__init__(snapshots,raises=raises)
        self.first_actions=0

    def open_first(self,*args):
        self.first_actions+=1
        if self.raises:raise RuntimeError('unknown click outcome')
        return True


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

    def test_first_draft_opens_without_per_card_accessibility(self):
        fake=FirstDraftFake([{**HOME,'targetCount':0},OPEN])
        with patch.object(module.jianying_registry,'first_draft',return_value=True):
            result=module.open_registered_project(self.result,{'mouseOpen':True},backend=fake,wait_timeout=1)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(fake.first_actions,1)
        self.assertEqual(fake.actions,0)

    def test_first_draft_gate_prevents_opening_another_card(self):
        fake=FirstDraftFake([{**HOME,'targetCount':0}])
        with patch.object(module.jianying_registry,'first_draft',return_value=False):
            result=module.open_registered_project(self.result,{'mouseOpen':True},backend=fake,wait_timeout=0)
        self.assertEqual(result['status'],'waiting_action')
        self.assertEqual(fake.first_actions,0)

    def test_idle_home_exits_before_index_registration(self):
        fake=FirstDraftFake([HOME,{**HOME,'targetCount':0},OPEN])
        order=[]
        fake.close_home=lambda *args:order.append('close_home') or True
        with patch.object(module,'NativeBackend',return_value=fake),patch.object(module.jianying_registry,'first_draft',return_value=True),patch.object(module.jianying_registry,'register',side_effect=lambda *args:order.append('register') or {}):
            result=module.open_registered_project(self.result,{'mouseOpen':True},wait_timeout=1)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(order,['close_home','register'])

    def test_other_editor_never_closes_or_registers(self):
        fake=FirstDraftFake([{'mode':'other_editor'}])
        with patch.object(module,'NativeBackend',return_value=fake),patch.object(module.jianying_registry,'register') as register:
            result=module.open_registered_project(self.result,{'mouseOpen':True},wait_timeout=0)
        self.assertEqual(result['status'],'waiting_action')
        register.assert_not_called()
        self.assertEqual(fake.first_actions,0)

    def test_home_exit_prompt_keeps_index_unchanged(self):
        fake=FirstDraftFake([HOME]);fake.close_home=lambda *args:False
        with patch.object(module,'NativeBackend',return_value=fake),patch.object(module.jianying_registry,'register') as register:
            result=module.open_registered_project(self.result,{'mouseOpen':True},wait_timeout=0)
        self.assertEqual(result['status'],'waiting_action')
        register.assert_not_called()
        self.assertEqual(fake.first_actions,0)

    def test_first_draft_click_unknown_outcome_is_not_repeated(self):
        fake=FirstDraftFake([{**HOME,'targetCount':0},HOME,OPEN],raises=True)
        with patch.object(module.jianying_registry,'first_draft',return_value=True):
            result=module.open_registered_project(self.result,{'mouseOpen':True},backend=fake,wait_timeout=1)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(fake.first_actions,1)

    def test_index_first_draft_requires_path_name_and_id(self):
        folder=self.folder/'draft';folder.mkdir()
        row={'draft_name':'registered','draft_fold_path':str(folder),'draft_id':'our-id'}
        index_path=self.folder/'root_meta_info.json'
        manifest={**self.manifest,'editorDraftId':'our-id'}
        with patch.dict('os.environ',{'LOCALAPPDATA':str(self.folder/'empty-profile')}),patch.object(module.jianying_projects,'_open_index',return_value=(manifest,False)):
            for changed in ({'draft_name':'other'},{'draft_id':'other-id'},{'draft_fold_path':str(self.folder/'other')}):
                index_path.write_text(json.dumps({'all_draft_store':[{**row,**changed}]}),'utf-8')
                self.assertFalse(module.jianying_registry.first_draft(folder))
            index_path.write_text(json.dumps({'all_draft_store':[row]}),'utf-8')
            self.assertTrue(module.jianying_registry.first_draft(folder))
            index_path.write_text(json.dumps({'all_draft_store':[{'draft_name':'other'},row]}),'utf-8')
            self.assertFalse(module.jianying_registry.first_draft(folder))

    def test_unknown_action_outcome_observes_without_retry(self):
        fake = Fake([HOME, HOME, OPEN], raises=True)
        result = self.run_flow(fake, timeout=1)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(fake.actions, 1)

    def test_native_reassigned_id_requires_metadata_name_path_and_id_agreement(self):
        folder=self.folder/'draft';folder.mkdir()
        row={'draft_name':'registered','draft_fold_path':str(folder),'draft_id':'native-id'}
        index_path=self.folder/'root_meta_info.json';index_path.write_text(json.dumps({'all_draft_store':[row]}),'utf-8')
        manifest={**self.manifest,'editorDraftId':'original-id'}
        meta=folder/'draft_meta_info.json'
        with patch.dict('os.environ',{'LOCALAPPDATA':str(self.folder/'empty-profile')}),patch.object(module.jianying_projects,'_open_index',return_value=(manifest,False)):
            for changed in ({'draft_name':'other'},{'draft_id':'other-id'},{'draft_fold_path':str(self.folder/'other')}):
                meta.write_text(json.dumps({**row,**changed}),'utf-8')
                self.assertFalse(module.jianying_registry.first_draft(folder))
            meta.write_text(json.dumps(row),'utf-8')
            self.assertTrue(module.jianying_registry.first_draft(folder))

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
