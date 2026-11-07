"""Exercise mount UI against local HTML, never a real platform or account."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
from patchright.sync_api import sync_playwright
import promotion_publish as publisher
checks=[]
with sync_playwright() as driver:
    browser=driver.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page();page.set_default_timeout(1000)
    try:
        base='''<button>添加链接</button><button>小程序短剧</button><button>视频号剧集</button>
        <input placeholder="请输入短剧名称"><input placeholder="搜索内容">
        <div class="drama-row" onclick="document.querySelector('.name').textContent='验收短剧'">验收短剧</div>
        <div style="display:none"><div class="drama-row">验收短剧</div></div>
        <div class="post-component-choose-wrap"><div class="choose-content"><div class="name"></div></div></div>'''
        for kind in ('mini_drama','native'):
            page.set_content(base)
            publisher.mount(page,{'platform':'weixin','profile':{'kind':kind,'value':'验收短剧'}})
            assert page.locator('.name').inner_text()=='验收短剧'
            checks.append(kind+'_exact_visible_row_ignores_hidden_clone')
        page.set_content('''<button>小程序</button><input placeholder="请输入小程序链接">
            <button onclick="document.querySelector('.mini-app').style.display='block'">确认添加</button>
            <div class="mini-app" style="display:none">验收小程序</div>''')
        publisher.mount(page,{'platform':'douyin','profile':{'value':'https://example.invalid/mini','dramaTitle':'验收小程序'}})
        assert page.get_by_placeholder('请输入小程序链接').input_value()=='https://example.invalid/mini'
        checks.append('douyin_link_requires_visible_expected_miniapp')
        page.set_content('''<button>小程序</button><button>小程序</button>''')
        try:publisher.exact(page,['小程序']);raise AssertionError('Ambiguous control accepted')
        except ValueError:pass
        checks.append('ambiguous_controls_stop_instead_of_first_match')
        # A failed mount must not invoke the final publish click.
        page.set_content('''<input type="file" accept="video/mp4"><input placeholder="视频标题">
            <button onclick="window.didPublish=true">发表</button><button>保存草稿</button>''')
        video=Path(json.loads(Path('tmp/promotion-studio-acceptance.json').read_text('utf-8'))['clip'])
        response=publisher.publish(page,{'platform':'weixin','file':str(video),'title':'本地测试','description':'',
            'mode':'publish','profile':{'kind':'mini_drama','value':'不存在'}})
        assert response['status']=='needs_attention' and not page.evaluate('Boolean(window.didPublish)')
        checks.append('missing_mount_never_clicks_publish')
        report={'ok':True,'checks':checks,'remotePublishing':False,'browser':'local HTML fixtures in Edge headless'}
        Path('tmp/promotion-publish-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('PROMOTION_PUBLISH_BROWSER_OK',len(checks))
    finally:browser.close()
