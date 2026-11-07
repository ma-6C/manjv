"""Launch the supplied new program with a fresh profile, never a real session."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def verify(module,output=None):
    module=Path(module).resolve()
    if not module.is_relative_to(ROOT/'tmp'):raise ValueError('Use a staged module only')
    output=Path(output).resolve() if output else module.parent
    if not output.is_relative_to(ROOT/'tmp'):raise ValueError('Use an isolated output directory')
    output.mkdir(parents=True,exist_ok=True)
    profile=output/('smoke-profile-'+str(time.time_ns()));profile.mkdir()
    env=os.environ.copy()
    for key in ('NODE_OPTIONS','NODE_PATH','ELECTRON_RUN_AS_NODE','VCAT_BASELINE','VCAT_BOOT_ONLY','VCAT_ACCOUNT_PHASE','VCAT_NETWORK_PROBE'):
        env.pop(key,None)
    env.update(MANJU_XIAOVMIAO_PROFILE=str(profile),VCAT_TEST_EXIT_MS='13000')
    manifest=json.loads((module/'module.json').read_text('utf-8'))
    exe=module/'程序'/manifest['executable']
    log=module/'logs/startup.ndjson'
    offset=log.stat().st_size if log.exists()else 0
    with (output/'smoke.stdout.log').open('wb')as out,(output/'smoke.stderr.log').open('wb')as err:
        process=subprocess.run([str(exe)],cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30)
    records=[]
    if log.exists():
        with log.open('rb')as stream:
            stream.seek(offset)
            records=[json.loads(line)for line in stream if line.strip()]
    by_event={row['event']:row for row in records}
    ready=by_event.get('local-workspace-ready',{})
    expected=profile/'workspace/.vcat/offline-local/vcat.db'
    checks={
        'process_exit_zero':process.returncode==0,
        'new_javascript_backend_loaded':by_event.get('server-loaded',{}).get('baseline')is False,
        'ipc_channels_registered':len(by_event.get('server-initialized',{}).get('handlers',[]))==6,
        'native_frontend_loaded':'did-finish-load'in by_event,
        'local_ipc_memory_valid':by_event.get('local-ipc-check',{}).get('memoryVerified')is True,
        'workspace_initialized':ready.get('modelCount')==43,
        'uses_isolated_profile':Path(ready.get('database','')).resolve()==expected.resolve(),
        'empty_test_accounts':ready.get('counts',{}).get('Account')==0,
        'no_startup_failure':not any(row['event']in {'startup-error','local-workspace-error','preload-error','renderer-gone','local-ipc-check-error'}for row in records),
    }
    report={'ok':all(checks.values()),'checks':checks,'realUserProfileUsed':False,'realAccountVerified':False,
            'testProfile':str(profile),'program':str(exe),'version':manifest['version'],'build':manifest['build']}
    (output/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    options=parser.parse_args();result=verify(options.module,options.output);print(json.dumps(result,ensure_ascii=True));raise SystemExit(not result['ok'])
