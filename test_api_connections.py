"""Independent accounts, deterministic routing and cloud-task deduplication."""
import copy,json,threading,unittest
from unittest.mock import patch
import ai_providers as ai
import api_connections as routes
import video_api
from test_ai_providers import config

def entry(cid='one',channel='text',**kw):
    return dict(id=cid,name=cid,channel=channel,provider='ark',protocol={'text':'chat','image':'ark_images','video':'ark_video','subtitle':'subtitle_json'}[channel],base='https://example.org/api/v3',model='test-model',enabled=True)|kw

def settings(channel='text'):
    cfg=config()|{'aiConnections':[entry('one',channel),entry('two',channel)],'aiRouting':{channel:{'primary':'one','backups':['two'],'autoFallback':True}},'aiSelection':{channel:'auto'}}
    routes.validate(cfg)
    for c in cfg['aiConnections']:ai.set_key(routes.bound(cfg,c),channel,'test-key-'+c['id'])
    return cfg

class ConnectionTests(unittest.TestCase):
    def setUp(self):ai._KEYS.clear()
    def test_separate_accounts_same_endpoint(self):
        cfg=settings();a,b=cfg['aiConnections'];self.assertEqual(ai.get_key(routes.bound(cfg,a),'text'),'test-key-one');self.assertEqual(ai.get_key(routes.bound(cfg,b),'text'),'test-key-two')
        self.assertNotEqual(ai.identity(a),ai.identity(b));self.assertNotIn('test-key',json.dumps(cfg))
    def test_edit_endpoint_cannot_leak_key(self):
        cfg=settings();c=cfg['aiConnections'][0]|{'base':'https://other.example/api'}
        self.assertFalse(ai.get_key(routes.bound(cfg,c),'text'))
    def test_fallback_on_rate_limit_and_trace(self):
        cfg=settings();events=[];cfg['_aiTrace']=events.append
        def request(*args,**kw):
            if args[2]=='test-key-one':raise ai.ProviderError('limited','RateLimit',429)
            return {'choices':[{'message':{'content':'backup'}}]}
        with patch.object(ai,'request_json',side_effect=request) as request_mock:result=ai.text_generate(cfg,'system','user')
        self.assertEqual(result['text'],'backup');self.assertEqual(request_mock.call_count,2);self.assertTrue(any(e['event']=='fallback' for e in events))
    def test_fixed_selection_ignores_backup(self):
        cfg=settings();cfg['aiSelection']['text']='one'
        with patch.object(ai,'request_json',side_effect=ai.ProviderError('limited','RateLimit',429)) as call:
            with self.assertRaises(ai.ProviderError):ai.text_generate(cfg,'s','u')
        self.assertEqual(call.call_count,1)
    def test_content_filter_no_fallback(self):
        cfg=settings()
        with patch.object(ai,'request_json',side_effect=ai.ProviderError('filtered','ContentFilter',400)) as call:
            with self.assertRaises(ai.ProviderError):ai.text_generate(cfg,'s','u')
        self.assertEqual(call.call_count,1)
    def test_missing_primary_key_uses_backup(self):
        cfg=settings();ai.set_key(routes.bound(cfg,cfg['aiConnections'][0]),'text','')
        self.assertEqual(routes.routed(cfg,'text',lambda selected:selected['_aiConnection']['id']),'two')
    def test_disabled_connection_and_channel_mismatch(self):
        cfg=settings();cfg['aiConnections'][0]['enabled']=False;self.assertEqual(routes.candidates(cfg,'text')[0]['id'],'two')
        cfg['aiSelection']['image']='two'
        with self.assertRaises(ValueError):routes.validate(cfg)
    def test_plaintext_secret_and_invalid_routes_rejected(self):
        cfg=settings();cfg['aiConnections'][0]['apiKey']='not-allowed'
        with self.assertRaises(ValueError):routes.validate(cfg)
        cfg=settings();cfg['aiRouting']['text']['backups']=['one']
        with self.assertRaises(ValueError):routes.validate(cfg)
    def test_image_route_uses_independent_key(self):
        cfg=settings('image');from PIL import Image
        with patch.object(ai,'request_json',return_value={'data':[{'b64_json':'aW1hZ2U='}]}) as call:result=ai.image_generate(cfg,'poster',Image.new('RGB',(8,8)))
        self.assertEqual(result,b'image');self.assertEqual(call.call_args.args[2],'test-key-one')
    def test_cloud_task_resume_does_not_submit(self):
        cfg=settings('video');c=cfg['aiConnections'][0];remote={'connection':c,'taskId':'known-task','status':'running'};record=[]
        with patch.object(video_api,'submit') as submit,patch.object(video_api,'poll',return_value=('succeeded','https://cdn.example/result.mp4')):
            result=video_api.generate(cfg,{'mode':'text'},remote,record.append,threading.Event(),lambda *a:None)
        submit.assert_not_called();self.assertEqual(result[1]['id'],'one')
    def test_video_timeout_blocks_fallback_and_resubmit(self):
        cfg=settings('video');journal=[];spec={'mode':'text'}
        with patch.object(video_api,'submit',side_effect=ai.ProviderError('timeout','NetworkError')) as call:
            with self.assertRaises(ai.ProviderError) as error:video_api.generate(cfg,spec,None,journal.append,threading.Event(),lambda *a:None)
        self.assertEqual(error.exception.code,'SubmissionUnknown');self.assertEqual(call.call_count,1);self.assertEqual(journal[-1]['status'],'submission_unknown')
        with patch.object(video_api,'submit') as call:
            with self.assertRaises(ai.ProviderError):video_api.generate(cfg,spec,journal[-1],journal.append,threading.Event(),lambda *a:None)
        call.assert_not_called()
    def test_video_explicit_rejection_can_fallback(self):
        cfg=settings('video');journal=[]
        def submit(cfg,c,spec):
            if c['id']=='one':raise ai.ProviderError('limited','RateLimit',429)
            return 'task-two'
        with patch.object(video_api,'submit',side_effect=submit),patch.object(video_api,'poll',return_value=('succeeded','https://cdn.example/result.mp4')):
            result=video_api.generate(cfg,{'mode':'text'},None,journal.append,threading.Event(),lambda *a:None)
        self.assertEqual(result[1]['id'],'two');self.assertEqual(journal[-1]['taskId'],'task-two')
    def test_video_adapters_payload_and_headers(self):
        cfg=settings('video');spec=video_api.validate_spec({'name':'demo','prompt':'A cat','mode':'image','reference':'https://example.org/image.jpg'})
        for protocol in ['ark_video','dashscope_video','json_video']:
            c=cfg['aiConnections'][0]|{'protocol':protocol};ai.set_key(routes.bound(cfg,c),'video','test-video-key')
            with patch.object(ai,'request_json',return_value={'id':'task','output':{'task_id':'task'}}) as call:self.assertEqual(video_api.submit(cfg,c,spec),'task')
            payload=call.call_args.args[1]
            if protocol=='ark_video':self.assertEqual(payload['content'][1]['image_url']['url'],spec['reference'])
            if protocol=='dashscope_video':self.assertEqual(payload['input']['media'][0]['type'],'first_frame');self.assertEqual(call.call_args.kwargs['extra_headers'],{'X-DashScope-Async':'enable'})
    def test_bad_video_parameters_rejected(self):
        for body in [{'prompt':''},{'prompt':'cat','duration':0},{'prompt':'cat','mode':'image','reference':'http://bad/image.jpg'}]:
            with self.assertRaises(ValueError):video_api.validate_spec(body)

if __name__=='__main__':unittest.main(verbosity=2)
