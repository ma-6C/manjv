"""Repeatable local release gate; isolated tests only, with no paid or account calls.

Run with the same Python interpreter used for the build. Browser regressions need
the local Playwright/Edge paths used by the existing project test harnesses.
"""
from pathlib import Path
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SUITES=[
    ('unit-contracts',['-m','unittest','test_ai_providers','test_api_connections','test_ai_model_discovery','verify_cost_reports','test_xiaovmiao','test_xiaovmiao_prepare','verify_jianying_automation'], 'Provider/editor responses and app launches are mocked.'),
    ('backend-reliability',['verify_backend_reliability.py'],'Real files and queue shutdown; injected storage faults.'),
    ('desktop-startup',['verify_desktop_startup.py'],'Startup import fault; native error dialog mocked.'),
    ('distribution-integrity',['verify_distribution_integrity.py'],'Every signed file is checked; corrupt, missing and escaping paths rejected.'),
    ('license-free-usage',['verify_license_free.py'],'Fresh and historical profiles use the workbench and real local processing without device activation.'),
    ('state-persistence',['verify_state_persistence.py'],'Real isolated state files.'),
    ('http-security',['test_sources_security.py'],'Loopback HTTP; no external accounts.'),
    ('task-diagnostics',['verify_task_diagnostics.py'],'Real FFmpeg failure and retry.'),
    ('storage-and-relink',['verify_storage_paths.py'],'Real files, media and editable drafts.'),
    ('continuous-production',['verify_production_handoff.py'],'Real FFmpeg/subtitle-region/cover/records/cost; no cloud or native editor.'),
    ('transform-pipeline',['verify_transform_pipeline.py'],'Real FFmpeg and decoding; forced CPU fallback.'),
    ('whole-episode-subtitles',['verify_subtitle_full.py'],'Real media; injected subtitle adapter outputs, no AI quality acceptance.'),
    ('subtitle-tail-timing',['verify_subtitle_tail.py'],'Real media; tail config and original-time preview mapping, with controlled model output.'),
    ('progress-and-cancel',['verify_progress.py'],'Real FFmpeg; subtitle-worker protocol and downloads simulated.'),
    ('download-recovery',['verify_workflow_hardening.py'],'Source responses mocked; real local FFmpeg downstream.'),
    ('source-completeness',['verify_source_completeness.py'],'Real truncated public preview is rejected; declared/full duration, native metadata and cache recovery checked.'),
    ('editable-drafts',['verify_jianying_official.py'],'Real draft export/copy; editor metadata controlled, no editor UI launch.'),
    ('removed-workflow',['verify_studio_removed.py'],'Loopback APIs and retired-route enforcement.'),
    ('provider-connections',['verify_connections.py'],'Loopback HTTP and media download; remote providers simulated.'),
    ('promotion-local',['verify_promotion_studio.py'],'Real local cuts; language model and ASR replies simulated.'),
    ('promotion-engines',['verify_promotion_engines.py'],'Loopback HTTP and engine selection; remote responses simulated.'),
    ('promotion-cloud-contract',['verify_promotion_mediakit.py'],'MediaKit protocol simulated; no paid requests.'),
    ('promotion-dramaclip',['verify_promotion_dramaclip.py'],'Actual bundled sidecar and FFmpeg; no paid model calls.'),
]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ui',action='store_true',help='Also run self-contained Edge UI suites');args=parser.parse_args()
    base=ROOT/'tmp'/('commercial-acceptance-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    base.mkdir(parents=True)
    report={'startedAt':datetime.datetime.now().astimezone().isoformat(),'base':str(base),'python':sys.executable,'suites':[],
            'scope':'Local candidate gate, not real-account, paid-model, physical-power-loss or clean-machine acceptance.'}
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUTF8']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    env['PYTHONPATH']=os.pathsep.join([str(ROOT),str(ROOT/'vendor')])
    commands=[(name,[sys.executable,*arguments],scope) for name,arguments,scope in SUITES]
    if args.ui:
        commands.extend((name,['node',script],scope) for name,script,scope in [
            ('library-ui','verify_library_advanced_ui.cjs','Actual Edge; API fixtures.'),
            ('connection-recovery-ui','verify_connection_recovery_ui.cjs','Actual Edge; injected HTTP/startup/hardware faults.')])
    for name,command,scope in commands:
        begun=time.monotonic();log=base/(name+'.log');error=''
        print('RUN '+name,flush=True)
        try:
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
            code=result.returncode
        except (OSError,subprocess.TimeoutExpired) as failure:code=-1;error=str(failure)
        report['suites'].append({'name':name,'ok':code==0,'returncode':code,'seconds':round(time.monotonic()-begun,2),'log':str(log),'scope':scope,'error':error})
        report['ok']=all(suite['ok'] for suite in report['suites'])
        (base/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(('PASS ' if code==0 else 'FAIL ')+name,flush=True)
    report['finishedAt']=datetime.datetime.now().astimezone().isoformat()
    (base/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/commercial-acceptance-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'ok':report['ok'],'passed':sum(s['ok'] for s in report['suites']),'suites':len(report['suites']),'report':str(base/'report.json')},ensure_ascii=True),flush=True)
    return 0 if report['ok'] else 1


if __name__=='__main__':sys.exit(main())
