from __future__ import annotations

import queue
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from desensitizer_app.core import DesensitizeError, write_report
from desensitizer_app.mapping import MappingStore
from desensitizer_app.processors import anonymize_file, restore_file


APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = APP_DIR / "output"


class DesensitizerApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("本地资料脱敏工具")
        self.root.geometry("980x680")
        self.root.minsize(860, 560)

        self.files: list[Path] = []
        self.restore_files: list[Path] = []
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self.output_dir = StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.restore_output_dir = StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.mapping_path = StringVar(value="")

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.anonymize_frame = ttk.Frame(notebook)
        self.restore_frame = ttk.Frame(notebook)
        notebook.add(self.anonymize_frame, text="文件脱敏")
        notebook.add(self.restore_frame, text="按映射还原")

        self._build_anonymize_tab()
        self._build_restore_tab()

        log_frame = ttk.LabelFrame(self.root, text="运行日志")
        log_frame.pack(fill=BOTH, expand=False, padx=10, pady=(0, 10))
        self.log_text = ScrolledText(log_frame, height=10, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True, padx=8, pady=8)

    def _build_anonymize_tab(self) -> None:
        file_frame = ttk.LabelFrame(self.anonymize_frame, text="输入文件")
        file_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)

        button_row = ttk.Frame(file_frame)
        button_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(button_row, text="添加文件", command=self.add_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="移除选中", command=self.remove_selected_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="清空", command=self.clear_files).pack(side=LEFT)

        self.file_list = ttk.Treeview(file_frame, columns=("path",), show="headings", height=8)
        self.file_list.heading("path", text="文件路径")
        self.file_list.column("path", width=760, anchor="w")
        self.file_list.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        output_frame = ttk.LabelFrame(self.anonymize_frame, text="输出目录")
        output_frame.pack(fill="x", padx=8, pady=8)
        ttk.Entry(output_frame, textvariable=self.output_dir).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Button(output_frame, text="选择", command=self.choose_output_dir).pack(side=RIGHT, padx=8, pady=8)

        custom_frame = ttk.LabelFrame(self.anonymize_frame, text="自定义敏感词（每行一个，可填客户名、项目名、内部系统名）")
        custom_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self.custom_terms_text = ScrolledText(custom_frame, height=6, wrap="word")
        self.custom_terms_text.pack(fill=BOTH, expand=True, padx=8, pady=8)

        action_row = ttk.Frame(self.anonymize_frame)
        action_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(action_row, text="开始脱敏", command=self.start_anonymize).pack(side=RIGHT)

    def _build_restore_tab(self) -> None:
        file_frame = ttk.LabelFrame(self.restore_frame, text="待还原文件")
        file_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)

        button_row = ttk.Frame(file_frame)
        button_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(button_row, text="添加文件", command=self.add_restore_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="移除选中", command=self.remove_selected_restore_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="清空", command=self.clear_restore_files).pack(side=LEFT)

        self.restore_file_list = ttk.Treeview(file_frame, columns=("path",), show="headings", height=8)
        self.restore_file_list.heading("path", text="文件路径")
        self.restore_file_list.column("path", width=760, anchor="w")
        self.restore_file_list.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        mapping_frame = ttk.LabelFrame(self.restore_frame, text="映射表 JSON")
        mapping_frame.pack(fill="x", padx=8, pady=8)
        ttk.Entry(mapping_frame, textvariable=self.mapping_path).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Button(mapping_frame, text="选择", command=self.choose_mapping_file).pack(side=RIGHT, padx=8, pady=8)

        output_frame = ttk.LabelFrame(self.restore_frame, text="输出目录")
        output_frame.pack(fill="x", padx=8, pady=8)
        ttk.Entry(output_frame, textvariable=self.restore_output_dir).pack(side=LEFT, fill="x", expand=True, padx=8, pady=8)
        ttk.Button(output_frame, text="选择", command=self.choose_restore_output_dir).pack(side=RIGHT, padx=8, pady=8)

        action_row = ttk.Frame(self.restore_frame)
        action_row.pack(fill="x", padx=8, pady=8)
        ttk.Button(action_row, text="开始还原", command=self.start_restore).pack(side=RIGHT)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择需要脱敏的文件",
            filetypes=[
                ("Supported files", "*.docx *.xlsx *.pdf *.txt *.md *.csv *.json *.log *.png *.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        for path in paths:
            p = Path(path)
            if p not in self.files:
                self.files.append(p)
                self.file_list.insert("", END, values=(str(p),))

    def add_restore_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择需要还原的文件",
            filetypes=[
                ("Supported files", "*.docx *.xlsx *.txt *.md *.csv *.json *.log"),
                ("All files", "*.*"),
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
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir.get() or str(APP_DIR))
        if path:
            self.output_dir.set(path)

    def choose_restore_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.restore_output_dir.get() or str(APP_DIR))
        if path:
            self.restore_output_dir.set(path)

    def choose_mapping_file(self) -> None:
        path = filedialog.askopenfilename(title="选择映射表", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.mapping_path.set(path)

    def start_anonymize(self) -> None:
        if not self.files:
            messagebox.showwarning("缺少文件", "请先添加需要脱敏的文件。")
            return
        output_dir = Path(self.output_dir.get()).expanduser()
        custom_terms = self._custom_terms()
        threading.Thread(
            target=self._run_anonymize,
            args=(list(self.files), output_dir, custom_terms),
            daemon=True,
        ).start()

    def start_restore(self) -> None:
        if not self.restore_files:
            messagebox.showwarning("缺少文件", "请先添加需要还原的文件。")
            return
        if not self.mapping_path.get():
            messagebox.showwarning("缺少映射表", "请选择脱敏时生成的映射表 JSON。")
            return
        threading.Thread(
            target=self._run_restore,
            args=(list(self.restore_files), Path(self.restore_output_dir.get()).expanduser(), Path(self.mapping_path.get())),
            daemon=True,
        ).start()

    def _run_anonymize(self, files: list[Path], output_dir: Path, custom_terms: list[str]) -> None:
        self._log("INFO", "Starting desensitization.")
        output_dir.mkdir(parents=True, exist_ok=True)
        mapping = MappingStore()
        rows: list[dict[str, object]] = []
        total_counts = Counter()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for file_path in files:
            try:
                output_path, counts, message = anonymize_file(file_path, output_dir, mapping, custom_terms)
                total_counts.update(counts)
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
            except Exception as exc:
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
        mapping_file = output_dir / f"mapping_{timestamp}.json"
        report_file = output_dir / f"report_{timestamp}.csv"
        mapping.save(mapping_file)
        write_report(report_file, rows)
        self._log("INFO", f"Mapping saved: {mapping_file}")
        self._log("INFO", f"Report saved: {report_file}")
        self._log("INFO", f"Done. Total findings: {dict(total_counts)}")

    def _run_restore(self, files: list[Path], output_dir: Path, mapping_path: Path) -> None:
        self._log("INFO", "Starting restoration.")
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            mapping = MappingStore.load(mapping_path)
        except Exception as exc:
            self._log("ERROR", f"Cannot load mapping file: {exc}")
            return
        for file_path in files:
            try:
                output_path, message = restore_file(file_path, output_dir, mapping)
                self._log("OK", f"{file_path.name} -> {output_path.name}; {message}")
            except Exception as exc:
                level = "WARN" if isinstance(exc, DesensitizeError) else "ERROR"
                self._log(level, f"{file_path.name}: {exc}")
        self._log("INFO", "Restoration done.")

    def _custom_terms(self) -> list[str]:
        content = self.custom_terms_text.get("1.0", END)
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _log(self, level: str, message: str) -> None:
        self.queue.put((level, message))

    def _poll_queue(self) -> None:
        try:
            while True:
                level, message = self.queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.log_text.insert(END, f"[{timestamp}] [{level}] {message}\n")
                self.log_text.see(END)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    DesensitizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
