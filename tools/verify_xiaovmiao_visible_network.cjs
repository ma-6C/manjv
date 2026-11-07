// Show only our isolated diagnostic Electron window, then inspect its real
// capture. No existing account profile, login interaction or publication.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),cp=require('node:child_process');
const ROOT=path.resolve(__dirname,'..'),program=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
const rel=path.relative(path.join(ROOT,'tmp'),out);
if(path.isAbsolute(rel)||rel.startsWith('..'))throw Error('Output must be in the workspace temporary directory');
fs.mkdirSync(out,{recursive:true});
const report=path.join(out,'page-load.json');if(fs.existsSync(report))throw Error('Use a fresh check directory');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function freePort(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
(async()=>{
 const port=await freePort(),env={...process.env,MANJU_XIAOVMIAO_NETWORK_CHECK:'1',
  MANJU_XIAOVMIAO_PROFILE:path.join(out,'isolated-profile'),MANJU_XIAOVMIAO_NETWORK_REPORT:report};
 for(const k of ['ELECTRON_RUN_AS_NODE','NODE_OPTIONS','NODE_PATH'])delete env[k];
 const stdout=fs.openSync(path.join(out,'stdout.log'),'w'),stderr=fs.openSync(path.join(out,'stderr.log'),'w');
 const proc=cp.spawn(program,['--inspect=127.0.0.1:'+port],{cwd:path.dirname(program),env,windowsHide:true,stdio:['ignore',stdout,stderr]});
 let socket,shown=false,id=0;const pending=new Map();
 try{
  let target;const until=Date.now()+15000;
  while(Date.now()<until){
   try{const r=await fetch('http://127.0.0.1:'+port+'/json/list');const a=await r.json();target=a.find(t=>t.webSocketDebuggerUrl);if(target)break;}catch{}
   if(proc.exitCode!==null)throw Error('Diagnostic exited before inspector became ready');await delay(100);
  }
  if(!target)throw Error('Diagnostic inspector did not start');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const r=JSON.parse(String(event.data));if(pending.has(r.id)){pending.get(r.id)(r);pending.delete(r.id);}});
  const evaluate=expression=>new Promise(resolve=>{const request=++id;pending.set(request,resolve);socket.send(JSON.stringify({id:request,method:'Runtime.evaluate',params:{expression,returnByValue:true}}));setTimeout(()=>{if(pending.has(request)){pending.delete(request);resolve({});}},1500);});
  const show=`(()=>{const E=require('electron');if(!E.app.isReady())return 0;const windows=E.BrowserWindow.getAllWindows();for(const w of windows){w.webContents.setBackgroundThrottling(false);w.setContentSize(1240,860);w.show();}for(const c of E.webContents.getAllWebContents()){if(c.getType()==='webview')c.setBackgroundThrottling(false);}return windows.length;})()`;
  const end=Date.now()+55000;
  while(Date.now()<end){
   if(!shown){const r=await evaluate(show);shown=(r.result?.result?.value||0)>0;}
   if(fs.existsSync(report))break;
   if(proc.exitCode!==null)throw Error('Diagnostic exited without page report');await delay(150);
  }
  if(!fs.existsSync(report))throw Error('Diagnostic page report timed out');
  const value=JSON.parse(fs.readFileSync(report,'utf8'));
  value.windowShownForVisualCheck=shown;value.existingProfileUsed=false;
  fs.writeFileSync(report,JSON.stringify(value,null,2));
  console.log(JSON.stringify(value));
  if(!shown||!value.ok)process.exitCode=1;
 }finally{
  if(socket)socket.close();
  for(let i=0;i<20&&proc.exitCode===null;i++)await delay(100);
  if(proc.exitCode===null){try{cp.execFileSync('taskkill',['/PID',String(proc.pid),'/T','/F'],{windowsHide:true,stdio:'ignore',timeout:10000});}catch{proc.kill();}}
  fs.closeSync(stdout);fs.closeSync(stderr);
 }
})().catch(e=>{console.error(String(e));process.exitCode=1;});
