"""Audit a selected or tracked source set without printing credential values."""
from pathlib import Path
import argparse,json,re,subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path);args=parser.parse_args()
files=json.loads(args.manifest.read_text('utf-8')) if args.manifest else subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
blocked_roots={'data','output','release','tmp','vendor','参考','备份','截图','授权管理','实际视频测试','客户检测工具','.codex','.agents','.aws','.venv'}
blocked_suffix={'.exe','.dll','.pyd','.pyc','.zip','.mjk','.dpapi','.pem','.key','.pfx','.p12','.mp4','.mkv','.pt','.pth','.onnx','.safetensors'}
patterns={
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
 'github_token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})'),
 'provider_key':re.compile(r'(?:\bsk-[A-Za-z0-9_-]{20,}|\bark-[a-fA-F0-9-]{30,}|\bAKIA[A-Z0-9]{16}\b)'),
 'device_license':re.compile(r'\bMJ1\.[A-Za-z0-9_-]{60,}\.[A-Za-z0-9_-]{40,}'),
}
issues=[];total=0;largest=[]
for name in files:
    if not name:continue
    path=root/name;relative=Path(name)
    if relative.parts[0] in blocked_roots or relative.suffix.lower() in blocked_suffix or '__pycache__' in relative.parts or name=='LicenseIssuer.cs':issues.append({'file':name,'rule':'excluded_artifact'})
    if not path.is_file():issues.append({'file':name,'rule':'missing_file'});continue
    size=path.stat().st_size;total+=size;largest.append((size,name))
    if size>10*1024*1024:issues.append({'file':name,'rule':'oversized_source_file'})
    if path.suffix.lower() not in {'.py','.js','.cjs','.cs','.json','.md','.txt','.ps1','.bat','.html','.css',''}:continue
    try:text=path.read_text('utf-8-sig')
    except UnicodeError:continue
    for line_no,line in enumerate(text.splitlines(),1):
        for rule,pattern in patterns.items():
            if pattern.search(line):issues.append({'file':name,'line':line_no,'rule':rule})
report={'files':len([p for p in files if p]),'bytes':total,'issues':issues,'largestFiles':[{'path':name,'bytes':size} for size,name in sorted(largest,reverse=True)[:5]]}
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(bool(issues))
