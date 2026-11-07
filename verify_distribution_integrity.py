"""Fail-closed integrity checks, including non-first-row failures under concurrency."""
from pathlib import Path
import copy
import hashlib
import json
import tempfile
import unittest
import os
import subprocess
import sys
from unittest.mock import patch
import licensing

ROOT=Path(__file__).resolve().parent


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='integrity-concurrency-',dir=ROOT/'tmp')
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        (self.home/'integrity.json').write_text('{}','utf-8')
        self.manifest={'product':'ManjuStudio','kind':'application','files':[]}
        for number in range(25):
            path=self.home/'nested'/f'file-{number:02d}.bin';path.parent.mkdir(exist_ok=True)
            value=('fixture-'+str(number)).encode();path.write_bytes(value)
            self.manifest['files'].append({'path':path.relative_to(self.home).as_posix(),'bytes':len(value),
                                          'sha256':hashlib.sha256(value).hexdigest()})

    def verify(self,manifest=None):
        with patch.object(sys,'frozen',True,create=True),patch.object(licensing,'signed_payload',return_value=manifest or self.manifest):
            licensing.verify_distribution(self.home)

    def test_all_signed_files_pass(self):self.verify()

    def test_same_size_tamper_in_middle_and_last_rows_fails(self):
        for row in (self.manifest['files'][12],self.manifest['files'][-1]):
            with self.subTest(path=row['path']):
                path=self.home/row['path'];original=path.read_bytes();path.write_bytes(b'x'*len(original))
                with self.assertRaises(RuntimeError):self.verify()
                path.write_bytes(original)

    def test_missing_file_fails(self):
        (self.home/self.manifest['files'][-1]['path']).unlink()
        with self.assertRaises(RuntimeError):self.verify()

    def test_changed_size_fails(self):
        (self.home/self.manifest['files'][10]['path']).write_bytes(b'changed size')
        with self.assertRaises(RuntimeError):self.verify()

    def test_parent_and_absolute_escape_paths_fail(self):
        for name in ('../outside.bin',str(self.home.parent/'outside.bin'),'C:relative.bin','nested/file-00.bin:stream'):
            with self.subTest(name=name):
                manifest=copy.deepcopy(self.manifest);manifest['files'][-1]['path']=name
                with self.assertRaises(RuntimeError):self.verify(manifest)

    def test_unreadable_file_fails_closed(self):
        original=Path.open
        denied=self.home/self.manifest['files'][-1]['path']
        def opened(path,*args,**kwargs):
            if path==denied:raise PermissionError('injected file access denial')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened),self.assertRaises(RuntimeError):self.verify()

    def test_empty_duplicate_and_malformed_rows_fail(self):
        variants=[[],[self.manifest['files'][0],self.manifest['files'][0]],['invalid-row'],
                  [dict(self.manifest['files'][0],bytes=True)],[dict(self.manifest['files'][0],sha256='invalid')]]
        for rows in variants:
            with self.subTest(rows=rows):
                manifest=copy.deepcopy(self.manifest);manifest['files']=rows
                with self.assertRaises(RuntimeError):self.verify(manifest)

    def test_link_to_outside_is_rejected_after_resolution(self):
        target=Path(tempfile.mkdtemp(prefix='integrity-outside-',dir=ROOT/'tmp'))
        self.addCleanup(__import__('shutil').rmtree,target)
        (target/'outside.bin').write_bytes(b'outside')
        link=self.home/'linked'
        if os.name=='nt':
            quoted=lambda path:"'"+str(path).replace("'","''")+"'"
            subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                'New-Item -ItemType Junction -Path '+quoted(link)+' -Target '+quoted(target)+' | Out-Null'],
                check=True,capture_output=True,timeout=10)
        else:link.symlink_to(target,target_is_directory=True)
        self.addCleanup(link.rmdir)
        self.manifest['files'].append({'path':'linked/outside.bin','bytes':7,'sha256':hashlib.sha256(b'outside').hexdigest()})
        with self.assertRaises(RuntimeError):self.verify()


if __name__=='__main__':unittest.main()
