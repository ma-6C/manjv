"""Verify the signed build and assemble the installer + unchanged v2 AI bundle."""
from pathlib import Path
import ast,hashlib,json,shutil,sys,time,zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import licensing

VERSION='v0.10.0'
DIST=ROOT/'release'/VERSION/'漫剧工坊'
OUT=DIST.parent/'对外发送'
RECORD=ROOT/'versions'/VERSION
OUT.mkdir(parents=True,exist_ok=True)

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

inputs=json.loads((RECORD/'build-inputs.json').read_text('utf-8'))
for name,sha in inputs['sourceSha256'].items():
    if digest(ROOT/name)!=sha:raise ValueError('Build input changed: '+name)
sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:del sys.frozen
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']=='0.10.0'
for name in ['app.js','connections.js','connections.css','index.html','progress.js','workflow.js']:
    assert digest(DIST/'_internal/web'/name)==digest(ROOT/'web'/name),name
core=json.loads((DIST/'_internal/engines/guoapp-core/manifest.json').read_text('utf-8'))
assert digest(DIST/'_internal/engines/guoapp-core/duanju_core.dll')==core['sha256']
tree=ast.parse((ROOT/'build_hardened.py').read_text('utf-8'))
modules=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MODULES' for t in n.targets))
compiled={}
for name in modules:
    matches=list((DIST/'_internal').glob(name+'.cp312-win_amd64.pyd'))
    assert len(matches)==1,name
    compiled[name]={'path':matches[0].relative_to(DIST).as_posix(),'sha256':digest(matches[0])}
installer=DIST.parent/'漫剧工坊-安装程序-0.10.0.exe'
assert installer.is_file()
engine=ROOT/'release/v0.9.3/对外发送/漫剧工坊-AI离线引擎-v2-cu128.zip'
expected='9b369e10e505262fd9730044cfe93697ee95e5fd29c19baea847a1c086e53ddb'
assert digest(engine)==expected,'Original engine archive checksum differs'
with zipfile.ZipFile(engine) as z:
    engine_manifest=licensing.signed_payload(json.loads(z.read('component-signature.json')))
    expected_entries={row['path']:row['bytes'] for row in engine_manifest['files']}
    assert set(z.namelist())==set(expected_entries)|{'component-signature.json'}
    assert all(z.getinfo(name).file_size==size for name,size in expected_entries.items())
    assert engine_manifest['kind']=='engine' and engine_manifest['version']=='vsr-1.4.0-sttn-cu128'
for src in (installer,engine):
    dst=OUT/src.name
    if dst.exists():raise FileExistsError('Refusing to replace delivery artifact: '+str(dst))
    shutil.copy2(src,dst)
    assert digest(dst)==digest(src)
notice='''漫剧工坊 0.10.0 安装与更新说明

请先完整解压本合集，把安装程序和 AI 引擎 ZIP 放在同一个文件夹里。
退出正在运行的漫剧工坊，再运行“漫剧工坊-安装程序-0.10.0.exe”。
老用户覆盖安装到原目录，已有项目、下载记录、设备授权和已导入模型保留原保存位置。

离线 AI 引擎：
已经导入 v2-cu128 的电脑，更新主程序即可，不必重复导入。
首次使用本地 AI 去字幕时，可在安装组件里勾选“导入同目录的离线 AI 引擎包”；也可安装后在软件“授权与组件”中导入随附 ZIP。
引擎 ZIP 不用自行解压或覆盖旧引擎文件夹，软件会校验并导入独立目录。

本次界面调整：
“任务与系统”不再单列 AI 接口，底部不再要求选择接口。
到“文案与封面”右上角点击“设置”，左侧可选择“文案接口”或“封面接口”。
两边分别填写平台、地址、模型和密钥，点击各自的保存按钮。已有连接可继续使用。
接口参数保存到本机；密钥只保留在本次运行中，重启后需重新填写。AI 文字和生图仍使用客户自己的云端服务，不属于离线引擎功能。

随附 v2-cu128 是现有本地去字幕引擎。剪映工程的人声分离与语音识别还需另配 Demucs、faster-whisper 依赖及本地模型，这些不包含在此 v2 包中。
本次没有运行覆盖安装、真实模型或客户显卡验收。不要把媒体编码检测通过视为所有 AI 模型均能在客户显卡运行。
'''
readme=OUT/'安装与更新说明.txt';readme.write_text(notice,'utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (OUT/installer.name,OUT/engine.name,readme)]
sums=OUT/'SHA256SUMS.txt';sums.write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in rows),'utf-8-sig')
target=OUT/'漫剧工坊-0.10.0-软件与AI引擎合集.zip'
partial=target.with_suffix('.zip.partial')
if target.exists() or partial.exists():raise FileExistsError('Bundle already exists')
print('ASSEMBLING_ZIP64',flush=True)
with zipfile.ZipFile(partial,'x',zipfile.ZIP_STORED,allowZip64=True) as z:
    for path in [OUT/installer.name,OUT/engine.name,readme,sums]:z.write(path,path.name)
partial.rename(target)
with zipfile.ZipFile(target) as z:
    assert set(z.namelist())=={installer.name,engine.name,readme.name,sums.name}
    for row in rows:
        with z.open(row['file']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
record={'version':'0.10.0','date':time.strftime('%Y-%m-%d'),'installer':rows[0],
        'bundle':{'file':target.name,'bytes':target.stat().st_size,'sha256':digest(target),'members':z.namelist()},
        'applicationIntegritySigned':True,'signedFiles':len(manifest['files']),'compiledModules':len(compiled),
        'compiledModuleFiles':compiled,'recordedBuildInputs':len(inputs['sourceSha256']),
        'packagedWebMatchesSource':True,'nativeCore':core,'nativeCoreHashVerified':True,
        'engine':{'file':engine.name,'sha256':expected,'reusedFrom':'0.9.3','signedFiles':len(engine_manifest['files']),'signatureAndArchiveHashVerified':True,'includesJianyingSeparationAndASR':False},
        'sourceUISettingsChecks':25,'sourceProviderChecks':26,'cloudResponses':'simulated',
        'installerExecuted':False,'realModelTestedThisRelease':False,'customerHardwareTested':False,
        'bundleMemberHashesVerified':True,'externalPlatformSubmitted':False}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
(RECORD/'engine-inputs.json').write_text(json.dumps(record['engine'],ensure_ascii=False,indent=2)+'\n','utf-8')
(OUT/'合集SHA256.txt').write_text(record['bundle']['sha256']+'  '+target.name+'\n','utf-8-sig')
print(json.dumps({'bundle':str(target),'bytes':record['bundle']['bytes'],'sha256':record['bundle']['sha256'],'signedFiles':record['signedFiles']},ensure_ascii=False),flush=True)
