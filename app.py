from __future__ import annotations

import hashlib
import os
import queue
import sys
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, BooleanVar, Canvas, Menu, PhotoImage, StringVar, Tk, filedialog, messagebox, simpledialog
from tkinter import ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText

from desensitizer_app import __version__
from desensitizer_app.candidates import (
    ENTITY_PREFIXES,
    CandidateHit,
    CandidateItem,
    ReplacementSpec,
    next_placeholder,
    prefix_for_entity,
)
from desensitizer_app.core import DesensitizeError, SkippedFile, write_report
from desensitizer_app.mapping import MappingStore, is_encrypted_mapping
from desensitizer_app.processors import (
    anonymize_file_with_replacements,
    is_known_file,
    restore_file,
    scan_file_candidates,
)


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


class DesensitizerApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.language = "zh"
        self.current_theme = "light"
        self.root.title(APP_NAME)
        self._app_icon_image: PhotoImage | None = None
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
        self.language_var = StringVar(value=self.language)
        self.theme_var = StringVar(value=self.current_theme)

        self.edit_value = StringVar(value="")
        self.edit_entity = StringVar(value="CUSTOM_TERM")
        self.edit_replacement = StringVar(value="")
        self._scroll_canvases: list[Canvas] = []

        self._style = ttk.Style(self.root)
        self.root.option_add("*tearOff", False)
        self._configure_fonts()
        self._setup_menu()
        self._build_ui()
        self._apply_theme(self.current_theme)
        self._poll_queue()

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
        width = min(1280, max(900, work_width - 80))
        height = min(760, max(620, work_height - 100))
        x = left + max(0, (work_width - width) // 2)
        y = top + max(0, min(40, (work_height - height) // 3))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(900, 620)

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
                "dark": "深色",
                "blue": "商务蓝",
                "green": "护眼绿",
                "teal": "青绿色",
                "purple": "淡紫色",
                "graphite": "石墨灰",
                "high_contrast": "高对比",
                "language": "语言",
                "chinese": "中文",
                "english": "English",
                "help": "帮助",
                "mapping_password_help": "映射表密码说明",
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
                "input_files": "输入文件",
                "add_file": "添加文件",
                "add_folder": "添加文件夹",
                "recursive_folders": "递归子文件夹",
                "remove_selected": "移除选中",
                "clear": "清空",
                "file_path": "文件路径",
                "output_dir": "输出目录",
                "choose": "选择",
                "custom_terms": "业务敏感词（每行一个，自动扫描时会加入候选）",
                "encrypt_mapping": "加密映射表（推荐）",
                "mapping_password_title": "映射表密码",
                "mapping_password_prompt": "请为本次加密映射表设置密码。还原时必须输入同一个密码；请妥善保存，遗失后无法恢复。",
                "mapping_password_confirm_prompt": "请再次输入映射表密码。",
                "mapping_password_mismatch": "两次输入的密码不一致。",
                "mapping_password_cancelled": "已取消。映射表加密需要输入密码。",
                "auto_detect": "自动识别可脱敏信息",
                "scan_candidates": "扫描候选信息",
                "start_anonymize": "开始脱敏",
                "candidate_frame": "候选敏感信息（先扫描或手动添加，再勾选确认）",
                "enable_all": "全部启用",
                "disable_all": "全部禁用",
                "toggle_selected": "切换选中",
                "delete_selected": "删除选中",
                "clear_candidates": "清空候选",
                "col_enabled": "启用",
                "col_entity": "类型",
                "col_value": "原文",
                "col_replacement": "替换为",
                "col_count": "次数",
                "col_files": "文件",
                "col_source": "来源",
                "edit_or_add": "编辑或手动新增",
                "value": "原文",
                "entity": "类型",
                "replacement": "替换为",
                "generate_placeholder": "生成占位符",
                "save_edit": "保存修改",
                "add_manual": "新增手动条目",
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
                "dark": "Dark",
                "blue": "Business Blue",
                "green": "Soft Green",
                "teal": "Teal",
                "purple": "Lavender",
                "graphite": "Graphite",
                "high_contrast": "High Contrast",
                "language": "Language",
                "chinese": "中文",
                "english": "English",
                "help": "Help",
                "mapping_password_help": "Mapping Password Help",
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
                "input_files": "Input Files",
                "add_file": "Add Files",
                "add_folder": "Add Folder",
                "recursive_folders": "Recursive Subfolders",
                "remove_selected": "Remove Selected",
                "clear": "Clear",
                "file_path": "File Path",
                "output_dir": "Output Folder",
                "choose": "Choose",
                "custom_terms": "Business Sensitive Terms (one per line; included in automatic scan)",
                "encrypt_mapping": "Encrypt Mapping File (Recommended)",
                "mapping_password_title": "Mapping Password",
                "mapping_password_prompt": "Set a password for this encrypted mapping file. The same password is required for restoration; keep it safe because it cannot be recovered.",
                "mapping_password_confirm_prompt": "Enter the mapping password again.",
                "mapping_password_mismatch": "The two passwords do not match.",
                "mapping_password_cancelled": "Cancelled. Mapping encryption requires a password.",
                "auto_detect": "Automatically Detect Sensitive Information",
                "scan_candidates": "Scan Candidates",
                "start_anonymize": "Start Desensitizing",
                "candidate_frame": "Sensitive Information Candidates (scan or add manually, then confirm)",
                "enable_all": "Enable All",
                "disable_all": "Disable All",
                "toggle_selected": "Toggle Selected",
                "delete_selected": "Delete Selected",
                "clear_candidates": "Clear Candidates",
                "col_enabled": "Enabled",
                "col_entity": "Type",
                "col_value": "Original",
                "col_replacement": "Replace With",
                "col_count": "Count",
                "col_files": "Files",
                "col_source": "Source",
                "edit_or_add": "Edit or Add Manually",
                "value": "Original",
                "entity": "Type",
                "replacement": "Replace With",
                "generate_placeholder": "Generate Placeholder",
                "save_edit": "Save Changes",
                "add_manual": "Add Manual Entry",
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
                "enabled_candidate_empty": "An enabled candidate has empty original text or replacement value.",
                "same_value_multiple_replacements": "The same original text has different replacements: {value}",
                "same_replacement_multiple_values": "The same replacement is used by multiple originals: {replacement}",
                "no_enabled_candidates": "No candidates are enabled. Scan candidates first or add manual entries.",
                "more_files": "{first}, {second} ... {count} total",
            },
        }
        return labels.get(self.language, labels["zh"]).get(key, key)

    def _configure_fonts(self) -> None:
        try:
            self.root.tk.call("tk", "scaling", 1.18)
        except Exception:
            pass
        families = set(tkfont.families(self.root))
        family = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "Segoe UI"
        font_specs = {
            "TkDefaultFont": {"size": 10},
            "TkTextFont": {"size": 10},
            "TkMenuFont": {"size": 10},
            "TkHeadingFont": {"size": 10, "weight": "bold"},
            "TkCaptionFont": {"size": 10},
            "TkSmallCaptionFont": {"size": 9},
            "TkTooltipFont": {"size": 9},
        }
        for name, options in font_specs.items():
            try:
                named_font = tkfont.nametofont(name)
                named_font.configure(family=family, **options)
            except Exception:
                continue

    def _setup_menu(self) -> None:
        self.menu_bar = Menu(self.root)
        self.root.configure(menu=self.menu_bar)
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        if self.menu_bar.index("end") is not None:
            self.menu_bar.delete(0, END)

        settings_menu = Menu(self.menu_bar)
        color_menu = Menu(settings_menu)
        for theme_key in ("light", "dark", "blue", "green", "teal", "purple", "graphite", "high_contrast"):
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

        help_menu = Menu(self.menu_bar)
        help_menu.add_command(label=self._text("mapping_password_help"), command=self._show_mapping_password_help)
        help_menu.add_command(label=self._text("open_source_license"), command=self._show_license_notice)
        help_menu.add_separator()
        help_menu.add_command(label=self._text("about"), command=self._show_about)
        self.menu_bar.add_cascade(label=self._text("help"), menu=help_menu)

    def _set_language(self, language: str) -> None:
        if language == self.language:
            return
        self.language = language
        self.language_var.set(language)
        self.root.title(self._text("app_title"))
        self._refresh_menu()
        self._rebuild_ui()
        messagebox.showinfo(self._text("language_title"), self._text("language_message"))

    def _rebuild_ui(self) -> None:
        custom_terms = ""
        log_content = ""
        if hasattr(self, "custom_terms_text"):
            custom_terms = self.custom_terms_text.get("1.0", END)
        if hasattr(self, "log_text"):
            log_content = self.log_text.get("1.0", END)

        for child in self.root.winfo_children():
            if child is self.menu_bar or isinstance(child, Menu):
                continue
            child.destroy()
        self._build_ui()

        if custom_terms:
            self.custom_terms_text.insert("1.0", custom_terms)
        if log_content:
            self.log_text.insert("1.0", log_content)
            self.log_text.see(END)

        for path in self.files:
            self.file_list.insert("", END, values=(str(path),))
        for path in self.restore_files:
            self.restore_file_list.insert("", END, values=(str(path),))
        self._refresh_candidate_tree()
        self._apply_theme(self.current_theme)

    def _apply_theme(self, theme: str) -> None:
        self.current_theme = theme
        self.theme_var.set(theme)
        palettes = {
            "light": {"bg": "#f5f6f8", "fg": "#1f2933", "field": "#ffffff", "button": "#eef1f5", "accent": "#1f6feb", "select": "#d8e8ff"},
            "dark": {"bg": "#202124", "fg": "#f1f3f4", "field": "#2d2f33", "button": "#383b40", "accent": "#8ab4f8", "select": "#3c4043"},
            "blue": {"bg": "#eef5fb", "fg": "#17324d", "field": "#ffffff", "button": "#d9eaf7", "accent": "#1769aa", "select": "#c7e0f4"},
            "green": {"bg": "#f0f7f1", "fg": "#1f3b2d", "field": "#ffffff", "button": "#dceee0", "accent": "#2e7d50", "select": "#c9e7d0"},
            "teal": {"bg": "#edf7f6", "fg": "#173b3a", "field": "#ffffff", "button": "#d6eeeb", "accent": "#16847f", "select": "#c4e7e3"},
            "purple": {"bg": "#f6f2fb", "fg": "#382d45", "field": "#ffffff", "button": "#e7ddf3", "accent": "#6f4aa8", "select": "#ded0ef"},
            "graphite": {"bg": "#eceff1", "fg": "#263238", "field": "#ffffff", "button": "#d8dde1", "accent": "#546e7a", "select": "#cfd8dc"},
            "high_contrast": {"bg": "#000000", "fg": "#ffffff", "field": "#111111", "button": "#222222", "accent": "#ffd400", "select": "#3a3a00"},
        }
        palette = palettes.get(theme, palettes["light"])
        if theme != "light" and "clam" in self._style.theme_names():
            self._style.theme_use("clam")
        elif "vista" in self._style.theme_names():
            self._style.theme_use("vista")

        self.root.configure(background=palette["bg"])
        self._style.configure(".", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("TFrame", background=palette["bg"])
        self._style.configure("TLabelframe", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("TLabel", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("TCheckbutton", background=palette["bg"], foreground=palette["fg"])
        self._style.configure("TButton", background=palette["button"], foreground=palette["fg"], padding=(12, 7))
        self._style.configure("TEntry", fieldbackground=palette["field"], foreground=palette["fg"])
        self._style.configure("TCombobox", fieldbackground=palette["field"], foreground=palette["fg"])
        self._style.configure("TNotebook", background=palette["bg"])
        self._style.configure("TNotebook.Tab", background=palette["button"], foreground=palette["fg"], padding=(18, 8))
        self._style.map("TNotebook.Tab", background=[("selected", palette["field"])], foreground=[("selected", palette["fg"])])
        self._style.configure("Treeview", background=palette["field"], fieldbackground=palette["field"], foreground=palette["fg"], rowheight=30)
        self._style.configure("Treeview.Heading", foreground=palette["fg"])
        self._style.map("Treeview", background=[("selected", palette["select"])], foreground=[("selected", palette["fg"])])
        if hasattr(self, "log_text"):
            self.log_text.configure(
                background=palette["field"],
                foreground=palette["fg"],
                insertbackground=palette["fg"],
            )
        if hasattr(self, "custom_terms_text"):
            self.custom_terms_text.configure(
                background=palette["field"],
                foreground=palette["fg"],
                insertbackground=palette["fg"],
            )
        for canvas in getattr(self, "_scroll_canvases", []):
            canvas.configure(background=palette["bg"])

    def _show_license_notice(self) -> None:
        messagebox.showinfo(self._text("license_title"), self._text("license_message"))

    def _show_mapping_password_help(self) -> None:
        messagebox.showinfo(self._text("mapping_password_help_title"), self._text("mapping_password_help_message"))

    def _show_about(self) -> None:
        if self.language == "en":
            message = (
                f"{APP_NAME_EN}\n"
                f"Version: {__version__}\n"
                f"Edition: {EDITION_NAME_EN}\n"
                f"Publisher: {COMPANY_NAME_EN}\n\n"
                f"License: {LICENSE_NAME}\n"
                "This tool processes supported files locally by default."
            )
        else:
            message = (
                f"{APP_NAME}\n"
                f"版本：{__version__}\n"
                f"版本类型：{EDITION_NAME}\n"
                f"出品方：{COMPANY_NAME}\n\n"
                f"许可证：{LICENSE_NAME}\n"
                "本工具默认在本地处理支持的文件。"
            )
        messagebox.showinfo(self._text("about_title"), message)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.anonymize_tab, self.anonymize_frame = self._create_scrollable_tab(notebook)
        self.restore_tab, self.restore_frame = self._create_scrollable_tab(notebook)
        notebook.add(self.anonymize_tab, text=self._text("tab_anonymize"))
        notebook.add(self.restore_tab, text=self._text("tab_restore"))

        self._build_anonymize_tab()
        self._build_restore_tab()

        log_frame = ttk.LabelFrame(self.root, text=self._text("run_log"))
        log_frame.pack(fill=BOTH, expand=False, padx=10, pady=(0, 10))
        self.log_text = ScrolledText(log_frame, height=4, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _create_scrollable_tab(self, parent: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(parent)
        canvas = Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")

        def on_mousewheel(event) -> None:
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

    def _build_anonymize_tab(self) -> None:
        top = ttk.Frame(self.anonymize_frame)
        top.pack(fill=BOTH, expand=True, padx=8, pady=8)

        file_frame = ttk.LabelFrame(top, text=self._text("input_files"))
        file_frame.pack(fill=BOTH, expand=False, padx=0, pady=(0, 8))

        button_row = ttk.Frame(file_frame)
        button_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(button_row, text=self._text("add_file"), command=self.add_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text=self._text("add_folder"), command=self.add_folder).pack(side=LEFT, padx=(0, 6))
        ttk.Checkbutton(button_row, text=self._text("recursive_folders"), variable=self.recursive_scan).pack(side=LEFT, padx=(4, 12))
        ttk.Button(button_row, text=self._text("remove_selected"), command=self.remove_selected_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text=self._text("clear"), command=self.clear_files).pack(side=LEFT)

        self.file_list = ttk.Treeview(file_frame, columns=("path",), show="headings", height=5)
        self.file_list.heading("path", text=self._text("file_path"))
        self.file_list.column("path", width=1040, anchor="w")
        self.file_list.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        output_frame = ttk.LabelFrame(top, text=self._text("output_dir"))
        output_frame.pack(fill="x", padx=0, pady=(0, 8))
        ttk.Entry(output_frame, textvariable=self.output_dir).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Checkbutton(output_frame, text=self._text("encrypt_mapping"), variable=self.encrypt_mapping).pack(side=LEFT, padx=(0, 8), pady=8)
        ttk.Button(output_frame, text=self._text("choose"), command=self.choose_output_dir).pack(side=RIGHT, padx=8, pady=8)

        custom_frame = ttk.LabelFrame(top, text=self._text("custom_terms"))
        custom_frame.pack(fill=BOTH, expand=False, padx=0, pady=(0, 10))
        self.custom_terms_text = ScrolledText(custom_frame, height=8, wrap="word", undo=True)
        self.custom_terms_text.pack(fill=BOTH, expand=True, padx=8, pady=8)

        scan_row = ttk.Frame(top)
        scan_row.pack(fill="x", padx=0, pady=(0, 8))
        ttk.Checkbutton(scan_row, text=self._text("auto_detect"), variable=self.auto_detect).pack(side=LEFT)
        ttk.Button(scan_row, text=self._text("scan_candidates"), command=self.start_scan_candidates).pack(side=LEFT, padx=(12, 6))
        ttk.Button(scan_row, text=self._text("start_anonymize"), command=self.start_anonymize).pack(side=RIGHT)

        candidate_frame = ttk.LabelFrame(top, text=self._text("candidate_frame"))
        candidate_frame.pack(fill=BOTH, expand=True)

        candidate_toolbar = ttk.Frame(candidate_frame)
        candidate_toolbar.pack(fill="x", padx=8, pady=8)
        ttk.Button(candidate_toolbar, text=self._text("enable_all"), command=self.enable_all_candidates).pack(side=LEFT, padx=(0, 6))
        ttk.Button(candidate_toolbar, text=self._text("disable_all"), command=self.disable_all_candidates).pack(side=LEFT, padx=(0, 6))
        ttk.Button(candidate_toolbar, text=self._text("toggle_selected"), command=self.toggle_selected_candidates).pack(side=LEFT, padx=(0, 6))
        ttk.Button(candidate_toolbar, text=self._text("delete_selected"), command=self.delete_selected_candidates).pack(side=LEFT, padx=(0, 6))
        ttk.Button(candidate_toolbar, text=self._text("clear_candidates"), command=self.clear_candidates).pack(side=LEFT)

        table_frame = ttk.Frame(candidate_frame)
        table_frame.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))
        columns = ("enabled", "entity", "value", "replacement", "count", "files", "source")
        self.candidate_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=9)
        headings = {
            "enabled": self._text("col_enabled"),
            "entity": self._text("col_entity"),
            "value": self._text("col_value"),
            "replacement": self._text("col_replacement"),
            "count": self._text("col_count"),
            "files": self._text("col_files"),
            "source": self._text("col_source"),
        }
        widths = {
            "enabled": 56,
            "entity": 150,
            "value": 240,
            "replacement": 180,
            "count": 56,
            "files": 260,
            "source": 70,
        }
        for column in columns:
            self.candidate_tree.heading(column, text=headings[column])
            self.candidate_tree.column(column, width=widths[column], anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.candidate_tree.yview)
        self.candidate_tree.configure(yscrollcommand=yscroll.set)
        self.candidate_tree.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=RIGHT, fill="y")
        self.candidate_tree.bind("<<TreeviewSelect>>", self.on_candidate_selected)

        edit_frame = ttk.LabelFrame(candidate_frame, text=self._text("edit_or_add"))
        edit_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(edit_frame, text=self._text("value")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ttk.Entry(edit_frame, textvariable=self.edit_value).grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        ttk.Label(edit_frame, text=self._text("entity")).grid(row=0, column=2, padx=8, pady=8, sticky="w")
        entity_box = ttk.Combobox(
            edit_frame,
            textvariable=self.edit_entity,
            values=sorted(ENTITY_PREFIXES.keys()),
            state="readonly",
            width=24,
        )
        entity_box.grid(row=0, column=3, padx=4, pady=8, sticky="w")
        ttk.Label(edit_frame, text=self._text("replacement")).grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ttk.Entry(edit_frame, textvariable=self.edit_replacement).grid(row=1, column=1, padx=4, pady=8, sticky="ew")
        ttk.Button(edit_frame, text=self._text("generate_placeholder"), command=self.generate_edit_placeholder).grid(
            row=1, column=2, padx=8, pady=8, sticky="w"
        )
        ttk.Button(edit_frame, text=self._text("save_edit"), command=self.save_candidate_edit).grid(
            row=1, column=3, padx=4, pady=8, sticky="w"
        )
        ttk.Button(edit_frame, text=self._text("add_manual"), command=self.add_manual_candidate).grid(
            row=1, column=4, padx=8, pady=8, sticky="w"
        )
        edit_frame.columnconfigure(1, weight=1)

    def _build_restore_tab(self) -> None:
        file_frame = ttk.LabelFrame(self.restore_frame, text=self._text("restore_files"))
        file_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)

        button_row = ttk.Frame(file_frame)
        button_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(button_row, text=self._text("add_file"), command=self.add_restore_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text=self._text("remove_selected"), command=self.remove_selected_restore_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text=self._text("clear"), command=self.clear_restore_files).pack(side=LEFT)

        self.restore_file_list = ttk.Treeview(file_frame, columns=("path",), show="headings", height=5)
        self.restore_file_list.heading("path", text=self._text("file_path"))
        self.restore_file_list.column("path", width=1040, anchor="w")
        self.restore_file_list.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        mapping_frame = ttk.LabelFrame(self.restore_frame, text=self._text("mapping_json"))
        mapping_frame.pack(fill="x", padx=8, pady=8)
        ttk.Entry(mapping_frame, textvariable=self.mapping_path).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Button(mapping_frame, text=self._text("choose"), command=self.choose_mapping_file).pack(side=RIGHT, padx=8, pady=8)

        output_frame = ttk.LabelFrame(self.restore_frame, text=self._text("output_dir"))
        output_frame.pack(fill="x", padx=8, pady=8)
        ttk.Entry(output_frame, textvariable=self.restore_output_dir).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Button(output_frame, text=self._text("start_restore"), command=self.start_restore).pack(side=RIGHT, padx=8, pady=8)
        ttk.Button(output_frame, text=self._text("choose"), command=self.choose_restore_output_dir).pack(side=RIGHT, padx=8, pady=8)

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

    def remove_selected_files(self) -> None:
        selected = self.file_list.selection()
        selected_paths = {Path(self.file_list.item(item, "values")[0]) for item in selected}
        self.files = [path for path in self.files if path not in selected_paths]
        for item in selected:
            self.file_list.delete(item)

    def remove_selected_restore_files(self) -> None:
        selected = self.restore_file_list.selection()
        selected_paths = {Path(self.restore_file_list.item(item, "values")[0]) for item in selected}
        self.restore_files = [path for path in self.restore_files if path not in selected_paths]
        for item in selected:
            self.restore_file_list.delete(item)

    def clear_files(self) -> None:
        self.files.clear()
        for item in self.file_list.get_children():
            self.file_list.delete(item)

    def clear_restore_files(self) -> None:
        self.restore_files.clear()
        for item in self.restore_file_list.get_children():
            self.restore_file_list.delete(item)

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

    def start_scan_candidates(self) -> None:
        if not self.files:
            messagebox.showwarning(self._text("missing_files_title"), self._text("scan_missing_files"))
            return
        if not self.auto_detect.get():
            messagebox.showinfo(self._text("manual_mode_title"), self._text("manual_mode_message"))
            return
        self.clear_candidates()
        custom_terms = self._custom_terms()
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
        threading.Thread(
            target=self._run_anonymize,
            args=(list(self.files), output_dir, replacements, mapping_password),
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
                )
        except ValueError as exc:
            self._log("ERROR", str(exc))
            self.queue.put(("anonymize_failed", str(exc)))
            return
        for file_path in files:
            try:
                output_path, counts, message = anonymize_file_with_replacements(file_path, output_dir, replacements)
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
                },
            )
        )

    def _merge_candidate_hits(self, hits: list[CandidateHit]) -> None:
        for hit in hits:
            key = self._candidate_key(hit.entity, hit.value)
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
                count=hit.count,
                files={str(hit.file)},
                source=hit.source,
            )
            self.candidates[key] = candidate
            self.candidate_order.append(key)
        self._refresh_candidate_tree()

    def add_manual_candidate(self) -> None:
        value = self.edit_value.get().strip()
        entity = self.edit_entity.get().strip() or "CUSTOM_TERM"
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
        entity = self.edit_entity.get().strip() or "CUSTOM_TERM"
        replacement = self.edit_replacement.get().strip()
        if not value or not replacement:
            messagebox.showwarning(self._text("incomplete_title"), self._text("incomplete_message"))
            return
        new_key = self._candidate_key(entity, value)
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

    def _refresh_candidate_tree(self) -> None:
        for item in self.candidate_tree.get_children():
            self.candidate_tree.delete(item)
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if not candidate:
                continue
            files = self._format_candidate_files(candidate)
            self.candidate_tree.insert(
                "",
                END,
                iid=candidate_id,
                values=(
                    self._text("yes") if candidate.enabled else self._text("no"),
                    candidate.entity,
                    candidate.value,
                    candidate.replacement,
                    candidate.count,
                    files,
                    self._text("manual") if candidate.source == "manual" else self._text("auto"),
                ),
            )

    def _selected_replacements(self) -> list[ReplacementSpec]:
        replacements: list[ReplacementSpec] = []
        by_value: dict[str, str] = {}
        by_replacement: dict[str, str] = {}
        for candidate_id in self.candidate_order:
            candidate = self.candidates.get(candidate_id)
            if not candidate or not candidate.enabled:
                continue
            value = candidate.value.strip()
            replacement = candidate.replacement.strip()
            if not value or not replacement:
                raise ValueError(self._text("enabled_candidate_empty"))
            existing_replacement = by_value.get(value)
            if existing_replacement and existing_replacement != replacement:
                raise ValueError(self._text("same_value_multiple_replacements").format(value=value))
            existing_value = by_replacement.get(replacement)
            if existing_value and existing_value != value:
                raise ValueError(self._text("same_replacement_multiple_values").format(replacement=replacement))
            by_value[value] = replacement
            by_replacement[replacement] = value
            replacements.append(
                ReplacementSpec(
                    entity=candidate.entity,
                    prefix=candidate.prefix,
                    value=value,
                    replacement=replacement,
                )
            )
        if not replacements:
            raise ValueError(self._text("no_enabled_candidates"))
        return replacements

    def _selected_candidate_ids(self) -> list[str]:
        return list(self.candidate_tree.selection())

    def _used_replacements(self) -> set[str]:
        return {candidate.replacement for candidate in self.candidates.values() if candidate.replacement}

    def _candidate_key(self, entity: str, value: str) -> str:
        digest = hashlib.sha256(f"{entity}\u241f{value}".encode("utf-8")).hexdigest()
        return f"candidate_{digest[:24]}"

    def _format_candidate_files(self, candidate: CandidateItem) -> str:
        if not candidate.files:
            return "-"
        names = sorted(Path(path).name for path in candidate.files)
        if len(names) <= 2:
            return ", ".join(names)
        return self._text("more_files").format(first=names[0], second=names[1], count=len(names))

    def _custom_terms(self) -> list[str]:
        content = self.custom_terms_text.get("1.0", END)
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _log(self, level: str, message: str) -> None:
        self.queue.put(("log", (level, message)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    level, message = payload
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.log_text.insert(END, f"[{timestamp}] [{level}] {message}\n")
                    self.log_text.see(END)
                elif kind == "candidates":
                    self._merge_candidate_hits(payload)
                elif kind == "anonymize_done":
                    self._show_anonymize_result(payload)
                elif kind == "anonymize_failed":
                    messagebox.showerror(self._text("anonymize_failed_title"), str(payload))
                elif kind == "restore_done":
                    self._show_restore_result(payload)
                elif kind == "restore_failed":
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
        message = (
            f"{self._text('restore_result_ok')}: {ok_count}\n"
            f"{self._text('restore_result_failed')}: {error_count}\n\n"
            f"{self._text('restore_result_output')}: {output_dir}"
        )
        if error_count:
            messagebox.showwarning(self._text("restore_done_error_title"), message)
        else:
            messagebox.showinfo(self._text("restore_done_title"), message)


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
