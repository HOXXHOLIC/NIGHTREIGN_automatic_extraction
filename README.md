## 工具介绍
通过PP-OCRv5_mobile识别游戏画面，配合固定按键序列完成遗物抽取、词条检查与存档替换。

## 系统要求
windows版本: win10 or win11  
.NET版本: .NET Framework 4.7.2  

---

## 下载与安装

1. 打开 [Releases](https://github.com/<YOUR_GITHUB_NAME>/automatic_extraction/releases/latest)
2. 下载最新的 `automatic_extraction.7z`
3. 解压到一个**不含中文**的文件夹

`main.exe`、`fix_tool.exe` 必须和 `automatic_extraction_UI.exe` 在同一目录。

---


## 快速开始
### 0.最重要的事
无论何时，在你使用脚本前，极其建议你**手动备份存档**，避免存档意外损坏  
`saves/original_save`、`saves/target_save`、`saves/blacklist_save` 会在每次启动 `main.exe` 时被清空并重新生成，**不要把它们当作唯一的存档备份**。 

搭配[B站的视频](https://space.bilibili.com/573664045?spm_id_from=333.1007.0.0)使用更佳，有更清晰的教程

### 1.解压
将automatic_extraction.rar解压到一个**不含中文**的文件目录中  
**不含中文**，这很重要，因为文件目录中如果含有中文会导致paddleocr出现错误，脚本无法正常识别

### 2.设置角色与画面
**开启游戏**，将角色设置为**追踪者**，画面设置为**无边框窗口化**。**关闭游戏**  
脚本使用固定按键序列，不是追踪者会导致按键流程偏移。 

### 3.设置游戏路径与游戏存档路径
右键 `automatic_extraction_UI.exe` → **以管理员身份运行**。
在工具右下角，你能直接粘贴路径或选择路径
- **游戏路径**：包含 `nightreign.exe` 的文件夹
- **存档路径**：通常是 `%APPDATA%\Nightreign`

### 4.设置你的配置
在automatic_extraction_UI.exe中，提供了三个可选遗物槽，通过勾选来决定它是否启用  
只设置三个上限的原因是，遗物槽多了，筛选遗物的效率会降低（~~我懒~~）  
自己设置配置，但第一次启动时我建议将**抽取次数设为3**，来测试该脚本是否能正常运行  
设置完配置后一定要点击**保存配置**

### 5.点击一键启动
点击一键启动后稍等一会，游戏和脚本将会自己启动，届时会有悬浮窗显示日志  

### 6. 如果识别超时

如果日志出现 `enter_rtable 超时` 或 `in_rtable 超时`：

1. 使用 UI 里的 **更改范围** 或 `fix_tool.exe` 重新框选区域
2. 修改后**重启自动化程序**

---

## 截图区域校准：fix_tool

在以下情况需要重新校准：

- 更换分辨率
- 修改 Windows 缩放比例（100% / 125% / 150% 等）
- 更换显示器或显示器排列
- 移动了游戏窗口
- OCR 总是识别不到目标文字

### 使用方法

1. 以管理员身份运行 `fix_tool.exe`，或在 UI 中点击 **更改范围**
2. 选择要修改的区域：
   - 遗物
   - 暗痕
   - 请按任一按钮
3. 点击“修改”，在 5 秒内切换到游戏
4. 在冻结画面上拖拽框选
5. 松开鼠标后：
   - `Enter` 确认
   - `R` 重选
   - `Esc` 或右键取消
6. 保存后会自动写入 `config.yaml`，并生成：
   - `region.png`：给人眼核对的截图
   - `config.yaml.bak`：上一步配置的备份
7. **重启自动化程序**，新区域才会生效

### 注意事项

- 标定时请使用**无边框窗口化 / 窗口化**；独占全屏下无法显示框选覆盖层
- 框选完成后不要移动游戏窗口
- 坐标是绝对物理像素，副屏可能产生负数，这是正常的
- `fix_tool` 已做 DPI 感知；125% 单屏和多屏环境已测试
- 不同显示器布局仍建议重新框选一次

---

## 常见问题
### 1.automatic_extraction_UI.exe无法打开
如果没有安装.NET Framework 4.7.2，会导致它无法打开，上面有安装下载链接，你也可以自行搜索下载  
也可能是安全软件和windowsdefender的原因
### 2.点击一键开始或更改范围后没有反应
这一般是main.exe或fix_tool.exe拦截  
确保安全软件和windowsdefender没有影响它们  
确保main.exe或fix_tool.exe这两个程序与automatic_extraction_UI.exe在同一文件夹中
### 3.点击一键开始后，悬浮窗出现enter_rtable 超时或in_rtable 超时
如果你的物理屏幕分辨率不是1920*1080，那大概率会出现这两种超时  
当你看见这两种超时中的一种时，说明已经等待了10分钟却仍旧无法识别到正确内容  
启动更改范围fix_tool

## 配置文件说明

### `config.yaml`

主程序通用配置：

- `mss_config`：遗物、暗痕、请按任一按钮的截图区域
- `ocr_proins`：OCR 超时和检测间隔
- `key_delay`：按键时长、界面等待、场景加载等待
- `mode_map`：抽取模式对应的按键序列

一般只需要用 `fix_tool` 修改 `mss_config`。  
`key_delay` 可以根据电脑性能微调，电脑性能不好的，将delay参数调高；

`ocr_proins` 和 `mode_map` 不建议随意修改。

### `target_config.json`

UI 保存的目标配置，包含：

- 三组遗物目标
- 抽取模式和次数
- 黑名单
- 游戏路径和存档路径

### 关于log文件夹
automatic_extraction文件夹内会有log文件夹，当发生了无法解决的错误时。  
可以在反馈问题时附上

### 关于save文件夹
automatic_extraction文件夹内会有save文件夹  
original_save文件夹内存档是程序备份的，这个存档的版本是你启动脚本之前的存档版本，可以使用这个版本回档  
target_save文件夹内存档是程序用的回档存档，出货了的话，存档将会保存在这个文件夹里  
blacklist_save是包含黑名单词条的存档，这也许有些多余。但由于ocr误差的原因我决定保留它，这里面的存档都是同时包含目标遗物和黑名单词条的存档  
**在每次启动main.exe**，会将上面这三个文件夹清空

## 免责声明
- 请在使用前手动备份存档。
- 使用本工具可能导致存档损坏或其他损失，作者不承担任何责任。
