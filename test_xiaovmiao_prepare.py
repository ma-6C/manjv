"""Check unpacked payload preparation without copying real user profiles."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from tools.prepare_xiaovmiao import prepare
from tools.adapt_xiaovmiao_reconstructed import adapt


class PreparationTests(unittest.TestCase):
    def test_unpacked_payload_excludes_profile_and_verifies_copy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp')as folder:
            root=Path(folder);source=root/'source';app=source/'resources/app';app.mkdir(parents=True)
            (source/'vcat-local.exe').write_bytes(b'test-exe')
            (app/'package.json').write_text(json.dumps({'main':'main.js'}),'utf8')
            (app/'main.js').write_text('fixture','utf8')
            (source/'profile').mkdir();(source/'profile/Cookies').write_bytes(b'not-a-real-cookie')
            (source/'runtime.log').write_text('not-shipped','utf8')
            destination=root/'module'
            result=prepare(source,destination,'vcat-local.exe','local-reconstructed','workspace')
            self.assertEqual(result['files'],3)
            self.assertFalse((destination/'程序/profile').exists())
            manifest=json.loads((destination/'module.json').read_text('utf8'))
            self.assertEqual(manifest['executable'],'vcat-local.exe')
            self.assertEqual(manifest['profileLayout'],'workspace')
            self.assertTrue(prepare(source,destination,'vcat-local.exe','local-reconstructed','workspace')['unchanged'])
            with self.assertRaises(FileExistsError):
                prepare(source,destination,'vcat-local.exe','local-reconstructed','legacy')

    def test_rejects_missing_or_outside_main(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp')as folder:
            root=Path(folder);app=root/'source/resources/app';app.mkdir(parents=True)
            (root/'source/vcat-local.exe').write_bytes(b'test-exe')
            (root/'outside.js').write_text('fixture','utf8')
            for entry in ['missing.js','../../../outside.js']:
                (app/'package.json').write_text(json.dumps({'main':entry}),'utf8')
                with self.assertRaisesRegex(ValueError,'入口'):
                    prepare(root/'source',root/'out','vcat-local.exe')

    def test_profile_override_adaptation_is_narrow_and_idempotent(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp')as folder:
            module=Path(folder);app=module/'程序/resources/app';app.mkdir(parents=True)
            (app/'package.json').write_text(json.dumps({'main':'main.js','version':'3.1.0','build':17}),'utf8')
            original="const profile=path.join(root,process.env.VCAT_NETWORK_PROBE==='account'?'account-probe-profile':process.env.VCAT_NETWORK_PROBE==='1'?'network-probe-profile':'profile');"
            (app/'main.js').write_text(original,'utf8')
            (module/'module.json').write_text(json.dumps({'executable':'vcat-local.exe','files':{}}),'utf8')
            result=adapt(module);self.assertTrue(result['ok'])
            data=(app/'main.js').read_bytes()
            self.assertEqual(data.decode(),original.replace('const profile=path.join(root,','const profile=path.resolve(process.env.MANJU_XIAOVMIAO_PROFILE||path.join(root,').replace("'profile');","'profile'));"))
            manifest=json.loads((module/'module.json').read_text('utf8'))
            self.assertEqual(manifest['files']['resources/app/main.js'],hashlib.sha256(data).hexdigest())
            adapt(module);self.assertEqual((app/'main.js').read_bytes(),data)


if __name__=='__main__':unittest.main()
