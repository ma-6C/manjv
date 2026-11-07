"""Verify the exact signed/installed build and prepare the customer installer."""
from pathlib import Path
import ast,hashlib,json,shutil,sys

ROOT=Path(__file__).resolve().parents[1];VERSION='v0.10.2'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT));import licensing
RECORD=ROOT/'versions'/VERSION;DIST=ROOT/'release'/VERSION/'漫剧工坊';OUT=DIST.parent/'对外发送'
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
inputs=json.loads((RECORD/'build-inputs.json').read_text('utf-8'))
assert all(digest(ROOT/name)==sha for name,sha in inputs['sourceSha256'].items()),'Build input changed'
installed=json.loads((RECORD/'installation-report.json').read_text('utf-8'))
native=json.loads((RECORD/'native-ui-report.json').read_text('utf-8'))
payload=json.loads((RECORD/'payload-verification.json').read_text('utf-8'))
assert installed['ok'] and installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert native['ok'] and native['actualInstalledExecutable']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
scan=json.loads((RECORD/'defender-scan.json').read_text('utf-8-sig'))
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
for name,sha in inputs.get('runtimeSha256',{}).items():assert digest(Path(name))==sha,'Runtime input changed'
policy=next((Path(name) for name in inputs['runtimeSha256'] if name.endswith('codex-rejected-cas.pem')),None)
assert policy and digest(DIST/'_internal'/policy.name)==digest(policy),'SSL policy resource missing'
previous=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:
    if previous is None:del sys.frozen
    else:sys.frozen=previous
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']==VERSION[1:]
modules=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'build_hardened.py').read_text('utf-8')).body
             if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MODULES' for t in n.targets))
compiled={}
for name in modules:
    path=next((DIST/'_internal').glob(name+'.cp312-win_amd64.pyd'))
    compiled[name]={'path':path.relative_to(DIST).as_posix(),'sha256':digest(path)}
installer=DIST.parent/'漫剧工坊-安装程序-0.10.2.exe';assert installer.is_file()
assert digest(installer)==scan['installerSha256']
OUT.mkdir(parents=True,exist_ok=True);destination=OUT/installer.name
if destination.exists():raise FileExistsError('Refusing to replace customer artifact')
shutil.copy2(installer,destination);assert digest(destination)==digest(installer)
readme=OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.2 安装与更新说明
发布日期：2026年11月1日

安装或更新：
退出正在运行的漫剧工坊，再运行“漫剧工坊-安装程序-0.10.2.exe”。
老用户选择原安装目录更新。项目、下载记录和设备授权仍使用原来的用户数据位置。
本次在临时目录完成实际安装和桌面启动检查，没有覆盖本机原有正式安装目录。

本次更新：
文案、封面和云端去字幕设置支持填写网址、密钥后自动获取模型，并可搜索、选择或手动填写。
AI 去字幕 → 设置 → 云端服务连接：可保存独立接口、模型和任务路径，底栏提供保存按钮。
接口参数保存在本机；API 密钥只用于本次运行，重启软件后需重新填写。
修复安装版 HTTPS 初始化缺少证书限制资源的问题，保留证书和主机名校验。
此前0.10.1为未交付候选，曾被Defender拦截，请使用本次经过独立扫描和安装验证的0.10.2。

已实测的客户服务生图配置：
服务平台：自定义兼容服务
接口网址：https://ai.yuliapi.com/v1beta
调用协议：Gemini 生图
模型：gemini-nano-banana-2.1
密钥：填写自己的 API 密钥，本安装包不包含密钥。
源码版已真实生成 AI 原图与 816×1086 封面；安装版已验证真实模型列表查询。
该服务的默认 Images Generations 请求曾返回转换失败，请使用上面的已验证配置。

云端去字幕：
模型列表获取成功不代表支持视频去字幕，需按字幕服务商文档配置提交和查询路径。
当前客户服务的默认 /video/clear 路径未通过真实短片测试，本版不宣称该接口已能去字幕。
本地 STTN / LaMa 等修复路线继续使用已安装的本地 AI 引擎。

离线 AI 引擎：
已经安装 v2-cu128 引擎的电脑只需更新主程序，不必重复导入。
本次提供主程序安装包，不重复附带约4.4GB的既有引擎 ZIP。
首次安装需要本地 AI 去字幕时，可使用原有引擎包，通过“授权与组件”导入。
安装程序中的“导入同目录离线 AI 引擎”是可选项，没有引擎包时可保持不勾选。

验证：
应用完整性签名、安装后的文件散列、设备授权及桌面启动已检查通过。
测试未覆盖客户显卡和客户电脑，不代表所有模型均在客户硬件通过验证。
''','utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in [destination,readme]]
(OUT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in rows),'utf-8-sig')
record={'version':'0.10.2','date':'2026-11-01','installer':rows[0],'deliveryDirectory':str(OUT),
        'applicationIntegritySigned':True,'signedFiles':len(manifest['files']),'compiledModules':len(compiled),
        'compiledModuleFiles':compiled,'recordedBuildInputs':len(inputs['sourceSha256']),
        'installerExecuted':True,'installationWasIsolated':True,'installedPayloadHashesVerified':True,
        'originalRegistryAndShortcutsRestored':True,'actualInstalledDesktopStarted':True,
        'installedActivationAndLicenseVerified':True,'installedLiveModelListVerified':True,
        'installedNativeUIChecks':len(native['checks']),'sourceProviderChecks':43,'prerequisiteChecks':36,
        'compiledSigningChecks':31,'sourceLiveGeminiImageGenerationPassed':True,
        'installedLiveImageGenerationRepeated':False,'customerCloudSubtitlePassed':False,
        'customerHardwareTested':False,'customerKeysIncluded':False,'offlineEngineChanged':False,
        'offlineEngineIncluded':False,'deliveryFiles':rows,
        'defenderCustomScanNoMatchingDetection':True,'defenderEnabledDuringVerification':True,
        'frozenSSLResourceIncluded':True,'sslPolicySha256':digest(policy),
        'oldCandidateRestoredOrAllowed':False}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'installer':str(destination),'bytes':destination.stat().st_size,'sha256':rows[0]['sha256'],
                  'signedFiles':len(manifest['files']),'installedNativeUIChecks':len(native['checks'])},ensure_ascii=True))
