using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class CheckDramaArchive
{
    private sealed class Entry
    {
        public string Title, SeriesId, Filename, Hash;
        public long Size;
        public int Episode;
        public readonly List<string> Matches = new List<string>();
    }

    private static string Text(Dictionary<string, object> row, string key)
    {
        return row.ContainsKey(key) ? Convert.ToString(row[key], CultureInfo.InvariantCulture) : "";
    }

    private static bool Linked(string path)
    {
        return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    private static string HashFile(string path)
    {
        using (var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
    }

    private static void AddFiles(string directory, List<string> files, List<string> errors)
    {
        try
        {
            foreach (string path in Directory.GetFiles(directory))
                if (String.Equals(Path.GetExtension(path), ".mp4", StringComparison.OrdinalIgnoreCase) && !Linked(path))
                    files.Add(path);
        }
        catch (IOException error) { errors.Add(Path.GetFileName(directory) + ": " + error.Message); }
        catch (UnauthorizedAccessException error) { errors.Add(Path.GetFileName(directory) + ": " + error.Message); }
    }

    [STAThread]
    private static int Main()
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        Console.Title = "漫剧工坊 · 剧集目录核对（只读视频）";
        try
        {
            string home = AppDomain.CurrentDomain.BaseDirectory;
            var serializer = new JavaScriptSerializer();
            var manifest = serializer.Deserialize<Dictionary<string, object>>(
                File.ReadAllText(Path.Combine(home, "核对清单.json"), Encoding.UTF8));
            var entries = new List<Entry>();
            foreach (Dictionary<string, object> drama in (IEnumerable)manifest["dramas"])
            foreach (Dictionary<string, object> record in (IEnumerable)drama["records"])
            {
                var entry = new Entry {
                    Title = Text(drama, "title"), SeriesId = Text(drama, "seriesId"),
                    Filename = Text(record, "filename"), Hash = Text(record, "sha256").ToLowerInvariant(),
                    Size = Convert.ToInt64(record["bytes"]), Episode = Convert.ToInt32(record["episode"])
                };
                if (entry.Hash.Length != 64 || entry.Hash.Any(c => !Uri.IsHexDigit(c)) || entry.Size < 1 || entry.Episode < 1)
                    throw new InvalidDataException("核对清单中的集数、大小或 SHA256 无效。");
                entries.Add(entry);
            }
            if (entries.Count == 0) throw new InvalidDataException("核对清单中没有下载记录。");
            Console.WriteLine("请在弹出的窗口中选择混放视频的【红果原生】母文件夹。");
            Console.WriteLine("本工具仅核对内容；不会移动、重命名或删除视频，也不会连接网络。\n");
            Application.EnableVisualStyles();
            string root;
            using (var picker = new FolderBrowserDialog())
            {
                picker.Description = "选择混放视频的【红果原生】母文件夹";
                picker.ShowNewFolderButton = false;
                if (picker.ShowDialog() != DialogResult.OK) return 0;
                root = Path.GetFullPath(picker.SelectedPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            }
            if (Linked(root)) throw new InvalidDataException("请选择实际文件夹，不使用目录链接。");
            var files = new List<string>();
            var errors = new List<string>();
            AddFiles(root, files, errors);
            foreach (string directory in Directory.GetDirectories(root))
                if (!Path.GetFileName(directory).StartsWith(".") && !Linked(directory))
                    AddFiles(directory, files, errors);
            var bySize = entries.GroupBy(e => e.Size).ToDictionary(g => g.Key, g => g.ToList());
            int considered = 0, hashed = 0;
            foreach (string path in files)
            {
                considered++;
                try
                {
                    long size = new FileInfo(path).Length;
                    List<Entry> candidates;
                    if (!bySize.TryGetValue(size, out candidates)) continue;
                    Console.WriteLine("核对 {0}/{1}：{2}", considered, files.Count, path.Substring(root.Length));
                    string hash = HashFile(path);
                    hashed++;
                    foreach (Entry entry in candidates.Where(e => e.Hash == hash))
                        entry.Matches.Add(path.Substring(root.Length));
                }
                catch (IOException error) { errors.Add(Path.GetFileName(path) + ": " + error.Message); }
                catch (UnauthorizedAccessException error) { errors.Add(Path.GetFileName(path) + ": " + error.Message); }
            }
            string prefix = "目录核对报告-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff", CultureInfo.InvariantCulture);
            string jsonPath = Path.Combine(root, prefix + ".json");
            string csvPath = Path.Combine(root, prefix + ".csv");
            var rows = entries.Select(e => new {
                title = e.Title, seriesId = e.SeriesId, episode = e.Episode,
                expectedFilename = e.Filename, bytes = e.Size, sha256 = e.Hash,
                status = e.Matches.Count > 0 ? "已按内容确认" : "未找到相同内容", matchedFiles = e.Matches
            }).ToArray();
            var report = new {
                format = 1, videoFilesScanned = files.Count, videoFilesHashed = hashed,
                expectedEpisodes = entries.Count, matchedEpisodes = entries.Count(e => e.Matches.Count > 0),
                note = "仅按文件大小和 SHA256 确认原下载内容。视频被剪辑或重新编码后无法据此确认，不根据文件名或缩略图猜测归属。",
                items = rows, errors = errors
            };
            File.WriteAllText(jsonPath, serializer.Serialize(report), new UTF8Encoding(false));
            using (var output = new StreamWriter(csvPath, false, new UTF8Encoding(true)))
            {
                output.WriteLine("剧名,剧集ID,集号,原文件名,核对结果,当前相对路径");
                foreach (Entry entry in entries)
                    output.WriteLine(String.Join(",", new[] { entry.Title, entry.SeriesId, entry.Episode.ToString(),
                        entry.Filename, entry.Matches.Count > 0 ? "已按内容确认" : "未找到相同内容", String.Join(" | ", entry.Matches) }.Select(Quote)));
            }
            Console.WriteLine("\n完成：确认 {0}/{1} 集。读取失败 {2} 项。", report.matchedEpisodes, entries.Count, errors.Count);
            Console.WriteLine("报告已保存：\n" + jsonPath + "\n" + csvPath);
            Console.WriteLine("未找到的集数可能已被重新编码、剪辑或移到其他目录，不能据此断定视频已丢失。");
            Console.WriteLine("\n把 JSON 报告发回即可；工具没有改动任何视频。按回车关闭。");
            Console.ReadLine();
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("未完成核对：" + error.Message + "\n没有移动、删除或重命名视频。按回车关闭。");
            Console.ReadLine();
            return 1;
        }
    }
}
