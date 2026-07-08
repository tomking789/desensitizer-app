from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


CONTACT_EMAIL = "yilinwanxiang@163.com"
OUTPUT_NAME = "合作企业定制化服务说明.pdf"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output_path = root / "marketing" / OUTPUT_NAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _register_fonts()
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=16 * mm,
        title="本地资料脱敏工具企业定制版服务说明",
        author="艺林万象（北京）科技有限公司",
    )
    doc.build(_build_story(styles), onFirstPage=_draw_page, onLaterPages=_draw_page)
    print(output_path)


def _register_fonts() -> None:
    try:
        pdfmetrics.getFont("STSong-Light")
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    common = {"fontName": "STSong-Light", "wordWrap": "CJK", "alignment": TA_LEFT}
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base["Title"],
            **common,
            fontSize=24,
            leading=31,
            textColor=colors.HexColor("#16324f"),
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN",
            **common,
            fontSize=10.8,
            leading=16,
            textColor=colors.HexColor("#486174"),
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "H1CN",
            **common,
            fontSize=14.2,
            leading=19,
            textColor=colors.HexColor("#135f75"),
            spaceBefore=7,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            **common,
            fontSize=11.5,
            leading=15.5,
            textColor=colors.HexColor("#1f3b53"),
            spaceBefore=3,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "BodyCN",
            **common,
            fontSize=9.1,
            leading=13.2,
            textColor=colors.HexColor("#263238"),
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "SmallCN",
            **common,
            fontSize=7.9,
            leading=10.8,
            textColor=colors.HexColor("#37474f"),
        ),
        "tiny": ParagraphStyle(
            "TinyCN",
            **common,
            fontSize=7.2,
            leading=9.7,
            textColor=colors.HexColor("#455a64"),
        ),
        "th": ParagraphStyle(
            "HeaderCN",
            **common,
            fontSize=8.1,
            leading=10.5,
            textColor=colors.white,
        ),
        "callout": ParagraphStyle(
            "CalloutCN",
            **common,
            fontSize=9.3,
            leading=13.5,
            textColor=colors.HexColor("#16324f"),
            leftIndent=4,
            rightIndent=4,
        ),
    }


def _build_story(styles: dict[str, ParagraphStyle]) -> list:
    story: list = []
    story.extend(_cover(styles))
    story.append(PageBreak())
    story.extend(_why_upgrade(styles))
    story.extend(_customization(styles))
    story.append(PageBreak())
    story.extend(_audit_scene(styles))
    story.append(PageBreak())
    story.extend(_differences(styles))
    story.extend(_delivery(styles))
    return story


def _cover(styles: dict[str, ParagraphStyle]) -> list:
    return [
        Spacer(1, 15 * mm),
        Paragraph("本地资料脱敏工具", styles["title"]),
        Paragraph("企业定制版服务说明", styles["title"]),
        Paragraph(
            "面向企业资料外发、AI 办公、项目协作、内部审计和合规复核场景，提供专属 Logo、企业定制化敏感词、行业规则、同名主体识别和可还原脱敏工作流。",
            styles["subtitle"],
        ),
        _summary_cards(styles),
        Spacer(1, 8 * mm),
        _callout(
            "通用版解决“能不能脱敏”；企业定制版解决“员工能不能按本企业规则稳定、批量、可复核地脱敏”。",
            styles,
        ),
        Spacer(1, 4 * mm),
        Paragraph(_email_line("企业合作与定制咨询邮箱："), styles["h2"]),
    ]


def _summary_cards(styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            _card("专属品牌入口", "软件标题、主界面横幅、关于页展示企业简称、专用版名称和客户 Logo。", styles),
            _card("企业敏感词库", "内置企业全称、简称、品牌、系统、项目代号、高管、客户和供应商名单。", styles),
        ],
        [
            _card("内部审计场景", "凭证、合同、客户清单、访谈纪要、审计底稿外发或给 AI 前统一脱敏。", styles),
            _card("可还原复核", "本地处理文件，输出加密映射表，持有映射表和密码的人可还原核对。", styles),
        ],
    ]
    table = Table(data, colWidths=[82 * mm, 82 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef6f8")),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#bdd7df")),
                ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#bdd7df")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _card(title: str, body: str, styles: dict[str, ParagraphStyle]) -> list:
    return [Paragraph(f"<b>{title}</b>", styles["h2"]), Paragraph(body, styles["small"])]


def _callout(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(text, styles["callout"])]], colWidths=[164 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f8fb")),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#bdd7df")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _why_upgrade(styles: dict[str, ParagraphStyle]) -> list:
    rows = [
        ["常见问题", "通用版局限", "企业定制版价值"],
        ["员工不知道哪些词必须脱敏", "每次手动输入，容易漏掉简称、项目代号、客户名、高管姓名", "企业专属词库内置到安装包，员工打开即可使用"],
        ["不同部门规则不一致", "每个人临时判断，输出文件风格不统一", "将企业规则、行业字段和替换格式统一配置"],
        ["外发后需要内部复核", "手动记录映射关系成本高，也容易丢失", "输出加密映射表，持有映射表和密码的人可还原核对"],
        ["AI 分析、审计抽样、外部协作风险高", "文件直接外发或上传，敏感信息容易暴露", "本地先脱敏，再给 AI 或外部人员使用"],
    ]
    return [
        Paragraph("一、为什么需要企业定制版", styles["h1"]),
        Paragraph("企业定制版不是简单换 Logo，而是把企业自己的标识、敏感词库、行业字段、脱敏策略和交付文档固化到工具里。", styles["body"]),
        _table(rows, [42 * mm, 54 * mm, 68 * mm], styles, header_bg="#135f75"),
    ]


def _customization(styles: dict[str, ParagraphStyle]) -> list:
    sections = [
        ("专属品牌与软件入口", "企业专用版名称、主界面横幅、关于页客户信息、Logo 和企业简称。"),
        ("企业定制化敏感词库", "企业全称/简称/英文名、品牌、系统、项目代号、高管、客户、供应商、合作伙伴。"),
        ("行业规则包", "财税审计、法务、HR、金融、医疗、制造等行业字段识别和模板。"),
        ("脱敏策略", "姓名、公司、手机号、证件号、邮箱、账号、项目代号的替换规则；可还原或不可还原策略。"),
        ("Excel 同名主体识别", "按员工编号、客户编号、手机号、邮箱、身份证号等主体键区分同名人员或同名客户。"),
        ("部署与交付", "企业专用安装包、企业配置包、词库模板、管理员维护说明、可选内网/离线部署。"),
    ]
    rows = [["定制方向", "具体内容"], *sections]
    return [
        Paragraph("二、企业定制版可以定制什么", styles["h1"]),
        _table(rows, [42 * mm, 122 * mm], styles, header_bg="#1f6f52"),
        Spacer(1, 3 * mm),
        _callout("企业词库会在软件启动时自动写入“业务敏感词”区域，员工不需要每次选择词库文件。", styles),
    ]


def _audit_scene(styles: dict[str, ParagraphStyle]) -> list:
    scenario_rows = [
        ["审计工作", "脱敏前风险", "企业版处理方式"],
        ["抽样凭证交给外部顾问复核", "凭证中包含客户名、供应商名、银行账号、经办人、手机号", "按企业词库和财税审计规则脱敏后外发"],
        ["客户/供应商清单做异常分析", "名称、联系人、电话、邮箱、账号直接暴露", "将主体替换为客户001、供应商001、人员001"],
        ["合同和访谈纪要交给 AI 总结", "合同主体、项目代号、联系人和内部系统名泄露", "本地脱敏后再给 AI 做摘要、分类和风险点提取"],
        ["审计底稿跨部门流转", "不同人员能看到超出权限的原始信息", "输出脱敏版用于流转，原文映射表由企业指定人员保存"],
    ]
    process_items = [
        "管理员维护客户、供应商、项目代号、高管、银行账户等企业词库。",
        "员工打开企业专用版，企业词库自动出现在“业务敏感词”区域。",
        "添加凭证、合同、客户清单、访谈纪要或审计底稿。",
        "扫描候选信息并人工确认，必要时调整替换值。",
        "输出脱敏文件、处理报告和加密映射表。",
        "如需回查，使用脱敏时生成的映射表和密码在“按映射还原”页还原。",
    ]
    benefit_items = [
        "外部顾问或 AI 能看到业务结构，但看不到真实客户、供应商、人员、账号。",
        "同一客户或供应商在多份文件中保持一致占位符，便于统计和关联分析。",
        "原始资料默认留在企业环境内，映射表和密码由企业自行保存。",
    ]
    return [
        Paragraph("三、内部审计场景怎么用", styles["h1"]),
        Paragraph("内部审计场景的核心不是把所有信息删掉，而是在不影响审计分析的前提下，把不该外泄的主体信息替换成稳定占位符。", styles["body"]),
        _table(scenario_rows, [40 * mm, 62 * mm, 62 * mm], styles, header_bg="#5a4b81"),
        Spacer(1, 4 * mm),
        Paragraph("推荐流程", styles["h2"]),
        _numbered_list(process_items, styles),
        Paragraph("实际好处", styles["h2"]),
        _bullet_list(benefit_items, styles),
    ]


def _differences(styles: dict[str, ParagraphStyle]) -> list:
    rows = [
        ["对比项", "通用版", "企业定制版"],
        ["界面标识", "通用软件名称和默认版本信息", "企业专用名称、Logo、横幅和关于页客户信息"],
        ["企业词库", "用户自行输入业务敏感词", "内置企业全称、品牌、项目代号、高管、客户和供应商等"],
        ["行业字段", "通用手机号、身份证、邮箱、银行卡等", "可叠加财税审计、法务、HR、金融、医疗、制造等行业规则"],
        ["Excel 同名主体", "普通文本替换，可能把同名人员合并", "按编号、手机号、邮箱、身份证号等主体键区分"],
        ["还原复核", "支持映射表还原", "围绕映射表保管、密码保存、归档要求设计复核流程"],
        ["交付内容", "通用安装包", "企业安装包、配置包、词库模板、Logo、管理员说明和使用流程"],
    ]
    return [
        Paragraph("四、企业版和通用版的差异", styles["h1"]),
        _table(rows, [32 * mm, 62 * mm, 70 * mm], styles, header_bg="#135f75"),
    ]


def _delivery(styles: dict[str, ParagraphStyle]) -> list:
    package_rows = [
        ["交付包", "适合客户", "包含内容"],
        ["标准企业定制包", "中小企业、单部门试点、AI 办公资料外发", "企业专用界面标识、默认词库、管理员导入、Excel 同名主体识别、加密映射表和基础报告"],
        ["行业增强包", "财税审计、法务、HR、金融、医疗、制造等高敏场景", "标准企业能力、行业字段识别规则、行业词库模板、脱敏策略模板、规则调优服务"],
        ["私有化部署包", "对数据出域、内网隔离、审计留痕要求较高的客户", "内网/离线安装、专属部署文档、可选权限控制和日志审计、年度维护"],
    ]
    input_items = [
        "企业全称、简称、英文名和企业 Logo。",
        "产品名、品牌名、系统名、内部平台名。",
        "高管姓名、部门名称、项目代号、客户、供应商和合作伙伴名称。",
        "行业字段示例，例如客户号、员工号、合同号、发票号、凭证号、项目编号。",
        "期望的脱敏显示方式，以及是否需要内网部署、离线部署或可还原流程。",
    ]
    return [
        Paragraph("五、推荐交付包", styles["h1"]),
        _table(package_rows, [34 * mm, 48 * mm, 82 * mm], styles, header_bg="#1f6f52"),
        Paragraph("六、企业需要提供的资料", styles["h1"]),
        _bullet_list(input_items, styles),
        _callout(
            _email_line("如需企业定制、部署支持、行业规则包或内部审计场景方案，请联系："),
            styles,
        ),
    ]


def _email_line(prefix: str) -> str:
    return f'{prefix}<font name="Helvetica">{CONTACT_EMAIL}</font>'


def _table(rows: list[list[str]], col_widths: list[float], styles: dict[str, ParagraphStyle], header_bg: str) -> Table:
    data = []
    for row_index, row in enumerate(rows):
        style = styles["th"] if row_index == 0 else styles["tiny"]
        data.append([Paragraph(cell, style) for cell in row])
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(_table_style(header_bg))
    return table


def _bullet_list(items: list[str], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, styles["body"]), leftIndent=6) for item in items],
        bulletType="bullet",
        leftIndent=13,
        bulletFontName="STSong-Light",
        bulletFontSize=7,
    )


def _numbered_list(items: list[str], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, styles["body"]), leftIndent=7) for item in items],
        bulletType="1",
        leftIndent=15,
        bulletFontName="STSong-Light",
        bulletFontSize=8,
    )


def _table_style(header_bg: str) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbfdfe")),
            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d2d8")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2),
        ]
    )


def _draw_page(canvas, doc) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#135f75"))
    canvas.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#486174"))
    canvas.setFont("STSong-Light", 7.7)
    canvas.drawString(16 * mm, 8 * mm, "本地资料脱敏工具企业定制版服务说明")
    canvas.drawRightString(width - 16 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()


if __name__ == "__main__":
    main()
