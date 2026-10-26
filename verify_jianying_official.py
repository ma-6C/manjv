"""Real draft-copy checks; controlled editor metadata never launches a test EXE.

This is not Jianying native editor acceptance. The local machine may have only
an old draft directory and no signed Jianying executable installed.
"""
from pathlib import Path
import json,os,subprocess,sys,tempfile,threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import jianying_projects as j

BASE=Path(tempfile.mkdtemp(prefix='jianying-official-',dir=ROOT/'tmp'))
report={'base':str(BASE),'checks':[],'nativeEditorOpened':False,'ok':False}
def check(label,value=True):
    assert value,label
    report['checks'].append(label);print('PASS '+label,flush=True)
def rejects(fn):
    try:fn()
    except (ValueError,FileNotFoundError):return True
    return False
def run(command,**kwargs):
    return subprocess.check_output(command,stderr=subprocess.STDOUT,**kwargs)

try:
    exe=BASE/'JianyingPro.exe';exe.write_bytes(b'not an executable, metadata fixture only')
    check('任意同名可执行文件不能被认可',j._verified_editor(exe) is None)
    metadata={'version':'9.9.0.1','ProductName':'剪映专业版','OriginalFilename':'JianyingPro.exe','CompanyName':'深圳市脸萌科技有限公司'}
    with patch.object(j,'_file_version',return_value=metadata),patch.object(j,'_signature',return_value={'valid':False,'publisher':'Unknown'}):
        check('版本信息不能代替有效官方数字签名',not j.status({'executable':str(exe)})['editorInstalled'])
    unsigned=j._signature(exe)
    check('实际未签名文件在系统校验中被拒绝',not unsigned['valid'])
    if os.name=='nt':check('实际Windows版本元信息读取可用',bool(j._file_version(Path(sys.executable)).get('version')))
    ffmpeg=next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))
    source=BASE/'真实样片.mp4'
    run([str(ffmpeg),'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=1',
         '-f','lavfi','-i','sine=sample_rate=48000:duration=1','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)])
    video={'path':str(source),'width':320,'height':180,'duration':1,'audio':True}
    analysis={'sourceSHA256':j.sha(source),'segments':[{'start':0,'end':.5},{'start':.5,'end':1}]}
    original_hash=j.sha(source)
    generated=j.generate(video,analysis,BASE/'输出',ffmpeg,run,threading.Event())
    folder=Path(generated['directory']);original=j.check(folder)
    check('继续生成带真实视频和音轨的可编辑草稿',len(original['assets'])==2 and len(original['ranges'])==2)
    with patch.object(j,'_file_version',return_value=metadata),patch.object(j,'_signature',return_value={'valid':False,'publisher':'Unknown'}),patch.object(j.subprocess,'Popen') as launch:
        check('有效工程也不会启动不可信同名程序',rejects(lambda:j.open_in_editor(folder,{'executable':str(exe)})) and not launch.called)
    draft_root=BASE/'剪映草稿位置';draft_root.mkdir()
    root_meta=draft_root/'root_meta_info.json';root_meta.write_text('{"existing":"user data stays byte exact"}','utf-8')
    root_hash=j.sha(root_meta);content_hash=j.sha(folder/'draft_content.json')
    copied=j.install_to_editor(folder,{'draftRoot':str(draft_root)})
    target=Path(copied['directory']);installed=j.check(target)
    check('真实草稿复制进独立剪映目录且可校验',target.parent==draft_root and installed['sourceSHA256']==original_hash)
    content=json.loads((target/'draft_content.json').read_text('utf-8'))
    material_paths=[m['path'] for group in ('videos','audios') for m in content['materials'][group]]
    check('导入后素材重定位到新目录',material_paths and all(Path(p).is_relative_to(target) and Path(p).is_file() for p in material_paths))
    meta=json.loads((target/'draft_meta_info.json').read_text('utf-8'))
    check('草稿名称路径与ID同步更新',meta['draft_fold_path']==str(target) and meta['draft_name']==copied['name'] and meta['draft_id']==content['id'])
    check('不覆盖剪映原有总索引',j.sha(root_meta)==root_hash and copied['indexModified'] is False)
    check('原媒体和原工程均未修改',j.sha(source)==original_hash and j.sha(folder/'draft_content.json')==content_hash)
    again=j.install_to_editor(folder,{'draftRoot':str(draft_root)})
    check('重复导入新建工程而不覆盖旧工程',again['directory']!=copied['directory'] and j.check(target)['draftSHA256']==installed['draftSHA256'])
    check('复制和导入不冒充官方打开成功',not copied['editorValidated'] and not installed['editorValidated'])
    check('拒绝把目标目录放入源工程内部',rejects(lambda:j.install_to_editor(folder,{'draftRoot':str(folder/'nested')})))
    check('拒绝系统或盘符根目录',rejects(lambda:j.install_to_editor(folder,{'draftRoot':str(Path.cwd().anchor)})))
    with patch.object(j,'_file_version',return_value=metadata),patch.object(j,'_signature',return_value={'valid':True,'publisher':'CN=深圳市脸萌科技有限公司','status':'Valid'}):
        trusted=j.status({'executable':str(exe),'draftRoot':str(draft_root)})
        check('受控官方签名元信息才允许构造启动命令',trusted['editorInstalled'] and trusted['editorSignatureVerified'])
        class Process:pid=12345
        with patch.object(j.subprocess,'Popen',return_value=Process()) as launch:
            opened=j.open_in_editor(target,{'executable':str(exe),'draftRoot':str(draft_root)})
            check('启动构造无shell和未验证URI参数',launch.call_args.args[0]==[str(exe)] and not launch.call_args.kwargs.get('shell',False))
            check('启动应用不会冒称指定工程已打开',opened['appLaunched'] and not opened['projectOpened'] and not opened['editorValidated'])
            original_draft=folder/'draft_content.json';original_bytes=original_draft.read_bytes()
            original_draft.write_bytes(b'changed original draft')
            check('原始生成工程篡改仍阻止启动',rejects(lambda:j.open_in_editor(folder,{'executable':str(exe)})))
            original_draft.write_bytes(original_bytes)
            native_content=target/'draft_content.json';native_meta=target/'draft_meta_info.json'
            # Simulate native rewrites including a format our bridge cannot parse.
            # Opening the app must not parse/decrypt or rewrite these editor files.
            native_meta.write_bytes(b'editor native modified metadata')
            meta_edited=j.open_in_editor(target,{'executable':str(exe)})
            check('仅原生元信息变化也报告编辑器已修改副本',meta_edited['editorModified'])
            native_content.write_bytes(b'editor native modified content')
            native_hashes=(j.sha(native_content),j.sha(native_meta))
            edited=j.open_in_editor(target,{'executable':str(exe)})
            check('已登记导入副本经原生改写后允许再次启动应用',edited['appLaunched'] and edited['editorModified'] and not edited['projectOpened'])
            check('再次启动不改写编辑器内容或元信息',native_hashes==(j.sha(native_content),j.sha(native_meta)))
            check('导入副本改写仍不能通过原始严格校验',rejects(lambda:j.check(target)))
            index_file=target/'manju_project.json';index_bytes=index_file.read_bytes();unsafe=json.loads(index_bytes)
            unsafe['assets'][0]['relative']='../../outside.mp4'
            index_file.write_text(json.dumps(unsafe),'utf-8')
            check('已编辑副本仍拒绝素材路径越界',rejects(lambda:j.open_in_editor(target,{'executable':str(exe)})))
            index_file.write_bytes(index_bytes)
            resource=target/'Resources'/'video.mp4';resource.write_bytes(b'changed in-place media')
            check('已编辑副本仍严格核对原登记素材哈希',rejects(lambda:j.open_in_editor(target,{'executable':str(exe)})))
    bad=target/'Resources'/'video.mp4';bad.write_bytes(b'changed')
    check('损坏工程先拦截而不继续复制',rejects(lambda:j.install_to_editor(target,{'draftRoot':str(draft_root)})))
    actual=j.status()
    report.update(ok=True,actualEditorState=actual['editorState'],actualEditorInstalled=actual['editorInstalled'])
finally:
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/jianying-official-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(report['checks']),'report':str(BASE/'report.json'),'actualEditorInstalled':report.get('actualEditorInstalled')},ensure_ascii=False),flush=True)
