"""Independent accounts, deterministic routing and cloud-task deduplication."""
import copy,json,threading,unittest
from unittest.mock import patch
import ai_providers as ai
import api_connections as routes
from test_ai_providers import config

def entry(cid='one',channel='text',**kw):
    return dict(id=cid,name=cid,channel=channel,provider='ark',protocol={'text':'chat','image':'ark_images','subtitle':'subtitle_json'}[channel],base='https://example.org/api/v3',model='test-model',enabled=True)|kw

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
    def test_video_generation_connection_is_rejected(self):
        cfg=settings();cfg['aiConnections'].append(entry('removed')|{'channel':'video','protocol':'ark_video'})
        with self.assertRaises(ValueError):routes.validate(cfg)
        with self.assertRaises(ValueError):routes.candidates(settings(),'video')
    def test_saved_video_settings_migrate_without_changing_text_connections(self):
        cfg=settings();original=copy.deepcopy(cfg)
        cfg['aiConnections'].append(entry('removed')|{'channel':'video','protocol':'ark_video'})
        cfg['aiRouting']['video']={'primary':'removed','backups':[],'autoFallback':False};cfg['aiSelection']['video']='removed'
        routes.retire_video_config(cfg);routes.validate(cfg)
        self.assertEqual(cfg,original)

if __name__=='__main__':unittest.main(verbosity=2)
