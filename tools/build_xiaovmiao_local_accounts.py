"""Adapt only local platform-account detection/persistence in a staging copy."""
from pathlib import Path
import json
import re
import shutil
import hashlib
import argparse
from repair_xiaovmiao_network import read_asar,write_asar,integrity,digest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'modules/xiaovmiao/程序'
DEST=ROOT/'tmp/xiaovmiao-local-accounts-stage/程序'


def build(destination=DEST,include_acceptance=True,baseline=None):
    destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT/'tmp'):raise ValueError('Stage must stay inside workspace tmp')
    baseline=Path(baseline).resolve()if baseline else SOURCE
    if baseline!=SOURCE and not baseline.is_relative_to(ROOT/'tmp'):raise ValueError('Baseline must stay inside workspace tmp')
    tree,items=read_asar(baseline/'resources/app.asar')
    original={name:hashlib.sha256(data).hexdigest()for name,_,data in items}
    if 'manju_local_accounts.js'in original:raise ValueError('Source already contains local-account adapter; use the saved baseline')
    output=[]
    boot="""
 const localAccounts=require('./manju_local_accounts').install({app,session:require('electron').session,webContents:require('electron').webContents,fs,path,log,ready:()=>localReady.then(()=>localRuntime)});
 if(process.env.MANJU_XIAOVMIAO_LOCAL_ACCOUNT_TEST==='1'){
  const timer=setTimeout(()=>{fs.writeFileSync(process.env.MANJU_XIAOVMIAO_ACCOUNT_REPORT,JSON.stringify({ok:false,error:'Local account acceptance timed out'}));app.exit(1);},35000);
  localReady.then(()=>require('./manju_account_acceptance').run({runtime:localRuntime,bridge:localAccounts,app,fs,path,output:process.env.MANJU_XIAOVMIAO_ACCOUNT_REPORT})).catch(error=>{clearTimeout(timer);fs.writeFileSync(process.env.MANJU_XIAOVMIAO_ACCOUNT_REPORT,JSON.stringify({ok:false,error:error.message}));app.exit(1);});
 }
"""
    if not include_acceptance:
        boot=boot[:boot.index(" if(process.env.MANJU_XIAOVMIAO_LOCAL_ACCOUNT_TEST")]
    for name,entry,data in items:
        if name=='main.js':
            text=data.decode('utf-8');anchor=' localReady.catch('
            if text.count(anchor)!=1:raise ValueError('Unexpected local bootstrap')
            text=text.replace(anchor,boot+anchor)
            assert text.count('platformNetwork.canRequest(session,details.url)')==1
            text=text.replace('platformNetwork.canRequest(session,details.url)','platformNetwork.canRequest(session,details.url,details)')
            assert text.count('net.request=denied;')==1
            text=text.replace('net.request=denied;',"const originalElectronRequest=net.request.bind(net);net.request=(input,...options)=>{if(require('./manju_local_accounts').allowsProfileRequest(input))return originalElectronRequest(input,...options);return denied();};")
            old="if(method==='LocalStartup.initialize')value=await localReady;"
            assert text.count(old)==1
            text=text.replace(old,"if(method==='LocalStartup.initialize')value=await localAccounts.call('LocalAccounts.load',[]);\n   else if(method==='AccountManager.getAllAccounts')value=await localAccounts.call('LocalAccounts.list',[]);\n   else if(method.startsWith('LocalAccounts.'))value=await localAccounts.call(method,args.slice(1));")
            pattern=r"else if\(method==='LocalStartup.loadLocalAccounts'\)\{.*?value=\{localAccountCount:count\};\s*\}"
            text,count=re.subn(pattern,"else if(method==='LocalStartup.loadLocalAccounts'){value=await localAccounts.call('LocalAccounts.load',[]);}",text,flags=re.S)
            assert count==1
            old='}else value=await handler.call(this,event,...args);'
            assert text.count(old)==1
            text=text.replace(old,"}else {value=await handler.call(this,event,...args);if(method==='AccountManager.listenSession')localAccounts.listen(args[1],event.sender);if(method==='AccountManager.removeSessionListen')localAccounts.stop(args[1]);}")
            old="}catch(e){log({event:'call-error',id,method,message:String(e.message).slice(0,300)});throw e;}"
            assert text.count(old)==1
            text=text.replace(old,old.replace('throw e;',"throw require('./manju_local_accounts').explainFeatureError(e,method,String(localRuntime?.LoginAccount?.userInfo?.user_id||0)!=='0');"))
            data=text.encode('utf-8')
        if name=='assets/app.min.js':
            text=data.decode('utf-8')
            for old,new in [('"LoginAccount.getUidAccount",t.uid,t.platform','"LocalAccounts.find",t.uid,t.platform'),('"AccountManager.addAccount",t,','"LocalAccounts.add",t,')]:
                assert text.count(old)==1,old;text=text.replace(old,new)
            for old,new in [('"LocalProxy.getProxyList"','"LocalAccounts.proxies"'),('"LoginAccount.getSubUserList"','"LocalAccounts.owners"')]:
                text=text.replace(old,new)
            # Each failed request must stop its own loading indicator. Leave the
            # original backend permission check and rejection intact.
            for method,tail in [('CommentManager.getCommentPostList','function eq()'),('CommentManager.loadPostComment','function eq()')]:
                start=text.index('n.getCall("'+method+'"')
                end=text.index(tail,start)
                segment=text[start:end]
                old='wZ.error(e.message),H(!1)'if method.endswith('getCommentPostList')else 'wZ.error(e.message),j(!1)'
                assert segment.count(old)==1,method
                new='wZ.error(e.message),j(!1)'if method.endswith('getCommentPostList')else 'wZ.error(e.message),H(!1)'
                text=text[:start]+segment.replace(old,new,1)+text[end:]
            data=text.encode('utf-8')
        if name=='manju_platform_network.js':data=(ROOT/'engines/xiaovmiao-platform-network.js').read_bytes()
        if hashlib.sha256(data).hexdigest()!=original[name]:entry['integrity']=integrity(data)
        output.append((name,entry,data))
    additions=[('manju_local_accounts.js',ROOT/'engines/xiaovmiao-local-accounts.js')]
    if include_acceptance:additions.append(('manju_account_acceptance.js',ROOT/'tools/xiaovmiao_account_acceptance.cjs'))
    for filename,source in additions:
        data=source.read_bytes();entry={'size':len(data),'offset':'0','integrity':integrity(data)}
        tree['files'][filename]=entry;output.append((filename,entry,data))
    if not destination.exists():shutil.copytree(SOURCE,destination)
    header=write_asar(tree,output,destination/'resources/app.asar')
    exe=(baseline/'vcat_local_init.exe').read_bytes()
    pattern=rb'("file":"resources\\\\app.asar","alg":"SHA256","value":")[0-9a-f]{64}'
    exe,count=re.subn(pattern,lambda match:match[1]+header,exe);assert count==1
    (destination/'vcat_local_init.exe').write_bytes(exe)
    _,verified=read_asar(destination/'resources/app.asar')
    modified=[name for name,_,data in verified if hashlib.sha256(data).hexdigest()!=original.get(name)]
    assert set(modified)=={'main.js','assets/app.min.js','manju_platform_network.js'}|{name for name,_ in additions}
    report={'ok':True,'changedArchiveFiles':modified,'testCodeIncluded':include_acceptance,'preloadAndCompiledBackendUnchanged':True,'softwareLoginFlowChanged':False,'userDataChanged':False,'sourceArchiveSha256':digest(SOURCE/'resources/app.asar'),'sourceExecutableSha256':digest(SOURCE/'vcat_local_init.exe'),'program':str(destination/'vcat_local_init.exe')}
    (destination.parent/'build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--production',action='store_true');parser.add_argument('--baseline',type=Path);args=parser.parse_args()
    print(json.dumps(build(ROOT/'tmp/xiaovmiao-local-accounts-production/程序'if args.production else DEST,not args.production,args.baseline),ensure_ascii=True))
