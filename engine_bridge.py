"""Adapter for the pinned MIT Tencent uploader. No publishing on import."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','login','upload'])
    parser.add_argument('--engine',required=True)
    parser.add_argument('--account',required=True)
    parser.add_argument('--request')
    args=parser.parse_args()
    root=Path(args.engine).resolve()
    if not (root/'uploader/tencent_uploader/main.py').is_file():
        raise RuntimeError('未找到 social-auto-upload 腾讯上传模块')
    sys.path.insert(0,str(root))
    # 本项目依赖位于vendor，不改动独立引擎的Python环境。
    sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
    from uploader.tencent_uploader.main import TencentVideo,tencent_setup,cookie_auth
    async def run():
        if args.action=='check':
            ok=await cookie_auth(args.account) if Path(args.account).is_file() else False
            print(json.dumps({'valid':ok}),flush=True)
            return
        if args.action=='login':
            result=await tencent_setup(args.account,handle=True,return_detail=True,headless=False)
            if not result.get('success'):raise RuntimeError('登录未完成，请重新扫码')
            print(json.dumps({'valid':True}),flush=True)
            return
        if not args.request:raise ValueError('上传任务缺少请求文件')
        request=json.loads(Path(args.request).read_text('utf-8'))
        from datetime import datetime
        date=datetime.fromisoformat(request['schedule']) if request.get('schedule') else 0
        class StudioTencentVideo(TencentVideo):
            async def apply_original_statement(self,page):
                # 上游默认选择AI标注；本应用只在用户明确启用时设置。
                if request.get('aiContent'):
                    self.content_label='含AI生成内容'
                    await super().apply_original_statement(page)

            async def submit_publish(self,page):
                # 使用正常可见按钮，不删除页面遮罩，不强制点击，也不因按钮消失就判成功。
                label='保存草稿' if self.is_draft else '发表'
                button=page.get_by_role('button',name=label,exact=True).first
                await button.wait_for(state='visible',timeout=60000)
                if await button.is_disabled():raise RuntimeError('平台提交按钮不可用，请检查必填项或提示')
                await button.click(timeout=15000)
                try:
                    await page.wait_for_url('**/post/list**',timeout=45000)
                    await page.get_by_text(request['title'],exact=False).first.wait_for(state='visible',timeout=20000)
                except Exception:
                    await page.screenshot(path=str(Path(args.request).with_suffix('.result.png')),full_page=True)
                    raise RuntimeError('已点击提交，但未能在作品列表确认结果。请先到官方后台核对，避免重复上传。')

        uploader=StudioTencentVideo(title=request['title'],file_path=request['file'],tags=[],publish_date=date,
            account_file=args.account,is_draft=request.get('mode','draft')=='draft',desc=request.get('description',''),
            headless=False,debug=False,publish_strategy='scheduled' if date else 'immediate')
        await uploader.tencent_upload_video()
        print(json.dumps({'completed':True,'mode':request.get('mode','draft')}),flush=True)
    asyncio.run(run())

if __name__=='__main__':main()
