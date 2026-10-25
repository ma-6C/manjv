"""Visible official-backend assistance; never submits or infers review success.

The browser and its local profile are owned by one actor thread.  Public commands
accept an account and a mode, not an arbitrary URL, selector, script or cookie.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from pathlib import Path
import os
import queue
import re
import threading
import time
from urllib.parse import urlsplit, urlunsplit

URLS = {'drama': 'https://channels.weixin.qq.com/mcn/login',
        'slice': 'https://channels.weixin.qq.com/platform'}


def safe_url(value):
    """Page URLs may contain login codes; do not send queries/fragments to UI."""
    try:
        item = urlsplit(str(value))
        if item.scheme not in ('https', 'http') or not item.hostname:
            return ''
        port = ':' + str(item.port) if item.port else ''
        return urlunsplit((item.scheme, item.hostname + port, item.path, '', ''))
    except ValueError:
        return ''


def official_url(value):
    try:
        item = urlsplit(str(value))
        return item.scheme == 'https' and item.hostname == 'channels.weixin.qq.com' and item.port in (None, 443)
    except ValueError:
        return False


def normalize_label(value):
    return re.sub(r'[\s*＊:：]+', '', str(value or '')).strip()


TEXT_FIELDS = {
    'title': ('剧名', '剧集名称', '短剧名称', '作品名称'),
    'synopsis': ('简介', '剧集简介', '短剧简介', '剧情简介', '作品简介'),
    'producer': ('制作方名称', '制作方', '制作机构'),
    'episodeCount': ('总集数', '剧集集数'),
    'trialEpisodes': ('试看集数', '免费试看集数'),
    'totalCostYuan': ('制作成本（元）', '制作成本(元)', '制作成本（万元）', '制作成本(万元)'),
    'dramaType': ('剧目类型', '剧集类型', '短剧类型'),
}
FILE_FIELDS = {
    'cover': ('封面', '封面图', '剧集封面'),
    'videos': ('正片', '分集视频', '剧集视频', '上传正片'),
    'proofImages': ('工程证明', '工程证明图', '剪辑工程截图'),
    'storyboardImages': ('分镜证明图', '分镜截图', '分镜证明'),
    'costImages': ('成本比例报告', '成本报告图片', '成本配置比例报告'),
    'copyrightImages': ('授权证明', '版权证明'),
    'costReports': ('成本报告', '制作成本报告'),
}
LABELS = {'title': '剧名', 'synopsis': '简介', 'producer': '制作方', 'episodeCount': '总集数',
          'trialEpisodes': '试看集数', 'totalCostYuan': '制作成本', 'dramaType': '剧目类型',
          'cover': '封面', 'videos': '正片视频', 'proofImages': '工程证明图',
          'storyboardImages': '分镜截图', 'costImages': '成本报告图片',
          'copyrightImages': '版权证明', 'costReports': '成本报告'}

_DOM_FIELDS = """() => {
 const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
 const labelText = e => {const c=e.cloneNode(true); c.querySelectorAll('input,textarea,select,button,[contenteditable]').forEach(n=>n.remove()); return c.textContent.trim();};
 const label = e => (e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') || '').split(/\\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim() || Array.from(e.labels || []).map(labelText).join(' ').trim());
 return Array.from(document.querySelectorAll('input,textarea,select,[contenteditable="true"]')).map((e,index) => ({index,tag:e.tagName.toLowerCase(),type:(e.getAttribute('type') || 'text').toLowerCase(),label:label(e).slice(0,180),visible:visible(e),enabled:!e.disabled&&!e.readOnly,multiple:!!e.multiple,accept:(e.accept || '').slice(0,240),options:e.tagName==='SELECT'?Array.from(e.options).map(o=>({label:o.label,value:o.value,disabled:o.disabled})):[]}));
}"""


def _matching(rows, names, *, file=False):
    labels = {normalize_label(n) for n in names}
    return [r for r in rows if normalize_label(r.get('label')) in labels and r.get('enabled')
            and (r.get('type') == 'file' if file else r.get('visible') and r.get('type') not in ('file', 'password', 'hidden', 'checkbox', 'radio'))]


def classify_page(url, text, rows):
    """Conservative visible-DOM evidence, independent of cookies and URL routes."""
    blockers = []
    if not official_url(url):
        return 'unknown', ['当前页面不是可辅助填写的视频号官方页面'], False
    if re.search(r'请完成安全验证|安全验证|滑块验证|访问过于频繁|操作频繁', text):
        blockers.append('官方页面要求安全验证或限制访问，请本人在网页处理')
    if re.search(r'暂无权限|无权访问|尚未开通|未开通权限|需要机构认证', text):
        blockers.append('官方页面提示权限或认证要求，请本人核对账号资格')
    login = bool(re.search(r'微信扫码登录|扫码登录|请使用微信扫描二维码|登录视频号助手|请扫码|微信扫一扫', text))
    form = bool(_matching(rows, TEXT_FIELDS['title']) and _matching(rows, TEXT_FIELDS['synopsis']))
    drama_context = bool(re.search(r'创建剧集|新增剧集|创建短剧|新增短剧|短剧提审|剧集提审|剧集信息|短剧信息', text))
    # A login prompt always wins over an old/hidden form left by a SPA.
    if login:
        return 'login_required', blockers, False
    authenticated = ((form and drama_context) or
                     bool(re.search(r'退出登录', text) and re.search(r'视频号助手|剧集管理|机构管理|账号设置', text)) or
                     bool(re.search(r'视频号\s*ID', text, re.I) and re.search(r'昨日数据|最近视频', text)))
    return ('authenticated' if authenticated else 'unknown'), blockers, bool(form and drama_context)


def _safe_files(key, value):
    if key == 'cover':
        value = [value] if value else []
    if not isinstance(value, list) or len(value) > (1000 if key == 'videos' else 50):
        raise ValueError('附件清单无效或超过辅助填写数量上限')
    extensions = ({'.mp4', '.mov', '.mkv', '.m4v', '.webm', '.avi'} if key == 'videos' else
                  {'.pdf', '.docx', '.csv', '.png', '.jpg', '.jpeg', '.webp'} if key == 'costReports' else
                  {'.png', '.jpg', '.jpeg', '.webp'})
    paths = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('附件缺少本地文件路径')
        path = Path(item['path']).expanduser().resolve()
        if path.suffix.lower() not in extensions or not path.is_file() or path.stat().st_size <= 0:
            raise ValueError('附件格式无效、为空或已移动，请重新检测资料')
        if path.stat().st_size > (20 * 1024**3 if key == 'videos' else 100 * 1024**2):
            raise ValueError('附件大小超过辅助填写上限，请在官方页面手动选择')
        paths.append(str(path))
    return paths


def _accepts(accept, paths):
    if not accept:
        return True
    parts = {x.strip().lower() for x in accept.split(',') if x.strip()}
    import mimetypes
    return all(any(p == Path(path).suffix.lower() or p == (mimetypes.guess_type(path)[0] or '') or
                   p.endswith('/*') and (mimetypes.guess_type(path)[0] or '').startswith(p[:-1]) for p in parts) for path in paths)


class BrowserManager:
    def __init__(self, data, *, _driver_factory=None):
        self.data = Path(data).resolve()
        self._factory = _driver_factory
        self._queue = queue.Queue()
        self._contexts = {}
        self._driver = None
        self._closed = False
        self._guard = threading.Lock()
        self._thread = threading.Thread(target=self._run, name='official-publish-browser', daemon=True)
        self._thread.start()

    def command(self, account, action, payload=None):
        if action not in ('open', 'check', 'assist', 'close'):
            raise ValueError('不支持的发布浏览器操作')
        if not isinstance(account, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(account.get('id', ''))):
            raise ValueError('账号标识无效')
        payload = payload or {}
        if not isinstance(payload, dict) or payload.get('mode', 'drama') not in URLS:
            raise ValueError('发布模式无效')
        # No command accepts an arbitrary browser destination or script.
        if any(k in payload for k in ('url', 'script', 'selector', 'cookies', 'storageState')):
            raise ValueError('只能通过账号入口打开官方后台')
        import copy
        future = Future()
        with self._guard:
            if self._closed:
                raise RuntimeError('发布浏览器服务已关闭，请重启软件')
            self._queue.put((dict(account), action, copy.deepcopy(payload), future))
        try:
            return future.result(timeout=75)
        except FutureTimeout:
            future.cancel()
            raise RuntimeError('浏览器操作仍在等待，请先查看官方窗口并稍后刷新检测，避免重复操作') from None

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            account, action, payload, future = item
            # Shutdown and dispatch share the same decision lock.  An action
            # already running may finish, but queued work must not open another
            # account window or select new files after the app starts closing.
            with self._guard:
                stopping = self._closed
                started = future.set_running_or_notify_cancel()
            if not started:
                continue
            if stopping:
                future.set_exception(RuntimeError('发布浏览器服务正在关闭，尚未开始的操作已取消'))
                continue
            try:
                result = self._command(account, action, payload)
            except (ValueError, RuntimeError) as error:
                future.set_exception(error)
            except Exception:
                # Driver exceptions often contain local profile paths and URL queries.
                future.set_exception(RuntimeError('官方浏览器操作未完成。请检查窗口、登录和页面提示后刷新检测；必要时关闭该窗口并重新打开。'))
            else:
                future.set_result(result)
        for context in list(self._contexts.values()):
            try:
                context.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._driver is not None:
            try:
                self._driver.stop()
            except Exception:
                pass

    def _new_context(self, profile, mode):
        profile.mkdir(parents=True, exist_ok=True)
        if self._factory:
            return self._factory(profile, mode, URLS[mode])
        if self._driver is None:
            try:
                # Reuse the already bundled uploader dependency; no init scripts,
                # custom user-agent, fingerprint rewriting or session extraction.
                from patchright.sync_api import sync_playwright
                self._driver = sync_playwright().start()
            except (ImportError, OSError):
                raise RuntimeError('未找到发布浏览器组件，请在完整开发环境或更新后的软件中运行') from None
        candidates = [Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
                      Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
                      Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe']
        browser = next((p for p in candidates if p.is_file()), None)
        if browser is None:
            raise RuntimeError('未找到 Edge 或 Chrome，请先安装浏览器再打开官方后台')
        try:
            return self._driver.chromium.launch_persistent_context(str(profile), executable_path=str(browser),
                headless=False, no_viewport=True, accept_downloads=False, timeout=25000)
        except Exception:
            raise RuntimeError('无法打开独立账号窗口。请关闭此账号上次的发布窗口后重试；登录资料仍保留在本机。') from None

    def _page(self, key, *, create=False):
        context = self._contexts.get(key)
        if context is None:
            return None
        try:
            pages = [p for p in context.pages if not p.is_closed()]
            if pages:
                official = [p for p in pages if official_url(p.url)]
                return (official or pages)[-1]
            if create:
                return context.new_page()
        except Exception:
            pass
        self._contexts.pop(key, None)
        try:
            context.close()
        except Exception:
            pass
        return None

    def _command(self, account, action, payload):
        mode = payload.get('mode', 'drama')
        key = (account['id'], mode)
        if action == 'close':
            context = self._contexts.pop(key, None)
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            return {'browserOpen': False, 'loginState': 'unknown', 'mode': mode, 'closed': True}
        page = self._page(key, create=action == 'open')
        if action == 'open':
            if page is None:
                profile = self.data / 'publish-browser' / mode / account['id']
                context = self._new_context(profile, mode)
                self._contexts[key] = context
                page = self._page(key, create=True)
                try:
                    page.goto(URLS[mode], wait_until='domcontentloaded', timeout=25000)
                except Exception:
                    # A slow platform should leave the visible window open for the user.
                    pass
            try:
                page.bring_to_front()
            except Exception:
                pass
        if page is None:
            return {'browserOpen': False, 'mode': mode, 'loginState': 'unknown', 'pageUrl': '', 'heading': '',
                    'blockers': ['请先打开此账号的官方后台'], 'formFields': [], 'fileInputs': [],
                    'state': 'needs_navigation', 'filled': [], 'pending': []}
        state, rows = self._inspect(page, mode)
        if action == 'assist':
            return self._assist(page, state, rows, payload.get('plan'))
        return state

    def _inspect(self, page, mode):
        url = page.url
        text = ''
        rows = []
        if official_url(url):
            try:
                text = page.locator('body').inner_text(timeout=4000)[:60000]
                rows = page.evaluate(_DOM_FIELDS)
            except Exception:
                pass
        login, blockers, form = classify_page(url, text, rows)
        heading = ''
        try:
            # Only a short UI heading is retained, never account/body text or values.
            headings = page.locator('h1,h2,[role="heading"]')
            for index in range(min(headings.count(), 10)):
                if headings.nth(index).is_visible():
                    heading = headings.nth(index).inner_text(timeout=1000).strip()[:120]
                    break
        except Exception:
            pass
        public_rows = [{k: r[k] for k in ('tag', 'type', 'label', 'multiple', 'accept')}
                       for r in rows if r['label'] and (r['visible'] or r['type'] == 'file')]
        return {'browserOpen': True, 'mode': mode, 'loginState': login, 'pageUrl': safe_url(url), 'heading': heading,
                'blockers': blockers, 'formRecognized': form, 'formFields': [r for r in public_rows if r['type'] != 'file'],
                'fileInputs': [r for r in public_rows if r['type'] == 'file'], 'checkedAt': time.time(),
                'note': '检测来自当前可见网页；不代表已上传、提交或审核通过。'}, rows

    def _assist(self, page, state, rows, plan):
        filled, pending = [], []
        result = dict(state, filled=filled, pending=pending, submitted=False, uploadCompleted=False)
        if state['loginState'] == 'login_required':
            return dict(result, state='needs_login')
        if state['mode'] != 'drama' or state['loginState'] != 'authenticated' or not state['formRecognized'] or state['blockers']:
            return dict(result, state='needs_navigation', pending=[{'key': 'form', 'label': '提审表单',
                'message': '请本人在官方窗口进入新建剧集或短剧提审表单，再刷新检测。未识别的页面不会自动点击。'}])
        if not isinstance(plan, dict) or not plan.get('ready') or not isinstance(plan.get('fields'), dict) or not isinstance(plan.get('files'), dict):
            raise ValueError('请先完成该剧资料检测，补齐缺项后再辅助填写')
        fields = plan['fields']
        controls = page.locator('input,textarea,select,[contenteditable="true"]')
        titles = _matching(rows, TEXT_FIELDS['title'])
        if len(titles) == 1:
            current = controls.nth(titles[0]['index']).input_value(timeout=2000).strip()
            if current and current != str(fields.get('title', '')).strip():
                return dict(result, state='needs_navigation', pending=[{'key': 'title', 'label': '剧名',
                    'message': '网页已填写其他剧名。请先确认进入正确的新建表单，避免覆盖已有草稿。'}])
        for key, aliases in TEXT_FIELDS.items():
            matches = _matching(rows, aliases)
            if len(matches) != 1:
                pending.append({'key': key, 'label': LABELS[key], 'message': '未找到唯一、明确标注的可填写字段，请在网页手动核对。'})
                continue
            row = matches[0]
            locator = controls.nth(row['index'])
            try:
                fresh = locator.evaluate("""e => {const labelText=n=>{const c=n.cloneNode(true);c.querySelectorAll('input,textarea,select,button,[contenteditable]').forEach(x=>x.remove());return c.textContent.trim();};return {tag:e.tagName.toLowerCase(),type:(e.getAttribute('type')||'text').toLowerCase(),label:e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\\s+/).map(id=>document.getElementById(id)?.innerText||'').join(' ').trim()||Array.from(e.labels||[]).map(labelText).join(' ').trim()};}""")
                if normalize_label(fresh['label']) != normalize_label(row['label']) or fresh['tag'] != row['tag'] or fresh['type'] != row['type']:
                    raise ValueError('页面字段已变化')
                value = fields.get(key)
                if value is None or value == '':
                    raise ValueError('资料没有此字段值')
                if key == 'dramaType':
                    if row['tag'] != 'select':
                        raise ValueError('请手动选择剧目类型')
                    label = {'animation': '漫剧', 'digital': '数字真人'}.get(value)
                    options = [r for r in row['options'] if r['label'].strip() == label and not r['disabled']]
                    if len(options) != 1:
                        raise ValueError('网页剧目选项与本地配置不一致')
                    current = locator.input_value(timeout=1500)
                    if current and current != options[0]['value'] and current not in ('0', '请选择'):
                        raise ValueError('网页已有选择，保留原值供本人核对')
                    locator.select_option(value=options[0]['value'], timeout=2500)
                else:
                    if row['tag'] not in ('input', 'textarea') or row['type'] not in ('text', 'number'):
                        raise ValueError('当前字段类型需要手动填写')
                    if key == 'totalCostYuan' and '万' in row['label']:
                        value = float(value) / 10000
                    value = format(value, 'g') if isinstance(value, (float, int)) and not isinstance(value, bool) else str(value)
                    current = locator.input_value(timeout=1500).strip()
                    if current and current != value:
                        raise ValueError('网页已有内容，保留原值供本人核对')
                    if not current:
                        locator.fill(value, timeout=2500)
                filled.append({'key': key, 'label': LABELS[key], 'action': 'field_checked_or_filled'})
            except Exception:
                pending.append({'key': key, 'label': LABELS[key], 'message': '网页字段已有值、结构发生变化或填写未完成，请手动核对；已有内容予以保留。'})
        # Re-read indices after possible reactive form rerenders.
        for key, aliases in FILE_FIELDS.items():
            items = plan['files'].get(key, [] if key != 'cover' else None)
            if not items:
                continue
            # Upload widgets may add controls after the previous selection.
            rows = page.evaluate(_DOM_FIELDS)
            controls = page.locator('input,textarea,select,[contenteditable="true"]')
            matches = _matching(rows, aliases, file=True)
            if len(matches) != 1:
                pending.append({'key': key, 'label': LABELS[key], 'message': '未找到唯一标注此用途的上传控件，请在官方页面手动选文件。'})
                continue
            row = matches[0]
            try:
                paths = _safe_files(key, items)
                if len(paths) > 1 and not row['multiple']:
                    raise ValueError('控件只接受单个文件')
                if not _accepts(row['accept'], paths):
                    raise ValueError('网页接受的文件格式不匹配')
                locator = controls.nth(row['index'])
                fresh = page.evaluate(_DOM_FIELDS)
                if row['index'] >= len(fresh) or fresh[row['index']]['type'] != 'file' or normalize_label(fresh[row['index']]['label']) != normalize_label(row['label']):
                    raise ValueError('上传控件已变化')
                current = locator.evaluate('e => e.files ? e.files.length : 0')
                if current:
                    raise ValueError('已有文件，保留不覆盖')
                # set_input_files means selected locally, not server-side upload success.
                locator.set_input_files(paths, timeout=5000)
                filled.append({'key': key, 'label': LABELS[key], 'action': 'files_selected', 'count': len(paths)})
            except Exception:
                pending.append({'key': key, 'label': LABELS[key], 'message': '文件已选择、网页限制或附件变化导致未自动选择；请在网页核对，已有附件不覆盖。'})
        pending.extend([
            {'key': 'upload', 'label': '上传与转码', 'message': '选择文件不等于上传完成，请在官方页面等待上传和转码结果。'},
            {'key': 'rights', 'label': '声明与授权', 'message': '请本人核对并选择平台声明；软件不会代勾版权或承诺条款。'},
            {'key': 'submit', 'label': '最终提交', 'message': '请本人在官方页面核对后提交，再按实际回执记录状态。'}])
        return dict(result, state='awaiting_confirmation', checkedAt=time.time())

    def shutdown(self):
        with self._guard:
            if self._closed:
                return
            self._closed = True
            self._queue.put(None)
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=8)
