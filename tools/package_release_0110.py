"""Publish only this run's verified 0.10.10 candidate into a separate folder."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.10.10'
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


inputs = read('build-inputs.json')
installed, reset = read('installation-report.json'), read('installation-reset-report.json')
native, payload = read('native-ui-report.json'), read('payload-verification.json')
scan = read('defender-scan.json')
full_regression = read('full-regression-report.json')
authenticode = read('authenticode-status.json')
upgrade, settings = read('upgrade-scenarios.json'), read('settings-reset-scenarios.json')
assert inputs['version'] == VERSION
assert full_regression['ok'] and all(suite['ok'] for suite in full_regression['suites'])
assert all(digest(ROOT / name) == sha for name, sha in inputs['sourceSha256'].items()), 'Source changed after build'
assert all(digest(name) == sha for name, sha in inputs['runtimeSha256'].items()), 'Runtime changed after build'
for result in (installed, reset):
    assert result['ok'] and result['originalRegistryRestored'] and result['originalShortcutsRestored']
    assert result['version'] == VERSION and result['upgradeFromVersion'] == 'v0.10.9'
assert installed['keepUserConfiguration'] and not reset['keepUserConfiguration']
assert upgrade['ok'] and upgrade['originalRegistryRestored'] and settings['ok']
assert native['ok'] and native['actualInstalledExecutable'] and not native['browserErrors']
assert native['version'] == VERSION and native['xiaovmiao']['realBundledLaunch']
assert payload['signedFileHashesVerified'] and payload['unsignedExtraFilesAbsent']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
manifest = licensing.signed_payload(json.loads((DIST / 'integrity.json').read_text('utf-8-sig')))
assert manifest['version'] == VERSION[1:] and manifest['product'] == 'ManjuStudio'
verify_manifest_file_set(DIST, manifest)


def verify(row):
    path = (DIST / row['path']).resolve()
    return (path.is_relative_to(DIST.resolve()) and path.is_file() and
            path.stat().st_size == row['bytes'] and digest(path) == row['sha256'])


with ThreadPoolExecutor(max_workers=8) as pool:
    assert all(pool.map(verify, manifest['files'])), 'Signed file changed'
installer = DIST.parent / '漫剧工坊-安装程序-0.10.10.exe'
assert digest(installer) == scan['installerSha256'] and digest(DIST / '漫剧工坊.exe') == scan['executableSha256']
old = json.loads((ROOT / 'versions/v0.10.9/build-record.json').read_text('utf-8'))
assert digest(ROOT / 'release/v0.10.9' / old['installer']['file']) == old['installer']['sha256'], 'Previous installer changed'
if OUT.exists():
    raise FileExistsError('Refusing to replace an existing candidate delivery')
OUT.mkdir(parents=True)
destination = OUT / installer.name
shutil.copy2(installer, destination)
assert digest(destination) == digest(installer)
readme = OUT / '候选版安装与验收范围.txt'
readme.write_text('''漫剧工坊 0.10.10 商用候选版
生成日期：2026年11月7日

运行“漫剧工坊-安装程序-0.10.10.exe”安装。
这是本轮持续测试和修复后的候选版本，尚未取得真实客户环境的正式商用验收。
本轮候选的逐项验证记录位于工作区 versions/v0.10.10；以本版本报告为准。
应用完整性清单已签署；本包尚未配置Windows发布者证书，主程序和安装器的Authenticode状态为NotSigned。

更新前退出漫剧工坊。旧版安装包及用户项目、成片、授权、模型、小v喵数据保留。
安装向导可以选择先卸载旧程序，“卸载旧版本时保留用户配置”默认勾选。
取消保留配置会先备份 state.json，只重置软件设置；备份失败会中止操作。
离线AI引擎仍单独导入，本包不携带客户API密钥、账号Cookie或用户数据库。

小v喵通过独立窗口打开，原来明确配置的程序与数据路径继续优先使用。
不要删除原修复版目录或“本地数据”。新旧布局数据不会自动合并。
随包程序首次准备需要额外磁盘空间，并会创建当前用户可写的运行副本。

本轮交付修复了状态损坏保护、任务退出保存、前端故障恢复，以及构建覆盖/额外文件混入的风险。
本地剧情识别、计划校验、混剪、预览与保存继续保留。
已移除的“开始工作”“三平台发布挂载”“点击跳转核对”功能不恢复。

验证范围：本轮构建输入、签名完整性、发行文件、Defender扫描、隔离升级和真实桌面入口运行。
隔离测试使用临时数据，测试后恢复原注册表和快捷方式。
本次没有以用户真实账号执行扫码、发布、评论、私信或云同步，也不据此宣称这些业务通过。
当前红果外部取流未通过：目录/详情可读不等于视频可下载。三条非VIP首集未获得可用播放地址，未下载或解密。
付费AI效果、真实客户电脑长期使用与完整商用验收仍需在相应环境确认。
''', 'utf-8-sig')
rows = [{'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in (destination, readme)]
(OUT / 'SHA256SUMS.txt').write_text(''.join(row['sha256'] + '  ' + row['file'] + '\n' for row in rows), 'utf-8-sig')
record = {'version': VERSION[1:], 'date': '2026-11-07', 'releaseChannel': 'commercial-candidate',
          'commercialCustomerAcceptanceComplete': False, 'installer': rows[0], 'deliveryDirectory': str(OUT),
          'recordedBuildInputs': len(inputs['sourceSha256']), 'compiledModules': len(payload['compiledModules']),
          'signedFiles': len(manifest['files']), 'installedNativeUIChecks': len(native['checks']),
          'sourceRegressionSuitesPassed': len(full_regression['suites']), 'authenticodeStatus': authenticode,
          'isolatedUpgradeFrom': 'v0.10.9', 'defaultConfigurationPreserved': True,
          'explicitSettingsResetVerified': True, 'registryAndShortcutsRestored': True,
          'previousInstallerPreserved': True, 'actualInstalledDesktopStarted': True,
          'defenderNoMatchingDetection': True, 'realUserAccountsTested': False,
          'customerHardwareTested': False, 'deliveryFiles': rows}
(RECORD / 'build-record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps(record, ensure_ascii=False))
