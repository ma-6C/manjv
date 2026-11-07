"""Restore original account IPC/startup, retaining an explicitly selected profile."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
from repair_xiaovmiao_network import read_asar,write_asar,integrity,digest

ROOT=Path(__file__).resolve().parents[1]
PROFILE_BOOT=r'''
(() => {
 const fs=require('node:fs'),path=require('node:path');
 const {app}=require('electron');
 const selected=process.env.MANJU_XIAOVMIAO_PROFILE;
 if(selected){
  const profile=path.resolve(selected);fs.mkdirSync(profile,{recursive:true});
  for(const folder of ['Desktop','Documents','Downloads','AppData/Roaming','AppData/Local'])fs.mkdirSync(path.join(profile,folder),{recursive:true});
  process.env.USERPROFILE=profile;process.env.HOME=profile;
  process.env.APPDATA=path.join(profile,'AppData/Roaming');process.env.LOCALAPPDATA=path.join(profile,'AppData/Local');
  app.setPath('userData',path.join(profile,'electron'));app.setPath('sessionData',path.join(profile,'electron'));
 }
 // Read-only startup observation for a fresh test profile; no account operations.
 const report=process.env.MANJU_XIAOVMIAO_FLOW_REPORT;
 if(report){
  let done=false;
  const finish=value=>{if(done)return;done=true;fs.writeFileSync(report,JSON.stringify(value,null,2));app.exit(value.ok?0:1);};
  const timer=setTimeout(()=>finish({ok:false,error:'Original account UI startup timed out'}),40000);
  app.on('browser-window-created',(_event,window)=>{
   window.webContents.once('did-finish-load',()=>{clearTimeout(timer);finish({ok:true,originalAccountFlow:true,windowCreated:true,mainDocumentLoaded:true,realAccountUsed:false});});
   window.webContents.once('render-process-gone',(_event,details)=>finish({ok:false,error:'Renderer exited',reason:details.reason}));
  });
 }
})();
'''


def prepare(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT/'tmp') or destination==source:
        raise ValueError('Prepare only in a separate workspace staging directory')
    archive=source/'resources/app.asar';source_exe=source/'小V猫.exe'
    tree,items=read_asar(archive)
    hashes={name:hashlib.sha256(data).hexdigest()for name,_,data in items}
    preload=next(data for name,_,data in items if name=='preload.js')
    if any(flag in preload for flag in (b'FAKE_USER',b'FAKE_TOKEN',b'handleLoginCall',b'local_free_token')):
        raise ValueError('Source overrides software authentication; use the untouched original')
    output=[];changed=[]
    for name,entry,data in items:
        if name=='main.js':data=PROFILE_BOOT.encode()+data
        if name=='assets/app.min.js':
            text=data.decode('utf-8');cleanup='n.getCall("Cleaner.cleanAllNotCache")'
            if text.count(cleanup)!=1:raise ValueError('Unexpected original cleanup hook')
            # Preserve old user data while restoring all account/login calls.
            data=text.replace(cleanup,'Promise.resolve()').encode('utf-8')
        if hashlib.sha256(data).hexdigest()!=hashes[name]:entry['integrity']=integrity(data);changed.append(name)
        output.append((name,entry,data))
    if not destination.exists():
        shutil.copytree(source,destination,ignore=lambda directory,names:[n for n in names if n.lower()in('uninst.exe','debug.log','小v猫.exe')])
    header_hash=write_asar(tree,output,destination/'resources/app.asar')
    executable=source_exe.read_bytes()
    pattern=rb'("file":"resources\\\\app.asar","alg":"SHA256","value":")[0-9a-f]{64}'
    executable,count=re.subn(pattern,lambda match:match[1]+header_hash,executable)
    if count!=1:raise ValueError('Unexpected original Electron integrity resource')
    (destination/'vcat_local_init.exe').write_bytes(executable)
    _,verified=read_asar(destination/'resources/app.asar')
    actual={name:hashlib.sha256(data).hexdigest()for name,_,data in verified}
    assert all(actual[name]==sha for name,sha in hashes.items()if name not in changed)
    report={'ok':True,'program':str(destination/'vcat_local_init.exe'),
        'originalPreloadUnchanged':actual['preload.js']==hashes['preload.js'],
        'compiledBackendUnchanged':actual['server/server.jsc']==hashes['server/server.jsc'],
        'originalAccountIpcRestored':True,'offlineInitializationRemoved':True,
        'fakeSoftwareLoginRemoved':True,'automaticUserDataCleanupSkipped':True,
        'userDataCopiedOrDeleted':False,'changedArchiveFiles':changed,
        'sourceProgramSha256':digest(source_exe),'sourceArchiveSha256':digest(archive)}
    (destination.parent/'preparation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('D:/小v猫'))
    parser.add_argument('--destination',type=Path,default=ROOT/'tmp/xiaovmiao-normal-account-flow/程序')
    options=parser.parse_args();print(json.dumps(prepare(options.source,options.destination),ensure_ascii=True))
