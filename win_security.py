"""Windows DPAPI and ECDSA-P256 verification, using system cryptographic providers."""
from __future__ import annotations
import ctypes,hashlib
from ctypes import wintypes as w

class Blob(ctypes.Structure):
    _fields_=[('size',w.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def _blob(data):
    memory=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    return Blob(len(data),memory),memory

def protect(data,entropy=b'ManjuStudio.License.v1',decrypt=False):
    incoming,hold=_blob(data);extra,extra_hold=_blob(entropy);out=Blob()
    lib=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=lib.CryptUnprotectData if decrypt else lib.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),w.LPVOID,ctypes.POINTER(Blob),w.LPVOID,w.LPVOID,w.DWORD,ctypes.POINTER(Blob)];fn.restype=w.BOOL
    if not fn(ctypes.byref(incoming),None,ctypes.byref(extra),None,None,1,ctypes.byref(out)):raise OSError('Windows无法解密当前用户的授权信息' if decrypt else 'Windows无法保护授权信息')
    try:return ctypes.string_at(out.data,out.size)
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree;free.argtypes=[w.HLOCAL];free.restype=w.HLOCAL;free(out.data)

def verify(public_blob,message,signature):
    if len(signature)!=64 or len(public_blob)!=72:return False
    api=ctypes.WinDLL('bcrypt');provider=w.HANDLE();key=w.HANDLE()
    api.BCryptOpenAlgorithmProvider.argtypes=[ctypes.POINTER(w.HANDLE),w.LPCWSTR,w.LPCWSTR,w.ULONG];api.BCryptOpenAlgorithmProvider.restype=w.LONG
    api.BCryptImportKeyPair.argtypes=[w.HANDLE,w.HANDLE,w.LPCWSTR,ctypes.POINTER(w.HANDLE),w.LPVOID,w.ULONG,w.ULONG];api.BCryptImportKeyPair.restype=w.LONG
    api.BCryptVerifySignature.argtypes=[w.HANDLE,w.LPVOID,w.LPVOID,w.ULONG,w.LPVOID,w.ULONG,w.ULONG];api.BCryptVerifySignature.restype=w.LONG
    api.BCryptDestroyKey.argtypes=[w.HANDLE];api.BCryptCloseAlgorithmProvider.argtypes=[w.HANDLE,w.ULONG]
    if api.BCryptOpenAlgorithmProvider(ctypes.byref(provider),'ECDSA_P256',None,0)!=0:return False
    try:
        if api.BCryptImportKeyPair(provider,None,'ECCPUBLICBLOB',ctypes.byref(key),public_blob,len(public_blob),0)!=0:return False
        digest=hashlib.sha256(message).digest()
        return api.BCryptVerifySignature(key,None,digest,len(digest),signature,len(signature),0)==0
    finally:
        if key:api.BCryptDestroyKey(key)
        api.BCryptCloseAlgorithmProvider(provider,0)

def machine_code():
    import winreg,os
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Cryptography',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
        guid=str(winreg.QueryValueEx(key,'MachineGuid')[0]).strip().lower()
    serial=w.DWORD();system=os.environ.get('SystemDrive','C:')+'\\'
    fn=ctypes.WinDLL('kernel32',use_last_error=True).GetVolumeInformationW
    fn.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.POINTER(w.DWORD),ctypes.POINTER(w.DWORD),w.LPWSTR,w.DWORD];fn.restype=w.BOOL
    if not fn(system,None,0,ctypes.byref(serial),None,None,None,0):raise OSError('无法读取系统盘标识')
    return 'MJ-'+hashlib.sha256(('ManjuStudio/device/v1|'+guid+'|'+format(serial.value,'08x')).encode()).hexdigest()[:32].upper()
