"""Loopback session bootstrap and strict request boundaries."""
import secrets,hmac
from http.cookies import SimpleCookie
class Session:
    def __init__(self):self.launch=secrets.token_urlsafe(32);self.cookie=secrets.token_urlsafe(32)
    def authenticated(self,headers):
        try:
            c=SimpleCookie();c.load(headers.get('Cookie',''));v=c.get('manju_session')
            return bool(v and hmac.compare_digest(v.value,self.cookie))
        except Exception:return False
def check(handler):
    port=handler.server.server_address[1]
    host=handler.headers.get('Host','')
    if handler.client_address[0]!='127.0.0.1' or host not in [f'127.0.0.1:{port}',f'localhost:{port}']:raise PermissionError('仅允许本机应用访问')
    origin=handler.headers.get('Origin')
    if origin and origin!='http://'+host:raise PermissionError('拒绝跨站请求')
    if handler.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('拒绝跨站请求')
def headers(handler):
    handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('X-Frame-Options','DENY')
    handler.send_header('Referrer-Policy','no-referrer')
    handler.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
