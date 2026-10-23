"""Protocol, authentication isolation and malformed-response regression tests."""
import copy,io,json,unittest,urllib.request
from unittest.mock import patch
import ai_providers as ai

def config():
    return {'textProvider':'ark','textProtocol':'chat','apiBase':'https://ark.cn-beijing.volces.com/api/v3',
        'textModel':'test-model','arkServiceTier':'default','textThinking':'disabled',
        'imageProvider':'ark','imageProtocol':'ark_images','imageApiBase':'https://ark.cn-beijing.volces.com/api/v3',
        'imageModel':'image-test-model','imageSize':'2K'}

class ProviderTests(unittest.TestCase):
    def setUp(self):
        ai._KEYS.clear();self.cfg=config();ai.set_key(self.cfg,'text','local-test-credential')
    def test_secret_bound_to_provider_endpoint_protocol(self):
        for field,value in [('textProvider','deepseek'),('apiBase','https://example.org/v1'),('textProtocol','responses')]:
            modified=self.cfg|{field:value}
            self.assertFalse(ai.get_key(modified,'text'))
        self.assertTrue(ai.get_key(self.cfg,'text'))
    def test_model_switch_retains_same_connection_key(self):
        self.assertTrue(ai.get_key(self.cfg|{'textModel':'other-model'},'text'))
    def test_image_credential_not_implicitly_shared(self):
        self.assertFalse(ai.get_key(self.cfg,'image'))
        ai.copy_text_key_to_image(self.cfg)
        self.assertTrue(ai.get_key(self.cfg,'image'))
        with self.assertRaises(ValueError):ai.copy_text_key_to_image(self.cfg|{'imageApiBase':'https://other.example/v1'})
    def test_secret_removal_and_redaction(self):
        self.assertEqual(ai.redact('contains local-test-credential'),'contains [已隐藏]')
        ai.set_key(self.cfg,'text','');self.assertFalse(ai.get_key(self.cfg,'text'))
    def test_url_validation(self):
        for bad in ['http://public.example/v1','https://user:password@example.org/v1','https://example.org?key=abc','https://example.org/#key','not-url']:
            with self.assertRaises(ValueError):ai.normalize_url(bad)
    def test_key_linebreak_rejected(self):
        with self.assertRaises(ValueError):ai.set_key(self.cfg,'text','abc\ndef')
    def test_provider_error_does_not_echo_server_body(self):
        error=ai.provider_error(404,json.dumps({'error':{'code':'ModelNotOpen','message':'local-test-credential account-id'}}))
        self.assertEqual(error.code,'ModelNotOpen');self.assertNotIn('local-test-credential',str(error));self.assertNotIn('account-id',str(error))
    def test_redirect_blocked(self):
        with self.assertRaises(ai.ProviderError):ai.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example')
    def test_chat_request(self):
        response={'choices':[{'message':{'content':'OK'}}],'model':'actual-model','service_tier':'default','usage':{'total_tokens':10}}
        with patch.object(ai,'request_json',return_value=response) as call:
            result=ai.text_generate(self.cfg,'system','user',64)
        args=call.call_args.args
        self.assertTrue(args[0].endswith('/chat/completions'));self.assertEqual(args[1]['thinking'],{'type':'disabled'})
        self.assertEqual(args[1]['service_tier'],'default');self.assertEqual(result['text'],'OK')
    def test_responses_protocol(self):
        cfg=self.cfg|{'textProtocol':'responses'};ai.set_key(cfg,'text','local-test-responses')
        response={'output':[{'type':'reasoning','summary':[]},{'type':'message','content':[{'type':'output_text','text':'answer'}]}]}
        with patch.object(ai,'request_json',return_value=response) as call:
            result=ai.text_generate(cfg,'system','user')
        self.assertTrue(call.call_args.args[0].endswith('/responses'));self.assertEqual(result['text'],'answer')
    def test_anthropic_protocol(self):
        cfg=self.cfg|{'textProvider':'anthropic','textProtocol':'anthropic','apiBase':'https://api.anthropic.com/v1'}
        ai.set_key(cfg,'text','local-test-anthropic')
        with patch.object(ai,'request_json',return_value={'content':[{'type':'thinking','thinking':'hidden'},{'type':'text','text':'answer'}]}) as call:
            result=ai.text_generate(cfg,'system','user')
        self.assertTrue(call.call_args.args[0].endswith('/messages'));self.assertEqual(result['text'],'answer')
    def test_gemini_protocol(self):
        cfg=self.cfg|{'textProvider':'gemini','textProtocol':'gemini','apiBase':'https://generativelanguage.googleapis.com/v1beta'}
        ai.set_key(cfg,'text','local-test-gemini')
        with patch.object(ai,'request_json',return_value={'candidates':[{'content':{'parts':[{'thought':True,'text':'hidden'},{'text':'answer'}]}}]}) as call:
            result=ai.text_generate(cfg,'system','user')
        self.assertIn(':generateContent',call.call_args.args[0]);self.assertEqual(result['text'],'answer')
    def test_unsupported_empty_output(self):
        for protocol in ai.TEXT_PROTOCOLS:
            with self.assertRaises(ai.ProviderError):ai.extract_text({},protocol)
    def test_auth_headers(self):
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        class Opener:
            def open(inner,request,**kwargs):
                self.captured=request
                return Response(b'{"ok":true}')
        for protocol,header in [('chat','Authorization'),('anthropic','X-api-key'),('gemini','X-goog-api-key')]:
            with patch.object(ai.urllib.request,'build_opener',return_value=Opener()):ai.request_json('https://example.org/v1',{},'local-header-key',protocol)
            self.assertIn(header,self.captured.headers)
            if protocol!='chat':self.assertNotIn('Authorization',self.captured.headers)
    def test_image_generations_and_edits(self):
        from PIL import Image
        image=Image.new('RGB',(16,16),'white');buf=io.BytesIO();image.save(buf,format='PNG')
        encoded=ai.base64.b64encode(buf.getvalue()).decode()
        for protocol in ['ark_images','openai_images','openai_edits']:
            cfg=self.cfg|{'imageProtocol':protocol,'imageSize':'1024x1536'};ai.set_key(cfg,'image','local-image-key')
            with patch.object(ai,'request_json',return_value={'data':[{'b64_json':encoded}]}) as call:
                output=ai.image_generate(cfg,'poster prompt',image)
            self.assertEqual(Image.open(io.BytesIO(output)).size,(16,16))
            if protocol=='openai_edits':self.assertIn('multipart/form-data',call.call_args.kwargs['content_type'])

if __name__=='__main__':unittest.main(verbosity=2)
