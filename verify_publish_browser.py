"""Actual Edge fixture checks; optional read-only official login-page probe.

Fixture requests are fulfilled in a separate test profile.  This proves safe
control matching and state handling, not successful official submission.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
from publish_browser import BrowserManager, safe_url, classify_page, normalize_label

LOGIN = '<html lang="zh-CN"><body><h1>视频号助手</h1><p>微信扫码登录</p><button>扫码登录</button></body></html>'
FORM = '''<html lang="zh-CN"><body><h1>创建剧集</h1><nav>剧集管理 · 退出登录</nav>
<label>剧集名称<input id="title"></label><label>剧集简介<textarea id="synopsis"></textarea></label>
<label>制作方名称<input id="producer"></label><label>总集数<input id="episodes" type="number"></label>
<label>试看集数<input id="trial" type="number"></label><label>制作成本（万元）<input id="cost" type="number"></label>
<label>剧目类型<select id="kind"><option value="">请选择</option><option value="comic">漫剧</option><option value="human">数字真人</option></select></label>
<label>封面图<input id="cover" type="file" accept="image/*"></label>
<label>正片<input id="videos" type="file" accept=".mp4" multiple></label>
<label>其他附件<input id="unknown" type="file"></label>
<label><input id="rights" type="checkbox">我确认拥有版权</label>
<button id="submit" onclick="window.submitted=(window.submitted||0)+1">提交提审</button>
</body></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Also open the actual official anonymous login page; never submit')
    args = parser.parse_args()
    (ROOT / 'tmp').mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='publish-browser-', dir=ROOT / 'tmp'))
    checks = []

    def check(name, result):
        if not result:
            raise AssertionError(name)
        checks.append(name)
        print('PASS', name, flush=True)

    check('URL query/fragment and credentials are not returned', safe_url('https://name:secret@channels.weixin.qq.com/mcn/login?code=secret#token') == 'https://channels.weixin.qq.com/mcn/login')
    check('Labels normalize required markers without fuzzy text matching', normalize_label(' * 剧集名称： ') == '剧集名称')
    check('Official URL alone cannot prove login', classify_page('https://channels.weixin.qq.com/platform', '加载中', [])[0] == 'unknown')
    check('Offsite content cannot prove login', classify_page('https://example.com/', '退出登录 视频号助手', [])[0] == 'unknown')
    check('Visible QR login is login_required', classify_page('https://channels.weixin.qq.com/mcn/login', '微信扫码登录', [])[0] == 'login_required')

    class ShutdownProbe(BrowserManager):
        def __init__(self, data):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.executed = []
            super().__init__(data)

        def _command(self, account, action, payload):
            if account['id'] == 'running':
                self.entered.set()
                if not self.release.wait(5):
                    raise RuntimeError('Shutdown probe timed out')
            self.executed.append(account['id'])
            return {'done': True}

    probe = ShutdownProbe(base / 'shutdown-probe')
    outcomes = {}

    def invoke(name):
        try:
            outcomes[name] = probe.command({'id': name}, 'open')
        except RuntimeError as error:
            outcomes[name] = str(error)

    running = threading.Thread(target=invoke, args=('running',))
    queued = threading.Thread(target=invoke, args=('queued',))
    stopping = threading.Thread(target=probe.shutdown)
    try:
        running.start()
        if not probe.entered.wait(2):
            raise AssertionError('Shutdown probe did not enter running command')
        queued.start()
        deadline = time.monotonic() + 2
        while probe._queue.qsize() < 1 and time.monotonic() < deadline:
            time.sleep(.005)
        if probe._queue.qsize() < 1:
            raise AssertionError('Shutdown probe second command was not queued')
        stopping.start()
        deadline = time.monotonic() + 2
        while not probe._closed and time.monotonic() < deadline:
            time.sleep(.005)
        if not probe._closed:
            raise AssertionError('Shutdown probe did not close command intake')
        probe.release.set()
        running.join(3); queued.join(3); stopping.join(3)
        check('Shutdown lets running action finish and rejects queued browser action',
              probe.executed == ['running'] and outcomes.get('running') == {'done': True} and
              isinstance(outcomes.get('queued'), str) and '尚未开始' in outcomes['queued'] and not probe._thread.is_alive())
    finally:
        probe.release.set()
        probe.shutdown()
        if running.ident is not None:running.join(2)
        if queued.ident is not None:queued.join(2)
        if stopping.ident is not None:stopping.join(2)

    captures = {}
    starts = []
    mode_html = {'drama': LOGIN, 'slice': LOGIN}
    manager = None

    def factory(profile, mode, target):
        from patchright.sync_api import sync_playwright
        if manager._driver is None:
            manager._driver = sync_playwright().start()
        exe = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
        context = manager._driver.chromium.launch_persistent_context(str(profile), executable_path=str(exe), headless=False,
            viewport={'width': 1100, 'height': 850}, timeout=25000)
        html = mode_html[mode]
        context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
        starts.append({'profile': str(profile), 'mode': mode, 'target': target, 'thread': threading.get_ident()})
        return context

    class FixtureManager(BrowserManager):
        close_after_inspect = False

        def _inspect(self, page, mode):
            state, rows = super()._inspect(page, mode)
            captures[mode] = page.evaluate('''() => ({values:Object.fromEntries(Array.from(document.querySelectorAll('input:not([type=file]),textarea,select')).map(e=>[e.id,e.type==='checkbox'?e.checked:e.value])),files:Object.fromEntries(Array.from(document.querySelectorAll('input[type=file]')).map(e=>[e.id,e.files.length])),submitted:window.submitted||0})''')
            if '创建剧集' in state['heading']:
                page.screenshot(path=str(base / '官方提审辅助-控件测试.png'), full_page=True)
            if self.close_after_inspect:
                self.close_after_inspect = False
                page.context.close()
            return state, rows

    manager = FixtureManager(base, _driver_factory=factory)
    account = {'id': 'fixture-account', 'name': '隔离控件测试账号'}
    try:
        check('Check never opens a missing browser implicitly', manager.command(account, 'check')['browserOpen'] is False)
        for account_bad, payload, label in [({'id': '../escape'}, {}, 'Account path traversal rejected'),
                                            (account, {'url': 'https://example.com'}, 'Arbitrary URL injection rejected')]:
            try:
                manager.command(account_bad, 'open', payload)
                ok = False
            except ValueError:
                ok = True
            check(label, ok)
        state = manager.command(account, 'open')
        check('Actual Edge fixture recognizes anonymous login', state['browserOpen'] and state['loginState'] == 'login_required')
        state = manager.command(account, 'assist', {'plan': {'ready': True, 'fields': {}, 'files': {}}})
        check('Login prompt blocks all form operations', state['state'] == 'needs_login' and not state['filled'])
        manager.command(account, 'close')
        mode_html['drama'] = FORM
        state = manager.command(account, 'open')
        check('Actual visible labeled drama form is recognized', state['formRecognized'] and state['loginState'] == 'authenticated')
        cover = base / 'cover.png'; cover.write_bytes(b'fixture-cover')
        video = base / 'episode01.mp4'; video.write_bytes(b'fixture-video')
        proof = base / 'proof.png'; proof.write_bytes(b'fixture-proof')
        plan = {'ready': True, 'fields': {'title': '辅助提审测试剧', 'synopsis': '仅用于本地控件适配验证。', 'producer': '测试制作方',
                                        'episodeCount': 1, 'trialEpisodes': 1, 'totalCostYuan': 125000, 'dramaType': 'animation'},
                'files': {'cover': {'path': str(cover)}, 'videos': [{'path': str(video)}], 'proofImages': [{'path': str(proof)}]}}
        result = manager.command(account, 'assist', {'plan': plan})
        manager.command(account, 'check')
        values = captures['drama']['values']
        (base / 'fixture-result.json').write_text(json.dumps({'result': result, 'capture': captures['drama']}, ensure_ascii=False, indent=2), 'utf-8')
        check('Seven matched text/select fields are filled', len([x for x in result['filled'] if x['action'] == 'field_checked_or_filled']) == 7 and values['title'] == plan['fields']['title'] and values['kind'] == 'comic')
        check('Cost unit is converted explicitly from yuan to ten-thousand yuan', values['cost'] == '12.5')
        check('Files selected only for exact-purpose file controls', captures['drama']['files'] == {'cover': 1, 'videos': 1, 'unknown': 0})
        check('Unmatched proof upload remains an actionable pending item', any(x['key'] == 'proofImages' for x in result['pending']))
        check('Rights and final submission are never clicked', values['rights'] is False and captures['drama']['submitted'] == 0 and result['submitted'] is False)
        check('Selected files are not reported as completed uploads', result['uploadCompleted'] is False and result['state'] == 'awaiting_confirmation')
        repeated = manager.command(account, 'assist', {'plan': plan})
        check('Existing attachments are preserved on repeated assistance', not any(x['action'] == 'files_selected' for x in repeated['filled']) and all(any(p['key'] == key for p in repeated['pending']) for key in ('cover', 'videos')))
        other = dict(plan, fields=dict(plan['fields'], title='其他剧目'))
        result = manager.command(account, 'assist', {'plan': other})
        check('A different existing drama draft is not overwritten', result['state'] == 'needs_navigation' and not result['filled'])
        manager.command(account, 'open', {'mode': 'slice'})
        check('Slice and drama use separate account profiles', starts[-1]['mode'] == 'slice' and starts[-1]['profile'] != starts[-2]['profile'] and starts[-1]['target'].endswith('/platform'))
        manager.close_after_inspect = True
        manager.command(account, 'check')
        check('Manually closed browser is detected', manager.command(account, 'check')['browserOpen'] is False)
        check('Manually closed browser can reopen', manager.command(account, 'open')['browserOpen'] is True)
        check('All browser profiles are created on one actor thread', len({x['thread'] for x in starts}) == 1 and starts[0]['thread'] != threading.get_ident())
    finally:
        manager.shutdown()

    live = None
    if args.live:
        actual = BrowserManager(base / 'official-anonymous-probe')
        try:
            opened = actual.command({'id': 'anonymous-probe'}, 'open')
            time.sleep(3)
            live = actual.command({'id': 'anonymous-probe'}, 'check')
            check('Actual official anonymous page opens with no submission', opened['browserOpen'] and live['browserOpen'] and live['pageUrl'].startswith('https://channels.weixin.qq.com/'))
        finally:
            actual.shutdown()
    report = {'base': str(base), 'passed': len(checks), 'checks': checks, 'officialReadOnly': live,
              'boundary': '控件测试使用隔离 Edge 及本地 HTML 响应；仅实际官方匿名页为只读访问。未执行扫码、上传、提交或审核验收。'}
    (base / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT / 'tmp/publish-browser-latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print('PUBLISH_BROWSER_OK', len(checks), str(base), flush=True)


if __name__ == '__main__':
    main()
