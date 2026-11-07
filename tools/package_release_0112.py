"""Publish this run's verified local-production and collection candidate."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import sys

if not __debug__:
    raise RuntimeError('Release gates require assertions; do not use python -O or PYTHONOPTIMIZE')

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.10.12'
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
upgrade_scenarios, settings_scenarios = read('upgrade-scenarios.json'), read('settings-reset-scenarios.json')
build_safety, compiled_summary = read('build-safety-report.json'), read('compiled-regression-report.json')
collection, production = read('hongguo-full-collection.json'), read('collected-production-report.json')
packaged_collection = read('packaged-hongguo-full-collection.json')
packaged_manager = read('packaged-hongguo-manager-report.json')
quality = read('visual-quality-review.json')
completeness, timing = read('source-completeness-compiled.json'), read('installed-startup-timing.json')
timing_repeat = read('installed-startup-repeat.json')
reopened = read('installed-ui-reopened-timing.json')
activation_exit = read('installed-ui-activation-exit.json')
tail = read('subtitle-tail-compiled-report.json')
assert inputs['version'] == VERSION
assert regression['ok'] and len(regression['suites']) >= 24 and all(suite['ok'] for suite in regression['suites'])
assert {'distribution-integrity', 'source-completeness', 'subtitle-tail-timing', 'library-ui', 'connection-recovery-ui'} <= {suite['name'] for suite in regression['suites']}
assert all(digest(ROOT / name) == sha for name, sha in inputs['sourceSha256'].items()), 'Source changed after build'
assert all(digest(name) == sha for name, sha in inputs['runtimeSha256'].items()), 'Runtime changed after build'
for result in (installed, reset):
    assert result['ok'] and result['originalRegistryRestored'] and result['originalShortcutsRestored']
    assert result['version'] == VERSION and result['upgradeFromVersion'] == 'v0.10.10'
assert installed['keepUserConfiguration'] and not reset['keepUserConfiguration']
assert upgrade_scenarios['ok'] and upgrade_scenarios['originalRegistryRestored'] and len(upgrade_scenarios['checks']) >= 25
assert settings_scenarios['ok'] and settings_scenarios['nativeHelperExecuted'] and not settings_scenarios['customerDataUsed'] and len(settings_scenarios['checks']) >= 25
assert build_safety['ok'] and build_safety['passed'] >= 10
assert compiled_summary['ok'] and compiled_summary['version'] == VERSION and len(compiled_summary['suites']) == 8
assert all(suite['ok'] and suite['returncode'] == 0 and not suite['sourceFallback'] for suite in compiled_summary['suites'])
assert native['ok'] and native['actualInstalledExecutable'] and native['version'] == VERSION
assert http['ok'] and http['version'] == VERSION and not http['customerDataUsed'] and not http['paidOrAccountCalls']
assert http['xiaovmiao']['bundled'] and http['xiaovmiao']['processRunning']
assert native['actualInstalledExecutable'].replace('\\', '/').casefold() == http['actualInstalledExecutable'].replace('\\', '/').casefold()
assert Path(http['actualInstalledExecutable']).resolve() == (Path(reset['installationDirectory']) / '漫剧工坊.exe').resolve()
assert timing['firstLoopbackHTTPResponseSeconds'] > 0 and timing['firstHTTPStatus'] == 403
assert timing['version'] == VERSION and timing['executableSHA256'] == scan['executableSha256']
assert timing['exe'].replace('\\', '/').casefold() == http['actualInstalledExecutable'].replace('\\', '/').casefold()
assert timing_repeat['version'] == VERSION and timing_repeat['executableSHA256'] == scan['executableSha256']
assert timing_repeat['firstLoopbackHTTPResponseSeconds'] > 0 and timing_repeat['firstHTTPStatus'] == 403
assert Path(timing_repeat['exe']).resolve() == Path(http['actualInstalledExecutable']).resolve()
assert timing_repeat['pid'] == http['processId'] == native['activationProcessId'] == activation_exit['pid']
assert activation_exit['exitCode'] == 0
assert reopened['version'] == VERSION and reopened['executableSHA256'] == scan['executableSha256']
assert not reopened['freshAppProfile'] and reopened['pid'] == native['processId']
assert Path(reopened['exe']).resolve() == Path(http['actualInstalledExecutable']).resolve()
assert Path(reopened['dataDirectory']).resolve() == Path(timing_repeat['dataDirectory']).resolve() == Path(native['dataDirectory']).resolve()
assert completeness['ok'] and completeness['compiled'] and completeness['passed'] >= 17
assert all(Path(path).suffix == '.pyd' for path in completeness['moduleOrigins'].values())
assert tail['ok'] and tail['previewTimestampMappingVerified'] and len(tail['checks']) >= 25
for test in ('verify_backend_reliability', 'verify_distribution_integrity', 'verify_source_completeness', 'verify_subtitle_tail',
             'verify_promotion_engines', 'verify_promotion_mediakit', 'verify_promotion_dramaclip', 'verify_signing_compatibility'):
    compiled=json.loads((DIST.parent / '验收证据' / (test + '-compiled-imports.json')).read_text('utf-8-sig'))
    assert compiled['version'] == VERSION and compiled['signedBuildVerified'] and not compiled['sourceFallback']
    assert compiled['test'] == test + '.py' and compiled['compiledModules']
    assert all(Path(row['path']).resolve().parent == (DIST / '_internal').resolve() and digest(row['path']) == row['sha256'] for row in compiled['compiledModules'].values())
assert collection['ok'] and collection['dllSha256'] == NATIVE_SHA and len(collection['videos']) == 3
assert not collection['wholeSeriesVerified'] and collection['sourceImagesRequested'] == 0
assert packaged_collection['ok'] and packaged_collection['dllSha256'] == NATIVE_SHA and len(packaged_collection['videos']) == 3
assert packaged_manager['ok'] and packaged_manager['compiled'] and packaged_manager['sourceImagesRequested'] == 0
assert packaged_manager['expectedEngineSha256'] == packaged_manager['component']['sha256'] == NATIVE_SHA
assert packaged_collection['version'] == packaged_manager['expectedEngineVersion'] == NATIVE_MANIFEST['version']
assert Path(packaged_collection['report']).resolve() == (Path(packaged_manager['base']) / 'report.json').resolve()
assert digest(packaged_collection['report']) == digest(RECORD / 'packaged-hongguo-manager-report.json')
assert {(row['seriesId'], row['videoId'], row['episode']): row['sha256'] for row in packaged_collection['videos']} == {(row['seriesId'], row['videoId'], row['episode']): row['sha256'] for row in collection['videos']}
assert all(Path(path).resolve().parent == (DIST / '_internal').resolve() and Path(path).suffix == '.pyd' for path in packaged_manager['moduleOrigins'].values())
assert all(row['ok'] for row in packaged_manager['targets'])
assert production['ok'] and production['nativeSHA256'] == NATIVE_SHA and not production['externalModelCalls'] and not production['platformPublished']
assert quality['ok'] and quality['visualReviewed'] and quality['nativeSHA256'] == NATIVE_SHA
assert quality['productionReportSHA256'] == digest(RECORD / 'collected-production-report.json')
assert quality['subtitleMode'] == 'vsr' and quality['subtitleModel'] == 'lama-box'
assert quality['tailCardsPreserved'] and quality['previewTimestampMappingVerified']
assert quality['subtitlePreserveTailSeconds'] > 0
assert len(quality['sampledFinalFrames']) >= 24
assert all(digest(row['frame']) == row['frameSHA256'] and digest(row['output']) == row['outputSHA256'] for row in quality['sampledFinalFrames'])
assert {row['output'] for row in quality['sampledFinalFrames']} == {row['path'] for row in production['outputs']}
assert production['projectIds'] == collection['projectIds'] and production['collectionReport'] == collection['report']
assert all(digest(row['path']) == row['sha256'] for row in collection['videos'])
assert all(digest(row['path']) == row['sha256'] for row in production['outputs'])
assert payload['signedFileHashesVerified'] and payload['unsignedExtraFilesAbsent']
assert payload['version'] == payload['signedManifestVersion'] == VERSION[1:]
assert set(payload['compiledModules']) == set(inputs['compiledProductModules'])
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
assert scan['version'] == VERSION and Path(scan['scanPath']).resolve() == DIST.parent.resolve()
manifest = licensing.signed_payload(json.loads((DIST / 'integrity.json').read_text('utf-8-sig')))
assert manifest['version'] == VERSION[1:] and manifest['product'] == 'ManjuStudio'
assert payload['signedFiles'] == len(manifest['files'])
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
assert len(authenticode) == 2
assert {(ROOT / row['file']).resolve() for row in authenticode} == {(DIST / '漫剧工坊.exe').resolve(), installer.resolve()}
for row in authenticode:
    assert row['status'] == 'NotSigned', 'Update delivery disclosure for changed Authenticode status'
if OUT.exists():
    raise FileExistsError('Refusing to replace an existing candidate delivery')
OUT.mkdir(parents=True)
destination = OUT / installer.name
shutil.copy2(installer, destination)
assert digest(destination) == digest(installer)
readme = OUT / '安装与验收范围.txt'
readme.write_text(('''漫剧工坊 0.10.12 本地制作与采集候选版
生成日期：2026年11月7日

运行“漫剧工坊-安装程序-0.10.12.exe”安装。
本轮按用户确认范围验收本地制作与采集，逐项证据在工作区 versions/v0.10.12。
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
原片含“未完待续”等尾卡时，可配置保留片尾秒数，让本地修补跳过尾段；默认 0 秒，按原片预览后选择。
受保护的尾段保留原有文字和图案，其中若含对白字幕也会保留；本轮样片选择保留最后 2 秒。
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
          'installerUpgradeFixtureChecks': len(upgrade_scenarios['checks']), 'installerSettingsChecks': len(settings_scenarios['checks']),
          'actualInstalledDesktopStarted': True, 'startupFirstHTTPSeconds': timing['firstLoopbackHTTPResponseSeconds'],
          'startupRepeatFirstHTTPSeconds': timing_repeat['firstLoopbackHTTPResponseSeconds'],
          'nativeCoreSHA256': NATIVE_SHA, 'realFullEpisodesVerified': 3, 'wholeSeriesVerified': False,
          'realPackagedFullEpisodesVerified': 3,
          'visualQualityReviewed': True, 'subtitleMode': quality['subtitleMode'], 'subtitleModel': quality['subtitleModel'],
          'tailCardsPreserved': True, 'previewTimestampMappingVerified': True,
          'collectedProductionChecks': len(production['checks']), 'defenderNoMatchingDetection': True,
          'realUserAccountsTested': False, 'customerHardwareTested': False, 'paidAITested': False, 'deliveryFiles': rows}
(RECORD / 'build-record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps(record, ensure_ascii=False))
