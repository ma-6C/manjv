"""Repair browser connectivity in a workspace copy; do not change user data."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil
import struct

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read_asar(path):
    with path.open('rb') as stream:
        header=stream.read(16);base=8+struct.unpack_from('<I',header,4)[0]
        tree=json.loads(stream.read(struct.unpack_from('<I',header,12)[0]));items=[]
        def walk(node,prefix=''):
            for name,entry in node['files'].items():
                name=prefix+name
                if 'files' in entry:walk(entry,name+'/')
                elif not entry.get('unpacked') and 'offset' in entry:
                    stream.seek(base+int(entry['offset']));items.append((name,entry,stream.read(entry['size'])))
        walk(tree)
    return tree,items


def integrity(data):
    return {'algorithm':'SHA256','hash':hashlib.sha256(data).hexdigest(),'blockSize':4194304,
            'blocks':[hashlib.sha256(data[i:i+4194304]).hexdigest() for i in range(0,len(data),4194304)]}


def write_asar(tree,items,path):
    offset=0
    for _,entry,data in items:entry['offset']=str(offset);entry['size']=len(data);offset+=len(data)
    encoded=json.dumps(tree,ensure_ascii=False,separators=(',',':')).encode()
    payload=struct.pack('<I',len(encoded))+encoded;payload+=b'\0'*((-len(payload))%4)
    header=struct.pack('<I',len(payload))+payload
    with path.open('wb') as stream:
        stream.write(struct.pack('<II',4,len(header)));stream.write(header)
        for _,_,data in items:stream.write(data)
    return hashlib.sha256(encoded).hexdigest().encode()


def repair(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT) or source==destination:
        raise ValueError('Only a separate workspace program copy can be modified')
    original=source/'resources/app.asar';exe=source/'vcat_local_init.exe'
    before={name:digest(source/name) for name in ('resources/app.asar','vcat_local_init.exe')}
    tree,items=read_asar(original);original_items={name:hashlib.sha256(data).hexdigest() for name,_,data in items}
    replacements={
        "const profile=path.join(work,'本地数据');": "const profile=path.resolve(process.env.MANJU_XIAOVMIAO_PROFILE||path.join(work,'本地数据'));",
        "app.commandLine.appendSwitch('host-resolver-rules','MAP * ~NOTFOUND');": "const platformNetwork=require('./manju_platform_network').install({app,log});",
        "callback({cancel:/^(https?|wss?|ftp):/i.test(details.url)});": "callback({cancel:/^(https?|wss?|ftp):/i.test(details.url)&&!platformNetwork.canRequest(session,details.url)});",
    }
    output=[]
    for name,entry,data in items:
        if name=='main.js':
            text=data.decode('utf-8')
            for old,new in replacements.items():
                if text.count(old)!=1:raise ValueError('Unexpected bootstrap source: '+old)
                text=text.replace(old,new)
            # Test mode does not load the product backend or touch real data.
            text="if(process.env.MANJU_XIAOVMIAO_NETWORK_CHECK==='1'){require('node:fs').writeFileSync(process.env.MANJU_XIAOVMIAO_NETWORK_REPORT+'.started','main-started');require('./manju_platform_network').smoke();}else{\n"+text+'\n}\n'
            data=text.encode();entry['integrity']=integrity(data)
        output.append((name,entry,data))
    policy=(ROOT/'engines/xiaovmiao-platform-network.js').read_bytes()
    entry={'size':len(policy),'offset':'0','integrity':integrity(policy)}
    tree['files']['manju_platform_network.js']=entry
    output.append(('manju_platform_network.js',entry,policy))
    backup=ROOT/'tmp/xiaovmiao-network-backup'/before['resources/app.asar'][:16]
    backup.mkdir(parents=True,exist_ok=True)
    for name in ('resources/app.asar','vcat_local_init.exe'):
        target=backup/Path(name).name
        if not target.exists():shutil.copy2(source/name,target)
    if not destination.exists():shutil.copytree(source,destination)
    tmp=destination/'resources/app.asar.network-tmp'
    header_hash=write_asar(tree,output,tmp)
    executable=exe.read_bytes()
    pattern=rb'("file":"resources\\\\app.asar","alg":"SHA256","value":")[0-9a-f]{64}'
    executable,count=re.subn(pattern,lambda match:match[1]+header_hash,executable)
    if count!=1:raise ValueError('Unexpected Electron archive-integrity metadata')
    tmp.replace(destination/'resources/app.asar')
    (destination/exe.name).write_bytes(executable)
    _,checked=read_asar(destination/'resources/app.asar')
    changed=[name for name,_,data in checked if hashlib.sha256(data).hexdigest()!=original_items.get(name)]
    if set(changed)!={'main.js','manju_platform_network.js'}:raise ValueError('Unexpected archive edits')
    if any(digest(source/name)!=sha for name,sha in before.items()):raise ValueError('Original program changed')
    report={'ok':True,'modifiedArchiveFiles':changed,'originalProgramUnchanged':True,
        'backendAndPreloadUnchanged':True,'network':'platform-webviews-only',
        'userDataCopied':False,'program':str(destination/exe.name)}
    manifest=destination.parent/'module.json'
    if manifest.is_file():
        value=json.loads(manifest.read_text('utf-8'));value['mode']='local-platform-browser'
        for name in ('resources/app.asar',exe.name):value['files'][name]=digest(destination/name)
        manifest.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/xiaovmiao-network-repair.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('D:/小v喵/本地初始化修复_20261103/程序'))
    parser.add_argument('--destination',type=Path,default=ROOT/'modules/xiaovmiao/程序')
    args=parser.parse_args();print(json.dumps(repair(args.source,args.destination),ensure_ascii=False))
