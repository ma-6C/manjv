"""Isolated persistence protection and real queue/shutdown race regression checks."""
from pathlib import Path
from unittest.mock import patch
import copy,json,os,subprocess,sys,tempfile,threading,time

ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='backend-reliability-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
sys.path.insert(0,str(ROOT/'vendor'))
import server as s

checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
    print('PASS '+name,flush=True)

def rejected(action):
    try:action()
    except (RuntimeError,ValueError,OSError):return
    raise AssertionError('unsafe action was accepted')

fixture=BASE/'database';fixture.mkdir()
state=fixture/'state.json'
empty={'config':{},'projects':[],'accounts':[],'logs':[]}
check('missing_workspace_can_initialize',s.read_persistent_json(state,empty)==empty)
first=copy.deepcopy(empty)|{'projects':[{'id':'preserved-project'}],'futureExtension':{'version':99}}
second=copy.deepcopy(first)|{'projects':[{'id':'new-project'}]}
s.write_persistent_json(state,first,empty)
s.write_persistent_json(state,second,empty)
check('save_keeps_previous_valid_workspace_backup',json.loads(state.with_suffix('.json.bak').read_text('utf-8'))==first)
check('unknown_fields_survive_persistence',s.read_persistent_json(state,empty)['futureExtension']=={'version':99})
before_current=state.read_bytes();before_backup=state.with_suffix('.json.bak').read_bytes()
rejected(lambda:s.write_persistent_json(state,{'config':[]},empty))
check('invalid_new_state_does_not_replace_current_or_backup',state.read_bytes()==before_current and state.with_suffix('.json.bak').read_bytes()==before_backup)
with patch.object(s,'replace_state_file',side_effect=PermissionError('simulated backup denial')):
    try:s.write_persistent_json(state,first,empty)
    except PermissionError:pass
    else:raise AssertionError('backup failure was hidden')
check('backup_write_failure_leaves_current_and_previous_backup_intact',state.read_bytes()==before_current and state.with_suffix('.json.bak').read_bytes()==before_backup)
corrupt=b'{partial-write'
state.write_bytes(corrupt)
before_backup=state.with_suffix('.json.bak').read_bytes()
rejected(lambda:s.read_persistent_json(state,empty))
check('corrupt_existing_workspace_is_never_treated_as_empty',state.read_bytes()==corrupt)
rejected(lambda:s.write_persistent_json(state,empty,empty))
check('save_refuses_to_overwrite_corruption_and_valid_backup',state.read_bytes()==corrupt and state.with_suffix('.json.bak').read_bytes()==before_backup)
for value in ([],{'config':[]},{'projects':{}},{'logs':['malformed-row']}):
    state.write_text(json.dumps(value),'utf-8')
    rejected(lambda:s.read_persistent_json(state,empty))
check('invalid_workspace_root_and_collection_shapes_are_rejected',True)
jobs=fixture/'jobs.json'
for value in ({},[{'id':'missing-fields'}],[{'id':'x','kind':'records','status':'paused','config':{},'ids':None}]):
    jobs.write_text(json.dumps(value),'utf-8')
    rejected(lambda:s.read_persistent_json(jobs,[]))
check('invalid_job_database_is_not_silently_discarded',True)

# Exercise the import path in a fresh interpreter, not only a helper function.
broken=BASE/'broken-startup';broken.mkdir();(broken/'state.json').write_bytes(corrupt)
env=os.environ.copy();env['MANJU_DATA']=str(broken);env['PYTHONIOENCODING']='utf-8'
startup_module=Path(s.__file__).resolve()
child_code=('import sys,importlib.util;from pathlib import Path;'
            'sys.path.insert(0,'+repr(str(startup_module.parent))+');'
            'origin=Path(importlib.util.find_spec("server").origin).resolve();'
            'assert str(origin)=='+repr(str(startup_module))+';'
            'print("STARTUP_MODULE="+str(origin),flush=True);import server')
child=subprocess.run([sys.executable,'-c',child_code],cwd=ROOT,env=env,capture_output=True,timeout=20,
    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
check('startup_stops_and_preserves_corrupt_database',child.returncode!=0 and (broken/'state.json').read_bytes()==corrupt
      and b'RuntimeError' in child.stderr and ('STARTUP_MODULE='+str(startup_module)).encode('utf-8') in child.stdout)

# A worker is held inside a real queue operation while shutdown takes place.
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output')})
project={'id':'fixture-project','name':'queue fixture','source':str(BASE),'videos':[],
    'artifacts':[],'rights':True,'status':'未处理','cover':'','review':'待准备','intro':''}
s.STATE['projects']=[project]
with patch.object(s,'persist_jobs',side_effect=PermissionError('simulated disk denial')),patch.object(s,'ensure_runner') as dispatch:
    rejected(lambda:s.create_job({'kind':'records','ids':[project['id']]}))
check('rejected_job_save_leaves_no_queued_task_or_dispatch',not s.JOBS and not dispatch.called)
with patch.object(s,'ensure_runner',lambda:None):
    blocked=s.create_job({'kind':'records','ids':[project['id']]})['id']
with patch.object(s,'persist_jobs',side_effect=PermissionError('access is denied')),patch.object(s,'worker') as dispatch:
    s.queue_runner()
check('queue_state_save_failure_blocks_processing_with_actionable_error',not dispatch.called and s.JOBS[blocked]['status']=='failed' and s.JOBS[blocked]['diagnostic']['code']=='PERMISSION')
before=copy.copy(s.JOBS[blocked]);s.JOBS[blocked]['cancel'].set()
with patch.object(s,'persist_jobs',side_effect=PermissionError('simulated disk denial')),patch.object(s,'ensure_runner') as dispatch:
    rejected(lambda:s.control_job(blocked,'resume'))
check('rejected_resume_save_restores_task_and_cancel_signal',s.JOBS[blocked]==before and s.JOBS[blocked]['cancel'].is_set() and not dispatch.called)
s.JOBS.clear();s.persist_jobs()
with patch.object(s,'ensure_runner',lambda:None):
    blocked=s.create_job({'kind':'records','ids':[project['id']]})['id']
with patch.object(s,'worker',side_effect=PermissionError('access is denied')):
    s.queue_runner()
check('worker_final_save_failure_cannot_leave_job_running',s.JOBS[blocked]['status']=='failed' and s.JOBS[blocked]['diagnostic']['code']=='PERMISSION')
s.JOBS.clear();s.persist_jobs()
entered=threading.Event();release=threading.Event()
def action(*args):
    entered.set()
    assert release.wait(10),'test worker was not released'
    # This operation has no subprocess and finishes just after shutdown.
    # The final cancellation boundary must still preserve an interrupted job.

with patch.object(s,'records',action):
    jid=s.create_job({'kind':'records','ids':[project['id']]})['id']
    assert entered.wait(10),'queue worker did not start'
    queued=s.create_job({'kind':'records','ids':[project['id']]})['id']
    s.shutdown_jobs()
    release.set()
    s.QUEUE_THREAD.join(10)
check('queue_thread_settles_after_shutdown',not s.QUEUE_THREAD.is_alive())
check('finishing_worker_does_not_overwrite_shutdown_status',s.JOBS[jid]['status']=='interrupted' and s.JOBS[queued]['status']=='interrupted')
saved=json.loads((s.DATA/'jobs.json').read_text('utf-8'))
check('shutdown_recovery_states_are_saved',all(j['status']=='interrupted' for j in saved))
before_ids=set(s.JOBS);before_jobs=(s.DATA/'jobs.json').read_bytes()
rejected(lambda:s.create_job({'kind':'records','ids':[project['id']]}))
rejected(lambda:s.control_job(jid,'resume'))
check('closed_service_rejects_new_and_resumed_jobs_without_queued_ghosts',set(s.JOBS)==before_ids and (s.DATA/'jobs.json').read_bytes()==before_jobs)

# Also cover the race where shutdown begins while request validation is running.
s.QUEUE_STOP.clear()
original_validate=s.validate_config
def closing_validation(config):
    result=original_validate(config)
    s.QUEUE_STOP.set()
    return result
with patch.object(s,'validate_config',closing_validation):
    rejected(lambda:s.create_job({'kind':'records','ids':[project['id']]}))
check('shutdown_during_job_validation_does_not_insert_task',set(s.JOBS)==before_ids and (s.DATA/'jobs.json').read_bytes()==before_jobs)

report={'ok':True,'passed':len(checks),'checks':checks,'base':str(BASE),
    'externalCalls':False,'userDataModified':False,'startupModuleOrigin':str(startup_module),
    'startupChildUsesSameModuleAsParent':True,'compiledServer':startup_module.suffix=='.pyd'}
(ROOT/'tmp/backend-reliability-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
