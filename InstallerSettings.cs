// Reset only the settings object in state.json; never remove a user-data tree.
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;
internal static class InstallerSettings {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern IntPtr CreateFile(string path,uint access,uint share,IntPtr security,uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern uint GetFinalPathNameByHandle(IntPtr handle,StringBuilder result,uint size,uint flags);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    static JavaScriptSerializer Json(){return new JavaScriptSerializer{MaxJsonLength=128*1024*1024,RecursionLimit=512};}
    static string DataHome(){
        string value=Environment.GetEnvironmentVariable("MANJU_DATA");
        string home=Path.GetFullPath(String.IsNullOrWhiteSpace(value)?Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ManjuStudio"):value);
        if(home.TrimEnd('\\')==Path.GetPathRoot(home).TrimEnd('\\'))throw new Exception("用户数据目录不能是磁盘根目录");
        // Match pathlib.resolve(), including the spelling/case of existing paths,
        // so the mutex is identical to the desktop application's data mutex.
        if(Directory.Exists(home)){
            IntPtr handle=CreateFile(home,0,7,IntPtr.Zero,3,0x02000000,IntPtr.Zero);
            if(handle==new IntPtr(-1))throw new Win32Exception(Marshal.GetLastWin32Error());
            try{
                var text=new StringBuilder(32768);uint n=GetFinalPathNameByHandle(handle,text,(uint)text.Capacity,0);
                if(n==0||n>=text.Capacity)throw new Exception("无法解析用户数据目录");
                home=text.ToString();
                if(home.StartsWith(@"\\?\UNC\"))home=@"\\"+home.Substring(8);
                else if(home.StartsWith(@"\\?\"))home=home.Substring(4);
            }finally{CloseHandle(handle);}
        }
        return home.TrimEnd('\\');
    }
    internal static string MutexName(string home){
        using(var sha=SHA256.Create())return @"Local\ManjuStudio."+BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(home))).Replace("-","").ToLowerInvariant().Substring(0,24);
    }
    static void RejectLink(string path){
        if((File.Exists(path)||Directory.Exists(path))&&(File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)
            throw new Exception("配置路径包含链接，未重置："+path);
    }
    static byte[] ReadState(string path,out Dictionary<string,object> state){
        RejectLink(path);
        if(new FileInfo(path).Length>128*1024*1024)throw new Exception("配置文件过大，未重置");
        byte[] raw=File.ReadAllBytes(path);string text=new UTF8Encoding(false,true).GetString(raw).TrimStart('\uFEFF');
        state=Json().DeserializeObject(text) as Dictionary<string,object>;
        if(state==null)throw new Exception("配置文件格式无效，原文件已保留");
        return raw;
    }
    internal static Dictionary<string,object> Run(bool apply){
        string home=DataHome();bool created;
        using(var gate=new Mutex(false,MutexName(home),out created)){
            if(!created)throw new Exception("漫剧工坊正在使用此配置，请先退出软件");
            string path=Path.Combine(home,"state.json");
            if(!File.Exists(path))return new Dictionary<string,object>{{"changed",false},{"reason","no_settings"}};
            Dictionary<string,object> state;byte[] original=ReadState(path,out state);
            string backups=Path.Combine(home,"settings-backups");RejectLink(backups);
            Directory.CreateDirectory(backups);
            string probe=Path.Combine(backups,".write-check-"+Guid.NewGuid().ToString("N"));
            try{using(File.Create(probe)){} }finally{if(File.Exists(probe))File.Delete(probe);}
            if(!apply)return new Dictionary<string,object>{{"changed",false},{"ready",true}};
            // Unknown fields, projects, accounts, media references, history and
            // task snapshots remain in the same state object.
            state["config"]=new Dictionary<string,object>();
            state.Remove("aiConnectionTests");state.Remove("trackSheetOptions");
            string id=DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+Guid.NewGuid().ToString("N");
            string backup=Path.Combine(backups,"before-reset-"+id+".json");
            string temp=Path.Combine(home,"state-reset-"+id+".tmp");
            File.WriteAllBytes(backup,original);
            try{
                byte[] updated=Encoding.UTF8.GetBytes(Json().Serialize(state));
                using(var file=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){file.Write(updated,0,updated.Length);file.Flush(true);}
                // Detect external edits before replacing. The desktop mutex also
                // prevents a live application from racing this reset.
                byte[] current=File.ReadAllBytes(path);
                if(!Equal(original,current))throw new Exception("配置在检查后发生变化，原文件已保留");
                for(int n=0;;n++){
                    try{File.Replace(temp,path,null);break;}
                    catch(IOException){if(n==5)throw;Thread.Sleep(10*(1<<n));}
                    catch(UnauthorizedAccessException){if(n==5)throw;Thread.Sleep(10*(1<<n));}
                }
            }finally{if(File.Exists(temp))File.Delete(temp);}
            return new Dictionary<string,object>{{"changed",true},{"backup",backup},{"resetFields",new[]{"config","aiConnectionTests","trackSheetOptions"}},
                {"projectsPreserved",true},{"otherUserFilesTouched",false}};
        }
    }
    static bool Equal(byte[] a,byte[] b){if(a.Length!=b.Length)return false;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])return false;return true;}
    [STAThread] static int Main(string[] args){
        Dictionary<string,object> report;int result=0;
        try{
            if(args.Length<1||(args[0]!="--check"&&args[0]!="--reset"))throw new Exception("未知配置处理参数");
            report=Run(args[0]=="--reset");report["ok"]=true;
        }catch(Exception error){report=new Dictionary<string,object>{{"ok",false},{"error",error.Message},{"originalSettingsPreserved",true}};result=20;}
        int at=Array.IndexOf(args,"--report");
        if(at>=0&&at+1<args.Length){try{File.WriteAllText(args[at+1],Json().Serialize(report),new UTF8Encoding(false));}catch{return 20;}}
        return result;
    }
}
