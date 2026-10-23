"""Atomic persistence survives a brief Windows sharing violation, never truncates old JSON."""
from pathlib import Path
from unittest.mock import patch
import os,sys,tempfile,json
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='state-replace-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.path.insert(0,str(ROOT/'vendor'))
if '--compiled' in sys.argv:sys.path.insert(0,str(ROOT/'release/v0.8.2/漫剧工坊/_internal'))
import server as s
target=BASE/'state.json';temporary=BASE/'state.tmp'
target.write_text('{"version":1}','utf-8');temporary.write_text('{"version":2}','utf-8')
real=Path.replace;calls=[]
def transient(path,to):
    calls.append(path)
    if len(calls)<3:raise PermissionError('simulated Windows sharing violation')
    return real(path,to)
with patch.object(Path,'replace',transient),patch.object(s.time,'sleep'):
    s.replace_state_file(temporary,target)
assert len(calls)==3 and json.loads(target.read_text())=={'version':2} and not temporary.exists()
checks=['transient_sharing_violation_retried','atomic_complete_json_replaces_previous']
temporary.write_text('{"version":3}','utf-8')
with patch.object(Path,'replace',side_effect=PermissionError('persistent denial')) as mocked,patch.object(s.time,'sleep'):
    try:s.replace_state_file(temporary,target)
    except PermissionError:pass
    else:raise AssertionError('permanent failure hidden')
    assert mocked.call_count==6
assert json.loads(target.read_text())=={'version':2} and json.loads(temporary.read_text())=={'version':3}
checks+=['permanent_failure_is_bounded_and_reported','previous_complete_json_preserved_on_failure']
report={'compiled':'--compiled' in sys.argv,'passed':len(checks),'checks':checks}
(ROOT/'tmp/state-persistence-082.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report))
