from __future__ import annotations

import hashlib
import json
import os
import queue
import sys
import threading
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, BooleanVar, Button, Canvas, Checkbutton, Menu, PhotoImage, StringVar, Tk, Toplevel, filedialog, messagebox, simpledialog
from tkinter import ttk
from tkinter import font as tkfont

from desensitizer_app import __version__
from desensitizer_app.candidates import (
    CandidateHit,
    CandidateItem,
    ReplacementSpec,
    next_placeholder,
    prefix_for_entity,
)
from desensitizer_app.core import DesensitizeError, SkippedFile, write_report
from desensitizer_app.enterprise import load_enterprise_profile
from desensitizer_app.history import HistoryRecord, export_history_csv, load_history, save_history
from desensitizer_app.mapping import MappingStore, is_encrypted_mapping
from desensitizer_app.processors import (
    anonymize_file_with_replacements,
    is_known_file,
    restore_file,
    scan_file_candidates,
)
from desensitizer_app.sensitive_table import (
    SensitiveExportRow,
    SensitiveTableRow,
    read_sensitive_table,
    write_sensitive_export,
    write_sensitive_template,
)
from desensitizer_app.telemetry import AnonymousTelemetry
from desensitizer_app.update_checker import check_for_update


APP_DIR = Path(__file__).resolve().parent


def _resource_path(relative_path: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return base_dir / relative_path


def _app_home() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return APP_DIR.parent


APP_HOME = _app_home()
DEFAULT_OUTPUT_DIR = APP_HOME / "输出文件"
APP_NAME = "本地资料脱敏工具"
APP_NAME_EN = "Local Data Desensitizer"
COMPANY_NAME = "艺林万象（北京）科技有限公司"
COMPANY_NAME_EN = "Yilin Wanxiang (Beijing) Technology Co., Ltd."
EDITION_NAME = "专业试用版"
EDITION_NAME_EN = "Professional Trial Edition"
LICENSE_NAME = "GNU AGPLv3-or-later"
CONTACT_EMAIL = "yilinwanxiang@163.com"
HISTORY_FILE = APP_HOME / "history.json"
ENTERPRISE_DIR = APP_HOME / "enterprise"


def _enable_dpi_awareness() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        try:
            # Try Per-Monitor V2 DPI awareness (Windows 10 1703+)
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            try:
                # Fallback to Per-Monitor DPI awareness (Windows 8.1+)
                # PROCESS_PER_MONITOR_DPI_AWARE = 2
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    # Fallback to System DPI awareness
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    try:
                        ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass
    except Exception:
        pass


_enable_dpi_awareness()


class RoundedButton(Canvas):
    """Canvas绘制的圆角按钮，支持hover效果和disabled状态"""
    
    def __init__(
        self,
        parent,
        text: str,
        command=None,
        bg_color: str = "#3B82F6",
        fg_color: str = "#FFFFFF",
        hover_color: str = "#2563EB",
        disabled_bg: str = "#E5E7EB",
        disabled_fg: str = "#9CA3AF",
        radius: int = 8,
        height: int = 32,
        font: tuple = None,
        state: str = "normal",
        auto_width: bool = True,
        **kwargs,
    ):
        self._bg_color = bg_color
        self._fg_color = fg_color
        self._hover_color = hover_color
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._radius = radius
        self._command = command
        self._state = state
        self._is_hovered = False
        self._auto_width = auto_width
        
        if font is None:
            import tkinter.font as tkfont
            font_family = tkfont.nametofont("TkDefaultFont").actual("family")
            font = (font_family, 9, "bold")
        self._font = font
        
        self._text = text
        
        if auto_width and "width" not in kwargs:
            import tkinter.font as tkfont
            test_font = tkfont.Font(font=self._font)
            text_width = test_font.measure(text) + 24
            kwargs["width"] = max(80, text_width)
        
        super().__init__(parent, height=height, highlightthickness=0, **kwargs)
        
        self.bind("<Configure>", self._on_resize)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        
        self._draw()
    
    def _draw(self):
        try:
            self.delete("all")
            w = self.winfo_width()
            h = self.winfo_height()
            if w <= 1 or h <= 1:
                return
            
            r = self._radius
            if self._state == "disabled":
                bg = self._disabled_bg
                fg = self._disabled_fg
            elif self._is_hovered:
                bg = self._hover_color
                fg = self._fg_color
            else:
                bg = self._bg_color
                fg = self._fg_color
            
            self._draw_rounded_rect(0, 0, w, h, r, bg)
            
            self.create_text(
                w // 2, h // 2,
                text=self._text,
                fill=fg,
                font=self._font,
                anchor="center",
            )
        except Exception:
            pass
    
    def _draw_rounded_rect(self, x1, y1, x2, y2, r, fill):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        self.create_polygon(points, fill=fill, smooth=True)
    
    def _on_resize(self, event):
        try:
            self._draw()
        except Exception:
            pass
    
    def _on_enter(self, event):
        if self._state == "normal":
            self._is_hovered = True
            self._draw()
    
    def _on_leave(self, event):
        self._is_hovered = False
        self._draw()
    
    def _on_press(self, event):
        if self._state == "normal":
            self._is_hovered = False
            self._draw()
    
    def _on_release(self, event):
        if self._state == "normal" and self._command:
            try:
                self._command()
            except Exception:
                pass
            w = self.winfo_width()
            h = self.winfo_height()
            self._is_hovered = 0 <= event.x <= w and 0 <= event.y <= h
            self._draw()
    
    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            if self._auto_width:
                import tkinter.font as tkfont
                test_font = tkfont.Font(font=self._font)
                text_width = test_font.measure(self._text) + 24
                new_width = max(80, text_width)
                try:
                    super().configure(width=new_width)
                except Exception:
                    pass
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self.configure(cursor="hand2" if self._state == "normal" else "arrow")
        if "bg_color" in kwargs:
            self._bg_color = kwargs.pop("bg_color")
        if "fg_color" in kwargs:
            self._fg_color = kwargs.pop("fg_color")
        if "hover_color" in kwargs:
            self._hover_color = kwargs.pop("hover_color")
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            try:
                super().configure(**kwargs)
            except Exception:
                pass
        self._draw()
    
    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)


class DesensitizerApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.language = "zh"
        self.current_theme = "light"
        self.active_tab = "anonymize"
        self.enterprise_profile = load_enterprise_profile(ENTERPRISE_DIR)
        self._enterprise_terms_loaded = False
        self.history_records = load_history(HISTORY_FILE)
        self.log_entries: list[str] = []
        self.telemetry = AnonymousTelemetry(APP_HOME, __version__, self._telemetry_edition)
        self.root.title(self._window_title())
        self._app_icon_image: PhotoImage | None = None
        self._enterprise_logo_image: PhotoImage | None = None
        self._set_app_icon()
        self._set_initial_window_geometry()

        self.files: list[Path] = []
        self.restore_files: list[Path] = []
        self.candidates: dict[str, CandidateItem] = {}
        self.candidate_order: list[str] = []
        self.candidate_index = 0
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.output_dir = StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.restore_output_dir = StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.mapping_path = StringVar(value="")
        self.recursive_scan = BooleanVar(value=True)
        self.auto_detect = BooleanVar(value=True)
        self.encrypt_mapping = BooleanVar(value=True)
        self.remove_headers_footers = BooleanVar(value=False)
        self.language_var = StringVar(value=self.language)
        self.theme_var = StringVar(value=self.current_theme)
        self.telemetry_enabled_var = BooleanVar(value=self.telemetry.is_enabled())

        self.edit_value = StringVar(value="")
        self.edit_entity = StringVar(value="CUSTOM_TERM")
        self.edit_replacement = StringVar(value="")
        self.status_var = StringVar(value="就绪")
        self._status_tone = "ready"
        self._busy_operation: str | None = None
        self._busy_button_texts: dict[object, str] = {}
        self.page_title_var = StringVar(value=self._text("tab_anonymize"))
        self.file_count_var = StringVar(value="")
        self.restore_file_count_var = StringVar(value="")
        self._scroll_canvases: list[Canvas] = []
        self._primary_buttons: list[Button] = []
        self._tool_buttons: list[Button] = []
        self._danger_buttons: list[Button] = []
        self._secondary_buttons: list[Button] = []
        self._segmented_buttons: dict[str, object] = {}
        self._toggle_chips: list[tuple[Checkbutton, BooleanVar]] = []
        self._checkboxes: list[dict[str, object]] = []

        self._style = ttk.Style(self.root)
        self.root.option_add("*tearOff", False)
        self._configure_fonts()
        self._setup_menu()
        self._build_ui()
        self._apply_theme(self.current_theme)
        self._poll_queue()
        self.root.after(600, self._initialize_telemetry)

    def _set_app_icon(self) -> None:
        try:
            icon_path = _resource_path("assets/app_icon.ico")
            if icon_path.exists():
                self.root.iconbitmap(default=str(icon_path))
            logo_path = _resource_path("assets/app_logo_256.png")
            if logo_path.exists():
                self._app_icon_image = PhotoImage(file=str(logo_path))
                self.root.iconphoto(True, self._app_icon_image)
        except Exception:
            pass

    def _set_initial_window_geometry(self) -> None:
        left, top, work_width, work_height = self._get_work_area()
        # Use more conservative sizing to avoid layout issues on high DPI
        width = min(max(960, int(work_width * 0.7)), work_width - 50)
        height = min(max(680, int(work_height * 0.78)), work_height - 40)
        x = left + max(0, (work_width - width) // 2)
        y = top + max(0, (work_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(800, 580)

    def _get_work_area(self) -> tuple[int, int, int, int]:
        try:
            import ctypes

            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = Rect()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _text(self, key: str) -> str:
        labels = {
            "zh": {
                "app_title": APP_NAME,
                "settings": "设置",
                "color": "颜色",
                "light": "浅色",
                "blue": "商务蓝",
                "green": "护眼绿",
                "teal": "青绿色",
                "purple": "淡紫色",
                "graphite": "石墨灰",
                "language": "语言",
                "chinese": "中文",
                "english": "English",
                "help": "帮助",
                "history": "历史",
                "upgrade_enterprise": "升级企业版",
                "anonymous_telemetry": "匿名使用统计",
                "telemetry_notice_title": "匿名使用统计",
                "telemetry_notice_message": (
                    "软件可发送匿名使用统计，用于了解安装量和功能使用情况。\n\n"
                    "统计信息只包含随机安装 ID、软件版本、系统类型、事件类型和处理数量；不会上传文件、路径、文件名、敏感词、映射表或文档内容。\n\n"
                    "你可以随时在“设置 -> 匿名使用统计”关闭。是否保持开启？"
                ),
                "telemetry_enabled_title": "匿名统计已开启",
                "telemetry_enabled_message": "匿名使用统计已开启。",
                "telemetry_disabled_title": "匿名统计已关闭",
                "telemetry_disabled_message": "匿名使用统计已关闭，本软件不会发送使用统计。",
                "mapping_password_help": "映射表密码说明",
                "contact": "联系方式",
                "contact_title": "联系方式",
                "contact_message": f"如需企业定制、部署支持或问题反馈，请联系：\n{CONTACT_EMAIL}",
                "enterprise_upgrade_title": "升级企业版",
                "enterprise_upgrade_heading": "升级企业版",
                "enterprise_upgrade_summary": (
                    "适合需要统一处理客户资料、合同、凭证、员工信息、项目资料，或把文档交给 AI 前先脱敏的团队。"
                    "企业版可预置专属 Logo、企业敏感词库和行业字段规则，让员工打开即可按公司规则处理。"
                ),
                "enterprise_upgrade_contact": "企业合作与定制咨询邮箱：\n{email}",
                "enterprise_upgrade_extra": "企业版可统一交付 Logo、企业敏感词库、行业字段规则、内部审计脱敏模板和部署支持。",
                "open_enterprise_guide": "查看服务说明",
                "copy_email": "复制邮箱",
                "close": "关闭",
                "copy_email_title": "邮箱已复制",
                "copy_email_message": "已复制联系邮箱：{email}",
                "enterprise_guide_missing_title": "未找到说明文件",
                "enterprise_guide_missing_message": "未在 marketing 目录找到服务说明文件。请通过邮箱联系我们获取：{email}",
                "enterprise_guide_open_failed_title": "打开说明失败",
                "enterprise_guide_open_failed_message": "无法自动打开服务说明文件：{error}\n\n你也可以通过邮箱联系我们：{email}",
                "enterprise_terms_title": "企业词库",
                "enterprise_terms_help_message": (
                    "企业专属词库不是让普通用户每次自己选择文件。\n\n"
                    "企业定制版交付时，词库会放在安装目录的 enterprise 文件夹中：\n"
                    "1. profile.json：企业名称、界面标识和少量默认词\n"
                    "2. terms.csv / terms.txt：企业专属词库\n"
                    "3. logo.png：企业 Logo（可选）\n\n"
                    "软件启动后会自动读取这些文件，并把词汇写入“业务敏感词”文本框。"
                    "用户只需要添加待脱敏文件、扫描候选信息、确认后开始脱敏。\n\n"
                    "如果界面显示“未配置”，说明当前是通用版或尚未放入正式企业配置；"
                    "管理员可用“导入补充词库文件”临时导入 CSV/TXT。"
                ),
                "open_source_license": "开源许可",
                "about": "关于",
                "about_title": "关于",
                "mapping_password_help_title": "映射表密码说明",
                "mapping_password_help_message": (
                    "脱敏时如果勾选“加密映射表（推荐）”，系统会要求用户自己设置并确认一个映射表密码。\n\n"
                    "还原时输入的就是这个密码，不是软件出品方生成的授权码，也不会保存在程序中。\n\n"
                    "密码遗失后无法恢复映射表中的原文。建议保存在企业密码管理器、项目交付记录或其他安全位置。"
                ),
                "license_title": "开源许可",
                "license_message": (
                    "本工具采用 GNU AGPLv3-or-later 授权。\n\n"
                    "分发可执行文件时，应同时提供对应源码或清晰的源码获取方式。\n"
                    "当前发布包应包含 AGPL-3.0.txt、NOTICE.md、SOURCE_CODE.md 和 source-code.zip。\n\n"
                    "请阅读随包许可证文件了解完整权利和义务。"
                ),
                "language_title": "语言设置",
                "language_message": "界面语言已切换。",
                "tab_anonymize": "文件脱敏",
                "tab_restore": "按映射还原",
                "run_log": "运行日志",
                "task_config": "任务配置",
                "step1_title": "步骤 1: 添加文件",
                "step2_title": "步骤 2: 配置敏感词",
                "step3_title": "步骤 3: 执行脱敏",
                "input_files": "输入文件",
                "input_files_hint": "添加需要处理的文件或文件夹",
                "upload_title": "将文件或文件夹添加到此处",
                "upload_hint": "点击上传文件，或使用下方按钮添加文件夹",
                "file_count": "已添加 {count} 个文件",
                "add_file": "添加文件",
                "add_folder": "添加文件夹",
                "recursive_folders": "含子文件夹",
                "remove_selected": "移除选中",
                "clear": "清空",
                "file_path": "文件路径",
                "output_dir": "输出目录",
                "choose": "选择",
                "custom_terms": "敏感词设置",
                "sensitive_table": "候选敏感信息",
                "sensitive_table_hint": "扫描或导入后，在表格中确认每一项是否启用和替换值。",
                "download_template": "模板",
                "import_sensitive_table": "导入",
                "export_sensitive_table": "导出",
                "dialog_sensitive_table": "选择敏感词表",
                "dialog_save_template": "保存敏感词模板",
                "dialog_export_sensitive_table": "导出候选敏感词",
                "template_saved_title": "模板已生成",
                "template_saved": "敏感词模板已保存：{path}",
                "sensitive_imported": "已导入 {count} 条敏感词设置。",
                "sensitive_import_error_title": "敏感词设置错误",
                "sensitive_import_error_intro": "导入文件存在冲突或缺失项，请修改后重新导入。",
                "sensitive_error_col_row": "行号",
                "sensitive_error_col_value": "原文",
                "sensitive_error_col_replacement": "替换为",
                "sensitive_error_col_enabled": "启用",
                "sensitive_error_col_error": "错误说明",
                "sensitive_exported_title": "导出完成",
                "sensitive_exported": "候选敏感词已导出：{path}",
                "no_candidates_to_export": "当前没有可导出的候选敏感信息。",
                "enterprise_terms_loaded_as_candidates": "已载入 {count} 条企业内置词。",
                "enterprise_terms_status": "企业专属词库已自动加载：{count} 条",
                "enterprise_terms_status_empty": "当前为通用版：未配置企业专属词库",
                "enterprise_terms_help": "企业专版启动时会自动读取安装目录 enterprise 下的 profile.json、terms.csv、terms.txt，并写入下方；员工无需每次导入。",
                "enterprise_terms_help_empty": "企业专属词库只会出现在企业定制版中。通用版可用“导入补充词库文件”临时导入 CSV/TXT。",
                "restore_builtin_terms": "恢复内置词库",
                "view_terms_help": "查看说明",
                "import_terms_file": "导入补充词库文件",
                "dialog_terms_file": "选择词库文件",
                "terms_imported_title": "词库处理完成",
                "terms_import_failed_title": "词库导入失败",
                "terms_imported": "已导入 {count} 条新词汇。",
                "terms_restored": "已补入 {count} 条内置词。重复词不会重复添加。",
                "terms_already_loaded": "内置企业词库已在下方文本框中，无需重复加载。",
                "encrypt_mapping": "加密映射表",
                "remove_headers_footers": "去除页眉页脚",
                "mapping_password_title": "映射表密码",
                "mapping_password_prompt": "请为本次加密映射表设置密码。还原时必须输入同一个密码；请妥善保存，遗失后无法恢复。",
                "mapping_password_confirm_prompt": "请再次输入映射表密码。",
                "mapping_password_mismatch": "两次输入的密码不一致。",
                "mapping_password_cancelled": "已取消。映射表加密需要输入密码。",
                "auto_detect": "自动",
                "auto_scan": "自动扫描",
                "scan_candidates": "扫描",
                "scan_sensitive": "扫描敏感信息",
                "start_anonymize": "开始脱敏",
                "candidate_frame": "候选敏感信息",
                "enable_all": "全启",
                "disable_all": "全禁",
                "toggle_selected": "切换",
                "delete_selected": "删除",
                "clear_candidates": "清空",
                "col_enabled": "启用",
                "col_entity": "类型",
                "col_value": "原文",
                "col_context": "主体/范围",
                "col_replacement": "替换为",
                "col_count": "次数",
                "col_files": "文件",
                "col_source": "来源",
                "col_action": "操作",
                "action_delete": "删除",
                "edit_or_add": "编辑或新增",
                "value": "原文",
                "entity": "类型",
                "replacement": "替换为",
                "generate_placeholder": "生成占位符",
                "save_edit": "保存修改",
                "add_manual": "新增手动条目",
                "status_ready": "就绪",
                "status_scanning": "正在扫描候选信息...",
                "status_anonymizing": "正在脱敏...",
                "status_restoring": "正在还原...",
                "status_done": "处理完成",
                "history_title": "历史记录",
                "history_empty": "暂无历史记录。",
                "history_export": "导出记录",
                "history_delete": "删除选中",
                "history_clear": "清空历史",
                "history_exported": "历史记录已导出：{path}",
                "history_confirm_clear": "确定清空全部历史记录吗？",
                "history_col_time": "时间",
                "history_col_action": "操作",
                "history_col_files": "文件数",
                "history_col_ok": "成功",
                "history_col_failed": "失败",
                "history_col_output": "输出目录",
                "history_action_anonymize": "脱敏",
                "history_action_restore": "还原",
                "history_export_dialog": "导出历史记录",
                "restore_files": "待还原文件",
                "mapping_json": "映射表 JSON",
                "start_restore": "开始还原",
                "dialog_select_anonymize": "选择需要脱敏的文件",
                "dialog_select_folder": "选择需要扫描的文件夹",
                "dialog_select_restore": "选择需要还原的文件",
                "dialog_output_dir": "选择输出目录",
                "dialog_mapping": "选择映射表",
                "supported_files": "支持的文件",
                "all_files": "全部文件",
                "missing_files_title": "缺少文件",
                "scan_missing_files": "请先添加需要扫描的文件或文件夹。",
                "manual_mode_title": "手动模式",
                "manual_mode_message": "自动识别已关闭。你可以直接在候选表下方手动新增条目。",
                "anonymize_missing_files": "请先添加需要脱敏的文件或文件夹。",
                "candidate_error_title": "候选信息有误",
                "restore_missing_files": "请先添加需要还原的文件。",
                "restore_failed_title": "还原失败",
                "restore_done_title": "还原完成",
                "restore_done_error_title": "还原完成（有错误）",
                "restore_result_ok": "还原成功文件数",
                "restore_result_failed": "还原失败文件数",
                "restore_result_output": "输出目录",
                "missing_mapping_title": "缺少映射表",
                "missing_mapping_message": "请选择脱敏时生成的映射表 JSON。",
                "missing_value_title": "缺少原文",
                "missing_value_message": "请输入需要脱敏的原文。",
                "select_one_title": "请选择一项",
                "select_one_message": "请先在候选表中选择一项再保存修改。",
                "incomplete_title": "信息不完整",
                "incomplete_message": "原文和替换值都不能为空。",
                "duplicate_title": "重复候选",
                "duplicate_message": "相同类型和原文的候选项已存在。",
                "anonymize_failed_title": "脱敏失败",
                "anonymize_done_title": "脱敏完成",
                "anonymize_done_error_title": "脱敏完成（有错误）",
                "anonymize_done_skip_title": "脱敏完成（有跳过）",
                "result_ok": "处理成功文件数",
                "result_skipped": "跳过文件数",
                "result_failed": "处理失败文件数",
                "result_counts": "替换统计",
                "result_mapping": "映射表",
                "result_report": "报告",
                "yes": "是",
                "no": "否",
                "manual": "手动",
                "auto": "自动",
                "excel_entity": "表格主体",
                "enabled_candidate_empty": "启用的候选项中存在空原文或空替换值。",
                "same_value_multiple_replacements": "同一原文存在不同替换值：{value}",
                "same_replacement_multiple_values": "同一替换值被多个原文使用：{replacement}",
                "no_enabled_candidates": "没有启用的候选项。请先扫描候选信息或手动新增条目。",
                "more_files": "{first}, {second} ... 共{count}个",
            },
            "en": {
                "app_title": APP_NAME_EN,
                "settings": "Settings",
                "color": "Color",
                "light": "Light",
                "blue": "Business Blue",
                "green": "Soft Green",
                "teal": "Teal",
                "purple": "Lavender",
                "graphite": "Graphite",
                "language": "Language",
                "chinese": "中文",
                "english": "English",
                "help": "Help",
                "history": "History",
                "upgrade_enterprise": "Upgrade to Enterprise",
                "anonymous_telemetry": "Anonymous Usage Statistics",
                "telemetry_notice_title": "Anonymous Usage Statistics",
                "telemetry_notice_message": (
                    "The general edition can send anonymous usage statistics so we can understand installation count and feature usage.\n\n"
                    "Statistics only include a random installation ID, app version, operating system, event type, and aggregate counts. "
                    "Files, paths, filenames, sensitive terms, mapping files, and document content are never uploaded.\n\n"
                    "You can turn this off anytime in Settings -> Anonymous Usage Statistics. Keep it enabled?"
                ),
                "telemetry_enabled_title": "Telemetry Enabled",
                "telemetry_enabled_message": "Anonymous usage statistics are enabled for the general edition.",
                "telemetry_disabled_title": "Telemetry Disabled",
                "telemetry_disabled_message": "Anonymous usage statistics are disabled. The app will not send usage statistics.",
                "mapping_password_help": "Mapping Password Help",
                "contact": "Contact",
                "contact_title": "Contact",
                "contact_message": f"For enterprise customization, deployment support, or feedback, contact:\n{CONTACT_EMAIL}",
                "enterprise_upgrade_title": "Upgrade to Enterprise",
                "enterprise_upgrade_heading": "Upgrade to Enterprise",
                "enterprise_upgrade_summary": (
                    "Built for teams that need to process client data, contracts, vouchers, employee records, project files, "
                    "or documents before sending them to AI tools. Enterprise builds can include your logo, sensitive terms, "
                    "and industry field rules so employees can follow company rules immediately."
                ),
                "enterprise_upgrade_contact": "Enterprise customization email:\n{email}",
                "enterprise_upgrade_extra": "Enterprise builds can include unified branding, company term libraries, industry field rules, internal audit templates, and deployment support.",
                "open_enterprise_guide": "Open Service Guide",
                "copy_email": "Copy Email",
                "close": "Close",
                "copy_email_title": "Email Copied",
                "copy_email_message": "Contact email copied: {email}",
                "enterprise_guide_missing_title": "Guide Not Found",
                "enterprise_guide_missing_message": "No service guide was found in the marketing folder. Contact us by email: {email}",
                "enterprise_guide_open_failed_title": "Cannot Open Guide",
                "enterprise_guide_open_failed_message": "The service guide could not be opened automatically: {error}\n\nYou can also contact us by email: {email}",
                "enterprise_terms_title": "Enterprise Terms",
                "enterprise_terms_help_message": (
                    "Built-in enterprise terms are not files that regular users must choose every time.\n\n"
                    "In an enterprise build, the terms are delivered in the enterprise folder next to the executable:\n"
                    "1. profile.json: enterprise identity, UI labels, and small default term set\n"
                    "2. terms.csv / terms.txt: enterprise-specific terms\n"
                    "3. logo.png: optional enterprise logo\n\n"
                    "The app reads these files on startup and writes the terms into the Business Sensitive Terms box. "
                    "Users only need to add files, scan candidates, review them, and start desensitization.\n\n"
                    "If the UI says not configured, this is a general build or the formal enterprise configuration has not been added. "
                    "Administrators can use Import Supplemental Term File to add CSV/TXT terms temporarily."
                ),
                "open_source_license": "Open Source License",
                "about": "About",
                "about_title": "About",
                "mapping_password_help_title": "Mapping Password Help",
                "mapping_password_help_message": (
                    "When Encrypt Mapping File is selected during desensitization, the user sets and confirms the mapping password.\n\n"
                    "The same password is required during restoration. It is not a license code generated by the publisher and is not stored by the program.\n\n"
                    "If the password is lost, the original values in the mapping file cannot be recovered. Store it in a password manager or other secure project record."
                ),
                "license_title": "Open Source License",
                "license_message": (
                    "This tool is licensed under GNU AGPLv3-or-later.\n\n"
                    "When distributing the executable, provide the corresponding source code or a clear way to obtain it.\n"
                    "The package should include AGPL-3.0.txt, NOTICE.md, SOURCE_CODE.md, and source-code.zip.\n\n"
                    "Read the included license files for the full rights and obligations."
                ),
                "language_title": "Language",
                "language_message": "The interface language has been changed.",
                "tab_anonymize": "Desensitize Files",
                "tab_restore": "Restore by Mapping",
                "run_log": "Run Log",
                "task_config": "Task Configuration",
                "step1_title": "Step 1: Add Files",
                "step2_title": "Step 2: Configure Sensitive Words",
                "step3_title": "Step 3: Execute Desensitization",
                "input_files": "Input Files",
                "input_files_hint": "Add files or folders to process",
                "upload_title": "Add files or folders here",
                "upload_hint": "Click to upload files, or use Add Folder below",
                "file_count": "{count} file(s) added",
                "add_file": "Add Files",
                "add_folder": "Add Folder",
                "recursive_folders": "Recursive Subfolders",
                "remove_selected": "Remove Selected",
                "clear": "Clear",
                "file_path": "File Path",
                "output_dir": "Output Folder",
                "choose": "Choose",
                "custom_terms": "Sensitive Term Settings",
                "sensitive_table": "Sensitive Candidates",
                "sensitive_table_hint": "Scan or import, then confirm enabled items and replacements in the table.",
                "download_template": "Download Template",
                "import_sensitive_table": "Import Table",
                "export_sensitive_table": "Export Candidates",
                "dialog_sensitive_table": "Select sensitive term table",
                "dialog_save_template": "Save sensitive term template",
                "dialog_export_sensitive_table": "Export candidates",
                "template_saved_title": "Template Created",
                "template_saved": "Template saved: {path}",
                "sensitive_imported": "{count} sensitive term(s) imported.",
                "sensitive_import_error_title": "Sensitive Term Error",
                "sensitive_import_error_intro": "The import file has conflicts or missing values. Fix it and import again.",
                "sensitive_error_col_row": "Row",
                "sensitive_error_col_value": "Original",
                "sensitive_error_col_replacement": "Replace With",
                "sensitive_error_col_enabled": "Enabled",
                "sensitive_error_col_error": "Error",
                "sensitive_exported_title": "Export Complete",
                "sensitive_exported": "Candidates exported: {path}",
                "no_candidates_to_export": "There are no candidates to export.",
                "enterprise_terms_loaded_as_candidates": "{count} built-in enterprise term(s) loaded.",
                "enterprise_terms_status": "Built-in enterprise terms loaded automatically: {count}",
                "enterprise_terms_status_empty": "General build: no enterprise terms configured",
                "enterprise_terms_help": "Enterprise builds automatically read profile.json, terms.csv, and terms.txt from the enterprise folder and place them below; users do not import them every time.",
                "enterprise_terms_help_empty": "Enterprise terms appear only in customized enterprise builds. In the general build, use Import Supplemental Term File for temporary CSV/TXT terms.",
                "restore_builtin_terms": "Restore Built-in Terms",
                "view_terms_help": "View Help",
                "import_terms_file": "Import Supplemental Term File",
                "dialog_terms_file": "Select term file",
                "terms_imported_title": "Term Processing Complete",
                "terms_import_failed_title": "Term Import Failed",
                "terms_imported": "{count} new term(s) imported.",
                "terms_restored": "{count} built-in term(s) restored. Duplicates are not added again.",
                "terms_already_loaded": "The built-in enterprise terms are already in the text box; no need to load them again.",
                "encrypt_mapping": "Encrypt Mapping File (Recommended)",
                "remove_headers_footers": "Remove Headers/Footers",
                "mapping_password_title": "Mapping Password",
                "mapping_password_prompt": "Set a password for this encrypted mapping file. The same password is required for restoration; keep it safe because it cannot be recovered.",
                "mapping_password_confirm_prompt": "Enter the mapping password again.",
                "mapping_password_mismatch": "The two passwords do not match.",
                "mapping_password_cancelled": "Cancelled. Mapping encryption requires a password.",
                "auto_detect": "Automatically Detect Sensitive Information",
                "auto_scan": "Auto Scan",
                "scan_candidates": "Scan Candidates",
                "scan_sensitive": "Scan Sensitive Info",
                "start_anonymize": "Start Desensitizing",
                "candidate_frame": "Sensitive Candidates",
                "enable_all": "Enable All",
                "disable_all": "Disable All",
                "toggle_selected": "Toggle Selected",
                "delete_selected": "Delete Selected",
                "clear_candidates": "Clear Candidates",
                "col_enabled": "Enabled",
                "col_entity": "Type",
                "col_value": "Original",
                "col_context": "Subject / Scope",
                "col_replacement": "Replace With",
                "col_count": "Count",
                "col_files": "Files",
                "col_source": "Source",
                "col_action": "Action",
                "action_delete": "Delete",
                "edit_or_add": "Edit or Add",
                "value": "Original",
                "entity": "Type",
                "replacement": "Replace With",
                "generate_placeholder": "Generate Placeholder",
                "save_edit": "Save Changes",
                "add_manual": "Add Manual Entry",
                "status_ready": "Ready",
                "status_scanning": "Scanning candidates...",
                "status_anonymizing": "Desensitizing...",
                "status_restoring": "Restoring...",
                "status_done": "Done",
                "history_title": "History",
                "history_empty": "No history yet.",
                "history_export": "Export",
                "history_delete": "Delete Selected",
                "history_clear": "Clear History",
                "history_exported": "History exported: {path}",
                "history_confirm_clear": "Clear all history records?",
                "history_col_time": "Time",
                "history_col_action": "Action",
                "history_col_files": "Files",
                "history_col_ok": "OK",
                "history_col_failed": "Failed",
                "history_col_output": "Output Folder",
                "history_action_anonymize": "Desensitize",
                "history_action_restore": "Restore",
                "history_export_dialog": "Export history",
                "restore_files": "Files to Restore",
                "mapping_json": "Mapping JSON",
                "start_restore": "Start Restore",
                "dialog_select_anonymize": "Select files to desensitize",
                "dialog_select_folder": "Select folder to scan",
                "dialog_select_restore": "Select files to restore",
                "dialog_output_dir": "Select output folder",
                "dialog_mapping": "Select mapping file",
                "supported_files": "Supported files",
                "all_files": "All files",
                "missing_files_title": "Missing Files",
                "scan_missing_files": "Please add files or folders to scan first.",
                "manual_mode_title": "Manual Mode",
                "manual_mode_message": "Automatic detection is disabled. You can add manual entries below the candidate table.",
                "anonymize_missing_files": "Please add files or folders to desensitize first.",
                "candidate_error_title": "Candidate Error",
                "restore_missing_files": "Please add files to restore first.",
                "restore_failed_title": "Restore Failed",
                "restore_done_title": "Restore Complete",
                "restore_done_error_title": "Restore Complete (with errors)",
                "restore_result_ok": "Successful restores",
                "restore_result_failed": "Failed restores",
                "restore_result_output": "Output folder",
                "missing_mapping_title": "Missing Mapping",
                "missing_mapping_message": "Please select the mapping JSON generated during desensitization.",
                "missing_value_title": "Missing Original Text",
                "missing_value_message": "Please enter the original text to desensitize.",
                "select_one_title": "Select One Item",
                "select_one_message": "Select one candidate in the table before saving changes.",
                "incomplete_title": "Incomplete Information",
                "incomplete_message": "Original text and replacement value cannot be empty.",
                "duplicate_title": "Duplicate Candidate",
                "duplicate_message": "A candidate with the same type and original text already exists.",
                "anonymize_failed_title": "Desensitizing Failed",
                "anonymize_done_title": "Desensitizing Complete",
                "anonymize_done_error_title": "Desensitizing Complete (with errors)",
                "anonymize_done_skip_title": "Desensitizing Complete (with skipped files)",
                "result_ok": "Successful files",
                "result_skipped": "Skipped files",
                "result_failed": "Failed files",
                "result_counts": "Replacement counts",
                "result_mapping": "Mapping file",
                "result_report": "Report",
                "yes": "Yes",
                "no": "No",
                "manual": "Manual",
                "auto": "Auto",
                "excel_entity": "Excel Entity",
                "enabled_candidate_empty": "An enabled candidate has empty original text or replacement value.",
                "same_value_multiple_replacements": "The same original text has different replacements: {value}",
                "same_replacement_multiple_values": "The same replacement is used by multiple originals: {replacement}",
                "no_enabled_candidates": "No candidates are enabled. Scan candidates first or add manual entries.",
                "more_files": "{first}, {second} ... {count} total",
            },
        }
        return labels.get(self.language, labels["zh"]).get(key, key)

    def _window_title(self) -> str:
        base_title = self.enterprise_profile.product_name or self._text("app_title")
        suffix = self.enterprise_profile.app_title_suffix
        return f"{base_title} - {suffix}" if suffix else base_title

    def _telemetry_edition(self) -> str:
        return "enterprise" if self.enterprise_profile.enabled else "general"

    def _edition_label(self) -> str:
        return self.enterprise_profile.edition_name or (EDITION_NAME_EN if self.language == "en" else EDITION_NAME)

    def _configure_fonts(self) -> None:
        try:
            current_scaling = float(self.root.tk.call("tk", "scaling"))
            # On Windows 11 with high DPI, ensure minimum scaling
            # Don't force a higher scaling as it may cause layout issues
            if current_scaling < 1.0:
                self.root.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass
        families = set(tkfont.families(self.root))
        if "Microsoft YaHei UI" in families:
            family = "Microsoft YaHei UI"
        elif "Segoe UI Variable Text" in families:
            family = "Segoe UI Variable Text"
        else:
            family = "Segoe UI"
        font_specs = {
            "TkDefaultFont": {"size": 9},
            "TkTextFont": {"size": 9},
            "TkMenuFont": {"size": 9},
            "TkHeadingFont": {"size": 9, "weight": "bold"},
            "TkCaptionFont": {"size": 9},
            "TkSmallCaptionFont": {"size": 8},
            "TkTooltipFont": {"size": 8},
        }
        for name, options in font_specs.items():
            try:
                named_font = tkfont.nametofont(name)
                named_font.configure(family=family, **options)
            except Exception:
                continue
        try:
            self.root.option_add("*Font", tkfont.nametofont("TkDefaultFont"))
            self.root.option_add("*Menu.font", tkfont.nametofont("TkMenuFont"))
        except Exception:
            pass

    def _setup_menu(self) -> None:
        self.menu_bar = Menu(self.root)
        self.root.configure(menu=self.menu_bar)
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        if self.menu_bar.index("end") is not None:
            self.menu_bar.delete(0, END)

        settings_menu = Menu(self.menu_bar)
        color_menu = Menu(settings_menu)
        for theme_key in ("light", "blue", "green", "teal", "purple", "graphite"):
            color_menu.add_radiobutton(
                label=self._text(theme_key),
                variable=self.theme_var,
                value=theme_key,
                command=lambda value=theme_key: self._apply_theme(value),
            )
        settings_menu.add_cascade(label=self._text("color"), menu=color_menu)

        language_menu = Menu(settings_menu)
        language_menu.add_radiobutton(
            label=self._text("chinese"),
            variable=self.language_var,
            value="zh",
            command=lambda: self._set_language("zh"),
        )
        language_menu.add_radiobutton(
            label=self._text("english"),
            variable=self.language_var,
            value="en",
            command=lambda: self._set_language("en"),
        )
        settings_menu.add_cascade(label=self._text("language"), menu=language_menu)
        self.menu_bar.add_cascade(label=self._text("settings"), menu=settings_menu)
        self.menu_bar.add_command(label=self._text("upgrade_enterprise"), command=self._show_enterprise_upgrade)
        self.menu_bar.add_command(label=self._text("history"), command=self._show_history_dialog)

        help_menu = Menu(self.menu_bar)
        help_menu.add_command(label=self._text("mapping_password_help"), command=self._show_mapping_password_help)
        help_menu.add_command(label=self._text("contact"), command=self._show_contact)
        help_menu.add_command(label=self._text("open_source_license"), command=self._show_license_notice)
        help_menu.add_separator()
        help_menu.add_command(label=self._text("about"), command=self._show_about)
        self.menu_bar.add_cascade(label=self._text("help"), menu=help_menu)

    def _set_language(self, language: str) -> None:
        if language == self.language:
            return
        self.language = language
        self.language_var.set(language)
        self.root.title(self._window_title())
        self._refresh_menu()
        self._rebuild_ui()
        messagebox.showinfo(self._text("language_title"), self._text("language_message"))

    def _initialize_telemetry(self) -> None:
        self._register_installation()
        self._check_for_update()
        self.telemetry.mark_notice_seen()

    def _register_installation(self) -> None:
        flag_dir = Path(os.environ.get("APPDATA", Path.home())) / "DesensitizerTool"
        flag_file = flag_dir / "registered.flag"
        if flag_file.exists():
            return
        endpoint = self.telemetry.endpoint
        if not endpoint:
            return
        try:
            installation_id = self.telemetry.settings.installation_id
            url = f"{endpoint.rstrip('/')}/register?id={installation_id}"
            with urllib.request.urlopen(url, timeout=5):
                flag_dir.mkdir(parents=True, exist_ok=True)
                flag_file.write_text(datetime.now().isoformat(), encoding="utf-8")
        except Exception:
            pass

    def _check_for_update(self) -> None:
        try:
            cfg_path = APP_HOME / "telemetry.json"
            if not cfg_path.exists() and getattr(sys, "frozen", False):
                cfg_path = Path(sys._MEIPASS) / "telemetry.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                url = cfg.get("update_check_url", "")
                if url:
                    check_for_update(__version__, url)
        except Exception:
            pass

    def _set_telemetry_enabled_from_menu(self) -> None:
        enabled = bool(self.telemetry_enabled_var.get())
        self.telemetry.set_enabled(enabled)
        self.telemetry.mark_notice_seen()
        title = self._text("telemetry_enabled_title") if enabled else self._text("telemetry_disabled_title")
        message = self._text("telemetry_enabled_message") if enabled else self._text("telemetry_disabled_message")
        messagebox.showinfo(title, message)

    def _track_usage(self, event_name: str, properties: dict[str, object] | None = None) -> None:
        self.telemetry.track(event_name, properties or {})

    def _rebuild_ui(self) -> None:
        for child in self.root.winfo_children():
            if child is self.menu_bar or isinstance(child, Menu):
                continue
            child.destroy()
        self._build_ui()

        for path in self.files:
            self.file_list.insert("", END, values=(str(path),))
        for path in self.restore_files:
            self.restore_file_list.insert("", END, values=(str(path),))
        self._refresh_candidate_tree()
        self._refresh_file_counts()
        self._apply_theme(self.current_theme)

    def _apply_theme(self, theme: str) -> None:
        self.current_theme = theme
        self.theme_var.set(theme)
        palettes = {
            "light": {
                "bg": "#f5f7fa", "fg": "#1a1d21", "muted": "#6b7280",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#f9fafb", "border": "#e5e7eb",
                "button": "#f3f4f6", "accent": "#3b82f6", "accent_active": "#2563eb",
                "accent_fg": "#ffffff", "select": "#dbeafe", "select_fg": "#1e3a5f",
                "sidebar": "#0f172a", "sidebar_border": "#1e293b",
                "sidebar_active": "#1e293b", "sidebar_hover": "#1a2332",
                "hover": "#f3f4f6", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#22c55e", "heading_bg": "#f9fafb",
            },
            "blue": {
                "bg": "#f0f4f8", "fg": "#0f172a", "muted": "#64748b",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#f8fafc", "border": "#cbd5e1",
                "button": "#e2e8f0", "accent": "#0ea5e9", "accent_active": "#0284c7",
                "accent_fg": "#ffffff", "select": "#e0f2fe", "select_fg": "#0c4a6e",
                "sidebar": "#0c4a6e", "sidebar_border": "#075985",
                "sidebar_active": "#075985", "sidebar_hover": "#0369a1",
                "hover": "#e2e8f0", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#10b981", "heading_bg": "#f1f5f9",
            },
            "green": {
                "bg": "#f0fdf4", "fg": "#14532d", "muted": "#6b7280",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#f0fdf4", "border": "#bbf7d0",
                "button": "#dcfce7", "accent": "#22c55e", "accent_active": "#16a34a",
                "accent_fg": "#ffffff", "select": "#dcfce7", "select_fg": "#14532d",
                "sidebar": "#14532d", "sidebar_border": "#166534",
                "sidebar_active": "#166534", "sidebar_hover": "#15803d",
                "hover": "#dcfce7", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#22c55e", "heading_bg": "#f0fdf4",
            },
            "teal": {
                "bg": "#f0fdfa", "fg": "#134e4a", "muted": "#6b7280",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#f0fdfa", "border": "#99f6e4",
                "button": "#ccfbf1", "accent": "#14b8a6", "accent_active": "#0d9488",
                "accent_fg": "#ffffff", "select": "#ccfbf1", "select_fg": "#134e4a",
                "sidebar": "#134e4a", "sidebar_border": "#115e59",
                "sidebar_active": "#115e59", "sidebar_hover": "#0f766e",
                "hover": "#ccfbf1", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#14b8a6", "heading_bg": "#f0fdfa",
            },
            "purple": {
                "bg": "#faf5ff", "fg": "#581c87", "muted": "#6b7280",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#faf5ff", "border": "#d8b4fe",
                "button": "#f3e8ff", "accent": "#a855f7", "accent_active": "#9333ea",
                "accent_fg": "#ffffff", "select": "#f3e8ff", "select_fg": "#581c87",
                "sidebar": "#581c87", "sidebar_border": "#6b21a8",
                "sidebar_active": "#6b21a8", "sidebar_hover": "#7e22ce",
                "hover": "#f3e8ff", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#a855f7", "heading_bg": "#faf5ff",
            },
            "graphite": {
                "bg": "#f9fafb", "fg": "#1f2937", "muted": "#6b7280",
                "surface": "#ffffff", "field": "#ffffff", "field_alt": "#f9fafb", "border": "#d1d5db",
                "button": "#e5e7eb", "accent": "#6b7280", "accent_active": "#4b5563",
                "accent_fg": "#ffffff", "select": "#e5e7eb", "select_fg": "#1f2937",
                "sidebar": "#1f2937", "sidebar_border": "#374151",
                "sidebar_active": "#374151", "sidebar_hover": "#4b5563",
                "hover": "#e5e7eb", "danger": "#ef4444", "danger_bg": "#fef2f2",
                "success": "#6b7280", "heading_bg": "#f3f4f6",
            },
        }
        palette = palettes.get(theme, palettes["light"])
        if sys.platform.startswith("win") and "vista" in self._style.theme_names():
            self._style.theme_use("vista")
        elif "clam" in self._style.theme_names():
            self._style.theme_use("clam")
        elif "vista" in self._style.theme_names():
            self._style.theme_use("vista")

        self._palette = palette
        self.root.configure(background=palette["bg"])
        self._style.configure(".", background=palette["bg"], foreground=palette["fg"], font=tkfont.nametofont("TkDefaultFont"))
        self._style.configure("TFrame", background=palette["bg"])
        self._style.configure("App.TFrame", background=palette["bg"])
        self._style.configure("Workspace.TFrame", background=palette["bg"])
        self._style.configure("Sidebar.TFrame", background=palette["sidebar"])
        self._style.configure("Surface.TFrame", background=palette["surface"], relief="flat")
        self._style.configure("Section.TFrame", background=palette["surface"], relief="flat")
        self._style.configure("Card.TFrame", background=palette["surface"], bordercolor=palette["border"], lightcolor=palette["surface"], darkcolor=palette["border"], relief="flat", borderwidth=1)
        self._style.configure(
            "Content.TFrame",
            background=palette["surface"],
            relief="flat",
            borderwidth=0,
        )
        self._style.configure(
            "Panel.TFrame",
            background=palette["surface"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            relief="solid",
            borderwidth=1,
        )
        self._style.configure("Toolbar.TFrame", background=palette["surface"])
        self._style.configure("Statusbar.TFrame", background=palette["surface"])
        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        default_font = tkfont.nametofont("TkDefaultFont")
        button_font = (font_family, 9)
        heading_font = (font_family, 9, "bold")
        self._style.configure("TLabelframe", background=palette["surface"], foreground=palette["fg"], bordercolor=palette["border"], relief="solid")
        self._style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["fg"], font=heading_font)
        self._style.configure("Card.TLabelframe", background=palette["surface"], foreground=palette["fg"], bordercolor=palette["border"], relief="solid")
        self._style.configure("Card.TLabelframe.Label", background=palette["bg"], foreground=palette["fg"], font=heading_font)
        self._style.configure("TLabel", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("Surface.TLabel", background=palette["surface"], foreground=palette["fg"])
        self._style.configure("Header.TLabel", background=palette["bg"], foreground=palette["fg"], font=(font_family, 11, "bold"))
        self._style.configure("PageTitle.TLabel", background=palette["bg"], foreground=palette["fg"], font=(font_family, 12, "bold"))
        self._style.configure("SidebarTitle.TLabel", background=palette["sidebar"], foreground="#ffffff", font=(font_family, 10, "bold"))
        self._style.configure("SidebarMuted.TLabel", background=palette["sidebar"], foreground="#94a3b8")
        self._style.configure("SidebarVersion.TLabel", background=palette["sidebar"], foreground="#64748b", font=(font_family, 8))
        self._style.configure("SectionTitle.TLabel", background=palette["surface"], foreground=palette["fg"], font=(font_family, 10, "bold"))
        self._style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["muted"])
        self._style.configure("SurfaceMuted.TLabel", background=palette["surface"], foreground=palette["muted"])
        self._style.configure("Status.TLabel", background=palette["surface"], foreground=palette["muted"], padding=(14, 8))
        self._style.configure("StatusAccent.TLabel", background=palette["surface"], foreground=palette["accent"], padding=(14, 6), font=(font_family, 9))
        self._style.configure("StatusSuccess.TLabel", background=palette["surface"], foreground=palette["success"], padding=(14, 6), font=(font_family, 9))
        self._style.configure("StatusDanger.TLabel", background=palette["surface"], foreground=palette["danger"], padding=(14, 6), font=(font_family, 9))
        self._style.configure("TCheckbutton", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("Surface.TCheckbutton", background=palette["surface"], foreground=palette["fg"], padding=(2, 2))
        self._style.map(
            "Surface.TCheckbutton",
            background=[("active", palette["surface"])],
            foreground=[("active", palette["fg"])],
        )
        self._style.configure("TButton", background=palette["button"], foreground=palette["fg"], bordercolor=palette["border"], focusthickness=0, focuscolor=palette["button"], padding=(8, 4), relief="flat", borderwidth=1, font=button_font)
        self._style.map("TButton", background=[("active", palette["hover"]), ("pressed", palette["select"])], foreground=[("active", palette["fg"]), ("disabled", palette["muted"])])
        self._style.configure("Tool.TButton", background=palette["surface"], foreground=palette["fg"], bordercolor=palette["border"], focusthickness=0, focuscolor=palette["surface"], padding=(8, 4), relief="flat", borderwidth=1, font=button_font)
        self._style.map("Tool.TButton", background=[("active", palette["hover"]), ("pressed", palette["select"])], foreground=[("active", palette["fg"])], bordercolor=[("active", palette["accent"]), ("pressed", palette["accent"])])
        self._style.configure("Secondary.TButton", background=palette["surface"], foreground=palette["fg"], bordercolor=palette["border"], focusthickness=0, focuscolor=palette["surface"], padding=(8, 4), relief="flat", borderwidth=1, font=button_font)
        self._style.map("Secondary.TButton", background=[("active", palette["hover"]), ("pressed", palette["select"])], foreground=[("active", palette["fg"]), ("disabled", palette["muted"])], bordercolor=[("active", palette["accent"]), ("pressed", palette["accent"]), ("disabled", palette["border"])])
        self._style.configure("Danger.TButton", background=palette["surface"], foreground=palette["danger"], bordercolor=palette["border"], focusthickness=0, focuscolor=palette["surface"], padding=(8, 4), relief="flat", borderwidth=1, font=button_font)
        self._style.map("Danger.TButton", background=[("active", palette["danger_bg"]), ("pressed", palette["danger_bg"])], foreground=[("active", palette["danger"]), ("disabled", palette["muted"])], bordercolor=[("active", palette["danger"]), ("pressed", palette["danger"])])
        self._style.configure("Accent.TButton", background=palette["accent"], foreground=palette["accent_fg"], bordercolor=palette["accent"], focusthickness=0, focuscolor=palette["accent"], padding=(12, 6), relief="flat", borderwidth=0, font=(font_family, 9, "bold"))
        self._style.map(
            "Accent.TButton",
            background=[("disabled", palette["button"]), ("active", palette["accent_active"]), ("pressed", palette["accent_active"])],
            foreground=[("disabled", palette["muted"]), ("active", palette["accent_fg"]), ("pressed", palette["accent_fg"])],
            bordercolor=[("disabled", palette["border"]), ("active", palette["accent_active"]), ("pressed", palette["accent_active"])],
        )
        self._style.configure("TEntry", fieldbackground=palette["field"], foreground=palette["fg"], bordercolor=palette["border"], padding=(6, 5), font=default_font)
        self._style.configure("TCombobox", fieldbackground=palette["field"], foreground=palette["fg"], font=default_font)
        self._style.configure("TNotebook", background=palette["bg"])
        self._style.configure("TNotebook.Tab", background=palette["button"], foreground=palette["fg"], padding=(12, 6), font=button_font)
        self._style.map("TNotebook.Tab", background=[("selected", palette["field"])], foreground=[("selected", palette["fg"])])
        self._style.configure("Vertical.TScrollbar", width=10, background=palette["button"], troughcolor=palette["surface"], bordercolor=palette["border"], arrowcolor=palette["muted"])
        self._style.configure("Horizontal.TScrollbar", width=10, background=palette["button"], troughcolor=palette["surface"], bordercolor=palette["border"], arrowcolor=palette["muted"])
        self._style.configure("Treeview", background=palette["field"], fieldbackground=palette["field"], foreground=palette["fg"], rowheight=24, bordercolor=palette["border"], lightcolor=palette["border"], darkcolor=palette["border"], font=default_font)
        self._style.configure("Treeview.Heading", background=palette["heading_bg"], foreground=palette["fg"], relief="flat", font=heading_font)
        self._style.map("Treeview", background=[("selected", palette["select"])], foreground=[("selected", palette["select_fg"])])
        self._style.map("Treeview.Heading", background=[("active", palette["hover"])])

        for canvas in getattr(self, "_scroll_canvases", []):
            canvas.configure(background=palette["bg"])
        for button in getattr(self, "_primary_buttons", []):
            self._style_primary_button(button, palette)
        for button in getattr(self, "_tool_buttons", []):
            self._style_tool_button(button, palette)
        for button in getattr(self, "_secondary_buttons", []):
            self._style_secondary_button(button, palette)
        for button in getattr(self, "_danger_buttons", []):
            self._style_danger_button(button, palette)
        for key, button in getattr(self, "_segmented_buttons", {}).items():
            self._style_segmented_button(button, palette, selected=(key == self.active_tab))
        for chip, variable in getattr(self, "_toggle_chips", []):
            self._style_toggle_chip(chip, variable, palette)
        for checkbox in getattr(self, "_checkboxes", []):
            self._style_checkbox(checkbox, palette)
        self._apply_tree_styles()
        self._refresh_action_state()
        self._update_statusbar_style()

    def _prepare_dialog(self, dialog: Toplevel) -> None:
        palette = getattr(self, "_palette", None)
        if palette:
            dialog.configure(background=palette["surface"])

    def _status_style_for_tone(self, tone: str) -> str:
        if tone in {"busy", "accent"}:
            return "StatusAccent.TLabel"
        if tone == "success":
            return "StatusSuccess.TLabel"
        if tone in {"error", "danger"}:
            return "StatusDanger.TLabel"
        return "Status.TLabel"

    def _update_statusbar_style(self) -> None:
        label = getattr(self, "statusbar_label", None)
        if not label:
            return
        try:
            label.configure(style=self._status_style_for_tone(getattr(self, "_status_tone", "ready")))
        except Exception:
            pass

    def _set_status(self, message: str, tone: str = "ready", flash: bool = False) -> None:
        self.status_var.set(message)
        self._status_tone = tone
        self._update_statusbar_style()
        if flash:
            self.root.after(1800, self._restore_ready_status)

    def _restore_ready_status(self) -> None:
        if getattr(self, "_busy_operation", None):
            return
        self._status_tone = "ready"
        self._update_statusbar_style()

    def _processing_text(self) -> str:
        return "Processing..." if self.language == "en" else "处理中..."

    def _begin_operation(self, operation: str, button: object | None = None) -> None:
        self._busy_operation = operation
        target_buttons = [
            getattr(self, "scan_action_button", None),
            getattr(self, "anonymize_action_button", None),
            getattr(self, "restore_action_button", None),
        ]
        if button and button not in target_buttons:
            target_buttons.append(button)
        for item in target_buttons:
            if not item:
                continue
            try:
                self._busy_button_texts.setdefault(item, str(item.cget("text")))
                item.configure(state="disabled")
                palette = getattr(self, "_palette", None)
                if palette and item in getattr(self, "_primary_buttons", []):
                    self._style_primary_button(item, palette)
            except Exception:
                pass
        if button:
            try:
                button.configure(text=self._processing_text())
                palette = getattr(self, "_palette", None)
                if palette and button in getattr(self, "_primary_buttons", []):
                    self._style_primary_button(button, palette)
            except Exception:
                pass

    def _end_operation(self) -> None:
        self._busy_operation = None
        for button, text in list(self._busy_button_texts.items()):
            try:
                button.configure(text=text, state="normal")
                palette = getattr(self, "_palette", None)
                if palette and button in getattr(self, "_primary_buttons", []):
                    self._style_primary_button(button, palette)
            except Exception:
                pass
        self._busy_button_texts.clear()
        self._refresh_page_action()
        self._refresh_action_state()

    def _empty_text(self, kind: str) -> str:
        if self.language == "en":
            messages = {
                "files": "No files added yet. Use Add Files or Add Folder to begin.",
                "restore": "No restore files added yet. Add files and choose a mapping file.",
                "candidates": "No candidates yet. Run Auto Scan, import a table, or add one manually.",
            }
        else:
            messages = {
                "files": "暂无文件。请添加文件或文件夹开始脱敏。",
                "restore": "暂无待还原文件。请添加文件并选择映射表。",
                "candidates": "暂无候选项。请自动扫描、导入表格或手动新增。",
            }
        return messages[kind]

    def _apply_tree_styles(self) -> None:
        palette = getattr(self, "_palette", None)
        if not palette:
            return
        trees = [
            getattr(self, "file_list", None),
            getattr(self, "restore_file_list", None),
            getattr(self, "candidate_tree", None),
        ]
        for tree in trees:
            if not tree:
                continue
            try:
                tree.tag_configure("odd", background=palette["field"])
                tree.tag_configure("even", background=palette["field_alt"])
                tree.tag_configure("empty", background=palette["field"], foreground=palette["muted"])
                tree.tag_configure("candidate_on", foreground=palette["success"])
                tree.tag_configure("candidate_off", foreground=palette["muted"])
                tree.tag_configure("danger", foreground=palette["danger"])
            except Exception:
                pass

    def _refresh_file_placeholders(self) -> None:
        if hasattr(self, "file_list"):
            self._retag_tree_rows(self.file_list, {"__empty_files__"})
            self._refresh_tree_placeholder(self.file_list, "__empty_files__", self._empty_text("files"), bool(self.files))
        if hasattr(self, "restore_file_list"):
            self._retag_tree_rows(self.restore_file_list, {"__empty_restore__"})
            self._refresh_tree_placeholder(self.restore_file_list, "__empty_restore__", self._empty_text("restore"), bool(self.restore_files))

    def _refresh_tree_placeholder(self, tree: ttk.Treeview, iid: str, text: str, has_items: bool) -> None:
        if tree.exists(iid):
            tree.delete(iid)
        if not has_items:
            tree.insert("", END, iid=iid, values=(text,), tags=("empty",))

    def _retag_tree_rows(self, tree: ttk.Treeview, excluded: set[str]) -> None:
        index = 0
        for item in tree.get_children():
            if item in excluded:
                continue
            tree.item(item, tags=("even" if index % 2 else "odd",))
            index += 1

    def _show_license_notice(self) -> None:
        messagebox.showinfo(self._text("license_title"), self._text("license_message"))

    def _show_mapping_password_help(self) -> None:
        messagebox.showinfo(self._text("mapping_password_help_title"), self._text("mapping_password_help_message"))

    def _show_enterprise_terms_help(self) -> None:
        messagebox.showinfo(self._text("enterprise_terms_title"), self._text("enterprise_terms_help_message"))

    def _show_contact(self) -> None:
        messagebox.showinfo(self._text("contact_title"), self._text("contact_message"))

    def _show_enterprise_upgrade(self) -> None:
        dialog = Toplevel(self.root)
        self._prepare_dialog(dialog)
        dialog.title(self._text("enterprise_upgrade_title"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog_width = 880
        dialog_height = 640
        wrap_width = dialog_width - 70
        self._center_child_window(dialog, dialog_width, dialog_height)

        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        container = ttk.Frame(dialog, style="Surface.TFrame", padding=(36, 32, 36, 28))
        container.pack(fill=BOTH, expand=True)

        ttk.Label(
            container,
            text=self._text("enterprise_upgrade_heading"),
            style="Surface.TLabel",
            font=(font_family, 16, "bold"),
            wraplength=wrap_width,
            justify=LEFT,
        ).pack(fill="x", anchor="w")
        ttk.Label(
            container,
            text=self._text("enterprise_upgrade_summary"),
            style="Surface.TLabel",
            font=(font_family, 11),
            wraplength=wrap_width,
            justify=LEFT,
        ).pack(fill="x", pady=(14, 20), anchor="w")

        ttk.Label(
            container,
            text=self._text("enterprise_upgrade_contact").format(email=CONTACT_EMAIL),
            style="Surface.TLabel",
            font=(font_family, 12, "bold"),
            wraplength=wrap_width,
            justify=LEFT,
        ).pack(fill="x", anchor="w")

        ttk.Label(
            container,
            text=self._text("enterprise_upgrade_extra"),
            style="SurfaceMuted.TLabel",
            font=(font_family, 11),
            wraplength=wrap_width,
            justify=LEFT,
        ).pack(fill="x", anchor="w", pady=(12, 0))

        button_row = ttk.Frame(container, style="Surface.TFrame")
        button_row.pack(fill="x", side="bottom")
        self._secondary_button(button_row, text=self._text("close"), command=dialog.destroy).pack(side=RIGHT)
        self._secondary_button(
            button_row,
            text=self._text("open_enterprise_guide"),
            command=lambda: self._open_enterprise_service_guide(dialog),
        ).pack(side=RIGHT, padx=(0, 8))
        self._secondary_button(
            button_row,
            text=self._text("copy_email"),
            command=lambda: self._copy_contact_email(dialog),
        ).pack(side=RIGHT, padx=(0, 8))

        dialog.grab_set()
        dialog.focus_set()

    def _copy_contact_email(self, parent: Toplevel | None = None) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(CONTACT_EMAIL)
        self.root.update()
        messagebox.showinfo(
            self._text("copy_email_title"),
            self._text("copy_email_message").format(email=CONTACT_EMAIL),
            parent=parent or self.root,
        )

    def _open_enterprise_service_guide(self, parent: Toplevel | None = None) -> None:
        guide_path = self._enterprise_service_guide_path()
        if guide_path is None:
            messagebox.showinfo(
                self._text("enterprise_guide_missing_title"),
                self._text("enterprise_guide_missing_message").format(email=CONTACT_EMAIL),
                parent=parent or self.root,
            )
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(guide_path))  # type: ignore[attr-defined]
            else:
                import webbrowser

                webbrowser.open(guide_path.as_uri())
        except Exception as exc:
            messagebox.showerror(
                self._text("enterprise_guide_open_failed_title"),
                self._text("enterprise_guide_open_failed_message").format(error=exc, email=CONTACT_EMAIL),
                parent=parent or self.root,
            )

    def _enterprise_service_guide_path(self) -> Path | None:
        search_dirs = [APP_HOME / "marketing", APP_DIR / "marketing", APP_DIR.parent / "marketing"]
        for marketing_dir in search_dirs:
            for filename in ("合作企业定制化服务说明.pdf", "合作企业定制化服务说明.md"):
                guide_path = marketing_dir / filename
                if guide_path.exists():
                    return guide_path
        return None

    def _center_child_window(self, window: Toplevel, width: int, height: int) -> None:
        self.root.update_idletasks()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = max(self.root.winfo_width(), width)
        root_height = max(self.root.winfo_height(), height)
        x = root_x + max(0, (root_width - width) // 2)
        y = root_y + max(0, (root_height - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _fit_child_window(self, window: Toplevel, min_width: int, min_height: int, pad_width: int = 0, pad_height: int = 0) -> None:
        window.update_idletasks()
        width = max(min_width, window.winfo_reqwidth() + pad_width)
        height = max(min_height, window.winfo_reqheight() + pad_height)
        self._center_child_window(window, width, height)

    def _show_about(self) -> None:
        enterprise_lines = ""
        if self.enterprise_profile.enabled:
            if self.language == "en":
                enterprise_lines = (
                    f"Customer: {self.enterprise_profile.customer_name or self.enterprise_profile.display_name}\n"
                    f"Enterprise Terms: {len(self.enterprise_profile.terms)}\n"
                )
            else:
                enterprise_lines = (
                    f"客户：{self.enterprise_profile.customer_name or self.enterprise_profile.display_name}\n"
                    f"企业内置词库：{len(self.enterprise_profile.terms)} 条\n"
                )
        if self.language == "en":
            message = (
                f"{self.enterprise_profile.product_name or APP_NAME_EN}\n"
                f"Version: {__version__}\n"
                f"Edition: {self._edition_label()}\n"
                f"{enterprise_lines}"
                f"Publisher: {COMPANY_NAME_EN}\n\n"
                f"License: {LICENSE_NAME}\n"
                "This tool processes supported files locally by default."
            )
        else:
            message = (
                f"{self.enterprise_profile.product_name or APP_NAME}\n"
                f"版本：{__version__}\n"
                f"版本类型：{self._edition_label()}\n"
                f"{enterprise_lines}"
                f"出品方：{COMPANY_NAME}\n\n"
                f"许可证：{LICENSE_NAME}\n"
                "本工具默认在本地处理支持的文件。"
            )
        messagebox.showinfo(self._text("about_title"), message)

    def _build_ui(self) -> None:
        self._scroll_canvases.clear()
        self._primary_buttons.clear()
        self._tool_buttons.clear()
        self._danger_buttons.clear()
        self._secondary_buttons.clear()
        self._segmented_buttons.clear()
        self._toggle_chips.clear()
        self._checkboxes.clear()
        self._build_enterprise_banner()

        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill=BOTH, expand=True)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", width=120)
        sidebar.pack(side=LEFT, fill="y")
        sidebar.pack_propagate(False)

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", padx=8, pady=(10, 0))
        ttk.Label(brand, text=self.enterprise_profile.product_name or self._text("app_title"), style="SidebarTitle.TLabel", wraplength=104).pack(anchor="w")
        ttk.Label(brand, text=self._edition_label(), style="SidebarMuted.TLabel").pack(anchor="w", pady=(2, 0))

        # Brand / nav separator
        palette = getattr(self, "_palette", {"sidebar_border": "#283347"})
        sep = Canvas(sidebar, height=1, borderwidth=0, highlightthickness=0, background=palette["sidebar_border"])
        sep.pack(fill="x", padx=8, pady=(8, 6))

        nav = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav.pack(fill="x", padx=4, pady=(0, 6))
        self._segmented_button(nav, "anonymize", "\U0001f512  " + self._text("tab_anonymize")).pack(fill="x", pady=(0, 2))
        self._segmented_button(nav, "restore", "\U0001f504  " + self._text("tab_restore")).pack(fill="x")

        # Version at sidebar bottom
        version_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
        version_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        ttk.Label(version_frame, text=f"v{__version__}", style="SidebarVersion.TLabel").pack(anchor="w")

        workspace = ttk.Frame(shell, style="Workspace.TFrame")
        workspace.pack(side=LEFT, fill=BOTH, expand=True)

        workspace.grid_rowconfigure(1, weight=1)
        workspace.grid_columnconfigure(0, weight=1)

        topbar = ttk.Frame(workspace, style="Workspace.TFrame")
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
        ttk.Label(topbar, textvariable=self.page_title_var, style="PageTitle.TLabel").pack(side=LEFT)

        content_host = ttk.Frame(workspace, style="Workspace.TFrame")
        content_host.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 4))
        self.anonymize_tab, self.anonymize_frame = self._create_scrollable_tab(content_host)
        self.restore_tab, self.restore_frame = self._create_scrollable_tab(content_host)

        statusbar = ttk.Frame(workspace, style="Statusbar.TFrame", height=28)
        statusbar.grid(row=2, column=0, sticky="ew", padx=0, pady=(0, 2))
        statusbar.grid_propagate(False)
        self.statusbar_label = ttk.Label(statusbar, textvariable=self.status_var, style="Status.TLabel")
        self.statusbar_label.pack(side=LEFT, padx=(10, 0))

        self._build_anonymize_tab()
        self._build_restore_tab()
        self._tab_pages = {"anonymize": self.anonymize_tab, "restore": self.restore_tab}
        self._show_main_tab(self.active_tab)
        self._refresh_file_counts()
        self._refresh_page_action()
        self._refresh_action_state()

    def _build_enterprise_banner(self) -> None:
        if not self.enterprise_profile.enabled:
            return
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=(10, 0))
        logo_path = self.enterprise_profile.logo_path
        if logo_path:
            try:
                logo = PhotoImage(file=str(logo_path))
                factor = 1
                while logo.width() // factor > 120 or logo.height() // factor > 36:
                    factor += 1
                if factor > 1:
                    logo = logo.subsample(factor, factor)
                self._enterprise_logo_image = logo
                ttk.Label(frame, image=logo).pack(side=LEFT, padx=(0, 8))
            except Exception as exc:
                self._log("WARN", f"Cannot load enterprise logo: {exc}")
        label_text = self.enterprise_profile.banner_text
        if not label_text:
            label_text = f"{self.enterprise_profile.display_name}专用版"
        term_count = len(self.enterprise_profile.terms)
        ttk.Label(frame, text=f"{label_text} | 企业内置词库 {term_count} 条").pack(side=LEFT)

    def _create_scrollable_tab(self, parent: ttk.Frame) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(parent, style="Workspace.TFrame")
        canvas = Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Workspace.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event) -> None:
            content.update_idletasks()
            canvas.itemconfigure(window_id, width=max(0, event.width - 20), height=max(content.winfo_reqheight(), event.height))

        def bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")

        def on_mousewheel(event) -> None:
            if self._event_originates_from_scrollable_tree(event, getattr(self, "candidate_tree", None)):
                return "break"
            canvas.yview_scroll(int(-event.delta / 120), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_content)
        outer.bind("<Enter>", bind_mousewheel)
        outer.bind("<Leave>", unbind_mousewheel)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill="y")
        self._scroll_canvases.append(canvas)
        return outer, content

    def _event_originates_from_widget(self, event, widget: object | None) -> bool:
        if widget is None:
            return False
        try:
            current = event.widget
            target = str(widget)
            while current is not None:
                if str(current) == target:
                    return True
                parent_name = getattr(current, "winfo_parent", lambda: "")()
                if not parent_name:
                    break
                current = current.nametowidget(parent_name)
        except Exception:
            return False
        return False

    def _scroll_tree_with_mousewheel(self, tree: ttk.Treeview, event) -> str | None:
        if not self._tree_can_scroll_with_mousewheel(tree, event):
            return None
        direction = self._mousewheel_direction(event)
        tree.yview_scroll(direction, "units")
        return "break"

    def _event_originates_from_scrollable_tree(self, event, tree: ttk.Treeview | None) -> bool:
        return self._event_originates_from_widget(event, tree) and bool(tree) and self._tree_can_scroll_with_mousewheel(tree, event)

    def _tree_can_scroll_with_mousewheel(self, tree: ttk.Treeview, event) -> bool:
        first, last = tree.yview()
        if first <= 0 and last >= 1:
            return False
        direction = self._mousewheel_direction(event)
        if direction < 0 and first <= 0:
            return False
        if direction > 0 and last >= 1:
            return False
        return True

    def _mousewheel_direction(self, event) -> int:
        return -1 if event.delta > 0 else 1

    def _card(self, parent: ttk.Frame, title: str) -> tuple[ttk.Frame, ttk.Frame]:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10, 12, 10))
        ttk.Label(card, text=title, style="SectionTitle.TLabel").pack(fill="x", anchor="w", pady=(0, 4))
        palette = getattr(self, "_palette", {"border": "#e5e7eb"})
        sep = Canvas(card, height=1, borderwidth=0, highlightthickness=0, background=palette["border"])
        sep.pack(fill="x", pady=(0, 8))
        body = ttk.Frame(card, style="Surface.TFrame")
        body.pack(fill=BOTH, expand=True)
        return card, body

    def _build_upload_area(self, parent: ttk.Frame) -> Canvas:
        palette = getattr(self, "_palette", {"surface": "#ffffff", "border": "#e5e7eb", "accent": "#3b82f6", "muted": "#6b7280", "fg": "#1a1d21"})
        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        canvas = Canvas(parent, height=70, borderwidth=0, highlightthickness=0, cursor="hand2", background=palette["surface"])

        def redraw(event=None) -> None:
            width = event.width if event else max(640, canvas.winfo_width())
            height = event.height if event else 70
            canvas.delete("all")
            panel_fill = "#f8fafc" if self.current_theme == "light" else palette["button"]
            canvas.create_rectangle(6, 6, width - 6, height - 6, fill=panel_fill, outline=palette["border"], dash=(4, 3), width=1)

            cx = width // 2
            text = "点击选择文件，或使用下方按钮添加" if self.language == "zh" else "Click to select files, or use buttons below"
            canvas.create_text(cx, 30, text="\u2601\ufe0f", fill=palette["accent"], font=(font_family, 18))
            canvas.create_text(cx, 55, text=text, fill=palette["fg"], font=(font_family, 9))

        canvas.bind("<Configure>", redraw)
        canvas.bind("<Button-1>", lambda _event: self.add_files())
        canvas.pack(fill="x")
        redraw()
        return canvas

    def _section(self, parent: ttk.Frame, title: str) -> tuple[ttk.Frame, ttk.Frame]:
        section = ttk.Frame(parent, style="Section.TFrame", padding=(0, 0, 0, 16))
        ttk.Label(section, text=title, style="SectionTitle.TLabel").pack(fill="x", anchor="w", pady=(0, 10))
        body = ttk.Frame(section, style="Section.TFrame")
        body.pack(fill=BOTH, expand=True)
        return section, body

    def _primary_button(self, parent: ttk.Frame, text: str, command) -> RoundedButton:
        palette = getattr(self, "_palette", {"accent": "#3b82f6", "accent_fg": "#ffffff", "accent_active": "#2563eb", "button": "#e5e7eb", "muted": "#9ca3af"})
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            bg_color=palette.get("accent", "#3b82f6"),
            fg_color=palette.get("accent_fg", "#ffffff"),
            hover_color=palette.get("accent_active", "#2563eb"),
            disabled_bg=palette.get("button", "#e5e7eb"),
            disabled_fg=palette.get("muted", "#9ca3af"),
            radius=8,
            height=32,
            auto_width=True,
        )
        self._primary_buttons.append(button)
        return button

    def _style_primary_button(self, button: object, palette: dict[str, str]) -> None:
        try:
            if not isinstance(button, RoundedButton):
                return
            disabled = str(button.cget("state")) == "disabled"
            button.configure(
                bg_color=palette.get("button", "#e5e7eb") if disabled else palette.get("accent", "#3b82f6"),
                fg_color=palette.get("muted", "#9ca3af") if disabled else palette.get("accent_fg", "#ffffff"),
                hover_color=palette.get("accent_active", "#2563eb"),
                state="disabled" if disabled else "normal",
            )
        except Exception:
            pass

    def _tool_button(self, parent: ttk.Frame, text: str, command) -> RoundedButton:
        palette = getattr(self, "_palette", {"surface": "#ffffff", "fg": "#1a1d21", "border": "#e5e7eb", "hover": "#f3f4f6", "button": "#e5e7eb", "muted": "#9ca3af"})
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            bg_color=palette.get("surface", "#ffffff"),
            fg_color=palette.get("fg", "#1a1d21"),
            hover_color=palette.get("hover", "#f3f4f6"),
            disabled_bg=palette.get("button", "#e5e7eb"),
            disabled_fg=palette.get("muted", "#9ca3af"),
            radius=6,
            height=28,
            auto_width=True,
        )
        self._tool_buttons.append(button)
        return button

    def _style_tool_button(self, button: object, palette: dict[str, str]) -> None:
        try:
            if not isinstance(button, RoundedButton):
                return
            disabled = str(button.cget("state")) == "disabled"
            button.configure(
                bg_color=palette.get("button", "#e5e7eb") if disabled else palette.get("surface", "#ffffff"),
                fg_color=palette.get("muted", "#9ca3af") if disabled else palette.get("fg", "#1a1d21"),
                hover_color=palette.get("hover", "#f3f4f6"),
                state="disabled" if disabled else "normal",
            )
        except Exception:
            pass

    def _secondary_button(self, parent: ttk.Frame, text: str, command) -> RoundedButton:
        palette = getattr(self, "_palette", {"surface": "#ffffff", "fg": "#1a1d21", "border": "#e5e7eb", "hover": "#f3f4f6", "button": "#e5e7eb", "muted": "#9ca3af"})
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            bg_color=palette.get("surface", "#ffffff"),
            fg_color=palette.get("fg", "#1a1d21"),
            hover_color=palette.get("hover", "#f3f4f6"),
            disabled_bg=palette.get("button", "#e5e7eb"),
            disabled_fg=palette.get("muted", "#9ca3af"),
            radius=8,
            height=32,
            auto_width=True,
        )
        self._secondary_buttons.append(button)
        return button

    def _style_secondary_button(self, button: object, palette: dict[str, str]) -> None:
        try:
            if not isinstance(button, RoundedButton):
                return
            disabled = str(button.cget("state")) == "disabled"
            button.configure(
                bg_color=palette.get("button", "#e5e7eb") if disabled else palette.get("surface", "#ffffff"),
                fg_color=palette.get("muted", "#9ca3af") if disabled else palette.get("fg", "#1a1d21"),
                hover_color=palette.get("hover", "#f3f4f6"),
                state="disabled" if disabled else "normal",
            )
        except Exception:
            pass

    def _danger_button(self, parent: ttk.Frame, text: str, command) -> RoundedButton:
        palette = getattr(self, "_palette", {"danger": "#ef4444", "danger_fg": "#ffffff", "danger_active": "#dc2626", "button": "#e5e7eb", "muted": "#9ca3af"})
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            bg_color=palette.get("danger", "#ef4444"),
            fg_color=palette.get("danger_fg", "#ffffff"),
            hover_color=palette.get("danger_active", "#dc2626"),
            disabled_bg=palette.get("button", "#e5e7eb"),
            disabled_fg=palette.get("muted", "#9ca3af"),
            radius=8,
            height=32,
            auto_width=True,
        )
        self._danger_buttons.append(button)
        return button

    def _style_danger_button(self, button: object, palette: dict[str, str]) -> None:
        try:
            if not isinstance(button, RoundedButton):
                return
            disabled = str(button.cget("state")) == "disabled"
            button.configure(
                bg_color=palette.get("button", "#e5e7eb") if disabled else palette.get("danger", "#ef4444"),
                fg_color=palette.get("muted", "#9ca3af") if disabled else palette.get("danger_fg", "#ffffff"),
                hover_color=palette.get("danger_active", "#dc2626"),
                state="disabled" if disabled else "normal",
            )
        except Exception:
            pass

    def _segmented_button(self, parent: ttk.Frame, key: str, text: str) -> ttk.Frame:
        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        item = ttk.Frame(parent, style="Sidebar.TFrame", height=32)
        item.pack_propagate(False)
        indicator = Canvas(item, width=3, height=20, borderwidth=0, highlightthickness=0)
        indicator.pack(side=LEFT, padx=(0, 6), pady=(6, 6))
        button = Button(
            item,
            text=text,
            command=lambda tab_key=key: self._show_main_tab(tab_key),
            font=(font_family, 9),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=6,
            pady=3,
            cursor="hand2",
            takefocus=True,
            anchor="w",
            overrelief="flat",
        )
        button.pack(side=LEFT, fill="x", expand=True)
        item.bind("<Button-1>", lambda _event, tab_key=key: self._show_main_tab(tab_key))
        indicator.bind("<Button-1>", lambda _event, tab_key=key: self._show_main_tab(tab_key))
        self._segmented_buttons[key] = {"frame": item, "indicator": indicator, "button": button}
        palette = getattr(self, "_palette", None)
        if palette:
            self._style_segmented_button(self._segmented_buttons[key], palette, selected=(key == self.active_tab))
        return item

    def _style_segmented_button(self, item: object, palette: dict[str, str], selected: bool) -> None:
        try:
            if isinstance(item, dict):
                frame = item.get("frame")
                indicator = item.get("indicator")
                button = item.get("button")
            else:
                frame = None
                indicator = None
                button = item
            if not isinstance(button, Button):
                return
            if selected:
                background = palette["sidebar_active"]
                foreground = "#ffffff" if self.current_theme == "light" else palette["accent"]
                indicator_fill = palette["accent"]
            else:
                background = palette["sidebar"]
                foreground = "#cbd5e1" if self.current_theme == "light" else palette["fg"]
                indicator_fill = palette["sidebar"]
            if isinstance(frame, ttk.Frame):
                frame.configure(style="Sidebar.TFrame")
            if isinstance(indicator, Canvas):
                indicator.configure(background=palette["sidebar"], width=3, height=20)
                indicator.delete("all")
                indicator.create_rectangle(0, 0, 3, 20, fill=indicator_fill, outline=indicator_fill)
            button.configure(
                background=background,
                foreground=foreground,
                activebackground="#273449" if self.current_theme == "light" else palette["hover"],
                activeforeground="#ffffff" if self.current_theme == "light" else palette["fg"],
                relief="flat",
                highlightbackground=palette["sidebar_border"],
            )
        except Exception:
            pass

    def _show_main_tab(self, key: str) -> None:
        pages = getattr(self, "_tab_pages", {})
        if key not in pages:
            key = "anonymize"
        for page in pages.values():
            page.pack_forget()
        pages[key].pack(fill=BOTH, expand=True)
        self.active_tab = key
        if key == "restore" and hasattr(self, "restore_action_button"):
            self.page_action_button = self.restore_action_button
        elif hasattr(self, "anonymize_action_button"):
            self.page_action_button = self.anonymize_action_button
        if hasattr(self, "page_title_var"):
            self.page_title_var.set(self._text("tab_restore") if key == "restore" else self._text("tab_anonymize"))
        self._refresh_page_action()
        self._refresh_action_state()
        palette = getattr(self, "_palette", None)
        if palette:
            for tab_key, button in self._segmented_buttons.items():
                self._style_segmented_button(button, palette, selected=(tab_key == key))

    def _refresh_page_action(self) -> None:
        action_button = getattr(self, "page_action_button", None)
        if not action_button:
            return
        if self.active_tab == "restore":
            action_button.configure(text=self._text("start_restore"), command=self.start_restore)
        else:
            action_button.configure(text=self._text("start_anonymize"), command=self.start_anonymize)
        palette = getattr(self, "_palette", None)
        if palette and action_button in getattr(self, "_primary_buttons", []):
            self._style_primary_button(action_button, palette)

    def _refresh_action_state(self) -> None:
        action_button = getattr(self, "page_action_button", None)
        if not action_button:
            return
        if getattr(self, "_busy_operation", None):
            action_button.configure(state="disabled")
            palette = getattr(self, "_palette", None)
            if palette and action_button in getattr(self, "_primary_buttons", []):
                self._style_primary_button(action_button, palette)
            return
        if self.active_tab == "restore":
            ready = bool(self.restore_files and self.mapping_path.get())
        else:
            ready = bool(self.files)
        action_button.configure(state="normal" if ready else "disabled")
        palette = getattr(self, "_palette", None)
        if palette and action_button in getattr(self, "_primary_buttons", []):
            self._style_primary_button(action_button, palette)

    def _refresh_file_counts(self) -> None:
        if hasattr(self, "file_count_var"):
            self.file_count_var.set(self._text("file_count").format(count=len(self.files)))
        if hasattr(self, "restore_file_count_var"):
            self.restore_file_count_var.set(self._text("file_count").format(count=len(self.restore_files)))
        self._refresh_file_placeholders()
        self._refresh_action_state()

    def start_auto_scan_candidates(self) -> None:
        self.auto_detect.set(True)
        self.start_scan_candidates()

    def _checkbox(self, parent: ttk.Frame, text: str, variable: BooleanVar) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Surface.TFrame")
        box = Canvas(frame, width=20, height=20, borderwidth=0, highlightthickness=0, cursor="hand2")
        label = ttk.Label(frame, text=text, style="Surface.TLabel", cursor="hand2")
        box.pack(side=LEFT, padx=(0, 6), pady=2)
        label.pack(side=LEFT)
        checkbox = {"frame": frame, "box": box, "label": label, "variable": variable, "text": text}

        def toggle(_event=None) -> None:
            variable.set(not variable.get())
            palette = getattr(self, "_palette", None)
            if palette:
                self._style_checkbox(checkbox, palette)

        frame.bind("<Button-1>", toggle)
        box.bind("<Button-1>", toggle)
        label.bind("<Button-1>", toggle)
        self._checkboxes.append(checkbox)
        palette = getattr(self, "_palette", None)
        if palette:
            self._style_checkbox(checkbox, palette)
        return frame

    def _style_checkbox(self, checkbox: dict[str, object], palette: dict[str, str]) -> None:
        try:
            box = checkbox["box"]
            label = checkbox["label"]
            variable = checkbox["variable"]
            if not isinstance(box, Canvas) or not isinstance(variable, BooleanVar):
                return
            selected = bool(variable.get())
            box.configure(background=palette["surface"])
            box.delete("all")
            fill = palette["accent"] if selected else palette["surface"]
            outline = palette["accent"] if selected else palette["border"]
            if selected:
                box.create_rectangle(5, 5, 18, 18, fill=palette["select"], outline="", width=0)
            box.create_rectangle(5, 3, 15, 17, fill=fill, outline=outline, width=1)
            box.create_rectangle(3, 5, 17, 15, fill=fill, outline=outline, width=1)
            box.create_oval(3, 3, 8, 8, fill=fill, outline=outline, width=1)
            box.create_oval(12, 3, 17, 8, fill=fill, outline=outline, width=1)
            box.create_oval(3, 12, 8, 17, fill=fill, outline=outline, width=1)
            box.create_oval(12, 12, 17, 17, fill=fill, outline=outline, width=1)
            if selected:
                box.create_line(6, 10, 9, 13, 15, 7, fill=palette["accent_fg"], width=2.4, capstyle="round", joinstyle="round")
            if isinstance(label, ttk.Label):
                label.configure(style="Surface.TLabel")
        except Exception:
            pass

    def _toggle_chip(self, parent: ttk.Frame, text: str, variable: BooleanVar) -> Checkbutton:
        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        chip = Checkbutton(
            parent,
            text=text,
            variable=variable,
            indicatoron=False,
            font=(font_family, 9),
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            padx=8,
            pady=4,
            cursor="hand2",
            takefocus=True,
            overrelief="flat",
        )
        chip.configure(command=lambda widget=chip, var=variable: self._refresh_toggle_chip(widget, var))
        self._toggle_chips.append((chip, variable))
        palette = getattr(self, "_palette", None)
        if palette:
            self._style_toggle_chip(chip, variable, palette)
        return chip

    def _refresh_toggle_chip(self, chip: Checkbutton, variable: BooleanVar) -> None:
        palette = getattr(self, "_palette", None)
        if palette:
            self._style_toggle_chip(chip, variable, palette)

    def _style_toggle_chip(self, chip: Checkbutton, variable: BooleanVar, palette: dict[str, str]) -> None:
        try:
            selected = bool(variable.get())
            background = palette["button"]
            foreground = palette["fg"]
            border = palette["border"]
            chip.configure(
                background=background,
                foreground=foreground,
                activebackground=palette["hover"],
                activeforeground=palette["fg"],
                selectcolor=background,
                highlightbackground=border,
                highlightcolor=border,
                relief="flat",
            )
        except Exception:
            pass

    def _build_anonymize_tab(self) -> None:
        top = ttk.Frame(self.anonymize_frame, style="Workspace.TFrame")
        top.pack(fill=BOTH, expand=True)

        # ===== 步骤 1: 添加文件 =====
        step1_card, step1_body = self._card(top, self._text("step1_title"))
        step1_card.pack(fill=BOTH, expand=False, padx=0, pady=(0, 8))

        upload_row = ttk.Frame(step1_body, style="Surface.TFrame")
        upload_row.pack(fill="x")
        self._build_upload_area(upload_row)

        upload_actions = ttk.Frame(step1_body, style="Surface.TFrame")
        upload_actions.pack(fill="x", pady=(6, 8))
        self._secondary_button(upload_actions, text="\u2795 " + self._text("add_file"), command=self.add_files).pack(side=LEFT, padx=(0, 8))
        self._secondary_button(upload_actions, text="\u2795 " + self._text("add_folder"), command=self.add_folder).pack(side=LEFT, padx=(0, 8))
        self._checkbox(upload_actions, self._text("recursive_folders"), self.recursive_scan).pack(side=LEFT)
        self._danger_button(upload_actions, text="\U0001f5d1 " + self._text("remove_selected"), command=self.remove_selected_files).pack(side=RIGHT)
        self._danger_button(upload_actions, text="\U0001f9f9 " + self._text("clear"), command=self.clear_files).pack(side=RIGHT, padx=(0, 8))
        ttk.Label(upload_actions, textvariable=self.file_count_var, style="SurfaceMuted.TLabel").pack(side=RIGHT, padx=(0, 8))

        self.file_list = ttk.Treeview(step1_body, columns=("path",), show="headings", height=2)
        self.file_list.heading("path", text=self._text("file_path"))
        self.file_list.column("path", width=700, anchor="w")
        self.file_list.pack(fill="x", expand=False)

        # ===== 步骤 2: 配置敏感词 =====
        step2_card, step2_body = self._card(top, self._text("step2_title"))
        step2_card.pack(fill=BOTH, expand=False, padx=0, pady=(0, 8))

        scan_row = ttk.Frame(step2_body, style="Surface.TFrame")
        scan_row.pack(fill="x", pady=(0, 6))
        self.scan_action_button = self._secondary_button(scan_row, text="\u26a1 " + self._text("auto_scan"), command=self.start_auto_scan_candidates)
        self.scan_action_button.pack(side=LEFT, padx=(0, 6))
        self._secondary_button(scan_row, text="+ " + self._text("add_manual"), command=self._show_manual_candidate_dialog).pack(side=LEFT, padx=(0, 6))

        # 候选信息按钮行（紧凑布局）
        candidate_actions = ttk.Frame(step2_body, style="Surface.TFrame")
        candidate_actions.pack(fill="x")
        self._secondary_button(candidate_actions, text="\u2611 全启", command=self.enable_all_candidates).pack(side=LEFT, padx=(0, 3))
        self._secondary_button(candidate_actions, text="\u2610 全禁", command=self.disable_all_candidates).pack(side=LEFT, padx=(0, 3))
        self._secondary_button(candidate_actions, text="\u21c4 切换", command=self.toggle_selected_candidates).pack(side=LEFT, padx=(0, 8))
        self._secondary_button(candidate_actions, text="模板", command=self.download_sensitive_template).pack(side=LEFT, padx=(0, 3))
        self._secondary_button(candidate_actions, text="导入", command=self.import_sensitive_table).pack(side=LEFT, padx=(0, 3))
        self._secondary_button(candidate_actions, text="导出", command=self.export_sensitive_table).pack(side=LEFT, padx=(0, 8))
        self._danger_button(candidate_actions, text="删除", command=self.delete_selected_candidates).pack(side=LEFT, padx=(0, 3))
        self._danger_button(candidate_actions, text="清空", command=self.clear_candidates).pack(side=LEFT)

        table_frame = ttk.Frame(step2_body, style="Surface.TFrame")
        table_frame.pack(fill=BOTH, expand=True)
        columns = ("enabled", "value", "replacement", "context", "count", "files", "source", "action")
        self.candidate_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=4)
        headings = {
            "enabled": self._text("col_enabled"),
            "value": self._text("col_value"),
            "context": self._text("col_context"),
            "replacement": self._text("col_replacement"),
            "count": self._text("col_count"),
            "files": self._text("col_files"),
            "source": self._text("col_source"),
            "action": self._text("col_action"),
        }
        widths = {
            "enabled": 45,
            "value": 100,
            "replacement": 100,
            "context": 80,
            "count": 35,
            "files": 90,
            "source": 45,
            "action": 50,
        }
        for column in columns:
            self.candidate_tree.heading(column, text=headings[column])
            self.candidate_tree.column(column, width=widths[column], anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.candidate_tree.yview)
        self.candidate_tree.configure(yscrollcommand=yscroll.set)
        self.candidate_tree.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=RIGHT, fill="y")
        self.candidate_tree.bind("<MouseWheel>", lambda event: self._scroll_tree_with_mousewheel(self.candidate_tree, event))
        self.candidate_tree.bind("<<TreeviewSelect>>", self.on_candidate_selected)
        self.candidate_tree.bind("<Double-1>", self._on_candidate_tree_double_click)
        self.candidate_tree.bind("<ButtonRelease-1>", self._on_candidate_tree_click)

        # ===== 步骤 3: 执行脱敏 =====
        step3_card, step3_body = self._card(top, self._text("step3_title"))
        step3_card.pack(fill=BOTH, expand=False, padx=0, pady=(0, 0))

        output_row = ttk.Frame(step3_body, style="Surface.TFrame")
        output_row.pack(fill="x", pady=(0, 6))
        ttk.Label(output_row, text=self._text("output_dir") + ":", style="Surface.TLabel").pack(side=LEFT)
        self._secondary_button(output_row, text="选择", command=self.choose_output_dir).pack(side=RIGHT)
        ttk.Entry(output_row, textvariable=self.output_dir).pack(side=LEFT, fill="x", expand=True, padx=(8, 8))

        options_row = ttk.Frame(step3_body, style="Surface.TFrame")
        options_row.pack(fill="x", pady=(0, 8))
        self._checkbox(options_row, self._text("encrypt_mapping"), self.encrypt_mapping).pack(side=LEFT, padx=(0, 12))
        self._checkbox(options_row, self._text("remove_headers_footers"), self.remove_headers_footers).pack(side=LEFT)

        action_row = ttk.Frame(step3_body, style="Surface.TFrame")
        action_row.pack(fill="x")
        self.anonymize_action_button = self._primary_button(action_row, text="\u2714 开始脱敏", command=self.start_anonymize)
        self.page_action_button = self.anonymize_action_button
        self.anonymize_action_button.pack(side=RIGHT)

        if not self._enterprise_terms_loaded:
            self._load_enterprise_terms_as_candidates(silent=True)

    def _build_restore_tab(self) -> None:
        restore_content = ttk.Frame(self.restore_frame, style="Workspace.TFrame")
        restore_content.pack(fill=BOTH, expand=True)

        restore_toolbar = ttk.Frame(restore_content, style="Workspace.TFrame")
        restore_toolbar.pack(fill="x", pady=(0, 8))
        self.restore_action_button = self._primary_button(restore_toolbar, text="\u2714 " + self._text("start_restore"), command=self.start_restore)
        self.restore_action_button.pack(side=RIGHT)

        guide_card, guide_frame = self._card(restore_content, self._text("tab_restore"))
        guide_card.pack(fill="x", padx=0, pady=(0, 10))
        guide_text = (
            "1. Add files  2. Choose mapping  3. Confirm output and restore"
            if self.language == "en"
            else "1. 添加文件  2. 选择映射表  3. 确认输出目录后还原"
        )
        ttk.Label(guide_frame, text=guide_text, style="SurfaceMuted.TLabel", wraplength=700, justify=LEFT).pack(fill="x", anchor="w")

        file_card, file_frame = self._card(restore_content, self._text("restore_files"))
        file_card.pack(fill="x", expand=False, padx=0, pady=(0, 10))

        button_row = ttk.Frame(file_frame, style="Surface.TFrame")
        button_row.pack(fill="x", pady=(0, 8))
        ttk.Label(button_row, textvariable=self.restore_file_count_var, style="SurfaceMuted.TLabel").pack(side=LEFT)
        self._danger_button(button_row, text="\U0001f9f9 " + self._text("clear"), command=self.clear_restore_files).pack(side=RIGHT)
        self._secondary_button(button_row, text="\U0001f5d1 " + self._text("remove_selected"), command=self.remove_selected_restore_files).pack(side=RIGHT, padx=(0, 6))
        self._secondary_button(button_row, text="\u2795 " + self._text("add_file"), command=self.add_restore_files).pack(side=RIGHT, padx=(0, 6))

        restore_table = ttk.Frame(file_frame, style="Surface.TFrame")
        restore_table.pack(fill="x", expand=False)
        self.restore_file_list = ttk.Treeview(restore_table, columns=("path",), show="headings", height=4)
        self.restore_file_list.heading("path", text=self._text("file_path"))
        self.restore_file_list.column("path", width=700, anchor="w")
        restore_yscroll = ttk.Scrollbar(restore_table, orient="vertical", command=self.restore_file_list.yview)
        self.restore_file_list.configure(yscrollcommand=restore_yscroll.set)
        self.restore_file_list.pack(side=LEFT, fill="x", expand=True)
        restore_yscroll.pack(side=RIGHT, fill="y")

        mapping_card, mapping_frame = self._card(restore_content, self._text("mapping_json"))
        mapping_card.pack(fill="x", padx=0, pady=(0, 10))
        self._secondary_button(mapping_frame, text="\U0001f4c2 " + self._text("choose"), command=self.choose_mapping_file).pack(side=RIGHT)
        ttk.Entry(mapping_frame, textvariable=self.mapping_path).pack(side=LEFT, fill="x", expand=True, padx=(0, 8))

        output_card, output_frame = self._card(restore_content, self._text("output_dir"))
        output_card.pack(fill="x", padx=0, pady=(0, 14))
        self._secondary_button(output_frame, text="\U0001f4c2 " + self._text("choose"), command=self.choose_restore_output_dir).pack(side=RIGHT)
        ttk.Entry(output_frame, textvariable=self.restore_output_dir).pack(side=LEFT, fill="x", expand=True, padx=(0, 8))

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title=self._text("dialog_select_anonymize"),
            filetypes=[
                (self._text("supported_files"), "*.docx *.xlsx *.pptx *.pdf *.txt *.md *.csv *.json *.log *.xml *.html *.png *.jpg *.jpeg *.doc *.xls"),
                (self._text("all_files"), "*.*"),
            ],
        )
        self._add_paths(Path(path) for path in paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title=self._text("dialog_select_folder"))
        if not folder:
            return
        root = Path(folder)
        iterator = root.rglob("*") if self.recursive_scan.get() else root.glob("*")
        all_files = [path for path in iterator if path.is_file()]
        known_count = sum(1 for path in all_files if is_known_file(path))
        self._add_paths(all_files)
        unsupported_count = len(all_files) - known_count
        self._log(
            "INFO",
            f"Folder added: {len(all_files)} file(s), {unsupported_count} unsupported extension(s) will be reported.",
        )

    def _add_paths(self, paths) -> None:
        existing = set(self.files)
        added = 0
        for path in paths:
            path = Path(path)
            if path in existing:
                continue
            self.files.append(path)
            existing.add(path)
            self.file_list.insert("", END, values=(str(path),))
            added += 1
        if added:
            self._log("INFO", f"Added {added} file(s).")
        self._refresh_file_counts()

    def add_restore_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title=self._text("dialog_select_restore"),
            filetypes=[
                (self._text("supported_files"), "*.docx *.xlsx *.pptx *.pdf *.txt *.md *.csv *.json *.log *.xml *.html"),
                (self._text("all_files"), "*.*"),
            ],
        )
        for path in paths:
            p = Path(path)
            if p not in self.restore_files:
                self.restore_files.append(p)
                self.restore_file_list.insert("", END, values=(str(p),))
        self._refresh_file_counts()

    def remove_selected_files(self) -> None:
        selected = [item for item in self.file_list.selection() if item != "__empty_files__"]
        selected_paths = {Path(self.file_list.item(item, "values")[0]) for item in selected}
        self.files = [path for path in self.files if path not in selected_paths]
        for item in selected:
            self.file_list.delete(item)
        self._refresh_file_counts()

    def remove_selected_restore_files(self) -> None:
        selected = [item for item in self.restore_file_list.selection() if item != "__empty_restore__"]
        selected_paths = {Path(self.restore_file_list.item(item, "values")[0]) for item in selected}
        self.restore_files = [path for path in self.restore_files if path not in selected_paths]
        for item in selected:
            self.restore_file_list.delete(item)
        self._refresh_file_counts()

    def clear_files(self) -> None:
        self.files.clear()
        for item in self.file_list.get_children():
            self.file_list.delete(item)
        self._refresh_file_counts()

    def clear_restore_files(self) -> None:
        self.restore_files.clear()
        for item in self.restore_file_list.get_children():
            self.restore_file_list.delete(item)
        self._refresh_file_counts()

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title=self._text("dialog_output_dir"), initialdir=self.output_dir.get() or str(APP_DIR))
        if path:
            self.output_dir.set(path)

    def choose_restore_output_dir(self) -> None:
        path = filedialog.askdirectory(title=self._text("dialog_output_dir"), initialdir=self.restore_output_dir.get() or str(APP_DIR))
        if path:
            self.restore_output_dir.set(path)

    def choose_mapping_file(self) -> None:
        path = filedialog.askopenfilename(
            title=self._text("dialog_mapping"),
            filetypes=[
                ("Encrypted mapping", "*.json.enc"),
                ("JSON", "*.json"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if path:
            self.mapping_path.set(path)
            self._refresh_action_state()

    def _enterprise_terms_status_text(self) -> str:
        if self.enterprise_profile.terms:
            return self._text("enterprise_terms_status").format(count=len(self.enterprise_profile.terms))
        return self._text("enterprise_terms_status_empty")

    def _enterprise_terms_inline_help(self) -> str:
        if self.enterprise_profile.terms:
            return self._text("enterprise_terms_help")
        return self._text("enterprise_terms_help_empty")

    def _enterprise_terms_action_text(self) -> str:
        if self.enterprise_profile.terms:
            return self._text("restore_builtin_terms")
        return self._text("view_terms_help")

    def load_builtin_enterprise_terms(self) -> None:
        count = self._load_enterprise_terms_as_candidates(silent=False)
        if count:
            messagebox.showinfo(
                self._text("terms_imported_title"),
                self._text("enterprise_terms_loaded_as_candidates").format(count=count),
            )

    def download_sensitive_template(self) -> None:
        path = filedialog.asksaveasfilename(
            title=self._text("dialog_save_template"),
            defaultextension=".xlsx",
            initialfile="敏感词批量导入模板.xlsx",
            filetypes=[
                ("Excel", "*.xlsx"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if not path:
            return
        try:
            write_sensitive_template(Path(path))
        except Exception as exc:
            messagebox.showerror(self._text("terms_import_failed_title"), str(exc))
            return
        messagebox.showinfo(self._text("template_saved_title"), self._text("template_saved").format(path=path))

    def import_sensitive_table(self) -> None:
        path = filedialog.askopenfilename(
            title=self._text("dialog_sensitive_table"),
            filetypes=[
                ("Sensitive term tables", "*.xlsx *.csv"),
                ("Excel", "*.xlsx"),
                ("CSV", "*.csv"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if not path:
            return
        try:
            rows = read_sensitive_table(Path(path))
            errors = self._validate_sensitive_rows(rows)
            if errors:
                self._show_sensitive_import_errors(errors)
                return
            count = self._import_sensitive_rows(rows)
        except Exception as exc:
            messagebox.showerror(self._text("terms_import_failed_title"), str(exc))
            return
        self._refresh_candidate_tree()
        messagebox.showinfo(self._text("terms_imported_title"), self._text("sensitive_imported").format(count=count))

    def export_sensitive_table(self) -> None:
        rows = self._candidate_export_rows()
        if not rows:
            messagebox.showinfo(self._text("sensitive_exported_title"), self._text("no_candidates_to_export"))
            return
        path = filedialog.asksaveasfilename(
            title=self._text("dialog_export_sensitive_table"),
            defaultextension=".xlsx",
            initialfile=f"候选敏感词_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            filetypes=[
                ("Excel", "*.xlsx"),
                ("CSV", "*.csv"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if not path:
            return
        try:
            write_sensitive_export(Path(path), rows)
        except Exception as exc:
            messagebox.showerror(self._text("terms_import_failed_title"), str(exc))
            return
        messagebox.showinfo(self._text("sensitive_exported_title"), self._text("sensitive_exported").format(path=path))

    def _load_enterprise_terms_as_candidates(self, silent: bool) -> int:
        if self._enterprise_terms_loaded:
            return 0
        self._enterprise_terms_loaded = True
        rows = [
            SensitiveTableRow(
                row_number=index,
                value=term.value,
                replacement=next_placeholder(prefix_for_entity(term.entity), self._used_replacements()),
                enabled=True,
                note=term.note or term.category,
            )
            for index, term in enumerate(self.enterprise_profile.terms, start=1)
            if term.value
        ]
        if not rows:
            return 0
        count = self._import_sensitive_rows(rows)
        if not silent:
            self._refresh_candidate_tree()
        return count

    def _validate_sensitive_rows(self, rows: list[SensitiveTableRow]) -> list[SensitiveTableRow]:
        final_by_value: dict[str, str] = {}
        for candidate in self.candidates.values():
            if not candidate.enabled or candidate.context_key:
                continue
            value = candidate.value.strip()
            replacement = candidate.replacement.strip()
            if value and replacement:
                final_by_value[value] = replacement

        imported_by_value: dict[str, tuple[bool, str, SensitiveTableRow]] = {}
        for row in rows:
            row.errors.clear()
            if not row.value:
                row.errors.append("原文不能为空")
            if row.enabled and not row.replacement:
                row.errors.append("替换为不能为空")
            if row.value and (row.replacement or not row.enabled):
                existing = imported_by_value.get(row.value)
                row_state = (row.enabled, row.replacement)
                if existing and (existing[0], existing[1]) != row_state:
                    row.errors.append("同一原文重复设置且内容不一致")
                    existing[2].errors.append("同一原文重复设置且内容不一致")
                imported_by_value[row.value] = (row.enabled, row.replacement, row)

        for value, (enabled, replacement, _row) in imported_by_value.items():
            if enabled:
                final_by_value[value] = replacement
            else:
                final_by_value.pop(value, None)

        final_by_replacement: dict[str, str] = {}
        for value, replacement in final_by_value.items():
            owner = final_by_replacement.get(replacement)
            if owner and owner != value:
                for row in rows:
                    if row.enabled and row.replacement == replacement and row.value in {value, owner}:
                        row.errors.append("多个原文使用同一个替换值")
                continue
            final_by_replacement[replacement] = value
        return [row for row in rows if row.errors]

    def _import_sensitive_rows(self, rows: list[SensitiveTableRow]) -> int:
        imported = 0
        for row in rows:
            candidate_id = self._candidate_id_for_value(row.value)
            if not row.enabled:
                if candidate_id:
                    self.candidates[candidate_id].enabled = False
                    imported += 1
                continue
            if candidate_id:
                candidate = self.candidates[candidate_id]
                candidate.enabled = True
                candidate.replacement = row.replacement
                candidate.source = "manual"
            else:
                entity = "CUSTOM_TERM"
                prefix = prefix_for_entity(entity)
                key = self._candidate_key(entity, row.value)
                candidate = CandidateItem(
                    id=key,
                    enabled=True,
                    entity=entity,
                    prefix=prefix,
                    value=row.value,
                    replacement=row.replacement,
                    count=0,
                    files=set(),
                    source="manual",
                )
                self.candidates[key] = candidate
                self.candidate_order.append(key)
            imported += 1
        return imported

    def _candidate_export_rows(self) -> list[SensitiveExportRow]:
        rows: list[SensitiveExportRow] = []
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if not candidate:
                continue
            rows.append(
                SensitiveExportRow(
                    value=candidate.value,
                    replacement=candidate.replacement,
                    enabled=candidate.enabled,
                    note=self._format_candidate_source(candidate.source),
                )
            )
        return rows

    def _show_sensitive_import_errors(self, rows: list[SensitiveTableRow]) -> None:
        dialog = Toplevel(self.root)
        self._prepare_dialog(dialog)
        dialog.title(self._text("sensitive_import_error_title"))
        dialog.transient(self.root)
        self._center_child_window(dialog, 780, 430)
        container = ttk.Frame(dialog, style="Surface.TFrame", padding=14)
        container.pack(fill=BOTH, expand=True)
        ttk.Label(container, text=self._text("sensitive_import_error_intro"), style="Muted.TLabel").pack(fill="x", anchor="w", pady=(0, 10))
        columns = ("row", "value", "replacement", "enabled", "error")
        tree = ttk.Treeview(container, columns=columns, show="headings", height=10)
        headings = {
            "row": self._text("sensitive_error_col_row"),
            "value": self._text("sensitive_error_col_value"),
            "replacement": self._text("sensitive_error_col_replacement"),
            "enabled": self._text("sensitive_error_col_enabled"),
            "error": self._text("sensitive_error_col_error"),
        }
        widths = {"row": 70, "value": 190, "replacement": 190, "enabled": 70, "error": 240}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="w")
        tree.tag_configure("error", background="#fff1f2")
        for row in rows:
            tree.insert(
                "",
                END,
                values=(row.row_number, row.value, row.replacement, self._text("yes") if row.enabled else self._text("no"), "；".join(row.errors)),
                tags=("error",),
            )
        tree.pack(fill=BOTH, expand=True)
        self._secondary_button(container, text=self._text("close"), command=dialog.destroy).pack(side=RIGHT, pady=(12, 0))
        dialog.grab_set()

    def start_scan_candidates(self) -> None:
        if not self.files:
            messagebox.showwarning(self._text("missing_files_title"), self._text("scan_missing_files"))
            return
        if not self.auto_detect.get():
            messagebox.showinfo(self._text("manual_mode_title"), self._text("manual_mode_message"))
            return
        self._clear_detected_candidates()
        custom_terms = self._custom_terms()
        self._set_status(self._text("status_scanning"), "busy")
        self._begin_operation("scan", getattr(self, "scan_action_button", None))
        threading.Thread(
            target=self._run_scan_candidates,
            args=(list(self.files), custom_terms),
            daemon=True,
        ).start()

    def _run_scan_candidates(self, files: list[Path], custom_terms: list[str]) -> None:
        self._log("INFO", "Starting candidate scan.")
        all_hits: list[CandidateHit] = []
        for file_path in files:
            try:
                hits, message = scan_file_candidates(file_path, custom_terms)
                all_hits.extend(hits)
                self._log("OK", f"{file_path.name}: {message}")
            except Exception as exc:
                level = "WARN" if isinstance(exc, DesensitizeError) else "ERROR"
                self._log(level, f"{file_path.name}: {exc}")
        self.queue.put(("candidates", all_hits))
        self._log("INFO", f"Candidate scan finished. {len(all_hits)} file-level candidate group(s).")

    def start_anonymize(self) -> None:
        if not self.files:
            messagebox.showwarning(self._text("missing_files_title"), self._text("anonymize_missing_files"))
            return
        try:
            replacements = self._selected_replacements()
        except ValueError as exc:
            messagebox.showerror(self._text("candidate_error_title"), str(exc))
            return
        mapping_password = None
        if self.encrypt_mapping.get():
            mapping_password = self._ask_mapping_password(confirm=True)
            if mapping_password is None:
                return
        output_dir = Path(self.output_dir.get()).expanduser()
        self._set_status(self._text("status_anonymizing"), "busy")
        self._begin_operation("anonymize", getattr(self, "anonymize_action_button", None))
        threading.Thread(
            target=self._run_anonymize,
            args=(list(self.files), output_dir, replacements, mapping_password, self.remove_headers_footers.get()),
            daemon=True,
        ).start()

    def start_restore(self) -> None:
        if not self.restore_files:
            messagebox.showwarning(self._text("missing_files_title"), self._text("restore_missing_files"))
            return
        if not self.mapping_path.get():
            messagebox.showwarning(self._text("missing_mapping_title"), self._text("missing_mapping_message"))
            return
        mapping_path = Path(self.mapping_path.get())
        mapping_password = None
        if is_encrypted_mapping(mapping_path):
            mapping_password = self._ask_mapping_password(confirm=False)
            if mapping_password is None:
                return
        self._set_status(self._text("status_restoring"), "busy")
        self._begin_operation("restore", getattr(self, "restore_action_button", None))
        threading.Thread(
            target=self._run_restore,
            args=(list(self.restore_files), Path(self.restore_output_dir.get()).expanduser(), mapping_path, mapping_password),
            daemon=True,
        ).start()

    def _ask_mapping_password(self, confirm: bool) -> str | None:
        password = simpledialog.askstring(
            self._text("mapping_password_title"),
            self._text("mapping_password_prompt"),
            show="*",
            parent=self.root,
        )
        if password is None:
            return None
        if not password:
            messagebox.showwarning(self._text("mapping_password_title"), self._text("mapping_password_cancelled"))
            return None
        if confirm:
            repeated = simpledialog.askstring(
                self._text("mapping_password_title"),
                self._text("mapping_password_confirm_prompt"),
                show="*",
                parent=self.root,
            )
            if repeated is None:
                return None
            if password != repeated:
                messagebox.showerror(self._text("mapping_password_title"), self._text("mapping_password_mismatch"))
                return None
        return password

    def _run_anonymize(
        self,
        files: list[Path],
        output_dir: Path,
        replacements: list[ReplacementSpec],
        mapping_password: str | None,
        remove_headers_footers: bool,
    ) -> None:
        self._log("INFO", "Starting desensitization with approved replacements.")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._log("ERROR", f"Cannot create output directory: {exc}")
            self.queue.put(("anonymize_failed", f"Cannot create output directory: {exc}"))
            return
        mapping = MappingStore()
        rows: list[dict[str, object]] = []
        total_counts = Counter()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ok_count = 0
        error_count = 0
        skipped_count = 0
        try:
            for replacement in replacements:
                mapping.add_explicit(
                    value=replacement.value,
                    entity=replacement.entity,
                    prefix=replacement.prefix,
                    placeholder=replacement.replacement,
                    context_key=replacement.context_key,
                    context_label=replacement.context_label,
                )
        except ValueError as exc:
            self._log("ERROR", str(exc))
            self.queue.put(("anonymize_failed", str(exc)))
            return
        for file_path in files:
            try:
                output_path, counts, message = anonymize_file_with_replacements(
                    file_path,
                    output_dir,
                    replacements,
                    remove_headers_footers=remove_headers_footers,
                )
                total_counts.update(counts)
                ok_count += 1
                rows.append(
                    {
                        "file": str(file_path),
                        "status": "ok",
                        "output": str(output_path),
                        "message": message,
                        "counts": dict(counts),
                    }
                )
                self._log("OK", f"{file_path.name} -> {output_path.name}; {dict(counts)}")
            except SkippedFile as exc:
                skipped_count += 1
                rows.append(
                    {
                        "file": str(file_path),
                        "status": "skipped",
                        "output": "",
                        "message": str(exc),
                        "counts": {},
                    }
                )
                self._log("SKIP", f"{file_path.name}: {exc}")
            except Exception as exc:
                error_count += 1
                rows.append(
                    {
                        "file": str(file_path),
                        "status": "error",
                        "output": "",
                        "message": str(exc),
                        "counts": {},
                    }
                )
                level = "WARN" if isinstance(exc, DesensitizeError) else "ERROR"
                self._log(level, f"{file_path.name}: {exc}")
        mapping_file = output_dir / (f"mapping_{timestamp}.json.enc" if mapping_password else f"mapping_{timestamp}.json")
        report_file = output_dir / f"report_{timestamp}.csv"
        try:
            if mapping_password:
                mapping.save_encrypted(mapping_file, mapping_password)
            else:
                mapping.save(mapping_file)
            write_report(report_file, rows)
        except Exception as exc:
            self._log("ERROR", f"Cannot write mapping or report: {exc}")
            self.queue.put(("anonymize_failed", f"Cannot write mapping or report: {exc}"))
            return
        self._log("INFO", f"Mapping saved: {mapping_file}")
        self._log("INFO", f"Report saved: {report_file}")
        self._log("INFO", f"Done. Total replacements: {dict(total_counts)}")
        self.queue.put(
            (
                "anonymize_done",
                {
                    "ok_count": ok_count,
                    "error_count": error_count,
                    "skipped_count": skipped_count,
                    "total_counts": dict(total_counts),
                    "mapping_file": str(mapping_file),
                    "report_file": str(report_file),
                    "output_dir": str(output_dir),
                    "input_files": [path.name for path in files],
                    "remove_headers_footers": remove_headers_footers,
                },
            )
        )

    def _run_restore(self, files: list[Path], output_dir: Path, mapping_path: Path, mapping_password: str | None) -> None:
        self._log("INFO", "Starting restoration.")
        ok_count = 0
        error_count = 0
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._log("ERROR", f"Cannot create output directory: {exc}")
            self.queue.put(("restore_failed", f"Cannot create output directory: {exc}"))
            return
        try:
            mapping = MappingStore.load(mapping_path, password=mapping_password)
        except Exception as exc:
            self._log("ERROR", f"Cannot load mapping file: {exc}")
            self.queue.put(("restore_failed", f"Cannot load mapping file: {exc}"))
            return
        for file_path in files:
            try:
                output_path, message = restore_file(file_path, output_dir, mapping)
                ok_count += 1
                self._log("OK", f"{file_path.name} -> {output_path.name}; {message}")
            except Exception as exc:
                error_count += 1
                level = "WARN" if isinstance(exc, DesensitizeError) else "ERROR"
                self._log(level, f"{file_path.name}: {exc}")
        self._log("INFO", "Restoration done.")
        self.queue.put(
            (
                "restore_done",
                {
                    "ok_count": ok_count,
                    "error_count": error_count,
                    "output_dir": str(output_dir),
                    "mapping_file": str(mapping_path),
                    "input_files": [path.name for path in files],
                },
            )
        )

    def _merge_candidate_hits(self, hits: list[CandidateHit]) -> None:
        for hit in hits:
            key = self._candidate_key(hit.entity, hit.value, hit.context_key)
            candidate = self.candidates.get(key)
            if candidate:
                candidate.count += hit.count
                candidate.files.add(str(hit.file))
                continue
            replacement = next_placeholder(hit.prefix, self._used_replacements())
            candidate = CandidateItem(
                id=key,
                enabled=True,
                entity=hit.entity,
                prefix=hit.prefix,
                value=hit.value,
                replacement=replacement,
                context_key=hit.context_key,
                context_label=hit.context_label,
                count=hit.count,
                files={str(hit.file)},
                source=hit.source,
            )
            self.candidates[key] = candidate
            self.candidate_order.append(key)
        self._refresh_candidate_tree()

    def add_manual_candidate(self) -> None:
        value = self.edit_value.get().strip()
        entity = "CUSTOM_TERM"
        if not value:
            messagebox.showwarning(self._text("missing_value_title"), self._text("missing_value_message"))
            return
        prefix = prefix_for_entity(entity)
        replacement = self.edit_replacement.get().strip() or next_placeholder(prefix, self._used_replacements())
        key = self._candidate_key(entity, value)
        if key in self.candidates:
            candidate = self.candidates[key]
            candidate.enabled = True
            candidate.replacement = replacement
            candidate.source = "manual"
            self._log("INFO", "Manual item matched an existing candidate and updated it.")
        else:
            self.candidate_index += 1
            candidate = CandidateItem(
                id=key,
                enabled=True,
                entity=entity,
                prefix=prefix,
                value=value,
                replacement=replacement,
                count=0,
                files=set(),
                source="manual",
            )
            self.candidates[key] = candidate
            self.candidate_order.append(key)
        self._refresh_candidate_tree()

    def save_candidate_edit(self) -> None:
        selected = self._selected_candidate_ids()
        if len(selected) != 1:
            messagebox.showwarning(self._text("select_one_title"), self._text("select_one_message"))
            return
        old_key = selected[0]
        candidate = self.candidates.get(old_key)
        if not candidate:
            return
        value = self.edit_value.get().strip()
        entity = candidate.entity or "CUSTOM_TERM"
        replacement = self.edit_replacement.get().strip()
        if not value or not replacement:
            messagebox.showwarning(self._text("incomplete_title"), self._text("incomplete_message"))
            return
        new_key = self._candidate_key(entity, value, candidate.context_key)
        if new_key != old_key and new_key in self.candidates:
            messagebox.showerror(self._text("duplicate_title"), self._text("duplicate_message"))
            return
        candidate.entity = entity
        candidate.prefix = prefix_for_entity(entity)
        candidate.value = value
        candidate.replacement = replacement
        if new_key != old_key:
            self.candidates[new_key] = candidate
            del self.candidates[old_key]
            self.candidate_order = [new_key if item == old_key else item for item in self.candidate_order]
            candidate.id = new_key
        self._refresh_candidate_tree()

    def generate_edit_placeholder(self) -> None:
        entity = self.edit_entity.get().strip() or "CUSTOM_TERM"
        prefix = prefix_for_entity(entity)
        self.edit_replacement.set(next_placeholder(prefix, self._used_replacements()))

    def on_candidate_selected(self, _event=None) -> None:
        selected = self._selected_candidate_ids()
        if len(selected) != 1:
            return
        candidate = self.candidates.get(selected[0])
        if not candidate:
            return
        self.edit_value.set(candidate.value)
        self.edit_entity.set(candidate.entity)
        self.edit_replacement.set(candidate.replacement)

    def _show_manual_candidate_dialog(self) -> None:
        dialog = Toplevel(self.root)
        self._prepare_dialog(dialog)
        dialog.title(self._text("add_manual"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        container = ttk.Frame(dialog, style="Surface.TFrame", padding=(18, 16, 18, 16))
        container.pack(fill=BOTH, expand=True)

        font_family = tkfont.nametofont("TkDefaultFont").actual("family")
        ttk.Label(container, text=self._text("add_manual"), style="Surface.TLabel", font=(font_family, 15, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        value_var = StringVar()
        replacement_var = StringVar()
        ttk.Label(container, text=self._text("value"), style="Surface.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        ttk.Entry(container, textvariable=value_var).grid(row=1, column=1, sticky="ew", pady=(0, 10))
        ttk.Label(container, text=self._text("replacement"), style="Surface.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        ttk.Entry(container, textvariable=replacement_var).grid(row=2, column=1, sticky="ew", pady=(0, 10))
        container.columnconfigure(1, weight=1)

        def generate_placeholder() -> None:
            replacement_var.set(next_placeholder(prefix_for_entity("CUSTOM_TERM"), self._used_replacements()))

        def save() -> None:
            value = value_var.get().strip()
            replacement = replacement_var.get().strip() or next_placeholder(prefix_for_entity("CUSTOM_TERM"), self._used_replacements())
            if not value:
                messagebox.showwarning(self._text("missing_value_title"), self._text("missing_value_message"), parent=dialog)
                return
            self.edit_value.set(value)
            self.edit_entity.set("CUSTOM_TERM")
            self.edit_replacement.set(replacement)
            self.add_manual_candidate()
            dialog.destroy()

        button_row = ttk.Frame(container, style="Surface.TFrame")
        button_row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        self._secondary_button(button_row, self._text("generate_placeholder"), generate_placeholder).pack(side=LEFT, padx=(0, 8))
        self._secondary_button(button_row, self._text("close"), dialog.destroy).pack(side=LEFT, padx=(0, 8))
        self._secondary_button(button_row, self._text("add_manual"), save).pack(side=LEFT)
        self._fit_child_window(dialog, 560, 300)
        dialog.grab_set()
        dialog.focus_set()

    def _on_candidate_tree_click(self, event) -> None:
        row_id = self.candidate_tree.identify_row(event.y)
        column_id = self.candidate_tree.identify_column(event.x)
        if not row_id:
            return
        if column_id == "#1":
            candidate = self.candidates.get(row_id)
            if candidate:
                candidate.enabled = not candidate.enabled
                self._refresh_candidate_tree()
        elif column_id == "#8":
            self.candidates.pop(row_id, None)
            self.candidate_order = [candidate_id for candidate_id in self.candidate_order if candidate_id != row_id]
            self._refresh_candidate_tree()

    def _on_candidate_tree_double_click(self, event) -> None:
        row_id = self.candidate_tree.identify_row(event.y)
        column_id = self.candidate_tree.identify_column(event.x)
        if not row_id or column_id != "#3":
            return
        candidate = self.candidates.get(row_id)
        if not candidate:
            return
        replacement = simpledialog.askstring(
            self._text("replacement"),
            self._text("replacement"),
            initialvalue=candidate.replacement,
            parent=self.root,
        )
        if replacement is None:
            return
        replacement = replacement.strip()
        if not replacement:
            messagebox.showwarning(self._text("incomplete_title"), self._text("incomplete_message"), parent=self.root)
            return
        candidate.replacement = replacement
        self._refresh_candidate_tree()

    def enable_all_candidates(self) -> None:
        for candidate in self.candidates.values():
            candidate.enabled = True
        self._refresh_candidate_tree()

    def disable_all_candidates(self) -> None:
        for candidate in self.candidates.values():
            candidate.enabled = False
        self._refresh_candidate_tree()

    def toggle_selected_candidates(self) -> None:
        for candidate_id in self._selected_candidate_ids():
            candidate = self.candidates.get(candidate_id)
            if candidate:
                candidate.enabled = not candidate.enabled
        self._refresh_candidate_tree()

    def delete_selected_candidates(self) -> None:
        selected = set(self._selected_candidate_ids())
        for candidate_id in selected:
            self.candidates.pop(candidate_id, None)
        self.candidate_order = [candidate_id for candidate_id in self.candidate_order if candidate_id not in selected]
        self._refresh_candidate_tree()

    def clear_candidates(self) -> None:
        self.candidates.clear()
        self.candidate_order.clear()
        self._refresh_candidate_tree()

    def _clear_detected_candidates(self) -> None:
        detected = {
            candidate_id
            for candidate_id, candidate in self.candidates.items()
            if candidate.source != "manual"
        }
        for candidate_id in detected:
            self.candidates.pop(candidate_id, None)
        self.candidate_order = [candidate_id for candidate_id in self.candidate_order if candidate_id not in detected]
        self._refresh_candidate_tree()

    def _refresh_candidate_tree(self) -> None:
        for item in self.candidate_tree.get_children():
            self.candidate_tree.delete(item)
        visible_index = 0
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if not candidate:
                continue
            files = self._format_candidate_files(candidate)
            tags = ["even" if visible_index % 2 else "odd"]
            tags.append("candidate_on" if candidate.enabled else "candidate_off")
            self.candidate_tree.insert(
                "",
                END,
                iid=candidate_id,
                values=(
                    "\u2713" if candidate.enabled else "\u2715",
                    candidate.value,
                    candidate.replacement,
                    candidate.context_label or "-",
                    candidate.count,
                    files,
                    self._format_candidate_source(candidate.source),
                    self._text("action_delete"),
                ),
                tags=tuple(tags),
            )
            visible_index += 1
        if visible_index == 0:
            self.candidate_tree.insert(
                "",
                END,
                iid="__empty_candidates__",
                values=(self._empty_text("candidates"), "", "", "", "", "", "", ""),
                tags=("empty",),
            )

    def _selected_replacements(self) -> list[ReplacementSpec]:
        replacements: list[ReplacementSpec] = []
        by_global_value: dict[str, str] = {}
        by_scoped_value: dict[tuple[str, str | None], str] = {}
        by_replacement: dict[str, str] = {}
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if not candidate or not candidate.enabled:
                continue
            value = candidate.value.strip()
            replacement = candidate.replacement.strip()
            if not value or not replacement:
                raise ValueError(self._text("enabled_candidate_empty"))
            if candidate.context_key:
                scope_key = (value, candidate.context_key)
                existing_replacement = by_scoped_value.get(scope_key)
                by_scoped_value[scope_key] = replacement
            else:
                existing_replacement = by_global_value.get(value)
                by_global_value[value] = replacement
            if existing_replacement and existing_replacement != replacement:
                raise ValueError(self._text("same_value_multiple_replacements").format(value=value))
            existing_value = by_replacement.get(replacement)
            owner = f"{value}\u241f{candidate.context_key or ''}"
            if existing_value and existing_value != owner:
                raise ValueError(self._text("same_replacement_multiple_values").format(replacement=replacement))
            by_replacement[replacement] = owner
            replacements.append(
                ReplacementSpec(
                    entity=candidate.entity,
                    prefix=candidate.prefix,
                    value=value,
                    replacement=replacement,
                    context_key=candidate.context_key,
                    context_label=candidate.context_label,
                )
            )
        if not replacements:
            raise ValueError(self._text("no_enabled_candidates"))
        return replacements

    def _selected_candidate_ids(self) -> list[str]:
        return [item for item in self.candidate_tree.selection() if item != "__empty_candidates__"]

    def _used_replacements(self) -> set[str]:
        return {candidate.replacement for candidate in self.candidates.values() if candidate.replacement}

    def _candidate_key(self, entity: str, value: str, context_key: str | None = None) -> str:
        digest = hashlib.sha256(f"{entity}\u241f{value}\u241f{context_key or ''}".encode("utf-8")).hexdigest()
        return f"candidate_{digest[:24]}"

    def _candidate_id_for_value(self, value: str) -> str | None:
        value = value.strip()
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if candidate and not candidate.context_key and candidate.value.strip() == value:
                return candidate_id
        return None

    def _format_candidate_files(self, candidate: CandidateItem) -> str:
        if not candidate.files:
            return "-"
        names = sorted(Path(path).name for path in candidate.files)
        if len(names) <= 2:
            return ", ".join(names)
        return self._text("more_files").format(first=names[0], second=names[1], count=len(names))

    def _format_candidate_source(self, source: str) -> str:
        if source == "manual":
            return self._text("manual")
        if source == "excel-entity":
            return self._text("excel_entity")
        return self._text("auto")

    def _custom_terms(self) -> list[str]:
        terms = []
        for candidate in self.candidates.values():
            if candidate.enabled and candidate.source == "manual" and candidate.value.strip():
                terms.append(candidate.value.strip())
        return terms

    def _log(self, level: str, message: str) -> None:
        self.queue.put(("log", (level, message)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    level, message = payload
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    line = f"[{timestamp}] [{level}] {message}"
                    self.log_entries.append(line)
                    if len(self.log_entries) > 300:
                        self.log_entries = self.log_entries[-300:]
                    if level == "ERROR":
                        self._set_status(message, "error")
                    else:
                        self._set_status(message, "busy" if getattr(self, "_busy_operation", None) else "ready")
                elif kind == "candidates":
                    self._merge_candidate_hits(payload)
                    self._end_operation()
                    self._set_status(self._text("status_done"), "success", flash=True)
                elif kind == "anonymize_done":
                    self._end_operation()
                    self._set_status(self._text("status_done"), "success", flash=True)
                    self._show_anonymize_result(payload)
                elif kind == "anonymize_failed":
                    self._end_operation()
                    self._set_status(str(payload), "error")
                    messagebox.showerror(self._text("anonymize_failed_title"), str(payload))
                elif kind == "restore_done":
                    self._end_operation()
                    self._set_status(self._text("status_done"), "success", flash=True)
                    self._show_restore_result(payload)
                elif kind == "restore_failed":
                    self._end_operation()
                    self._set_status(str(payload), "error")
                    messagebox.showerror(self._text("restore_failed_title"), str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _show_anonymize_result(self, result: dict[str, object]) -> None:
        ok_count = result.get("ok_count", 0)
        error_count = result.get("error_count", 0)
        skipped_count = result.get("skipped_count", 0)
        total_counts = result.get("total_counts", {})
        mapping_file = result.get("mapping_file", "")
        report_file = result.get("report_file", "")
        self._add_history_record(
            action="anonymize",
            file_count=len(result.get("input_files", []) or []),
            ok_count=int(ok_count),
            failed_count=int(error_count),
            skipped_count=int(skipped_count),
            output_dir=str(result.get("output_dir", "")),
            mapping_file=str(mapping_file),
            report_file=str(report_file),
            input_files=list(result.get("input_files", []) or []),
        )
        self._track_usage(
            "anonymize_done",
            {
                "file_count": len(result.get("input_files", []) or []),
                "ok_count": int(ok_count),
                "failed_count": int(error_count),
                "skipped_count": int(skipped_count),
                "remove_headers_footers": bool(result.get("remove_headers_footers", False)),
            },
        )
        message = (
            f"{self._text('result_ok')}: {ok_count}\n"
            f"{self._text('result_skipped')}: {skipped_count}\n"
            f"{self._text('result_failed')}: {error_count}\n"
            f"{self._text('result_counts')}: {total_counts}\n\n"
            f"{self._text('result_mapping')}: {mapping_file}\n"
            f"{self._text('result_report')}: {report_file}"
        )
        if error_count:
            messagebox.showwarning(self._text("anonymize_done_error_title"), message)
        elif skipped_count:
            messagebox.showwarning(self._text("anonymize_done_skip_title"), message)
        else:
            messagebox.showinfo(self._text("anonymize_done_title"), message)

    def _show_restore_result(self, result: dict[str, object]) -> None:
        ok_count = result.get("ok_count", 0)
        error_count = result.get("error_count", 0)
        output_dir = result.get("output_dir", "")
        self._add_history_record(
            action="restore",
            file_count=len(result.get("input_files", []) or []),
            ok_count=int(ok_count),
            failed_count=int(error_count),
            output_dir=str(output_dir),
            mapping_file=str(result.get("mapping_file", "")),
            input_files=list(result.get("input_files", []) or []),
        )
        self._track_usage(
            "restore_done",
            {
                "file_count": len(result.get("input_files", []) or []),
                "ok_count": int(ok_count),
                "failed_count": int(error_count),
            },
        )
        message = (
            f"{self._text('restore_result_ok')}: {ok_count}\n"
            f"{self._text('restore_result_failed')}: {error_count}\n\n"
            f"{self._text('restore_result_output')}: {output_dir}"
        )
        if error_count:
            messagebox.showwarning(self._text("restore_done_error_title"), message)
        else:
            messagebox.showinfo(self._text("restore_done_title"), message)

    def _add_history_record(
        self,
        action: str,
        file_count: int,
        ok_count: int,
        failed_count: int,
        skipped_count: int = 0,
        output_dir: str = "",
        mapping_file: str = "",
        report_file: str = "",
        input_files: list[str] | None = None,
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = HistoryRecord(
            id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
            timestamp=timestamp,
            action=action,
            file_count=file_count,
            ok_count=ok_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            output_dir=output_dir,
            mapping_file=mapping_file,
            report_file=report_file,
            input_files=input_files or [],
        )
        self.history_records.insert(0, record)
        self.history_records = self.history_records[:200]
        save_history(HISTORY_FILE, self.history_records)

    def _show_history_dialog(self) -> None:
        dialog = Toplevel(self.root)
        self._prepare_dialog(dialog)
        dialog.title(self._text("history_title"))
        dialog.transient(self.root)
        dialog.resizable(True, True)
        self._center_child_window(dialog, 1120, 640)
        dialog.minsize(980, 560)

        container = ttk.Frame(dialog, style="Surface.TFrame", padding=(20, 18, 20, 18))
        container.pack(fill=BOTH, expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        columns = ("time", "action", "files", "ok", "failed", "output")
        table_frame = ttk.Frame(container, style="Surface.TFrame")
        table_frame.grid(row=0, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        headings = {
            "time": self._text("history_col_time"),
            "action": self._text("history_col_action"),
            "files": self._text("history_col_files"),
            "ok": self._text("history_col_ok"),
            "failed": self._text("history_col_failed"),
            "output": self._text("history_col_output"),
        }
        widths = {"time": 190, "action": 100, "files": 90, "ok": 90, "failed": 90, "output": 520}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], minwidth=widths[column], anchor="w", stretch=(column == "output"))
        for record in self.history_records:
            tree.insert(
                "",
                END,
                iid=record.id,
                values=(
                    record.timestamp,
                    self._history_action_label(record.action),
                    record.file_count,
                    record.ok_count,
                    record.failed_count + record.skipped_count,
                    record.output_dir,
                ),
            )

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        if not self.history_records:
            ttk.Label(container, text=self._text("history_empty"), style="SurfaceMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))

        button_row = ttk.Frame(container, style="Surface.TFrame")
        button_row.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._secondary_button(button_row, text=self._text("history_export"), command=self._export_history).pack(side=LEFT)
        self._secondary_button(button_row, text=self._text("history_delete"), command=lambda: self._delete_history_selection(tree)).pack(side=LEFT, padx=(8, 0))
        self._danger_button(button_row, text=self._text("history_clear"), command=lambda: self._clear_history(tree)).pack(side=LEFT, padx=(8, 0))
        self._secondary_button(button_row, text=self._text("close"), command=dialog.destroy).pack(side=RIGHT)
        dialog.grab_set()

    def _history_action_label(self, action: str) -> str:
        if action == "restore":
            return self._text("history_action_restore")
        return self._text("history_action_anonymize")

    def _export_history(self) -> None:
        path = filedialog.asksaveasfilename(
            title=self._text("history_export_dialog"),
            defaultextension=".csv",
            initialfile=f"脱敏历史记录_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            filetypes=[("CSV", "*.csv"), (self._text("all_files"), "*.*")],
        )
        if not path:
            return
        export_history_csv(Path(path), self.history_records)
        messagebox.showinfo(self._text("history_title"), self._text("history_exported").format(path=path))

    def _delete_history_selection(self, tree: ttk.Treeview) -> None:
        selected = set(tree.selection())
        if not selected:
            return
        self.history_records = [record for record in self.history_records if record.id not in selected]
        for item in selected:
            tree.delete(item)
        save_history(HISTORY_FILE, self.history_records)

    def _clear_history(self, tree: ttk.Treeview) -> None:
        if not self.history_records:
            return
        if not messagebox.askyesno(self._text("history_title"), self._text("history_confirm_clear")):
            return
        self.history_records = []
        for item in tree.get_children():
            tree.delete(item)
        save_history(HISTORY_FILE, self.history_records)


def main() -> None:
    if os.environ.get("DESENSITIZER_SELF_TEST") == "1":
        print("desensitizer self test ok")
        return
    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    DesensitizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
