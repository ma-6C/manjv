using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;
using System.Drawing;
using System.Web.Script.Serialization;
using Microsoft.Win32;

// Runs as the current user. Only the pinned Microsoft VC++ installer requests elevation.
internal static class PrerequisiteRunner {
    internal static readonly Version MinimumVC=new Version(14,50,35717,0);
    const string VCKey=@"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64";
    const string EdgeKey=@"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";
    const string VCHash="843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c";
    const string EdgeHash="0625fb5c1e75be58a164e14f95aa58a3e5badb859b3d17c952385f3e4a9ff3e8";
    static readonly object Gate=new object();
    static string LogRoot=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ManjuStudio","install-logs");
    static string ReportPath,SessionLog,VendorLog;
    static volatile string Phase="正在检查系统运行环境…";
    static volatile bool Finished;
    static int Result=1,RawCode;
    static string Message="",Component="";
    static Dictionary<string,object> Snapshot;
    static Version ParseVersion(object value) {
        Version v;string s=Convert.ToString(value).Trim().TrimStart('v','V');
        return Version.TryParse(s,out v)?v:new Version(0,0,0,0);
    }
    internal static bool AtLeast(string value,string required){return ParseVersion(value)>=ParseVersion(required);}
    static Dictionary<string,object> RegistryVC(RegistryView view) {
        var row=new Dictionary<string,object>{{"view",view.ToString()},{"installed",false},{"version",""}};
        try{using(var root=RegistryKey.OpenBaseKey(RegistryHive.LocalMachine,view))using(var key=root.OpenSubKey(VCKey)){
            if(key!=null){row["installed"]=Convert.ToInt32(key.GetValue("Installed",0))==1;row["version"]=Convert.ToString(key.GetValue("Version",""));}
        }}catch(Exception e){row["error"]=e.GetType().Name;}
        return row;
    }
    static string FileVersion(string name) {
        try{var info=FileVersionInfo.GetVersionInfo(Path.Combine(Environment.SystemDirectory,name));return new Version(info.FileMajorPart,info.FileMinorPart,info.FileBuildPart,info.FilePrivatePart).ToString();}
        catch{return "";}
    }
    static bool WebViewReady() {
        foreach(var view in new[]{RegistryView.Registry32,RegistryView.Registry64})foreach(var hive in new[]{RegistryHive.LocalMachine,RegistryHive.CurrentUser}){
            try{using(var root=RegistryKey.OpenBaseKey(hive,view))using(var key=root.OpenSubKey(EdgeKey))if(key!=null&&ParseVersion(key.GetValue("pv",""))>new Version(0,0,0,0))return true;}catch{}
        }
        return false;
    }
    internal static bool EvaluateVC(bool registryPresent,string version,string[] dllVersions) {
        // DLLs are required even if a registry value remains from a damaged installation.
        return dllVersions.Length==3&&dllVersions.All(v=>ParseVersion(v)>=MinimumVC);
    }
    static Dictionary<string,object> Inspect() {
        var x64=RegistryVC(RegistryView.Registry64);var x86view=RegistryVC(RegistryView.Registry32);
        var versions=new Dictionary<string,string>();foreach(var name in new[]{"vcruntime140.dll","vcruntime140_1.dll","msvcp140.dll"})versions[name]=FileVersion(name);
        bool reg64=(bool)x64["installed"]&&ParseVersion(x64["version"])>=MinimumVC;
        bool reg32=(bool)x86view["installed"]&&ParseVersion(x86view["version"])>=MinimumVC;
        return new Dictionary<string,object>{{"windows",Environment.OSVersion.VersionString},{"is64BitOS",Environment.Is64BitOperatingSystem},
            {"minimumVC",MinimumVC.ToString()},{"registry64",x64},{"registry32",x86view},{"dllVersions",versions},
            {"vcRegistryReady",reg64||reg32},{"vcReady",EvaluateVC(reg64||reg32,"",versions.Values.ToArray())},{"webViewReady",WebViewReady()}};
    }
    internal static int Normalize(int code){uint c=unchecked((uint)code);return (c&0xffff0000U)==0x80070000U?(int)(c&0xffff):code;}
    internal static int Classify(int raw,bool ready) {
        int c=Normalize(raw);
        if(c==3010||c==1641)return 3010;
        if((c==0||c==1638)&&ready)return 0;
        if(c==0||c==1638)return 5101;
        if(c==1223||c==1602)return 1602;
        return c;
    }
    internal static string Explain(int code) {
        switch(code){
            case 0:return "系统运行库已就绪，可以继续安装漫剧工坊。";
            case 3010:return "微软运行库已安装，需要重新启动 Windows 后再运行漫剧工坊。";
            case 1618:return "Windows 正在安装其他软件或更新。请等待该安装完成，再重新运行本安装包。";
            case 1602:return "运行库安装或管理员授权已取消。请重新安装并由电脑使用者确认 Windows 权限提示。";
            case 1460:return "等待运行库安装已超过10分钟。请查看微软安装窗口与日志，完成或关闭该安装后再重试。";
            case 5101:return "微软安装程序已退出，但运行库检测尚未通过。请重启电脑后重试，或根据日志修复运行库。";
            case 5102:return "附带的微软运行库安装文件校验失败，请重新获取原始安装包。";
            case 1625:return "系统策略阻止了运行库安装，请由这台电脑的管理员处理。";
            case 1603:return "微软运行库安装失败，请查看安装日志中的具体原因。";
            default:return "运行库安装未完成，返回码 "+code+"。请查看日志并处理后重试。";
        }
    }
    static void Log(string value){lock(Gate){File.AppendAllText(SessionLog,DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")+" "+value+Environment.NewLine,Encoding.UTF8);}}
    static void WriteReport(string command,int code) {
        var value=new Dictionary<string,object>{{"command",command},{"result",code},{"rawCode",RawCode},{"message",Message},{"phase",Phase},
            {"snapshot",Snapshot},{"log",SessionLog},{"microsoftLog",VendorLog??""},{"at",DateTime.Now.ToString("o")}};
        string data=new JavaScriptSerializer().Serialize(value);File.WriteAllText(ReportPath,data,new UTF8Encoding(false));
        File.WriteAllText(Path.Combine(Path.GetDirectoryName(SessionLog),"report.json"),data,new UTF8Encoding(false));
    }
    internal static int Supervise(Func<bool> isFinished,Func<int> result,Func<bool> cancelled,TimeSpan timeout,Action tick) {
        var timer=Stopwatch.StartNew();
        while(!isFinished()){
            if(cancelled())return 1602;
            if(timer.Elapsed>=timeout)return 1460;
            tick();Thread.Sleep(100);
        }
        return result();
    }
    static void Worker(string command,string payload) {
        try {
            bool vc=command=="--install-vc";string expected=vc?VCHash:EdgeHash;
            Phase="正在校验微软运行库安装文件…";Log(Phase);
            using(var hash=SHA256.Create())using(var file=File.OpenRead(payload)){
                var digest=BitConverter.ToString(hash.ComputeHash(file)).Replace("-","").ToLowerInvariant();
                if(digest!=expected){Result=5102;return;}
            }
            Phase=vc?"请确认 Windows 管理员权限窗口；随后会显示微软安装进度。":"正在安装 WebView2，请等待微软安装程序完成。";Log(Phase);
            bool repair=vc&&(bool)Snapshot["vcRegistryReady"];
            VendorLog=Path.Combine(Path.GetDirectoryName(SessionLog),vc?"vc-redist.log":"webview2-install.log");
            var start=new ProcessStartInfo{FileName=payload,UseShellExecute=true,WindowStyle=ProcessWindowStyle.Normal,
                Arguments=vc?(repair?"/repair":"/install")+" /passive /norestart /log \""+VendorLog+"\"":"/silent /install"};
            if(vc)start.Verb="runas";
            Log("Starting pinned Microsoft installer; mode="+(repair?"repair":"install"));
            using(var process=Process.Start(start)){
                if(process==null)throw new Exception("无法获取安装进程句柄");
                Phase=vc?"微软 Visual C++ 安装程序正在运行，请查看其进度窗口。":"微软 WebView2 安装程序正在运行。";
                process.WaitForExit();RawCode=process.ExitCode;Log("Microsoft exit="+RawCode+", normalized="+Normalize(RawCode));
            }
            Snapshot=Inspect();Result=Classify(RawCode,(bool)Snapshot[vc?"vcReady":"webViewReady"]);
        }catch(System.ComponentModel.Win32Exception e){RawCode=e.NativeErrorCode;Result=Normalize(e.NativeErrorCode)==1223?1602:Normalize(e.NativeErrorCode);Log(e.ToString());}
        catch(Exception e){Result=1;Log(e.ToString());}
        finally{Finished=true;}
    }
    static int Monitor(string command,string payload,bool silent) {
        var worker=new Thread(()=>Worker(command,payload));worker.IsBackground=true;
        if(silent){worker.Start();return Supervise(()=>Finished,()=>Result,()=>false,TimeSpan.FromMinutes(10),()=>{});}
        int outcome=1;bool timedOut=false;var watch=Stopwatch.StartNew();
        using(var form=new Form{Text="漫剧工坊 · 安装系统运行库",Size=new Size(650,340),StartPosition=FormStartPosition.CenterScreen,
            FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=true,Font=new Font("Microsoft YaHei UI",10)}){
            var title=new Label{Left=25,Top=22,Width=590,Height=35,Text="正在准备 "+Component,Font=new Font("Microsoft YaHei UI",15,FontStyle.Bold)};
            var status=new Label{Left=25,Top=72,Width=590,Height=60,Text=Phase};
            var progress=new ProgressBar{Left=25,Top=142,Width=585,Height=18,Style=ProgressBarStyle.Marquee};
            var elapsed=new Label{Left=25,Top=175,Width=580,Height=32};
            var detail=new Label{Left=25,Top=211,Width=580,Height=40,Text="若出现 Windows 权限提示，请由电脑使用者确认。安装日志会自动保留。"};
            var cancel=new Button{Left=450,Top=261,Width=160,Height=33,Text="停止等待"};
            bool complete=false;
            cancel.Click+=(s,e)=>{if(MessageBox.Show(form,"停止等待后，已开始的微软安装可能仍在进行。请先完成该安装，再重试主安装包。","停止本次等待？",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes){outcome=1602;complete=true;form.Close();}};
            form.FormClosing+=(s,e)=>{if(!complete){e.Cancel=true;cancel.PerformClick();}};
            var timer=new System.Windows.Forms.Timer{Interval=250};timer.Tick+=(s,e)=>{
                status.Text=Phase;elapsed.Text="已等待 "+watch.Elapsed.ToString(@"mm\:ss")+" / 最长10分钟";
                if(Finished||watch.Elapsed>=TimeSpan.FromMinutes(10)){
                    timedOut=!Finished;outcome=timedOut?1460:Result;complete=true;timer.Stop();form.Close();
                }
            };
            form.Controls.AddRange(new Control[]{title,status,progress,elapsed,detail,cancel});form.Shown+=(s,e)=>{timer.Start();worker.Start();};
            Application.Run(form);timer.Dispose();
        }
        if(timedOut)Log("Supervisor timeout; Microsoft installation may still be running.");
        return outcome;
    }
    [STAThread] static int Main(string[] args) {
        string command=args.Length>0?args[0]:"--diagnose";bool silent=args.Contains("--silent");
        try {
            Directory.CreateDirectory(LogRoot);string session=Path.Combine(LogRoot,DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Process.GetCurrentProcess().Id);Directory.CreateDirectory(session);
            SessionLog=Path.Combine(session,"supervisor.log");ReportPath=Path.Combine(LogRoot,"prerequisites-last.json");
            int at=Array.IndexOf(args,"--report");if(at>=0)ReportPath=Path.GetFullPath(args[at+1]);
            Snapshot=Inspect();Log("Command="+command+"; snapshot="+new JavaScriptSerializer().Serialize(Snapshot));int code;
            if(command=="--check-vc")code=(bool)Snapshot["vcReady"]?0:10;
            else if(command=="--check-webview")code=(bool)Snapshot["webViewReady"]?0:10;
            else if(command=="--diagnose")code=0;
            else if(command=="--install-vc"||command=="--install-webview"){
                if(args.Length<2)throw new Exception("缺少运行库安装文件");
                Component=command=="--install-vc"?"Microsoft Visual C++ x64":"Microsoft WebView2";
                if((bool)Snapshot[command=="--install-vc"?"vcReady":"webViewReady"]){code=0;Phase="运行库已就绪，跳过重复安装。";}
                else code=Monitor(command,Path.GetFullPath(args[1]),silent);
            }else throw new Exception("未知诊断参数");
            Message=code==10?"缺少兼容运行库，需要安装。":Explain(code);Log(Message);WriteReport(command,code);
            if(command=="--diagnose"&&!silent)MessageBox.Show("Visual C++ x64："+((bool)Snapshot["vcReady"]?"已就绪":"需要安装或修复")+"\nWebView2："+((bool)Snapshot["webViewReady"]?"已就绪":"需要安装")+"\n\n诊断文件已保存：\n"+ReportPath,"漫剧工坊安装诊断",MessageBoxButtons.OK,MessageBoxIcon.Information);
            if(code!=0&&code!=10&&!silent)MessageBox.Show(Message+"\n\n诊断文件："+ReportPath+"\n安装日志："+SessionLog,"运行库安装结果",MessageBoxButtons.OK,code==3010?MessageBoxIcon.Information:MessageBoxIcon.Warning);
            return code;
        }catch(Exception e){try{if(SessionLog!=null)Log(e.ToString());}catch{}if(!silent)MessageBox.Show(e.Message,"安装环境检查失败");return 1;}
    }
}
