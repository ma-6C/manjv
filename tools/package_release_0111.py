"""Publish this run's verified local-production and collection candidate."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.10.11'
NATIVE_MANIFEST = json.loads((ROOT / 'engines/guoapp-core/manifest.json').read_text('utf-8-sig'))
NATIVE_SHA = NATIVE_MANIFEST['sha256']
RECORD = ROOT / 'versions' / VERSION
DIST = ROOT / 'release' / VERSION / '漫剧工坊'
OUT = DIST.parent / '候选交付'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import licensing
from tools.release_safety import verify_manifest_file_set


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name):
    return json.loads((RECORD / name).read_text('utf-8-sig'))


inputs, payload = read('build-inputs.json'), read('payload-verification.json')
installed, reset = read('installation-report.json'), read('installation-reset-report.json')
native, http = read('native-ui-observed-report.json'), read('installed-http-report.json')
scan, regression = read('defender-scan.json'), read('full-regression-report.json')
authenticode = read('authenticode-status.json')
collection, production = read('hongguo-full-collection.json'), read('collected-production-report.json')
quality = read('visual-quality-review.json')
completeness, timing = read('source-completeness-compiled.json'), read('installed-startup-timing.json')
assert inputs['version'] == VERSION
assert regression['ok'] and len(regression['suites']) >= 22 and all(suite['ok'] for suite in regression['suites'])
assert all(digest(ROOT / name) == sha for name, sha in inputs['sourceSha256'].items()), 'Source changed after build'
assert all(digest(name) == sha for name, sha in inputs['runtimeSha256'].items()), 'Runtime changed after build'
for result in (installed, reset):
    assert result['ok'] and result['originalRegistryRestored'] and result['originalShortcutsRestored']
    assert result['version'] == VERSION and result['upgradeFromVersion'] == 'v0.10.10'
assert installed['keepUserConfiguration'] and not reset['keepUserConfiguration']
assert native['ok'] and native['actualInstalledExecutable'] and native['version'] == VERSION
assert http['ok'] and http['version'] == VERSION and not http['customerDataUsed'] and not http['paidOrAccountCalls']
assert http['xiaovmiao']['bundled'] and http['xiaovmiao']['processRunning']
assert native['actualInstalledExecutable'].replace('\\', '/').casefold() == http['actualInstalledExecutable'].replace('\\', '/').casefold()
assert timing['firstLoopbackHTTPResponseSeconds'] > 0 and timing['firstHTTPStatus'] == 403
assert timing['version'] == VERSION and timing['executableSHA256'] == scan['executableSha256']
assert timing['exe'].replace('\\', '/').casefold() == http['actualInstalledExecutable'].replace('\\', '/').casefold()
assert completeness['ok'] and completeness['compiled'] and completeness['passed'] >= 17
assert all(Path(path).suffix == '.pyd' for path in completeness['moduleOrigins'].values())
assert collection['ok'] and collection['dllSha256'] == NATIVE_SHA and len(collection['videos']) == 3
assert not collection['wholeSeriesVerified'] and collection['sourceImagesRequested'] == 0
assert production['ok'] and production['nativeSHA256'] == NATIVE_SHA and not production['externalModelCalls'] and not production['platformPublished']
assert quality['ok'] and quality['visualReviewed'] and quality['nativeSHA256'] == NATIVE_SHA
assert quality['productionReportSHA256'] == digest(RECORD / 'collected-production-report.json')
assert quality['subtitleMode'] == 'vsr' and quality['subtitleModel'] == 'lama'
assert production['projectIds'] == collection['projectIds'] and production['collectionReport'] == collection['report']
assert all(digest(row['path']) == row['sha256'] for row in collection['videos'])
assert all(digest(row['path']) == row['sha256'] for row in production['outputs'])
assert payload['signedFileHashesVerified'] and payload['unsignedExtraFilesAbsent']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
manifest = licensing.signed_payload(json.loads((DIST / 'integrity.json').read_text('utf-8-sig')))
assert manifest['version'] == VERSION[1:] and manifest['product'] == 'ManjuStudio'
verify_manifest_file_set(DIST, manifest)


def verify(row):
    path = (DIST / row['path']).resolve()
    return path.is_relative_to(DIST.resolve()) and path.is_file() and path.stat().st_size == row['bytes'] and digest(path) == row['sha256']


with ThreadPoolExecutor(max_workers=8) as pool:
    assert all(pool.map(verify, manifest['files'])), 'Signed file changed'
assert digest(DIST / '_internal/engines/guoapp-core/duanju_core.dll') == NATIVE_SHA
installer = DIST.parent / ('漫剧工坊-安装程序-' + VERSION[1:] + '.exe')
assert digest(installer) == scan['installerSha256'] and digest(DIST / '漫剧工坊.exe') == scan['executableSha256']
old_scan = json.loads((ROOT / 'versions/v0.10.10/defender-scan.json').read_text('utf-8-sig'))
assert digest(ROOT / 'release/v0.10.10/漫剧工坊-安装程序-0.10.10.exe') == old_scan['installerSha256'], 'Previous installer changed'
for row in authenticode:
    assert row['status'] == 'NotSigned', 'Update delivery disclosure for changed Authenticode status'
if OUT.exists():
    raise FileExistsError('Refusing to replace an existing candidate delivery')
OUT.mkdir(parents=True)
destination = OUT / installer.name
shutil.copy2(installer, destination)
assert digest(destination) == digest(installer)
readme = OUT / '安装与验收范围.txt'
readme.write_text(('''漫剧工坊 0.10.11 本地制作与采集候选版
生成日期：2026年11月7日

运行“漫剧工坊-安装程序-0.10.11.exe”安装。
本轮按用户确认范围验收本地制作与采集，逐项证据在工作区 versions/v0.10.11。
应用完整性清单已签署；尚未配置 Windows 发布者证书，主程序与安装器的 Authenticode 状态均为 NotSigned。

更新前退出漫剧工坊。旧版安装包及用户项目、成片、授权、模型、小v喵数据保留。
安装向导“卸载旧版本时保留用户配置”默认勾选。
取消保留配置会先备份 state.json，再仅重置软件设置；备份失败会中止操作。
本包不携带客户 API 密钥、账号 Cookie 或用户数据库，离线 AI 引擎按需单独导入。

本轮红果原生核心为 {native_version}：已用最终 DLL 在全新临时队列中实际采集并导入三条全集样本。
第26集、第37集与对照第1集均核对集数、声明时长、文件哈希并完整解码音视频。
短试看不再作为全集成功入库；无法取到完整文件时显示失败原因。
三条实采原件已继续完成本地 LaMa 字幕区域修补、视频、高光、封面、制作记录、成本报告和本地材料包流程。
已对选定画面进行视觉复核，修补效果受原片和区域选择影响；本地高光完成不代表付费 AI 语义质量已经验收。
本轮覆盖三条样本，未宣称整部剧全部分集、所有账号或第三方接口长期可用。

本轮还验证了编译模块、本地队列恢复、完整性防篡改、Defender 扫描、两种真实隔离升级、实际安装 EXE 的桌面和 HTTP 流程。
测试使用独立临时数据，结束后恢复原注册表和快捷方式。
小v喵通过独立窗口打开，已有明确配置的程序与数据路径继续优先使用；不要删除原修复版和本地数据目录。

未在本轮使用用户真实账号发布、评论、私信或云同步，未调用客户付费 AI。
真实客户电脑、长期运行、付费 AI 和平台账号业务仍需各自环境验收，本包不宣称已完成全部商业验收。
''').format(native_version=NATIVE_MANIFEST['version']), 'utf-8-sig')
rows = [{'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in (destination, readme)]
(OUT / 'SHA256SUMS.txt').write_text(''.join(row['sha256'] + '  ' + row['file'] + '\n' for row in rows), 'utf-8-sig')
record = {'version': VERSION[1:], 'date': '2026-11-07', 'releaseChannel': 'commercial-candidate',
          'scope': 'local production and collection', 'commercialCustomerAcceptanceComplete': False,
          'installer': rows[0], 'deliveryDirectory': str(OUT), 'recordedBuildInputs': len(inputs['sourceSha256']),
          'compiledModules': len(payload['compiledModules']), 'signedFiles': len(manifest['files']),
          'installedNativeUIChecks': len(native['checks']), 'installedHTTPChecks': len(http['checks']),
          'sourceRegressionSuitesPassed': len(regression['suites']), 'authenticodeStatus': authenticode,
          'isolatedUpgradeFrom': 'v0.10.10', 'defaultConfigurationPreserved': True,
          'explicitSettingsResetVerified': True, 'registryAndShortcutsRestored': True, 'previousInstallerPreserved': True,
          'actualInstalledDesktopStarted': True, 'startupFirstHTTPSeconds': timing['firstLoopbackHTTPResponseSeconds'],
          'nativeCoreSHA256': NATIVE_SHA, 'realFullEpisodesVerified': 3, 'wholeSeriesVerified': False,
          'visualQualityReviewed': True, 'subtitleMode': quality['subtitleMode'], 'subtitleModel': quality['subtitleModel'],
          'collectedProductionChecks': len(production['checks']), 'defenderNoMatchingDetection': True,
          'realUserAccountsTested': False, 'customerHardwareTested': False, 'paidAITested': False, 'deliveryFiles': rows}
(RECORD / 'build-record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps(record, ensure_ascii=False))
