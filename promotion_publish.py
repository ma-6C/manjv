"""Isolated visible-browser publisher and external MatrixMedia CLI adapter.

This implementation does not vendor GPL source. Platform selectors require live
account validation; a missing mount control never falls through to publishing.
"""
from pathlib import Path
import json
import re
import time

URLS={'douyin':'https://creator.douyin.com/creator-micro/content/upload',
      'weixin':'https://channels.weixin.qq.com/platform/post/create'}


def matrix_command(row):
    p=row['profile'];exe=Path(p['matrixPath'])
    if row['platform']!='weixin' or not exe.is_file() or exe.suffix.lower()!='.exe':
        raise ValueError('MatrixMedia 挂载仅用于视频号，请配置有效 EXE')
    args=[str(exe),'cli','publish','-p','sph','--phone',row['accountName'],
          '-f',row['clip']['path'],'-t',row['clip']['title'],
          '--description',row['clip'].get('description','')]
    args+=['--sph-drama-id' if p['kind']=='mini_drama' else '--sph-series-id',p['value']]
    if p['mode']=='draft':args.append('--draft')
    return args


def visible(locator):
    return [locator.nth(i) for i in range(min(locator.count(),80)) if locator.nth(i).is_visible()]


def one(locator, name):
    items=visible(locator)
    if len(items)!=1:raise ValueError('无法唯一定位'+name+'，请在官方页面核对权限或界面变化')
    return items[0]


def exact(page, labels):
    for label in labels:
        items=visible(page.get_by_text(label,exact=True))
        if len(items)==1:return items[0]
    raise ValueError('平台未显示可用入口：'+' / '.join(labels))


def wait_form(page, platform, seconds=150):
    """A visible editor on an official upload origin is required, not a cookie."""
    from urllib.parse import urlsplit
    host=urlsplit(URLS[platform]).hostname
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if page.is_closed():raise ValueError('发布窗口已关闭')
        if urlsplit(page.url).hostname==host:
            controls=page.locator('[contenteditable="true"], input[placeholder*="标题"], textarea[placeholder*="标题"]')
            login=visible(page.get_by_text(re.compile('扫码登录|请使用.*扫描二维码')))
            if not login and (visible(controls) or page.locator('input[type="file"][accept*="video"],input[type="file"][accept*=".mp4"]').count()):return
        page.wait_for_timeout(500)
    raise ValueError('未检测到已登录的发布表单，请在窗口中完成扫码或安全验证后重试')


def mount(page, request):
    profile=request['profile'];platform=request['platform'];value=profile['value']
    if platform=='weixin':
        exact(page,['添加链接']).click(timeout=10000)
        exact(page,['小程序短剧','短剧'] if profile['kind']=='mini_drama' else ['视频号剧集','剧集']).click(timeout=10000)
        search=page.get_by_placeholder('请输入短剧名称',exact=True) if profile['kind']=='mini_drama' else page.get_by_placeholder('搜索内容',exact=True)
        field=one(search,'短剧搜索框');field.fill(value);field.press('Enter')
        # Exact title selection avoids a different drama sharing a title prefix.
        candidate=page.locator('.drama-row').filter(has=page.get_by_text(value,exact=True))
        candidate.first.wait_for(state='attached',timeout=20000)
        one(candidate,'剧名候选行').click(timeout=10000)
        echo=page.locator('.post-component-choose-wrap .choose-content .name')
        one(echo,'已挂载的剧名').wait_for(state='visible',timeout=10000)
        if one(echo,'已挂载的剧名').inner_text().strip()!=value:
            raise ValueError('发布页回显剧名与目标不一致，已停止提交')
    else:
        exact(page,['添加小程序','小程序']).click(timeout=10000)
        field=one(page.locator('input[placeholder*="小程序链接"],textarea[placeholder*="小程序链接"],input[placeholder*="粘贴链接"]'),'小程序分享链接输入框')
        field.fill(value)
        exact(page,['确认添加','添加','确定']).click(timeout=10000)
        # The expected name must appear in a mounted mini-app component.
        echo=page.locator('[class*="anchor"],[class*="micro-app"],[class*="microApp"],[class*="mini-app"],[class*="miniApp"]').filter(has_text=profile['dramaTitle'])
        echo.first.wait_for(state='visible',timeout=20000)


def publish(page, request):
    platform=request['platform']
    uploads=page.locator('input[type="file"]')
    chosen=None
    for i in range(uploads.count()):
        item=uploads.nth(i);accept=(item.get_attribute('accept') or '').lower()
        if 'video' in accept or '.mp4' in accept:
            if chosen is not None:raise ValueError('平台存在多个视频上传框，请人工核对')
            chosen=item
    if chosen is None:raise ValueError('未找到平台视频上传框')
    chosen.set_input_files(request['file'],timeout=60000)
    title=page.locator('input[placeholder*="标题"],textarea[placeholder*="标题"]')
    editors=visible(page.locator('[contenteditable="true"]'))
    if visible(title):one(title,'视频标题').fill(request['title'][:30] if platform=='douyin' else request['title'])
    if len(editors)==1:
        editors[0].fill(request['title']+'\n'+request.get('description',''))
    elif not visible(title):raise ValueError('无法唯一识别作品标题编辑框')
    page.wait_for_timeout(1000)
    try:
        mount(page,request)
    except Exception as error:
        # No submit is allowed without visible mount evidence. Attempt a draft
        # only when the platform offers a unique enabled draft control.
        drafts=visible(page.get_by_role('button',name='保存草稿',exact=True))
        saved=False
        if len(drafts)==1 and drafts[0].is_enabled():
            try:drafts[0].click(timeout=10000);saved=True
            except Exception:pass
        return {'status':'needs_attention','mountStatus':'pending',
                'message':('已尝试保存草稿；' if saved else '未提交作品；')+'挂载未确认：'+str(error)[:500]}
    label=('保存草稿' if request['mode']=='draft' else ('发表' if platform=='weixin' else '发布'))
    button=one(page.get_by_role('button',name=label,exact=True),label)
    end=time.monotonic()+600
    while not button.is_enabled() and time.monotonic()<end:page.wait_for_timeout(500)
    if not button.is_enabled():raise ValueError('上传处理未完成或必填字段未通过，请核对平台提示')
    # Re-check immediately before the only submission click.
    if platform=='weixin':
        echo=one(page.locator('.post-component-choose-wrap .choose-content .name'),'挂载剧名')
        if echo.inner_text().strip()!=request['profile']['value']:raise ValueError('挂载在提交前发生变化')
    button.click(timeout=15000)
    try:
        page.wait_for_url('**/post/list**' if platform=='weixin' else '**/content/manage**',timeout=60000)
        page.get_by_text(request['title'][:30] if platform=='douyin' else request['title'],exact=False).first.wait_for(state='visible',timeout=15000)
    except Exception:
        return {'status':'needs_attention','mountStatus':'selected_unverified',
                'message':'已点击提交，但未能在作品列表确认结果；请先核对平台，勿重复上传。'}
    return {'status':'draft_saved' if request['mode']=='draft' else 'published_unverified',
            'mountStatus':'selected_unverified','message':'已在平台列表检测到作品；请打开作品点击入口，核对实际跳转。'}


def worker(account, request_path, result_path):
    from patchright.sync_api import sync_playwright
    request=json.loads(Path(request_path).read_text('utf-8'))
    platform=request['platform'];result={'status':'needs_attention','mountStatus':'pending','message':'发布未完成'}
    if platform not in URLS:raise ValueError('不支持此平台的桌面自动发布')
    account=Path(account);account.parent.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as driver:
        browser=driver.chromium.launch(channel='msedge',headless=False)
        context=browser.new_context(storage_state=str(account) if account.is_file() else None)
        page=context.new_page();page.set_default_timeout(15000)
        try:
            page.goto(URLS[platform],wait_until='domcontentloaded',timeout=60000)
            try:wait_form(page,platform)
            except ValueError as error:
                result={'status':'login_required','mountStatus':'pending','message':str(error)}
            else:
                context.storage_state(path=str(account))
                result=publish(page,request)
                context.storage_state(path=str(account))
        except Exception as error:
            result={'status':'needs_attention','mountStatus':'pending',
                    'message':'平台自动操作未完成，请检查后台后再处理：'+str(error)[:500]}
        finally:
            # Screenshots can include personal account data; do not persist them.
            Path(result_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
            context.close();browser.close()
