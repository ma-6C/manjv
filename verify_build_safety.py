"""Reproduce unsafe build replacement and accidental companion-profile collection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.release_safety import new_release_destination, companion_files, copy_companion, verify_manifest_file_set

ROOT = Path(__file__).resolve().parent


class BuildSafetyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='build-safety-', dir=ROOT / 'tmp')
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)

    def module(self):
        module = self.home / 'module'
        program = module / '程序'
        program.mkdir(parents=True)
        (program / 'vcat-local.exe').write_bytes(b'fixture-executable')
        (program / 'resources').mkdir()
        (program / 'resources/app.js').write_bytes(b'fixture-application')
        files = {p.relative_to(program).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in program.rglob('*') if p.is_file()}
        (module / 'module.json').write_text(json.dumps({'executable': 'vcat-local.exe', 'files': files}), 'utf-8')
        return module

    def test_build_entry_points_stop_before_collecting_or_replacing_existing_release(self):
        for entry in ('build_desktop.py', 'build_hardened.py'):
            with self.subTest(entry=entry):
                # The copied real entry point fails at the guard before importing
                # PyInstaller, compiling modules or invoking a payload builder.
                copy = self.home / entry
                copy.write_bytes((ROOT / entry).read_bytes())
                release = self.home / 'release/v9.9.9'
                release.mkdir(parents=True, exist_ok=True)
                marker = release / 'delivered-original.exe'
                marker.write_bytes(b'delivered-original')
                result = subprocess.run([sys.executable, '-B', str(copy), '--version', 'v9.9.9'],
                                        cwd=ROOT, env={**__import__('os').environ, 'PYTHONPATH': str(ROOT)},
                                        capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'FileExistsError', result.stderr)
                self.assertEqual(marker.read_bytes(), b'delivered-original')
                self.assertFalse((self.home / 'tmp').exists())

    def test_new_destination_accepts_only_unused_version(self):
        self.assertEqual(new_release_destination(self.home, 'v9.9.8'), self.home / 'release/v9.9.8/漫剧工坊')
        with self.assertRaises(ValueError):
            new_release_destination(self.home, '../v9.9.8')

    def test_installer_entry_point_preserves_existing_executable(self):
        copy = self.home / 'build_installer.py'
        copy.write_bytes((ROOT / 'build_installer.py').read_bytes())
        release = self.home / 'release/v9.9.9'
        (release / '漫剧工坊').mkdir(parents=True)
        installer = release / '漫剧工坊-安装程序-9.9.9.exe'
        installer.write_bytes(b'existing-delivery')
        result = subprocess.run([sys.executable, '-B', str(copy), '--version', 'v9.9.9'],
                                cwd=ROOT, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'FileExistsError', result.stderr)
        self.assertEqual(installer.read_bytes(), b'existing-delivery')
        self.assertFalse((self.home / 'tmp').exists())

    def test_clean_companion_copies_exact_manifest_and_bytes(self):
        module = self.module()
        output = self.home / 'output'
        copy_companion(module, output)
        self.assertEqual((module / 'module.json').read_bytes(), (output / 'module.json').read_bytes())
        self.assertEqual(companion_files(module), companion_files(output))

    def test_installer_rejects_unsigned_extra_profile(self):
        payload = self.home / 'signed-payload'
        payload.mkdir()
        (payload / 'application.exe').write_bytes(b'signed-file-fixture')
        manifest = {'files': [{'path': 'application.exe'}]}
        verify_manifest_file_set(payload, manifest)
        (payload / 'state.json').write_text('{"fixture":"private settings"}', 'utf-8')
        with self.assertRaises(ValueError):
            verify_manifest_file_set(payload, manifest)

    def test_installer_rejects_missing_manifest_file(self):
        payload = self.home / 'signed-payload'
        payload.mkdir()
        with self.assertRaises(ValueError):
            verify_manifest_file_set(payload, {'files': [{'path': 'application.exe'}]})

    def test_unlisted_user_cookie_stops_bundle_without_output(self):
        module = self.module()
        (module / '程序/profile').mkdir()
        (module / '程序/profile/Cookies').write_bytes(b'fixture-account-cookie')
        output = self.home / 'output'
        with self.assertRaises(ValueError):
            copy_companion(module, output)
        self.assertFalse(output.exists())

    def test_changed_program_stops_bundle_without_output(self):
        module = self.module()
        (module / '程序/resources/app.js').write_bytes(b'unexpected-modification')
        output = self.home / 'output'
        with self.assertRaises(ValueError):
            copy_companion(module, output)
        self.assertFalse(output.exists())

    def test_missing_manifest_and_escape_path_are_rejected(self):
        module = self.module()
        (module / 'module.json').unlink()
        with self.assertRaises(ValueError):
            companion_files(module)
        (module / 'module.json').write_text(json.dumps({'files': {'../state.json': '0' * 64}}), 'utf-8')
        with self.assertRaises(ValueError):
            companion_files(module)

    def test_listed_profile_is_rejected_even_with_valid_hash(self):
        module = self.module()
        program = module / '程序'
        (program / '本地数据').mkdir()
        profile = program / '本地数据/vcat.db'
        profile.write_bytes(b'fixture-private-database')
        manifest = json.loads((module / 'module.json').read_text('utf-8'))
        manifest['files']['本地数据/vcat.db'] = hashlib.sha256(profile.read_bytes()).hexdigest()
        (module / 'module.json').write_text(json.dumps(manifest), 'utf-8')
        with self.assertRaises(ValueError):
            companion_files(module)


if __name__ == '__main__':
    unittest.main()
