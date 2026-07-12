# 企业定制配置

本目录用于放置合作企业专属配置。

## 普通员工如何使用

普通员工不需要自己选择或导入“内置企业词库”。

正式企业专用版交付时，管理员会把企业配置文件放在本目录。软件启动后会自动读取这些配置，并把企业全称、简称、产品名、项目名、高管姓名等词汇写入主界面的“业务敏感词”文本框。

员工正常操作流程是：

1. 打开企业专用版软件。
2. 添加需要脱敏的文件或文件夹。
3. 检查“业务敏感词”区域中已自动出现的企业词汇。
4. 如本次任务还有临时词汇，可直接追加到文本框，或点击“导入补充词库文件”导入 CSV/TXT。
5. 点击“扫描候选信息”，确认候选项后点击“开始脱敏”。

界面中的“恢复内置词库”按钮只用于用户误删文本框中的内置词后重新补入；不是每次使用前都必须点击。

如果界面显示“当前为通用版：未配置企业专属词库”，说明当前安装包没有放入正式企业配置文件。

## 管理员如何配置

正式交付某个企业版本时：

1. 复制 `profile.example.json` 为 `profile.json`。
2. 将示例企业名称、简称、产品名称、高管姓名等替换为客户确认后的内容。
3. 如需维护更大的词库，复制 `terms.example.csv` 为 `terms.csv`，按行补充企业专属词汇。
4. 如需显示客户 Logo，将客户提供的透明背景 PNG 放为 `logo.png`，或在 `profile.json` 中通过 `logo_path` 指定文件名。

程序启动时会自动读取：

- `enterprise/profile.json`
- `enterprise/terms.csv`
- `enterprise/terms.txt`
- `enterprise/logo.png`

词库文件建议使用带 BOM 的 UTF-8 编码，便于在中文 Windows 的 Excel 中直接打开。

Logo 建议规格：

- PNG 或 GIF，优先 PNG。
- 透明背景，横向比例优先。
- 建议宽度不低于 512px。
- 文件大小建议小于 2MB。

不要把未经客户确认的员工姓名、高管姓名、客户名单或供应商名单写入正式配置包。

## 自动化构建（交付人员使用）

提供客户 Logo 和词库后，一键生成定制安装包：

```bash
python scripts/build_enterprise.py \
    --customer-name "客户全称" \
    --customer-short-name "客户简称" \
    --logo "客户logo.png" \
    --terms "客户词库.csv"
```

脚本会自动：
1. 生成 `profile.json` 和 `terms.csv`
2. 运行 PyInstaller 编译可执行文件
3. 注入企业配置到输出目录
4. 调用 Inno Setup 生成 Windows 安装包（如需）

详细 SOP 见 `marketing/企业定制交付SOP.md`。
