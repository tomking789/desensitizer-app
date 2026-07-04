# 本地资料脱敏工具

这是一个本地桌面脱敏工具，用于在把资料交给 ChatGPT、Codex 或其他 AI 应用前，先在本机识别、确认并替换敏感信息。

当前定位：专业试用版。

## 许可证

本项目接受 AGPL 约束，采用 GNU Affero General Public License v3.0 or later 授权。

分发可执行文件时，应同时提供对应源码，或提供清晰的源码获取方式。当前本地发布包会随附源码归档：

```text
..\本地资料脱敏工具\source-code.zip
```

详细说明见：

- `LICENSE`
- `AGPL-3.0.txt`
- `NOTICE.md`
- `SOURCE_CODE.md`

## 启动方式

普通用户建议直接打开根目录下的发布版：

```text
..\本地资料脱敏工具\本地资料脱敏工具.exe
```

开发或调试时也可以双击：

```text
start_desensitizer.cmd
```

启动脚本会优先打开根目录下的发布版 exe；如果发布版不存在，才会尝试用本机 Python 运行源码。

## 主要功能

- 支持添加多个文件。
- 支持添加文件夹。
- 文件夹默认递归扫描子文件夹，可在界面关闭。
- 文件夹内所有文件都会加入任务列表，不支持的格式会在日志和报告里说明。
- 自动识别候选敏感信息。
- 候选信息可人工确认：启用、禁用、删除、修改原文、修改替换值。
- 支持不自动识别，直接手动新增“原文 -> 替换值”。
- 执行脱敏时只替换用户确认启用的候选项。
- 默认加密映射表，输出 `mapping_*.json.enc`。
- 按映射还原完成后显示成功/失败统计。
- 默认输出目录改为程序主目录下的 `输出文件`。
- 支持中英文界面切换。
- 支持多套颜色主题。
- 随发布包提供 AGPL 许可证、开源声明和对应源码归档。
- 随发布包提供免责声明、示例文件、演示流程、行业敏感词模板和一页产品介绍 PDF。

## 当前支持

- Word：`.docx`
- Excel：`.xlsx`
- PowerPoint：`.pptx`
- 文本型 PDF：`.pdf`，会在原 PDF 版式上做安全覆盖脱敏并输出新的 `.pdf`
- 普通文本：`.txt`、`.md`、`.csv`、`.json`、`.log`、`.xml`、`.html`
- 按映射表还原：支持 `.docx`、`.xlsx`、`.pptx`、文本型 `.pdf` 和普通文本文件

## 当前暂不支持

- 图片 OCR 脱敏（当前会在报告中标记为跳过，不计为失败；请先自行转换为文字版文件）
- 扫描版 PDF OCR 脱敏（当前会提示先转换为文字版 PDF、Word 或文本）
- `.doc`、`.xls` 老格式文件自动转换（请先用 Word/Excel/WPS 另存为 `.docx/.xlsx`）

这些需要 OCR 或文档转换能力。当前版本保持轻量，不内置 PaddleOCR 或 LibreOffice。

## 脱敏流程

1. 打开“文件脱敏”页。
2. 点击“添加文件”或“添加文件夹”。
3. 如选择文件夹，按需保留或关闭“递归子文件夹”。
4. 如果要自动识别，勾选“自动识别可脱敏信息”，点击“扫描候选信息”。
5. 在候选表里检查识别结果，可启用、禁用、删除、修改替换值。
6. 如果有遗漏，在“编辑或手动新增”区域输入原文和替换值，点击“新增手动条目”。
7. 选择输出目录。
8. 点击“开始脱敏”。

每次脱敏会输出：

- 脱敏后的文件
- `mapping_YYYYMMDD_HHMMSS.json.enc`，默认加密
- `report_YYYYMMDD_HHMMSS.csv`

`mapping_*.json` 或 `mapping_*.json.enc` 含还原资料所需信息，只能保存在本地，不要上传给 AI 或公开仓库。加密映射表的密码由用户在脱敏时自行设置；还原时输入同一个密码。程序不会生成、保存或代管该密码，遗失后无法还原。

## 试用资料

发布包和源码目录包含：

- `DISCLAIMER.md`：软件免责声明
- `templates/行业敏感词模板`：行业敏感词模板
- `demo/示例文件`：演示用 Word、Excel、PDF、文本和 CSV 文件
- `demo/演示流程.md`：完整演示步骤
- `marketing/本地资料脱敏工具-产品介绍.pdf`：一页产品介绍 PDF

## 手动模式

如果不希望自动识别：

1. 取消勾选“自动识别可脱敏信息”。
2. 在候选表下方手动新增条目。
3. 确认候选项启用。
4. 点击“开始脱敏”。

## 还原流程

1. 打开“按映射还原”页。
2. 添加需要还原的脱敏文件。
3. 选择对应的 `mapping_*.json`。
4. 选择输出目录。
5. 点击“开始还原”。

如果选择的是 `mapping_*.json.enc` 加密映射表，系统会要求输入脱敏时设置的同一个映射表密码。

## 内置识别规则

- 中国大陆手机号
- 中国大陆身份证号，带校验位验证
- 邮箱
- 银行卡号，带 Luhn 校验
- 统一社会信用代码，带校验位验证
- IPv4 地址
- URL
- 常见 API Key、token、password、private key
- 带标签的人名，例如 `姓名: 张三`、`客户姓名: 张三`
- 常见中文机构名后缀
- 合同号、订单号、项目编号、工单号等带标签编号
- 用户在业务敏感词输入框中补充的客户名、项目名、系统名等

自动识别不可能 100% 覆盖所有敏感信息。高风险资料建议先扫描，再人工检查候选表，并用手动条目补充遗漏。

---

# Local Document Desensitizer

This is a local desktop desensitization tool for identifying, reviewing, and replacing sensitive information before sharing files with ChatGPT, Codex, or other AI applications.

Current positioning: professional trial edition.

## License

This project is distributed under the GNU Affero General Public License v3.0 or later.

When distributing executable builds, provide the corresponding source code or a clear way to obtain it. The current local release package includes a source code archive:

```text
..\本地资料脱敏工具\source-code.zip
```

See the following files for details:

- `LICENSE`
- `AGPL-3.0.txt`
- `NOTICE.md`
- `SOURCE_CODE.md`

## How To Start

For regular users, open the packaged executable from the root directory:

```text
..\本地资料脱敏工具\本地资料脱敏工具.exe
```

For development or debugging, you can also double-click:

```text
start_desensitizer.cmd
```

The startup script tries to open the packaged executable first. If the executable does not exist, it falls back to running the source code with the local Python installation.

## Key Features

- Add multiple files.
- Add folders.
- Recursively scan subfolders by default, with an option to turn recursion off.
- Add all files in a folder to the task list; unsupported formats are reported in the log and report.
- Automatically detect candidate sensitive information.
- Review candidate entries manually: enable, disable, delete, edit source text, and edit replacement values.
- Skip automatic detection and add manual "source text -> replacement value" entries directly.
- Replace only the candidate entries that the user has confirmed and enabled.
- Encrypt mapping files by default and output `mapping_*.json.enc`.
- Show success and failure statistics after restoration.
- Use `输出文件` under the program root as the default output directory.
- Switch between Chinese and English UI.
- Choose from multiple color themes.
- Include the AGPL license, open source notice, and corresponding source archive in the release package.
- Include a disclaimer, sample files, demo workflow, industry sensitive-word templates, and a one-page product introduction PDF in the release package.

## Currently Supported

- Word: `.docx`
- Excel: `.xlsx`
- PowerPoint: `.pptx`
- Text-based PDF: `.pdf`; the tool applies safe overlay redaction on the original PDF layout and outputs a new `.pdf`
- Plain text: `.txt`, `.md`, `.csv`, `.json`, `.log`, `.xml`, `.html`
- Mapping-based restoration: `.docx`, `.xlsx`, `.pptx`, text-based `.pdf`, and plain-text files

## Not Currently Supported

- Image OCR desensitization. Image files are currently marked as skipped in the report and are not counted as failures. Convert them to text-based files first.
- Scanned PDF OCR desensitization. Convert scanned PDFs to text-based PDF, Word, or text files first.
- Automatic conversion of legacy `.doc` and `.xls` files. Save them as `.docx` or `.xlsx` with Word, Excel, or WPS first.

These capabilities require OCR or document conversion. The current version stays lightweight and does not bundle PaddleOCR or LibreOffice.

## Desensitization Workflow

1. Open the "File Desensitization" page.
2. Click "Add Files" or "Add Folder".
3. If you select a folder, keep or disable "Recursive Subfolders" as needed.
4. To use automatic detection, enable "Automatically identify desensitizable information" and click "Scan Candidate Information".
5. Review the detected candidates. You can enable, disable, delete, or edit replacement values.
6. If anything is missing, enter the source text and replacement value in the edit/manual-add area, then click "Add Manual Entry".
7. Select the output directory.
8. Click "Start Desensitization".

Each run outputs:

- Desensitized files
- `mapping_YYYYMMDD_HHMMSS.json.enc`, encrypted by default
- `report_YYYYMMDD_HHMMSS.csv`

`mapping_*.json` and `mapping_*.json.enc` contain the information needed for restoration. Keep them local and do not upload them to AI tools or public repositories. The password for encrypted mapping files is set by the user during desensitization. Use the same password during restoration. The program does not generate, save, or manage this password, and lost passwords cannot be recovered.

## Trial Materials

The release package and source directory include:

- `DISCLAIMER.md`: software disclaimer
- `templates/行业敏感词模板`: industry sensitive-word templates
- `demo/示例文件`: sample Word, Excel, PDF, text, and CSV files
- `demo/演示流程.md`: complete demo steps
- `marketing/本地资料脱敏工具-产品介绍.pdf`: one-page product introduction PDF

## Manual Mode

If you do not want automatic detection:

1. Disable "Automatically identify desensitizable information".
2. Add entries manually below the candidate table.
3. Confirm that the entries are enabled.
4. Click "Start Desensitization".

## Restoration Workflow

1. Open the "Restore From Mapping" page.
2. Add the desensitized files that need to be restored.
3. Select the corresponding `mapping_*.json`.
4. Select the output directory.
5. Click "Start Restoration".

If you select an encrypted `mapping_*.json.enc` mapping file, the system asks for the same mapping password that was set during desensitization.

## Built-In Detection Rules

- Mainland China mobile phone numbers
- Mainland China ID numbers with checksum validation
- Email addresses
- Bank card numbers with Luhn validation
- Unified social credit codes with checksum validation
- IPv4 addresses
- URLs
- Common API keys, tokens, passwords, and private keys
- Labeled names, such as `姓名: 张三` or `客户姓名: 张三`
- Common Chinese organization-name suffixes
- Labeled contract numbers, order numbers, project IDs, work order IDs, and similar identifiers
- Customer names, project names, system names, and similar terms supplied by the user in the business sensitive-word input

Automatic detection cannot cover all sensitive information with 100% accuracy. For high-risk materials, scan first, then manually review the candidate table and add manual entries for anything missed.
