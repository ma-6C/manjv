"""Model discovery must work before save, without leaking or moving credentials."""
import copy
import unittest
from unittest.mock import patch

import ai_providers as ai
from test_ai_providers import config


class ModelDiscoveryTests(unittest.TestCase):
    def setUp(self):
        ai._KEYS.clear()
        self.cfg=config()|{'textProvider':'custom','apiBase':'https://gateway.example','textModel':''}

    def test_bare_origin_and_blank_model_normalise_without_config_write(self):
        original=copy.deepcopy(self.cfg)
        with patch.object(ai,'request_json',return_value={'data':[{'id':'text-one'},{'id':'text-two'}]}) as call:
            result=ai.discover_models(self.cfg,key='fixture-discovery-key')
        self.assertEqual(call.call_args.args[0],'https://gateway.example/v1/models')
        self.assertEqual(result['base'],'https://gateway.example/v1')
        self.assertEqual(result['count'],2)
        self.assertEqual(self.cfg,original)
        self.assertNotIn('fixture-discovery-key',str(result))
        self.assertFalse(ai.get_key(self.cfg|{'apiBase':result['base']},'text'))

    def test_existing_session_key_survives_url_normalisation(self):
        ai.set_key(self.cfg,'text','fixture-existing-key')
        with patch.object(ai,'request_json',return_value={'data':[]}):
            result=ai.discover_models(self.cfg)
        self.assertEqual(ai.get_key(self.cfg|{'apiBase':result['base']},'text'),'fixture-existing-key')

    def test_official_origin_uses_its_own_api_prefix(self):
        for preset in [p for p in ai.PRESETS if p['id'] in ['ark','dashscope','openrouter','gemini']]:
            origin='https://'+ai.urllib.parse.urlsplit(preset['base']).netloc
            with self.subTest(provider=preset['id']),patch.object(ai,'request_json',return_value={'data':[]}) as call:
                result=ai.discover_models(self.cfg,draft={'provider':preset['id'],'protocol':preset['protocol'],'base':origin},key='fixture-key')
            self.assertEqual(result['base'],preset['base'])
            self.assertEqual(call.call_args.args[0],preset['base']+'/models')

    def test_explicit_gateway_path_preserved_and_no_500_model_cutoff(self):
        rows=[{'id':'model-'+str(i)} for i in range(650)]+[{'id':'model-1'},None,{'id':''}]
        with patch.object(ai,'request_json',return_value={'data':rows}) as call:
            result=ai.discover_models(self.cfg,draft={'base':'https://gateway.example/proxy/v1/'},key='fixture-key')
        self.assertEqual(call.call_args.args[0],'https://gateway.example/proxy/v1/models')
        self.assertEqual(result['count'],650)

    def test_root_fallback_only_for_missing_route_or_invalid_list(self):
        for error in [ai.ProviderError('not found','HTTPError',404),ai.ProviderError('html','InvalidResponse')]:
            with self.subTest(error=error.code),patch.object(ai,'request_json',side_effect=[error,{'data':[{'id':'root-model'}]}]) as call:
                result=ai.discover_models(self.cfg,key='fixture-key')
            self.assertEqual(result['base'],'https://gateway.example')
            self.assertEqual(call.call_count,2)

    def test_auth_quota_and_network_failures_never_retry_another_route(self):
        for status,code in [(401,'new_api_error'),(403,'Forbidden'),(429,'RateLimit'),(None,'NetworkError')]:
            with self.subTest(status=status),patch.object(ai,'request_json',side_effect=ai.ProviderError('failure',code,status)) as call:
                with self.assertRaises(ai.ProviderError):ai.discover_models(self.cfg,key='fixture-key')
            self.assertEqual(call.call_count,1)
            self.assertFalse(ai.get_key(self.cfg|{'apiBase':self.cfg['apiBase']+'/v1'},'text'))

    def test_no_secret_reuse_for_changed_draft_identity(self):
        ai.set_key(self.cfg,'text','fixture-private-key')
        for draft in [{'base':'https://other.example/v1'},{'provider':'openai'},{'protocol':'responses'}]:
            with self.subTest(draft=draft),patch.object(ai,'request_json') as call:
                with self.assertRaises(ai.ProviderError) as raised:ai.discover_models(self.cfg,draft=draft)
            self.assertEqual(raised.exception.code,'MissingKey')
            call.assert_not_called()

    def test_named_connection_key_stays_bound_to_its_id(self):
        c=dict(id='named',channel='text',provider='custom',protocol='chat',base='https://gateway.example',model='')
        cfg=self.cfg|{'_aiConnection':c}
        ai.set_key(cfg,'text','fixture-named-key')
        with patch.object(ai,'request_json',return_value={'data':[]}):ai.discover_models(cfg)
        resolved=c|{'base':c['base']+'/v1'}
        self.assertEqual(ai.get_key(cfg|{'_aiConnection':resolved},'text'),'fixture-named-key')
        self.assertFalse(ai.get_key(self.cfg|{'apiBase':resolved['base']},'text'))
        self.assertFalse(ai.get_key(cfg|{'_aiConnection':resolved|{'id':'other'}},'text'))

    def test_draft_query_cannot_replace_newer_saved_key(self):
        resolved=self.cfg|{'apiBase':self.cfg['apiBase']+'/v1'}
        ai.set_key(resolved,'text','fixture-newer-key')
        with patch.object(ai,'request_json',return_value={'data':[]}):
            ai.discover_models(self.cfg,key='fixture-older-query-key')
        self.assertEqual(ai.get_key(resolved,'text'),'fixture-newer-key')

    def test_unsupported_schema_does_not_report_empty_success(self):
        for data in [{},{'data':{}},{'models':'not a list'}]:
            with self.subTest(data=data),patch.object(ai,'request_json',return_value=data):
                with self.assertRaises(ai.ProviderError):ai.discover_models(self.cfg,key='fixture-key')

    def test_empty_list_is_valid(self):
        with patch.object(ai,'request_json',return_value={'data':[]}):
            self.assertEqual(ai.discover_models(self.cfg,key='fixture-key')['models'],[])

    def test_native_gemini_and_anthropic_pagination(self):
        for protocol,pages,next_query in [
            ('gemini',[{'models':[{'name':'models/one'}],'nextPageToken':'next page'},{'models':[{'name':'models/two'}]}],'pageToken=next+page'),
            ('anthropic',[{'data':[{'id':'one'}],'has_more':True,'last_id':'one'},{'data':[{'id':'two'}],'has_more':False}],'after_id=one'),
        ]:
            with self.subTest(protocol=protocol),patch.object(ai,'request_json',side_effect=pages) as call:
                result=ai.discover_models(self.cfg,draft={'protocol':protocol},key='fixture-key')
            self.assertEqual(result['models'],['one','two'])
            self.assertIn(next_query,call.call_args.args[0])
            self.assertEqual(call.call_args.args[3],protocol)

    def test_image_credentials_and_protocol_are_independent(self):
        with patch.object(ai,'request_json',return_value={'data':[{'id':'image-one'}]}) as call:
            result=ai.discover_models(self.cfg,'image',{'provider':'custom','protocol':'openai_images','base':'https://images.example'},'fixture-image-key')
        self.assertEqual(call.call_args.args[3],'openai_images')
        self.assertEqual(result['base'],'https://images.example/v1')
        self.assertFalse(ai.get_key(self.cfg,'text'))

    def test_subtitle_draft_discovers_models_without_changing_task_base(self):
        with patch.object(ai,'request_json',return_value={'data':[{'id':'erase-one'}]}) as call:
            result=ai.discover_models(self.cfg,'subtitle',{'provider':'custom','protocol':'subtitle_json','base':'https://subtitle.example'},'fixture-subtitle-key')
        self.assertEqual(call.call_args.args[0],'https://subtitle.example/v1/models')
        self.assertEqual(call.call_args.args[3],'subtitle_json')
        self.assertEqual(result['base'],'https://subtitle.example')
        self.assertEqual(result['modelsBase'],'https://subtitle.example/v1')
        self.assertIn('不代表',result['note'])
        self.assertFalse(ai._KEYS)

    def test_subtitle_named_session_key_stays_at_task_base(self):
        c=dict(id='subtitle-account',channel='subtitle',provider='custom',protocol='subtitle_json',base='https://subtitle.example',model='erase-one')
        cfg=self.cfg|{'_aiConnection':c};ai.set_key(cfg,'subtitle','fixture-subtitle-session')
        with patch.object(ai,'request_json',return_value={'data':[{'id':'erase-one'}]}):
            self.assertEqual(ai.list_models(cfg,'subtitle'),['erase-one'])
        self.assertEqual(ai.get_key(cfg,'subtitle'),'fixture-subtitle-session')
        self.assertFalse(ai.get_key(cfg|{'_aiConnection':c|{'base':c['base']+'/v1'}},'subtitle'))

    def test_subtitle_rejects_text_protocol_and_missing_key(self):
        for protocol in ['chat','subtitle_json']:
            with self.subTest(protocol=protocol),patch.object(ai,'request_json') as call:
                with self.assertRaises(ValueError):
                    ai.discover_models(self.cfg,'subtitle',{'protocol':protocol,'base':'https://subtitle.example'})
            call.assert_not_called()

    def test_invalid_drafts_and_keys_rejected_before_network(self):
        for draft,key in [({'base':'http://gateway.example'},'fixture-key'),({'protocol':'subtitle_json'},'fixture-key'),({'id':'other'},'fixture-key'),({},'line\nbreak')]:
            with self.subTest(draft=draft),patch.object(ai,'request_json') as call:
                with self.assertRaises(ValueError):ai.discover_models(self.cfg,draft=draft,key=key)
            call.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
