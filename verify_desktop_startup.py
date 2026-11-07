"""Startup import failures must remain visible without modifying saved user state."""
import builtins
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import ctypes


class StartupTests(unittest.TestCase):
    def test_saved_state_error_is_logged_and_shown(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='desktop-startup-') as directory:
            home=Path(directory);state=home/'state.json';state.write_bytes(b'{damaged')
            original_import=builtins.__import__
            def fail_server(name,*args,**kwargs):
                if name=='server':raise ValueError('配置文件损坏，原文件已保留：'+str(state))
                return original_import(name,*args,**kwargs)
            with patch.dict(os.environ,{'MANJU_DATA':directory}),patch.object(sys,'argv',['desktop.py']),patch('builtins.__import__',side_effect=fail_server),patch.object(ctypes.windll.user32,'MessageBoxW',return_value=1) as dialog:
                with self.assertRaises(SystemExit) as error:runpy.run_path(str(ROOT/'desktop.py'),run_name='__main__')
            self.assertEqual(error.exception.code,1)
            self.assertEqual(state.read_bytes(),b'{damaged')
            self.assertIn('配置文件损坏',(home/'desktop-error.log').read_text('utf-8'))
            self.assertIn('配置文件损坏',dialog.call_args.args[1])
            self.assertIn('desktop-error.log',dialog.call_args.args[1])


if __name__=='__main__':unittest.main()
