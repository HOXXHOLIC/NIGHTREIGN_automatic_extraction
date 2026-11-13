import os
import sys

import mss
import numpy as np

import pydirectinput as pdi
import time

import yaml
import json
import shutil
import logging
from logging.handlers import RotatingFileHandler

import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import threading
import queue
# DPI
import ctypes
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    if hasattr(sys, '_MEIPASS'): # noinspection PyProtectedMember
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))
BASE_PATH = get_base_path()

def resource_path(relative_path):
    return os.path.join(BASE_PATH, relative_path)

# 修复PaddleOCR DLL路径
paddle_libs = os.path.join(BASE_PATH, "Lib", "site-packages", "paddle", "libs")
if os.path.exists(paddle_libs):
    os.environ["PATH"] = paddle_libs + ";" + os.environ.get("PATH", "")
from paddleocr import PaddleOCR

class LogWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.78)
        self.root.attributes("-topmost", True)
        self.root.wm_attributes("-toolwindow", True)
        self.root.configure(bg="black")
        self.root.geometry("600x300+1100+10")
        self.text = ScrolledText(
            self.root,
            bg="black",
            fg="#00FF00",
            insertbackground="white",
            font=("Consolas", 10),
            wrap="word"
        )
        self.text.pack(fill="both", expand=True)
        self.text.config(state="disabled")

        self.offset_x = 0
        self.offset_y = 0

        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.on_move)

        self.root.bind("<Button-3>", self.exit_program)

        self.log_queue = queue.Queue()

        self.text.tag_config("INFO", foreground="#00FF00")
        self.text.tag_config("WARNING", foreground="yellow")
        self.text.tag_config("ERROR", foreground="red")

        self.update_log()

    def start_move(self, event):
        self.offset_x = event.x
        self.offset_y = event.y

    def on_move(self, event):
        x = event.x_root - self.offset_x
        y = event.y_root - self.offset_y
        self.root.geometry(f"+{x}+{y}")

    def exit_program(self, _event=None):
        self.root.destroy()
        os._exit(0)

    def write_log(self, level, message):
        self.log_queue.put((level, message))

    def update_log(self):
        while not self.log_queue.empty():
            level, msg = self.log_queue.get()
            self.text.config(state="normal")
            self.text.insert(
                "end",
                msg + "\n",
                level
            )

            line_count = int(
                self.text.index("end-1c").split(".")[0]
            )
            if line_count > 1000:
                self.text.delete(
                    "1.0",
                    f"{line_count - 1000}.0"
                )
            self.text.see("end")
            self.text.config(state="disabled")
        self.root.after(100, self.update_log)

    def run(self):
        self.root.mainloop()

class TkinterHandler(logging.Handler):
    def __init__(self, floating_log_window):
        super().__init__()
        self.floating_log_window = floating_log_window
    def emit(self, record):
        msg = self.format(record)
        self.floating_log_window.write_log(
            record.levelname,
            msg
        )

logger = logging.getLogger("my_logger")
logger.setLevel(logging.INFO)
logger.propagate = False

def setup_logger():
    floating_log_window = LogWindow()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    file_handler = RotatingFileHandler(
        str(resource_path("log/pylog.log")),
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    tkinter_handler = TkinterHandler(
        floating_log_window
    )
    tkinter_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.addHandler(tkinter_handler)
    return floating_log_window

# 配置
class AppConfig:
    def __init__(self, cfg: dict):

        mss_cfg = cfg["mss_config"]
        self.relic_region = {
            "left": mss_cfg["relic_x"],
            "top": mss_cfg["relic_y"],
            "width": mss_cfg["relic_width"],
            "height": mss_cfg["relic_height"]
        }

        self.dmark_region = {
            "left": mss_cfg["dmark_x"],
            "top": mss_cfg["dmark_y"],
            "width": mss_cfg["dmark_width"],
            "height": mss_cfg["dmark_height"]
        }

        self.start_region = {
            "left": mss_cfg["start_x"],
            "top": mss_cfg["start_y"],
            "width": mss_cfg["start_width"],
            "height": mss_cfg["start_height"]
        }

        ocr_proins = cfg["ocr_proins"]
        self.timeout = ocr_proins["timeout"]
        self.ins_interval = ocr_proins["ins_interval"]

        delay_cfg = cfg["key_delay"]
        self.key_press_duration = delay_cfg["key_press_duration"]
        self.key_press_interval = delay_cfg["key_press_interval"]
        self.delay_ui_short = delay_cfg["delay_ui_short"]
        self.delay_ui_normal = delay_cfg["delay_ui_normal"]
        self.delay_scene_load = delay_cfg["delay_scene_load"]
        self.delay_full_load = delay_cfg["delay_full_load"]
        self.delay_startup = delay_cfg["delay_startup"]

        self.mode_map = cfg["mode_map"]

        self.originalsave_path = resource_path("saves/original_save")
        self.targetsave_path = resource_path("saves/target_save")
        self.blacklistsave_path = resource_path("saves/blacklist_save")

# 传输
class TargetConfig:
    def __init__(self, tg_cfg, bl_data):

        self.set1 = tg_cfg["set1"]
        self.set2 = tg_cfg["set2"]
        self.set3 = tg_cfg["set3"]

        self.extra_mode = tg_cfg["extra_mode"]
        self.extra_times = tg_cfg["extra_times"]

        self.blacklist_index = tg_cfg["black_list"]
        self.blacklist_or = [
            bl_data["blacklist_data"][str(i)]
            for i in self.blacklist_index
            if i != 0 and str(i) in bl_data["blacklist_data"]
        ]
        self.blacklist = text_clean(self.blacklist_or)

        self.game_path = tg_cfg["game_path"]
        self.gamesave_path = tg_cfg["gamesave_path"]

# 运行
class RuntimeState:
    def __init__(self, tg_cfg: TargetConfig):

        self.ocr_result = []

        self.checked_result = 0

        self.set_enable_num = (
            tg_cfg.set1["enable"] +
            tg_cfg.set2["enable"] +
            tg_cfg.set3["enable"]
        )

        self.now_set = tg_cfg.set1

class Context:
    def __init__(self, app_cfg: AppConfig, tg_cfg: TargetConfig):
        self.app = app_cfg
        self.target = tg_cfg
        self.state = RuntimeState(tg_cfg)

        self.times = 0
        self.ocr = None

# 状态机.懒得细写,随便搞一个简单点的
class State:
    INIT = "INIT"
    RUN_MODE = "RUN_MODE"
    CHECK_SET = "CHECK_SET"
    SAVE = "SAVE"
    EXIT = "EXIT"

def init_mss_ocr(ctx: Context):
    ctx.ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        text_detection_model_dir=resource_path("ocr_model/PP-OCRv5_mobile_det"),
        text_recognition_model_dir=resource_path("ocr_model/PP-OCRv5_mobile_rec"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

def init_save(ctx: Context):
    clear_directory(ctx.app.originalsave_path)
    clear_directory(ctx.app.targetsave_path)
    clear_directory(ctx.app.blacklistsave_path)

    copy_all(ctx.target.gamesave_path, ctx.app.originalsave_path)
    copy_all(ctx.target.gamesave_path, ctx.app.targetsave_path)

# ocr
def mss_ocr(ctx: Context, region):
    with mss.MSS() as sct:
        screenshot = sct.grab(region)

    """
    mss.tools.to_png(
        screenshot.rgb,
        screenshot.size,
        output="orl_pic.png"
    """
    img = np.array(screenshot)[:, :, :3]

    results = ctx.ocr.predict(img)
    result = results[0]
    return result["rec_texts"]

def presskey(ctx: Context, key):
    pdi.keyDown(key)
    time.sleep(ctx.app.key_press_duration)
    pdi.keyUp(key)
    time.sleep(ctx.app.key_press_interval)

def move_up(ctx: Context, n):
    for _ in range(n):
        presskey(ctx, "up")

def move_down(ctx: Context, n):
    for _ in range(n):
        presskey(ctx, "down")

def clear_directory(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def copy_all(src, dst):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

def save_replace(ctx: Context):
    if ctx.state.checked_result == 0:
        copy_all(ctx.app.targetsave_path, ctx.target.gamesave_path)
    elif ctx.state.checked_result == 1:
        copy_all(ctx.target.gamesave_path, ctx.app.targetsave_path)
    elif ctx.state.checked_result == 2:
        time_str = time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime())
        created_path = os.path.join(str(ctx.app.blacklistsave_path), time_str)
        os.makedirs(created_path, exist_ok=True)
        copy_all(ctx.target.gamesave_path, created_path)
        copy_all(ctx.app.targetsave_path, ctx.target.gamesave_path)

def extra_loop(ctx: Context):
    for _ in range(ctx.target.extra_times):
        presskey(ctx, "f")
        presskey(ctx, "down")
        presskey(ctx, "f")
        presskey(ctx, "f")
        presskey(ctx, "f")

def run_mode(ctx: Context):
    cfg = ctx.app.mode_map.get(ctx.target.extra_mode)
    presskey(ctx, "m")
    move_down(ctx, cfg["down"])
    presskey(ctx, "f")
    time.sleep(ctx.app.delay_ui_normal)

    if cfg.get("extra"):
        logger.info("进入为王之证抽取循环")
        presskey(ctx, "f")
        time.sleep(ctx.app.delay_ui_short)
        presskey(ctx, "up")
        time.sleep(ctx.app.delay_ui_short)
        move_up(ctx, 10)

    else:
        logger.info("进入为暗痕抽取循环")
        move_up(ctx, cfg.get("up", 1))

    for _ in range(cfg.get("right", 0)):
        presskey(ctx, "right")

    logger.info(f"即将进行抽取,本次抽取{ctx.target.extra_times}次"
                )
    extra_loop(ctx)
    logger.info("抽取结束")

    presskey(ctx, "q")
    time.sleep(ctx.app.delay_ui_short)
    if cfg.get("double_q"):
        presskey(ctx, "q")
        time.sleep(ctx.app.delay_ui_short)

def transitioner(ctx: Context):
    presskey(ctx, "m")
    move_down(ctx, 3)
    presskey(ctx, "f")
    time.sleep(ctx.app.delay_ui_normal)
    presskey(ctx, "f1")

def handle_entry(ctx: Context, entry):
    presskey(ctx, "f")
    move_down(ctx, entry["class"] - 1)
    presskey(ctx, "f")
    move_down(ctx, entry["target"])
    presskey(ctx, "f")
    presskey(ctx, "q")
    presskey(ctx, "q")

def set_check(ctx: Context, s):
    presskey(ctx, "4")
    presskey(ctx, "1")
    # 读取
    ctx.state.now_set = s
    logger.info("现在正在检测")
    logger.info(s)
    # 三个词条
    for entry in (s["entry1"], s["entry2"], s["entry3"]):
        if entry["enable"]:
            handle_entry(ctx, entry)
        presskey(ctx, "down")
    # 拼装三个主词条
    key_attr = s["color"] + s["size"] + s["type"]
    # 找最后一个1的位置
    last = max((i for i, v in enumerate(key_attr) if v == 1), default=-1)
    # 剪裁or置空,用于节省时间
    key_attr = key_attr[:last + 1]
    # 移动主属性
    for i in key_attr:
        presskey(ctx, "down")
        if i == 1:
            presskey(ctx, "f")
    presskey(ctx, "q")
    time.sleep(ctx.app.delay_ui_short)

def has_3cn(ctx: Context):
    count = 0
    for line in ctx.state.ocr_result:
        for ch in line:
            if '\u4e00' <= ch <= '\u9fff':
                count += 1
                if count >= 3:
                    return True
    return False

# 结果清洗
def text_clean(arr):
    def keep_chinese(s):
        result = ""
        for ch in s:
            if '\u4e00' <= ch <= '\u9fff':
                result += ch
        return result
    return [keep_chinese(s) for s in arr]

def simple_match(ctx: Context):
    for oentry in ctx.state.ocr_result:
        for bentry in ctx.target.blacklist:
            if bentry in oentry:
                return True
    return False

def check_entry(ctx: Context):
    if ctx.state.checked_result in (1, 2):
        return
    # OCR + 清洗
    ctx.state.ocr_result = text_clean(mss_ocr(ctx, ctx.app.relic_region))
    logger.info("当前识别到的词条:")
    logger.info(ctx.state.ocr_result)
    logger.info("黑名单词条:")
    logger.info(ctx.target.blacklist)
    # 没识别到
    if not ctx.state.ocr_result or not has_3cn(ctx):
        ctx.state.checked_result = 0
        logger.info("没有识别到目的词条")
        return
    logger.info("识别到目的词条，进行黑名单检测")
    # 黑名单命中
    if ctx.target.blacklist and simple_match(ctx):
        logger.info(r"包含目标黑名单词条，本轮循环结束时将游戏存档存储到saves\blacklist_save文件夹下")
        ctx.state.checked_result = 2
        return
    # 命中目标词条（正常情况）
    logger.info(r"不包含目标黑名单词条，本轮循环结束时将游戏存档储存到saves\target_save文件夹下")
    ctx.state.checked_result = 1
    # 禁用当前set
    s = ctx.state.now_set
    if s == ctx.target.set1:
        ctx.target.set1["enable"] = False
    elif s == ctx.target.set2:
        ctx.target.set2["enable"] = False
    elif s == ctx.target.set3:
        ctx.target.set3["enable"] = False
    ctx.state.set_enable_num -= 1
    logger.info(s)
    logger.info("该组已标记为无效,不再检测该组")

def return_inter(ctx: Context):
    presskey(ctx, "q")
    time.sleep(ctx.app.delay_ui_short)
    logger.info("下一步进行暗痕检测，并判断是否卡键")
    correction_process(ctx)
    logger.info("下一步即将退出并进行存档替换")
    presskey(ctx, "esc")
    time.sleep(0.1)
    presskey(ctx, "f1")
    time.sleep(0.1)
    time.sleep(ctx.app.delay_ui_short)
    time.sleep(0.1)
    presskey(ctx, "up")
    time.sleep(0.1)
    presskey(ctx, "f")
    time.sleep(0.1)
    presskey(ctx, "f")
    time.sleep(0.1)
    presskey(ctx, "left")
    time.sleep(0.1)
    presskey(ctx, "f")
    time.sleep(ctx.app.delay_full_load / 2)
    logger.info("即将替换存档，建议不要在替换完成之前终止或退出程序")
    save_replace(ctx)
    logger.info("替换存档完毕")
    time.sleep(ctx.app.delay_full_load / 2)

def has_more_than_three_chinese(text):
    text = str(text)
    chinese_count = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            chinese_count += 1
            if chinese_count > 3:
                return True
    return False

def is_valid_dmark(text):
    text = str(text)
    has_digit = False
    has_chinese = False
    for ch in text:
        if ch.isdigit():
            has_digit = True
        if '\u4e00' <= ch <= '\u9fff':
            has_chinese = True
        if has_digit and has_chinese:
            break
    return has_digit and not has_chinese

def has_valid_dmark(ctx):
    dmark_num = mss_ocr(ctx, ctx.app.dmark_region)
    if not isinstance(dmark_num, list):
        dmark_num = [dmark_num]
    for text in dmark_num:
        if is_valid_dmark(text):
            return True, text
    return False, dmark_num

def fix_stuck_key(ctx, key="q", key1 = "esc", times=20, interval=0.1):
    logger.info(f"开始执行卡键修复，实际上就是先连续按 {key1} 键 20 次， 再连续按{key}键 20 次\n"
                "它仅能修复简单的卡键"
                )
    for _ in range(times):
        time.sleep(interval)
        presskey(ctx, key1)
    for _ in range(times):
        time.sleep(interval)
        presskey(ctx, key)
    logger.info("卡键修复结束了。")

def spam_press_key(ctx, key="f", duration=7.0, interval=0.1):
    end_time = time.time() + duration
    while time.time() < end_time:
        presskey(ctx, key)
        time.sleep(interval)

# 进入检测
def enter_rtable(ctx: Context):
    start_time = time.time()
    while time.time() - start_time < ctx.app.timeout:
        r_text = mss_ocr(ctx, ctx.app.start_region)
        if isinstance(r_text, list):
            text = "".join(str(item) for item in r_text)
        else:
            text = str(r_text)
        # 如果中文字符超过 3 个，则认为检测成功
        if has_more_than_three_chinese(text):
            logger.info(f"检测到: {text}，正在进入圆桌厅堂")
            spam_press_key(ctx, key="f", duration=ctx.app.delay_scene_load, interval=0.1)
            return
        logger.info("未检测到目标文字，等待2s后重新检查")
        time.sleep(ctx.app.ins_interval)

    logger.error("enter_rtable-timeout")
    logger.error(
        f"在{ctx.app.timeout}秒内未检测到按任一按钮,等待时间过长。\n"
        "可能是游戏未启动或者是start部分截屏框错位。\n"
        "请右键关闭检查配置\n"
        "可以考虑一下执行 UI 里的更改范围或联系我。感谢你的反馈"
    )
    raise RuntimeError("enter_rtable 超时")

# 识别暗痕
def in_rtable(ctx: Context):
    start_time = time.time()
    while time.time() - start_time < ctx.app.timeout:
        is_valid, dmark = has_valid_dmark(ctx)
        if is_valid:
            logger.info(f"检测到暗痕数量! 当前暗痕数: {dmark}")
            time.sleep(ctx.app.delay_ui_short)
            return
        logger.info("未检测到暗痕数量，等待2s后重新检查")
        time.sleep(ctx.app.ins_interval)
    # 超过600秒仍未检测到
    logger.error("in_rtable-timeout")
    logger.error(
        f"在{ctx.app.timeout}秒内未检测到暗痕数量,等待时间过长。\n"
        "可能是游戏加载失败或者是dmark部分截屏框错位。\n"
        "请右键关闭检查配置\n"
        "现在可以考虑一下执行 UI 里的更改范围或联系我。感谢你的反馈"
    )
    raise RuntimeError("in_rtable 超时")

# 识别暗痕,尝试修复
def correction_process(ctx: Context):
    is_valid, result = has_valid_dmark(ctx)
    if is_valid:
        logger.info(f"识别到当前暗痕数: {result}，运行正常")
        return
    logger.warning(
        f"当前暗痕数识别异常，现在识别到: {result}。\n"
        "可能原因是截屏框错位或者卡键。"
        "下面将尝试进行卡键修复。"
    )
    fix_stuck_key(ctx)
    is_valid, result = has_valid_dmark(ctx)
    if is_valid:
        logger.info(f"修复成功，当前暗痕数: {result}。")
        return
    logger.error("correction_process-fixfailed")
    logger.error(
        f"修复后仍未识别到正确的暗痕数，现在识别到: {result}。\n"
        "如果暗痕数不正确或识别到空，大概率是dmark部分截屏框错位。"
        "请鼠标右键点击来结束程序。"
        "现在可以考虑一下执行 UI 里的更改范围或联系我。感谢你的反馈"
    )
    raise RuntimeError("correction_process 修复失败")

def save_enable_state(ctx: Context):
    with open(resource_path("target_config.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    data["set1"]["enable"] = ctx.target.set1["enable"]
    data["set2"]["enable"] = ctx.target.set2["enable"]
    data["set3"]["enable"] = ctx.target.set3["enable"]

    with open(resource_path("target_config.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def config_updata(ctx: Context):
    ctx.state.checked_result = 0
    save_enable_state(ctx)

def loop_controller(ctx: Context):
    state = State.RUN_MODE
    while state != State.EXIT:
        # RUN_MODE
        if state == State.RUN_MODE:
            logger.info("下一步进行请按任一按钮检测")
            enter_rtable(ctx)
            logger.info("下一步进行暗痕检测")
            in_rtable(ctx)
            logger.info("下一步进入遗物抽取")
            run_mode(ctx)
            logger.info("下一步进行暗痕检测，并判断是否卡键")
            correction_process(ctx)
            state = State.CHECK_SET

        # CHECK_SET
        elif state == State.CHECK_SET:
            transitioner(ctx)
            logger.info("下一步进行遗物检查")
            for s in (ctx.target.set1, ctx.target.set2, ctx.target.set3):
                if s["enable"]:
                    set_check(ctx, s)
                    check_entry(ctx)
                if ctx.state.checked_result in (1, 2):
                    break
            state = State.SAVE

        # SAVE+RETURN
        elif state == State.SAVE:
            return_inter(ctx)
            # 配置更新
            config_updata(ctx)

            ctx.times += 1
            logger.info(f"当前轮次 {ctx.times} 已结束即将开始下一轮\n\n\n")

            if ctx.state.set_enable_num == 0:
                logger.info("目标遗物已经全部找到")
                state = State.EXIT
            else:
                state = State.RUN_MODE

def main():
    logger.info("启动脚本成功，正在进行配置初始化")
    with open(resource_path("config.yaml"), "r", encoding="utf-8") as f:
        config1 = yaml.safe_load(f)
    with open(resource_path("target_config.json"), "r", encoding="utf-8") as f:
        target_config1 = json.load(f)
    with open(resource_path("blacklist_data.json"), "r", encoding="utf-8") as f:
        blacklist_data1 = json.load(f)
    app_cfg = AppConfig(config1)
    tg_cfg = TargetConfig(target_config1, blacklist_data1)
    ctx = Context(app_cfg, tg_cfg)

    init_mss_ocr(ctx)
    init_save(ctx)

    if ctx.state.set_enable_num == 0:
        logger.info("没有启用任何目标，请检查是否启用目标!")
        return

    logger.info("配置初始化成功，在" + str(ctx.app.delay_startup) + "秒后，开始尝试进入圆桌厅堂")
    time.sleep(ctx.app.delay_startup)
    logger.info(str(ctx.app.delay_startup) + "秒已经过去")

    try:
        loop_controller(ctx)
    except Exception as e:
        logger.error(f"自动化流程因异常终止: {e}")

if __name__ == "__main__":
    log_fwindow = setup_logger()

    # 主逻辑线程
    threading.Thread(
        target=main,
        daemon=False
    ).start()

    # tkinter主循环
    log_fwindow.run()