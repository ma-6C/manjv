"""Give the supplied unpacked build the companion launcher's profile override."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def adapt(module):
    module=Path(module).resolve()
    if not module.is_relative_to(ROOT/'tmp'):
        raise ValueError('Adapt a staging copy inside workspace tmp only')
    manifest_file=module/'module.json'
    manifest=json.loads(manifest_file.read_text('utf-8'))
    app=module/'程序/resources/app'
    package=json.loads((app/'package.json').read_text('utf-8'))
    if manifest['executable']!='vcat-local.exe' or package['main']!='main.js':
        raise ValueError('Unexpected reconstructed application entry')
    main=app/'main.js'
    text=main.read_text('utf-8')
    old="const profile=path.join(root,process.env.VCAT_NETWORK_PROBE==='account'?'account-probe-profile':process.env.VCAT_NETWORK_PROBE==='1'?'network-probe-profile':'profile');"
    new="const profile=path.resolve(process.env.MANJU_XIAOVMIAO_PROFILE||path.join(root,process.env.VCAT_NETWORK_PROBE==='account'?'account-probe-profile':process.env.VCAT_NETWORK_PROBE==='1'?'network-probe-profile':'profile'));"
    if old in text:
        if text.count(old)!=1:raise ValueError('Unexpected profile bootstrap')
        manifest['upstreamMainSha256']=hashlib.sha256(main.read_bytes()).hexdigest()
        main.write_bytes(text.replace(old,new).encode('utf-8'))
    elif text.count(new)!=1:
        raise ValueError('Profile bootstrap not recognized')
    manifest.update(mode='local-reconstructed',profileLayout='workspace',version=package['version'],build=package.get('build'),
                    dataPathOverride='MANJU_XIAOVMIAO_PROFILE',adaptedFiles=['resources/app/main.js'])
    manifest['files']['resources/app/main.js']=hashlib.sha256(main.read_bytes()).hexdigest()
    manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    return {'ok':True,'version':manifest['version'],'build':manifest['build'],
            'files':len(manifest['files']),'adaptedFiles':manifest['adaptedFiles'],
            'upstreamBusinessCodeUnchanged':True,'userDataCopied':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--module',type=Path,required=True)
    print(json.dumps(adapt(parser.parse_args().module),ensure_ascii=True))
