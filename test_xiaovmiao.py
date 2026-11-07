"""Focused checks for executable boundaries and private runtime preparation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import xiaovmiao


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp')
        self.root = Path(self.temp.name)
        self.bundle = self.root/'app/modules/xiaovmiao'
        self.program = self.bundle/'程序'
        (self.program/'resources').mkdir(parents=True)
        (self.program/'vcat_local_init.exe').write_bytes(b'fixture-never-executed')
        (self.program/'resources/app.asar').write_bytes(b'fixture-archive')
        self.files = {p.relative_to(self.program).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in self.program.rglob('*') if p.is_file()}
        self.manifest = self.bundle/'module.json'
        self.manifest.write_text(json.dumps({'files':self.files}), 'utf-8')
        self.manager = xiaovmiao.Manager(self.root/'data', self.root/'app')

    def tearDown(self):
        self.temp.cleanup()

    def test_bundle_is_preferred_and_runtime_is_private(self):
        status = self.manager.status()
        self.assertTrue(status['bundled']); self.assertTrue(status['localMode'])
        path = self.manager.prepare_runtime(self.manager.executable())
        self.assertTrue(path.is_relative_to(self.root/'data'))
        self.assertEqual(path.read_bytes(), b'fixture-never-executed')
        self.assertEqual(self.manager.prepare_runtime(self.manager.executable()), path)
        self.assertFalse((self.bundle/'本地数据').exists())

    def test_changed_payload_is_rejected(self):
        (self.program/'resources/app.asar').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            self.manager.prepare_runtime(self.manager.executable())

    def test_manifest_cannot_escape_program_directory(self):
        self.manifest.write_text(json.dumps({'files':{'../../outside.exe':'a'*64}}), 'utf-8')
        with self.assertRaisesRegex(ValueError, '清单'):
            self.manager.prepare_runtime(self.manager.executable())

    def test_configured_missing_path_never_falls_back(self):
        self.manager.configure(str(self.program/'vcat_local_init.exe'))
        (self.program/'vcat_local_init.exe').unlink()
        self.assertFalse(self.manager.status()['available'])

    def test_configure_persists_and_default_resets(self):
        chosen = str(self.program/'vcat_local_init.exe')
        self.manager.configure(chosen)
        reloaded = xiaovmiao.Manager(self.root/'data', self.root/'app')
        self.assertEqual(reloaded.path, chosen)
        reloaded.configure('')
        self.assertEqual(reloaded.path, '')
        self.assertTrue(reloaded.status()['bundled'])

    def test_invalid_selection_is_rejected(self):
        for path in ('relative.exe', '//server/share/program.exe', str(self.manifest)):
            with self.assertRaises(ValueError):
                self.manager.configure(path)

    def test_launch_is_argument_list_and_scrubs_electron_node_options(self):
        proc = Mock(); proc.wait.side_effect = xiaovmiao.subprocess.TimeoutExpired('fixture', .4)
        proc.poll.return_value = None
        with patch.dict('os.environ', {'NODE_OPTIONS':'unsafe-fixture', 'ELECTRON_RUN_AS_NODE':'1'}), \
             patch.object(xiaovmiao.subprocess, 'Popen', return_value=proc) as launch:
            status = self.manager.open()
        args, kwargs = launch.call_args
        self.assertEqual(len(args[0]), 1); self.assertNotIn('shell', kwargs)
        self.assertNotIn('NODE_OPTIONS', kwargs['env'])
        self.assertNotIn('ELECTRON_RUN_AS_NODE', kwargs['env'])
        self.assertTrue(status['launchRequested'])

    def test_selected_existing_program_keeps_its_own_data(self):
        external = self.root/'existing/程序'
        (external/'resources').mkdir(parents=True)
        (external/'vcat_local_init.exe').write_bytes(b'fixture-external')
        (external/'resources/app.asar').write_bytes(b'fixture-asar')
        profile = external.parent/'本地数据'
        profile.mkdir(); (profile/'keep.txt').write_text('existing-profile', 'utf-8')
        self.manager.configure(str(external/'vcat_local_init.exe'))
        proc = Mock(); proc.wait.return_value = 0; proc.poll.return_value = 0
        with patch.object(xiaovmiao.subprocess, 'Popen', return_value=proc) as launch:
            self.manager.open()
        self.assertEqual(launch.call_args.args[0], [str(external/'vcat_local_init.exe')])
        self.assertEqual((profile/'keep.txt').read_text('utf-8'), 'existing-profile')
        self.assertFalse((self.root/'data/components').exists())

    def test_repaired_program_uses_existing_profile_and_persists_selection(self):
        profile=self.root/'original/本地数据';profile.mkdir(parents=True)
        self.manager.configure(str(self.program/'vcat_local_init.exe'),str(profile))
        reloaded=xiaovmiao.Manager(self.root/'data',self.root/'app')
        self.assertEqual(reloaded.profile,str(profile))
        proc=Mock();proc.wait.return_value=0;proc.poll.return_value=0
        with patch.object(xiaovmiao.subprocess,'Popen',return_value=proc) as launch:
            reloaded.open()
        self.assertEqual(launch.call_args.kwargs['env']['MANJU_XIAOVMIAO_PROFILE'],str(profile))
        self.assertFalse((self.bundle/'本地数据').exists())

    def legacy_profile(self,key):
        root=self.root/'data/components/xiaovmiao'/key
        profile=root/'本地数据';(profile/'.vcat/offline-local').mkdir(parents=True)
        (profile/'.vcat/offline-local/vcat.db').write_bytes(b'preserve-existing-database')
        (root/'ready.json').write_text(json.dumps({'payload':key}),'utf-8')
        return profile

    def test_changed_bundled_program_keeps_existing_profile(self):
        profile=self.legacy_profile('a'*16)
        proc=Mock();proc.wait.return_value=0;proc.poll.return_value=0
        with patch.object(xiaovmiao.subprocess,'Popen',return_value=proc) as launch:self.manager.open()
        self.assertEqual(launch.call_args.kwargs['env']['MANJU_XIAOVMIAO_PROFILE'],str(profile))
        self.assertEqual((profile/'.vcat/offline-local/vcat.db').read_bytes(),b'preserve-existing-database')
        self.assertEqual(xiaovmiao.Manager(self.root/'data',self.root/'app').profile,str(profile))

    def test_multiple_legacy_profiles_do_not_silently_create_empty_database(self):
        self.legacy_profile('a'*16);self.legacy_profile('b'*16)
        with self.assertRaisesRegex(ValueError,'多份'):
            self.manager.open()

    def unpacked_program(self):
        (self.program/'resources/app.asar').unlink()
        app=self.program/'resources/app';app.mkdir()
        (app/'main.js').write_text('// fixture, never executed', 'utf-8')
        (app/'package.json').write_text(json.dumps({'main':'main.js'}),'utf-8')
        exe=self.program/'vcat-local.exe';exe.write_bytes(b'fixture-new-executable')
        self.files={p.relative_to(self.program).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.program.rglob('*')if p.is_file()}
        self.manifest.write_text(json.dumps({'files':self.files,'executable':exe.name,
            'mode':'local-reconstructed','profileLayout':'workspace'}),'utf-8')
        return exe,app

    def workspace_profile(self,key):
        root=self.root/'data/components/xiaovmiao'/key
        profile=root/'本地数据';(profile/'workspace/.vcat/offline-local').mkdir(parents=True)
        (profile/'workspace/.vcat/offline-local/vcat.db').write_bytes(b'preserve-workspace-database')
        (root/'ready.json').write_text(json.dumps({'payload':key,'profileLayout':'workspace'}),'utf-8')
        return profile

    def test_unpacked_manifest_executable_preferred_and_copied(self):
        exe,app=self.unpacked_program()
        # The old executable still exists but must not win over the manifest.
        self.assertEqual(self.manager.executable(),exe)
        self.assertTrue(self.manager.status()['localMode'])
        runtime=self.manager.prepare_runtime(exe)
        self.assertEqual(runtime.name,'vcat-local.exe')
        self.assertEqual(runtime.read_bytes(),b'fixture-new-executable')
        self.assertEqual((runtime.parent/'resources/app/main.js').read_bytes(),(app/'main.js').read_bytes())
        self.assertEqual(xiaovmiao.checked_executable(str(runtime)),runtime)

    def test_unpacked_main_must_be_valid_and_stay_inside_app(self):
        exe,app=self.unpacked_program()
        for main in ('missing.js','../outside.js',str(self.root/'outside.js'),'..',True,None,{'path':'main.js'}):
            with self.subTest(main=main):
                (app/'package.json').write_text(json.dumps({'main':main}),'utf-8')
                with self.assertRaisesRegex(ValueError,'启动入口'):
                    xiaovmiao.checked_executable(str(exe))
        (app/'package.json').write_text('invalid-json','utf-8')
        with self.assertRaisesRegex(ValueError,'启动入口'):
            xiaovmiao.checked_executable(str(exe))

    def test_unpacked_main_can_use_nested_relative_file(self):
        exe,app=self.unpacked_program();(app/'nested').mkdir()
        (app/'nested/boot.cjs').write_text('// fixture','utf-8')
        (app/'package.json').write_text(json.dumps({'main':'nested/boot.cjs'}),'utf-8')
        self.assertEqual(xiaovmiao.checked_executable(str(exe)),exe)

    def test_manifest_executable_cannot_select_external_path(self):
        exe,app=self.unpacked_program()
        for name in ('../outside.exe',str(exe),'folder/vcat-local.exe','folder\\vcat-local.exe','C:outside.exe','main.js',None):
            with self.subTest(name=name):
                self.assertIsNone(xiaovmiao.manifest_executable(name))
        custom=self.program/'new-custom.exe';custom.write_bytes(b'custom-fixture')
        value=json.loads(self.manifest.read_text('utf-8'));value['executable']=custom.name
        self.manifest.write_text(json.dumps(value),'utf-8')
        self.assertEqual(self.manager.candidates()[0],str(custom))

    def test_workspace_layout_ignores_legacy_and_keeps_workspace(self):
        exe,_=self.unpacked_program()
        legacy=self.legacy_profile('a'*16);workspace=self.workspace_profile('b'*16)
        runtime=self.manager.prepare_runtime(exe);self.manager.bundled_profile(runtime)
        self.assertEqual(self.manager.profile,str(workspace))
        self.assertEqual((legacy/'.vcat/offline-local/vcat.db').read_bytes(),b'preserve-existing-database')
        self.assertEqual((workspace/'workspace/.vcat/offline-local/vcat.db').read_bytes(),b'preserve-workspace-database')

    def test_workspace_default_does_not_reuse_legacy_profile(self):
        exe,_=self.unpacked_program();legacy=self.legacy_profile('a'*16)
        runtime=self.manager.prepare_runtime(exe);self.manager.bundled_profile(runtime)
        self.assertEqual(self.manager.profile,str(runtime.parent.parent/'本地数据'))
        self.assertNotEqual(self.manager.profile,str(legacy))

    def test_legacy_layout_does_not_reuse_workspace_profile(self):
        workspace=self.workspace_profile('b'*16)
        runtime=self.manager.prepare_runtime(self.manager.executable());self.manager.bundled_profile(runtime)
        self.assertEqual(self.manager.profile,str(runtime.parent.parent/'本地数据'))
        self.assertNotEqual(self.manager.profile,str(workspace))

    def test_unpacked_selected_profile_and_normal_launch_environment(self):
        exe,_=self.unpacked_program();profile=self.root/'selected-profile';profile.mkdir()
        self.manager.configure(str(exe),str(profile))
        proc=Mock();proc.wait.return_value=0;proc.poll.return_value=0
        probes={key:'fixture'for key in ('VCAT_BASELINE','VCAT_BOOT_ONLY','VCAT_TEST_EXIT_MS','VCAT_NETWORK_PROBE','VCAT_ACCOUNT_PHASE')}
        with patch.dict('os.environ',probes),patch.object(xiaovmiao.subprocess,'Popen',return_value=proc)as launch:
            self.manager.open()
        self.assertEqual(launch.call_args.kwargs['env']['MANJU_XIAOVMIAO_PROFILE'],str(profile))
        for key in probes:self.assertNotIn(key,launch.call_args.kwargs['env'])
        self.assertEqual(xiaovmiao.Manager(self.root/'data',self.root/'app').profile,str(profile))


if __name__ == '__main__':
    unittest.main()
