using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Launcher {
    [STAThread]
    static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string bundled = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), @".cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe");
        string runtime = File.Exists(bundled) ? bundled : "pythonw.exe";
        try {
            Process.Start(new ProcessStartInfo {
                FileName = runtime,
                Arguments = "\"" + Path.Combine(root, "desktop.py") + "\"",
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        } catch (Exception e) {
            MessageBox.Show("无法启动桌面应用，请先安装 Python 及项目依赖。\n" + e.Message, "漫剧工坊", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
