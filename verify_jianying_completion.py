"""Artifact and retry regressions; GPU/editor integration has separate reports."""
import json
import tempfile
import threading
import unittest
import uuid
import types
import contextlib
from unittest.mock import patch
from pathlib import Path

import jianying_ai
import jianying_library
import task_progress
import jianying_jobs
import jianying_visual
import jianying_timeline
import jianying_editing
import project_evidence
import jianying_automation


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'tmp')
        self.root=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def library(self):
        resources=self.root/'Resources';resources.mkdir()
        for name in ('人声.wav','背景声.wav','素材01.mp4'):(resources/name).write_bytes(name.encode())
        audio=lambda name:{'id':str(uuid.uuid4()),'path':str(resources/name),'duration':45000000}
        data={'id':str(uuid.uuid4()),'materials':{'audios':[audio('背景声.wav'),audio('人声.wav'),audio('人声.wav')],
            'videos':[{'id':str(uuid.uuid4()),'path':str(resources/'素材01.mp4'),'duration':3000000,'width':1280,'height':720}]}}
        meta={};library=jianying_library.write(self.root,data,meta)
        index={'library':library,'assets':[{'relative':x['relative']} for x in library['files']]}
        return data,meta,index

    def test_bin_keeps_full_stems_once_and_links_repeated_timeline_materials(self):
        data,meta,index=self.library()
        jianying_library.validate(self.root,data,meta,index)
        self.assertEqual([x['name'] for x in index['library']['files']],['人声.wav','背景声.wav','素材01.mp4'])
        self.assertEqual(index['library']['audios'],2)
        voices=[a['local_material_id'] for a in data['materials']['audios'] if a['path'].endswith('人声.wav')]
        self.assertEqual(len(set(voices)),1)
        rows=[x for g in meta['draft_materials'] for x in g['value']]
        ordered=sorted(rows,key=lambda x:x['import_time'],reverse=True)
        self.assertEqual([x['extra_info'] for x in ordered],['人声.wav','背景声.wav','素材01.mp4'])

    def test_missing_bin_asset_is_rejected(self):
        data,meta,index=self.library()
        (self.root/'Resources/人声.wav').unlink()
        with self.assertRaisesRegex(ValueError,'缺失'):jianying_library.validate(self.root,data,meta,index)

    def test_virtual_bin_link_omission_is_rejected(self):
        data,meta,index=self.library()
        path=self.root/'draft_virtual_store.json';virtual=json.loads(path.read_text('utf-8'))
        virtual['draft_virtual_store'][1]['value'].pop();path.write_text(json.dumps(virtual),'utf-8')
        with self.assertRaisesRegex(ValueError,'列表索引'):jianying_library.validate(self.root,data,meta,index)

    def test_library_switch_retries_in_a_fresh_worker_then_reports_actual_provider(self):
        (self.root/'demucs').mkdir()
        attempts=[]
        def run(args,**kwargs):
            request,response=map(Path,args[-2:]);cfg=json.loads(request.read_text('utf-8'))
            attempts.append((cfg['device'],cfg['cudaLibraries']))
            if len(attempts)==1:
                response.write_text(json.dumps({'ok':False,'error':'CUDA no kernel image'}),'utf-8')
                raise RuntimeError('child failed')
            response.write_text(json.dumps({'ok':True,'device':'cuda','cudaLibraries':{'provider':'nvidia'}}),'utf-8')
        opts={'aiPython':str(self.root/'python.exe'),'aiModelRoot':str(self.root),'cudaLibraries':'auto','aiDevice':'auto',
              'separationModel':'htdemucs','asrLanguage':'zh','captionLength':14}
        (self.root/'python.exe').write_bytes(b'test')
        result=jianying_ai.worker('separate',self.root/'input.wav',self.root,opts,run,threading.Event(),lambda *a:None)
        self.assertEqual(attempts,[('cuda','torch'),('cuda','nvidia')])
        warning=jianying_ai.fallback_warnings('人声分离',result)[0]
        self.assertIn('GPU / NVIDIA',warning);self.assertNotIn('已改用 CPU',warning)

    def test_input_failure_does_not_trigger_device_retries(self):
        (self.root/'demucs').mkdir();(self.root/'python.exe').touch();attempts=[]
        def run(args,**kwargs):
            attempts.append(args)
            Path(args[-1]).write_text(json.dumps({'ok':False,'error':'输入音频格式无效'}),'utf-8')
            raise RuntimeError('child failed')
        opts={'aiPython':str(self.root/'python.exe'),'aiModelRoot':str(self.root),'cudaLibraries':'auto','aiDevice':'auto',
              'separationModel':'htdemucs','asrLanguage':'zh','captionLength':14}
        with self.assertRaisesRegex(RuntimeError,'音频格式无效'):
            jianying_ai.worker('separate',self.root/'input.wav',self.root,opts,run,threading.Event(),lambda *a:None)
        self.assertEqual(len(attempts),1)

    def test_gpu_failure_keeps_original_trace_and_matching_recovery_in_export(self):
        error=jianying_ai.AIWorkerError('[WinError 127] 找不到指定的程序。','original child traceback','separate')
        error.video='第0118集.mp4'
        job={'id':'test','kind':'jianying_project','status':'failed','stage':'汇总'}
        diagnostic=task_progress.failure(job,error)
        self.assertEqual(diagnostic['code'],'CUDA_LIBRARIES')
        self.assertEqual(diagnostic['stage'],'人声分离')
        self.assertEqual(diagnostic['details'],'original child traceback')
        self.assertIn('cuBLAS/cuDNN',diagnostic['nextStep'])
        job['diagnostic']=diagnostic
        job['jianyingAI']=[{'action':'separate','event':'failed','provider':'nvidia','error':'DLL load failed C:\\Users\\customer\\private.dll',
            'libraries':{'versions':{'nvidia-cudnn-cu12':'9.7.1.26'}}}]
        report=task_progress.report(job)
        self.assertIn('DLL load failed',report['jianyingAI'][0]['error'])
        self.assertNotIn('customer',json.dumps(report))
        self.assertEqual(report['jianyingAI'][0]['versions']['nvidia-cudnn-cu12'],'9.7.1.26')

    def test_failed_gpu_attempt_is_logged_immediately_with_trace_before_cpu_retry(self):
        logs=[];job={'id':'test','kind':'jianying_project','stage':'分离'}
        host=types.SimpleNamespace(telemetry=task_progress,diagnostic_text=task_progress.safe_text,
            log=lambda message,**kwargs:logs.append({'message':message,**kwargs}),LOCK=threading.RLock(),persist_jobs=lambda:None)
        event={'action':'separate','attempt':1,'device':'cuda','provider':'nvidia','event':'failed','error':'CUDA DLL load failed',
               'traceback':'original worker traceback','retry':{'device':'cpu','provider':'cpu'}}
        jianying_jobs._ai_log(host,job,{'name':'第0118集.mp4','projectName':'测试剧'},event)
        self.assertEqual(logs[0]['level'],'warning')
        self.assertIn('测试剧',logs[0]['message']);self.assertIn('CUDA DLL load failed',logs[0]['message'])
        self.assertEqual(logs[0]['diagnostic']['traceback'],'original worker traceback')
        self.assertIn('自动改用 CPU',logs[0]['diagnostic']['nextStep'])
        self.assertEqual(job['jianyingAI'][0]['event'],'failed')

    def test_visible_project_number_requires_exact_match(self):
        name='第0118集_流程_73b5129f97a3-0'
        exact=jianying_visual.match_identity('368532 流程 73b5129f97a3 · 0',name)
        self.assertTrue(exact['projectIdentityVerified']);self.assertFalse(exact['projectTitleVerified'])
        self.assertFalse(jianying_visual.match_identity('368532 流程 73b5129 7a3 · 0',name)['projectIdentityVerified'])
        numeric='第0118集_工程_123456789012345'
        self.assertTrue(jianying_visual.match_identity('工程 123456789012345',numeric)['projectIdentityVerified'])
        self.assertFalse(jianying_visual.match_identity('工程 123456789012346',numeric)['projectIdentityVerified'])
        self.assertFalse(jianying_visual.match_identity('工程 9123456789012345',numeric)['projectIdentityVerified'])

    def test_project_properties_match_name_field_without_matching_media_or_path(self):
        name='第0118集_流程_d3cbaff6b8c5-0'
        value=jianying_visual.match_properties('草稿名称 第0118集 流程 d3cbaff6b8c5 0 保存位置 C:/Projects',name)
        self.assertTrue(value['projectIdentityVerified']);self.assertFalse(value['projectTitleVerified'])
        other='草稿名称 其他工程 保存位置 C:/Projects/第0118集_流程_d3cbaff6b8c5-0'
        self.assertFalse(jianying_visual.match_properties(other,name)['projectIdentityVerified'])
        self.assertFalse(jianying_visual.match_properties('素材名称 '+name,name)['projectIdentityVerified'])

    def test_capture_accepts_current_qt_editor_and_rejects_home_without_desktop_scan(self):
        root=types.SimpleNamespace(AutomationId='MainWindow',ProcessId=123)
        surface=types.SimpleNamespace(AutomationId='MainWindow.surface_main')
        auto=types.SimpleNamespace(UIAutomationInitializerInThread=contextlib.nullcontext,ControlFromHandle=lambda hwnd:root)
        capture=project_evidence.WindowsCapture()
        with patch.dict('sys.modules',{'uiautomation':auto}),patch.object(jianying_automation.NativeBackend,'_roots',return_value=[root]),\
             patch.object(jianying_automation,'media_missing',return_value=False),patch.object(jianying_automation,'_tree',return_value=iter([root,surface])):
            self.assertTrue(capture._editor_surface(1))
        root.AutomationId='HomeWindow'
        with patch.dict('sys.modules',{'uiautomation':auto}),patch.object(jianying_automation.NativeBackend,'_roots',return_value=[root]),\
             patch.object(jianying_automation,'media_missing',return_value=False),patch.object(jianying_automation,'_tree',return_value=iter([root])):
            self.assertFalse(capture._editor_surface(1))

    def test_random_cut_lengths_preserve_whole_source_including_tiny_tail(self):
        opts=jianying_timeline.options({})
        for duration in (2000000,2000001,3999999,10000001,45233333,125000001,3600000000):
            scenes=[{'start':0,'end':duration/1e6}]
            for seed in range(60):
                cuts=jianying_timeline.ranges(scenes,duration,opts,seed=seed)
                self.assertEqual(cuts[0]['sourceStart'],0)
                self.assertEqual(sum(c['sourceDuration'] for c in cuts),duration)
                self.assertEqual(cuts[-1]['start']+cuts[-1]['duration'],duration)
                for a,b in zip(cuts,cuts[1:]):self.assertEqual(a['sourceStart']+a['sourceDuration'],b['sourceStart'])
                self.assertTrue(all(2000000<=c['sourceDuration']<=10000000 for c in cuts))

    def test_dense_scene_boundaries_are_merged_and_seed_survives_retry(self):
        opts=jianying_timeline.options({})
        scenes=[{'start':i,'end':i+1} for i in range(45)]
        first=jianying_timeline.ranges(scenes,45000000,opts,seed='job-a')
        self.assertLess(len(first),15)
        self.assertGreater(len({c['sourceDuration'] for c in first}),1)
        self.assertEqual(first,jianying_timeline.ranges(scenes,45000000,opts,seed='job-a'))
        self.assertNotEqual(first,jianying_timeline.ranges(scenes,45000000,opts,seed='job-b'))
        mapped=list(jianying_editing.mapped_intervals(0,45000000,first))
        self.assertEqual(sum(x[1] for x in mapped),45000000)
        self.assertEqual(sum(x[3] for x in mapped),45000000)

    def test_short_source_is_preserved_and_invalid_analysis_still_rejected(self):
        opts=jianying_timeline.options({})
        short=jianying_timeline.ranges([{'start':0,'end':1.2}],1200000,opts,seed='short')
        self.assertEqual([x['sourceDuration'] for x in short],[1200000])
        with self.assertRaisesRegex(ValueError,'间隙或重叠'):
            jianying_timeline.ranges([{'start':0,'end':3},{'start':4,'end':8}],8000000,opts)
        with self.assertRaisesRegex(ValueError,'提高'):
            jianying_timeline.ranges([{'start':0,'end':2.1}],2100000,jianying_timeline.options({'shotSeconds':2}))


if __name__=='__main__':unittest.main(verbosity=2)
