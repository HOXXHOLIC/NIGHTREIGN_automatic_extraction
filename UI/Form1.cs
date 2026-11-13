using Newtonsoft.Json;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Drawing;
using System.Text;

namespace automatic_extraction_UI
{
    public partial class Form1 : Form
    {
        //--------------------获取路径--------------------
        public static string GetBasePath()
        {
            return AppDomain.CurrentDomain.BaseDirectory;
        }
        public static string ResourcePath(string relativePath)
        {
            if (string.IsNullOrEmpty(relativePath))
                return GetBasePath();

            relativePath = relativePath.Replace('/', Path.DirectorySeparatorChar)
                                       .Replace('\\', Path.DirectorySeparatorChar);

            return Path.Combine(GetBasePath(), relativePath);
        }
        //--------------------数据类,target_config--------------------
        public class Entry
        {
            public bool enable { get; set; }
            public int @class { get; set; }
            public int target { get; set; }
        }

        public class SetConfig
        {
            public bool enable { get; set; }
            public int[] color { get; set; }
            public int[] size { get; set; }
            public int[] type { get; set; }

            public Entry entry1 { get; set; }
            public Entry entry2 { get; set; }
            public Entry entry3 { get; set; }
        }

        public class TargetConfig
        {
            public SetConfig set1 { get; set; }
            public SetConfig set2 { get; set; }
            public SetConfig set3 { get; set; }

            public int extra_mode { get; set; }
            public int extra_times { get; set; }

            public List<int> black_list { get; set; }

            public string game_path { get; set; }
            public string gamesave_path { get; set; }
        }
        //--------------------数据类,data--------------------
        public class DataEntry
        {
            public string text { get; set; }
        }

        public class DataItem
        {
            public string text { get; set; }
            public List<DataEntry> entries { get; set; }
        }
        //--------------------数据类,blacklist_data--------------------
        public class BlacklistData
        {
            public Dictionary<string, string> blacklist_data { get; set; }
        }
        //--------------------读取target_config--------------------
        private TargetConfig LoadTargetConfig()
        {
            string path = ResourcePath("target_config.json");

            string json = File.ReadAllText(path);

            return JsonConvert.DeserializeObject<TargetConfig>(json);
        }
        //--------------------读取data--------------------
        private List<DataItem> LoadData()
        {
            string path = ResourcePath("data.json");

            string json = File.ReadAllText(path);

            return JsonConvert.DeserializeObject<List<DataItem>>(json);
        }
        //--------------------读取blacklist--------------------
        private BlacklistData LoadBlacklist()
        {
            string path = ResourcePath("blacklist_data.json");

            string json = File.ReadAllText(path);

            return JsonConvert.DeserializeObject<BlacklistData>(json);
        }
        //--------------------修改target_config--------------------
        private void SaveTargetConfig(TargetConfig config)
        {
            string path = ResourcePath("target_config.json");

            string json = JsonConvert.SerializeObject(config, Formatting.Indented);

            File.WriteAllText(path, json);
        }
        //--------------------准备变量--------------------
        private TargetConfig config;
        private List<DataItem> dataList;
        private BlacklistData blacklistData;
        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr hWnd);
        private bool IsProcessRunning(string name)
        {
            return Process.GetProcessesByName(name).Length > 0;
        }
        private void KillProcess(string name)
        {
            var processes = Process.GetProcessesByName(name);

            foreach (var p in processes)
            {
                try
                {
                    p.Kill();
                    p.WaitForExit();
                }
                catch { }
            }
        }
        private void UpdateStatus()
        {
            bool gameRunning = IsProcessRunning("nightreign");
            bool mainRunning = IsProcessRunning("main"); // 如果是 mian 改这里

            // 游戏状态
            lblGameStatus.Text = gameRunning ? "游戏：运行中" : "游戏：未运行";
            lblGameStatus.ForeColor = gameRunning ? Color.Green : Color.Red;

            // 脚本状态
            lblMainStatus.Text = mainRunning ? "脚本：运行中" : "脚本：未运行";
            lblMainStatus.ForeColor = mainRunning ? Color.Green : Color.Red;
        }
        //--------------------extra_mode实现--------------------
        private void InitExtraMode()
        {
            cmbExtraMode.Items.Clear();

            for (int i = 1; i <= 8; i++)
            {
                if (i == 1)
                    cmbExtraMode.Items.Add("暗痕普通模式");
                else if (i == 2)
                    cmbExtraMode.Items.Add("暗痕深夜模式");
                else if (i == 3)
                    cmbExtraMode.Items.Add("为王之证普通模式");
                else if (i == 4)
                    cmbExtraMode.Items.Add("为王之证深夜模式");
                else if (i == 5)
                    cmbExtraMode.Items.Add("暗痕普通模式1.02");
                else if (i == 6)
                    cmbExtraMode.Items.Add("暗痕深夜模式1.02");
                else if (i == 7)
                    cmbExtraMode.Items.Add("为王之证普通模式1.02");
                else if (i == 8)
                    cmbExtraMode.Items.Add("为王之证深夜模式1.02");
            }

            cmbExtraMode.SelectedIndex = config.extra_mode - 1;
        }

        private void cmbExtraMode_SelectedIndexChanged(object sender, EventArgs e)
        {
            config.extra_mode = cmbExtraMode.SelectedIndex + 1;
        }
        //--------------------extra_times实现--------------------
        private void InitExtraTimes()
        {
            numExtraTimes.Value = config.extra_times;
        }

        private void numExtraTimes_ValueChanged(object sender, EventArgs e)
        {
            config.extra_times = (int)numExtraTimes.Value;
        }

        //--------------------black_list实现--------------------
        private void InitBlacklist()
        {
            ComboBox[] cmbs = { cmbBL1, cmbBL2, cmbBL3, cmbBL4, cmbBL5 };
            CheckBox[] chks = { chkBL1, chkBL2, chkBL3, chkBL4, chkBL5 };

            // 填充所有下拉内容
            foreach (var cmb in cmbs)
            {
                cmb.Items.Clear();

                foreach (var kv in blacklistData.blacklist_data)
                {
                    cmb.Items.Add(kv.Value); // 显示文字
                }
            }

            // 初始化值
            for (int i = 0; i < 5; i++)
            {
                int val = config.black_list[i];

                if (val == 0)
                {
                    chks[i].Checked = false;
                    cmbs[i].Enabled = false;
                }
                else
                {
                    chks[i].Checked = true;
                    cmbs[i].Enabled = true;

                    // 找到对应index
                    int index = int.Parse(blacklistData.blacklist_data.Keys.ToList()[val - 1]) - 1;
                    cmbs[i].SelectedIndex = val - 1;
                }
            }
        }
        private void UpdateBlacklist(int i, CheckBox chk, ComboBox cmb)
        {
            if (!chk.Checked)
            {
                cmb.Enabled = false;
                config.black_list[i] = 0;
            }
            else
            {
                cmb.Enabled = true;

                if (cmb.SelectedIndex >= 0)
                    config.black_list[i] = cmb.SelectedIndex + 1;
            }
        }

        private void chkBL1_CheckedChanged(object sender, EventArgs e)
        {
            UpdateBlacklist(0, chkBL1, cmbBL1);
        }

        private void chkBL2_CheckedChanged(object sender, EventArgs e)
        {
            UpdateBlacklist(1, chkBL2, cmbBL2);
        }

        private void chkBL3_CheckedChanged(object sender, EventArgs e)
        {
            UpdateBlacklist(2, chkBL3, cmbBL3);
        }
        private void checkBox4_CheckedChanged(object sender, EventArgs e)
        {
            UpdateBlacklist(3, chkBL4, cmbBL4);
        }

        private void chkBL5_CheckedChanged(object sender, EventArgs e)
        {
            UpdateBlacklist(4, chkBL5, cmbBL5);
        }
        private void cmbBL1_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (chkBL1.Checked)
                config.black_list[0] = cmbBL1.SelectedIndex + 1;
        }

        private void cmbBL2_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (chkBL2.Checked)
                config.black_list[1] = cmbBL2.SelectedIndex + 1;
        }

        private void cmbBL3_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (chkBL3.Checked)
                config.black_list[2] = cmbBL3.SelectedIndex + 1;
        }

        private void cmbBL4_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (chkBL4.Checked)
                config.black_list[3] = cmbBL4.SelectedIndex + 1;
        }

        private void cmbBL5_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (chkBL5.Checked)
                config.black_list[4] = cmbBL5.SelectedIndex + 1;
        }
        //--------------------set实现--------------------
        private void InitSetUI()
        {
            InitSet(grpSet1, config.set1, 1);
            InitSet(grpSet2, config.set2, 2);
            InitSet(grpSet3, config.set3, 3);
        }
        private void InitSet(GroupBox grp, SetConfig set, int idx)
        {
            // enable
            CheckBox chkEnable = (CheckBox)this.Controls.Find($"chkSet{idx}Enable", true)[0];
            chkEnable.Checked = set.enable;
            grp.Enabled = set.enable;

            chkEnable.CheckedChanged += (s, e) =>
            {
                set.enable = chkEnable.Checked;
                grp.Enabled = chkEnable.Checked;
            };

            // color
            for (int i = 0; i < 4; i++)
            {
                CheckBox chk = (CheckBox)this.Controls.Find($"chkSet{idx}Color{i + 1}", true)[0];

                chk.Checked = set.color[i] == 1;

                int index = i;
                chk.CheckedChanged += (s, e) =>
                {
                    set.color[index] = chk.Checked ? 1 : 0;
                };
            }

            // size
            for (int i = 0; i < 3; i++)
            {
                CheckBox chk = (CheckBox)this.Controls.Find($"chkSet{idx}Size{i + 1}", true)[0];

                chk.Checked = set.size[i] == 1;

                int index = i;
                chk.CheckedChanged += (s, e) =>
                {
                    set.size[index] = chk.Checked ? 1 : 0;
                };
            }

            // type
            for (int i = 0; i < 2; i++)
            {
                CheckBox chk = (CheckBox)this.Controls.Find($"chkSet{idx}Type{i + 1}", true)[0];

                chk.Checked = set.type[i] == 1;

                int index = i;
                chk.CheckedChanged += (s, e) =>
                {
                    set.type[index] = chk.Checked ? 1 : 0;
                };
            }

            // entry
            InitEntry(set.entry1, idx, 1);
            InitEntry(set.entry2, idx, 2);
            InitEntry(set.entry3, idx, 3);
        }
        private void InitEntry(Entry entry, int setIdx, int entryIdx)
        {
            CheckBox chk = (CheckBox)this.Controls.Find($"chkSet{setIdx}E{entryIdx}", true)[0];
            ComboBox cmbClass = (ComboBox)this.Controls.Find($"cmbSet{setIdx}E{entryIdx}Class", true)[0];
            ComboBox cmbTarget = (ComboBox)this.Controls.Find($"cmbSet{setIdx}E{entryIdx}Target", true)[0];

            // 填充 class
            cmbClass.Items.Clear();
            foreach (var d in dataList)
            {
                cmbClass.Items.Add(d.text);
            }

            // 初始化 enable
            chk.Checked = entry.enable;
            cmbClass.Enabled = entry.enable;
            cmbTarget.Enabled = entry.enable;

            chk.CheckedChanged += (s, e) =>
            {
                entry.enable = chk.Checked;
                cmbClass.Enabled = chk.Checked;
                cmbTarget.Enabled = chk.Checked;
            };

            // 初始化 class
            if (entry.@class > 0)
                cmbClass.SelectedIndex = entry.@class - 1;

            // class 改变 → 刷新 target
            cmbClass.SelectedIndexChanged += (s, e) =>
            {
                int classIndex = cmbClass.SelectedIndex;

                entry.@class = classIndex + 1;

                cmbTarget.Items.Clear();

                if (classIndex >= 0)
                {
                    var selected = dataList[classIndex];

                    foreach (var item in selected.entries)
                    {
                        cmbTarget.Items.Add(item.text);
                    }

                    cmbTarget.SelectedIndex = 0;
                    entry.target = 1;
                }
            };

            // 初始化 target
            if (entry.@class > 0)
            {
                var selected = dataList[entry.@class - 1];

                cmbTarget.Items.Clear();
                foreach (var item in selected.entries)
                {
                    cmbTarget.Items.Add(item.text);
                }

                if (entry.target > 0)
                    cmbTarget.SelectedIndex = entry.target - 1;
            }

            // target 改变
            cmbTarget.SelectedIndexChanged += (s, e) =>
            {
                entry.target = cmbTarget.SelectedIndex + 1;
            };
        }
        //--------------------path实现--------------------
        private void InitPaths()
        {
            txtGamePath.Text = config.game_path;
            txtSavePath.Text = config.gamesave_path;
        }
        private void txtGamePath_TextChanged(object sender, EventArgs e)
        {
            config.game_path = txtGamePath.Text;
        }
        private void txtSavePath_TextChanged(object sender, EventArgs e)
        {
            config.gamesave_path = txtSavePath.Text;
        }
        private void btnBrowseGame_Click(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = "选择游戏目录";

                if (dlg.ShowDialog() == DialogResult.OK)
                {
                    txtGamePath.Text = dlg.SelectedPath;
                }
                if (!Directory.Exists(txtGamePath.Text))
                {
                    MessageBox.Show("路径不存在！");
                }
            }
        }
        private void btnBrowseSave_Click(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = "选择存档目录";

                if (dlg.ShowDialog() == DialogResult.OK)
                {
                    txtSavePath.Text = dlg.SelectedPath;
                }
            }
        }
        //--------------------一键启动实现--------------------
        private void btnStart_Click(object sender, EventArgs e)
        {
            try
            {
                StartGameAndScript();
            }
            catch (Exception ex)
            {
                MessageBox.Show("启动失败：" + ex.Message);
            }
        }
        private void StartGameAndScript()
        {
            string gameExe = Path.Combine(config.game_path, "nightreign.exe");

            // 检查游戏
            if (!File.Exists(gameExe))
            {
                MessageBox.Show("未能找到 nightreign.exe，请选择正确的游戏路径！");
                return;
            }

            // 关闭已有进程
            KillProcess("nightreign");
            KillProcess("main");

            // 处理steam_appid.txt
            string appidPath = Path.Combine(config.game_path, "steam_appid.txt");

            if (!File.Exists(appidPath) || File.ReadAllText(appidPath).Trim() != "2622380")
            {
                File.WriteAllText(appidPath, "2622380");
            }

            // 启动游戏
            Process gameProcess = Process.Start(new ProcessStartInfo
            {
                FileName = gameExe,
                WorkingDirectory = config.game_path
            });

            // main.exe管理员
            string mainExe = ResourcePath("main.exe");

            Process.Start(new ProcessStartInfo
            {
                FileName = mainExe,
                WorkingDirectory = GetBasePath(),
                Verb = "runas" // 管理员权限
            });

            // 激活窗口
            Task.Run(() =>
            {
                Thread.Sleep(5000);

                if (gameProcess != null)
                {
                    IntPtr handle = IntPtr.Zero;

                    for (int i = 0; i < 10; i++)
                    {
                        gameProcess.Refresh();
                        handle = gameProcess.MainWindowHandle;

                        if (handle != IntPtr.Zero)
                            break;

                        Thread.Sleep(500);
                    }

                    if (handle != IntPtr.Zero)
                    {
                        SetForegroundWindow(handle);
                    }
                }
            });
        }

        public Form1()
        {
            InitializeComponent();
        }
        private void Form1_Load(object sender, EventArgs e)
        {
            config = LoadTargetConfig();
            dataList = LoadData();
            blacklistData = LoadBlacklist();
            var timer = new System.Windows.Forms.Timer();
            timer.Interval = 1000;
            timer.Tick += (s, ev) => UpdateStatus();
            timer.Start();

            InitExtraMode();
            InitExtraTimes();
            InitBlacklist();
            InitSetUI();
            InitPaths();
        }

        private void btnSave_Click(object sender, EventArgs e)
        {
            try
            {
                SaveTargetConfig(config);

                MessageBox.Show("保存成功！", "提示");
            }
            catch (Exception ex)
            {
                MessageBox.Show("保存失败：" + ex.Message);
            }
        }

        private void btnStop_Click(object sender, EventArgs e)
        {
            try
            {
                KillProcess("main");
                MessageBox.Show("脚本已停止");
            }
            catch (Exception ex)
            {
                MessageBox.Show("停止失败：" + ex.Message);
            }
        }

        private void btnRefresh_Click(object sender, EventArgs e)
        {
            try
            {
                config = LoadTargetConfig();

                InitExtraMode();
                InitExtraTimes();
                InitBlacklist();
                InitSetUI();
                InitPaths();

                MessageBox.Show("配置已更新！");
            }
            catch (Exception ex)
            {
                MessageBox.Show("更新失败：" + ex.Message);
            }
        }

        private void btnFix_Click(object sender, EventArgs e)
        {
            try
            {
                string processName = "fix_tool";

                if (Process.GetProcessesByName(processName).Length > 0)
                {
                    MessageBox.Show("fix_tool.exe 已经启动", "提示",
                                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }

                string fixToolExe = ResourcePath("fix_tool.exe");

                Process.Start(new ProcessStartInfo
                {
                    FileName = fixToolExe,
                    WorkingDirectory = GetBasePath(),
                    Verb = "runas"
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show("启动 fix_tool.exe 失败：" + ex.Message,
                                "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
