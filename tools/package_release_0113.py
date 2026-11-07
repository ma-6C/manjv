"""Verify and deliver the build that removes local activation requirements."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import sys

if not __debug__:
    raise RuntimeError('Release verification requires Python assertions')

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.10.13'
RECORD = ROOT/'versions'/VERSION
DIST = ROOT/'release'/VERSION/'漫剧工坊'
OUT = DIST.parent/'对外发送'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import licensing
from tools.release_safety import verify_manifest_file_set


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name):
    return json.loads((RECORD/name).read_text('utf-8-sig'))


inputs = read('build-inputs.json')
payload = read('payload-verification.json')
source = read('license-free-source-report.json')
compiled_usage = read('license-free-compiled-report.json')
regression = read('full-regression-report.json')
ui_regression = read('activation-removed-ui-report.json')
compiled = read('compiled-regression-report.json')
installed = read('installation-report.json')
http = read('installed-http-report.json')
native = read('native-ui-observed-report.json')
timing = read('installed-startup-timing.json')
scan = read('defender-scan.json')
authenticode = read('authenticode-status.json')

assert inputs['version'] == VERSION
assert all(digest(ROOT/name) == sha for name, sha in inputs['sourceSha256'].items())
assert all(digest(name) == sha for name, sha in inputs['runtimeSha256'].items())
assert source['ok'] and source['version'] == VERSION and not source['compiled'] and len(source['checks']) >= 19
assert regression['ok'] and len(regression['suites']) >= 25 and all(row['ok'] for row in regression['suites'])
assert 'license-free-usage' in {row['name'] for row in regression['suites']}
assert ui_regression['ok'] and len(ui_regression['checks']) >= 13
assert compiled_usage['ok'] and compiled_usage['version'] == VERSION and compiled_usage['compiled']
assert all(Path(path).resolve().parent == (DIST/'_internal').resolve() and Path(path).suffix == '.pyd' for path in compiled_usage['moduleOrigins'].values())
assert compiled['ok'] and compiled['version'] == VERSION
assert {row['name'] for row in compiled['suites']} >= {'verify_license_free', 'verify_distribution_integrity'}
assert all(row['ok'] and not row['sourceFallback'] for row in compiled['suites'])
for row in compiled['suites']:
    evidence = json.loads((DIST.parent/'验收证据'/(row['name']+'-compiled-imports.json')).read_text('utf-8'))
    assert evidence['version'] == VERSION and evidence['signedBuildVerified'] and not evidence['sourceFallback']
    assert evidence['pythonOptimizationLevel'] == 0
    assert evidence['compiledModules']
    for module in evidence['compiledModules'].values():
        path = Path(module['path']).resolve()
        assert path.parent == (DIST/'_internal').resolve() and path.suffix == '.pyd'
        assert digest(path) == module['sha256']
assert installed['ok'] and installed['version'] == VERSION
assert installed['upgradeFromVersion'] == 'v0.10.12' and installed['keepUserConfiguration']
assert installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert http['ok'] and http['version'] == VERSION and http['noActivationRequired']
assert http['activationCodeIssued'] is False and not http['customerDataUsed'] and not http['paidOrAccountCalls']
assert http['xiaovmiao']['bundled'] and http['xiaovmiao']['processRunning']
assert native['ok'] and native['version'] == VERSION and native['noActivationRequired']
assert Path(http['actualInstalledExecutable']).resolve() == (Path(installed['installationDirectory'])/'漫剧工坊.exe').resolve()
assert Path(native['actualInstalledExecutable']).resolve() == Path(http['actualInstalledExecutable']).resolve()
assert native['processId'] == http['processId'] == timing['pid']
assert timing['version'] == VERSION and timing['firstLoopbackHTTPResponseSeconds'] > 0
assert timing['exe'] == http['actualInstalledExecutable']
assert timing['executableSHA256'] == scan['executableSha256']
assert payload['version'] == payload['signedManifestVersion'] == VERSION[1:]
assert payload['signedFileHashesVerified'] and payload['unsignedExtraFilesAbsent']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert set(payload['compiledModules']) == set(inputs['compiledProductModules'])
assert scan['version'] == VERSION and scan['noMatchingDetection']
assert scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
assert Path(scan['scanPath']).resolve() == DIST.parent.resolve()

manifest = licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version'] == VERSION[1:] and manifest['product'] == 'ManjuStudio'
assert payload['signedFiles'] == len(manifest['files'])
verify_manifest_file_set(DIST, manifest)


def verify_file(row):
    path = (DIST/row['path']).resolve()
    return path.is_relative_to(DIST.resolve()) and path.is_file() and path.stat().st_size == row['bytes'] and digest(path) == row['sha256']


with ThreadPoolExecutor(max_workers=8) as pool:
    assert all(pool.map(verify_file, manifest['files']))
installer = DIST.parent/('漫剧工坊-安装程序-'+VERSION[1:]+'.exe')
assert digest(installer) == scan['installerSha256']
assert digest(DIST/'漫剧工坊.exe') == scan['executableSha256']
old_scan = json.loads((ROOT/'versions/v0.10.12/defender-scan.json').read_text('utf-8-sig'))
assert digest(ROOT/'release/v0.10.12/漫剧工坊-安装程序-0.10.12.exe') == old_scan['installerSha256']
assert len(authenticode) == 2
assert {(ROOT/row['file']).resolve() for row in authenticode} == {(DIST/'漫剧工坊.exe').resolve(), installer.resolve()}
assert all(row['status'] == 'NotSigned' for row in authenticode)
if OUT.exists():
    raise FileExistsError('Refusing to replace an existing delivery')
OUT.mkdir(parents=True)
destination = OUT/installer.name
shutil.copy2(installer, destination)
assert digest(destination) == digest(installer)
readme = OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.13
生成日期为 2026 年 11 月 7 日。

运行同目录的安装程序完成更新，启动后直接进入工作台。
本机激活码、机器码绑定和授权有效期验证已移除。
“本地组件”页面用于管理离线 AI 引擎。

安装前退出漫剧工坊。本轮已从 0.10.12 做隔离升级并验证保留配置。
离线 AI 引擎可在“本地组件”页面另行导入。

本轮以空白数据和本地生成的样片验证了工作台、视频任务和真实桌面操作。安装文件通过完整性校验和 Defender 扫描。
红果三集采集和 LaMa 成片验收记录位于 0.10.12 版本资料。

安装完整性清单已签署。
主程序和安装器的 Windows 发布者签名状态为 NotSigned。
''', 'utf-8-sig')
files = [{'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in (destination, readme)]
(OUT/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in files), 'utf-8-sig')
record = {'version': VERSION[1:], 'date': '2026-11-07', 'scope': 'Remove local activation requirements',
          'noActivationRequired': True, 'installer': files[0], 'deliveryDirectory': str(OUT),
          'recordedBuildInputs': len(inputs['sourceSha256']), 'compiledModules': len(payload['compiledModules']),
          'signedFiles': len(manifest['files']), 'compiledRegressionSuites': len(compiled['suites']),
          'sourceRegressionSuites': len(regression['suites']), 'activationRemovedUIChecks': len(ui_regression['checks']),
          'installedNativeUIChecks': len(native['checks']), 'installedHTTPChecks': len(http['checks']),
          'isolatedUpgradeFrom': 'v0.10.12', 'defaultConfigurationPreserved': True,
          'registryAndShortcutsRestored': True, 'previousInstallerPreserved': True,
          'startupFirstHTTPSeconds': timing['firstLoopbackHTTPResponseSeconds'],
          'authenticodeStatus': authenticode, 'defenderNoMatchingDetection': True,
          'customerDataUsed': False, 'paidOrAccountCalls': False, 'deliveryFiles': files}
(RECORD/'build-record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', 'utf-8')
print(json.dumps(record, ensure_ascii=False))
