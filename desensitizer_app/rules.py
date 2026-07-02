from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable


Validator = Callable[[str], bool]


@dataclass(frozen=True)
class Rule:
    name: str
    entity: str
    prefix: str
    pattern: re.Pattern[str]
    group: str | int = 0
    priority: int = 50
    validator: Validator | None = None


@dataclass(frozen=True)
class Finding:
    entity: str
    prefix: str
    value: str
    start: int
    end: int
    rule_name: str
    priority: int


def _normalize_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def validate_cn_id(value: str) -> bool:
    value = value.upper()
    if not re.fullmatch(
        r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dX]",
        value,
    ):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_map = "10X98765432"
    total = sum(int(value[i]) * weights[i] for i in range(17))
    return check_map[total % 11] == value[-1]


def validate_luhn(value: str) -> bool:
    digits = _normalize_digits(value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def validate_uscc(value: str) -> bool:
    value = value.upper()
    if not re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", value):
        return False
    chars = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    weights = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
    total = 0
    for index, char in enumerate(value[:17]):
        try:
            total += chars.index(char) * weights[index]
        except ValueError:
            return False
    check_index = 31 - total % 31
    if check_index == 31:
        check_index = 0
    return chars[check_index] == value[-1]


def _compile(pattern: str, flags: int = re.IGNORECASE | re.MULTILINE) -> re.Pattern[str]:
    return re.compile(pattern, flags)


DEFAULT_RULES: list[Rule] = [
    Rule(
        name="private_key_block",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----",
            re.MULTILINE,
        ),
        priority=100,
    ),
    Rule(
        name="openai_key",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        priority=95,
    ),
    Rule(
        name="github_token",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|github_pat_[A-Za-z0-9_]{20,}"),
        priority=95,
    ),
    Rule(
        name="aws_access_key",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(r"\bAKIA[0-9A-Z]{16}\b"),
        priority=95,
    ),
    Rule(
        name="google_api_key",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        priority=95,
    ),
    Rule(
        name="secret_assignment",
        entity="SECRET",
        prefix="SECRET",
        pattern=_compile(
            r"(?P<label>\b(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key|private[_-]?key)\b\s*[:=]\s*[\"']?)(?P<value>[A-Za-z0-9_./+=:-]{8,})(?=[\"'\s;,\)]|$)"
        ),
        group="value",
        priority=90,
    ),
    Rule(
        name="cn_id_card",
        entity="CN_ID_CARD",
        prefix="ID",
        pattern=_compile(
            r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\w)"
        ),
        priority=85,
        validator=validate_cn_id,
    ),
    Rule(
        name="cn_mobile",
        entity="CN_PHONE",
        prefix="PHONE",
        pattern=_compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)"),
        priority=80,
    ),
    Rule(
        name="email",
        entity="EMAIL",
        prefix="EMAIL",
        pattern=_compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        priority=75,
    ),
    Rule(
        name="cn_uscc",
        entity="CN_SOCIAL_CREDIT_CODE",
        prefix="USCC",
        pattern=_compile(r"(?<![A-Z0-9])[0-9A-HJ-NPQRTUWXY]{18}(?![A-Z0-9])"),
        priority=75,
        validator=validate_uscc,
    ),
    Rule(
        name="bank_card",
        entity="BANK_CARD",
        prefix="CARD",
        pattern=_compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
        priority=70,
        validator=validate_luhn,
    ),
    Rule(
        name="ipv4",
        entity="IP_ADDRESS",
        prefix="IP",
        pattern=_compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
        ),
        priority=65,
    ),
    Rule(
        name="url",
        entity="URL",
        prefix="URL",
        pattern=_compile(r"\bhttps?://[^\s<>()\"']+"),
        priority=60,
    ),
    Rule(
        name="labeled_person_colon",
        entity="PERSON",
        prefix="PERSON",
        pattern=_compile(
            r"(?P<label>(?:客户姓名|姓名|客户|联系人|负责人|法人|收件人|患者|员工|申请人|经办人)\s*[:：]\s*)(?P<value>[\u4e00-\u9fff]{2,4})(?![\u4e00-\u9fff])"
        ),
        group="value",
        priority=55,
    ),
    Rule(
        name="labeled_person_space",
        entity="PERSON",
        prefix="PERSON",
        pattern=_compile(
            r"(?P<label>(?:客户姓名|姓名|客户|联系人|负责人|法人|收件人|患者|员工|申请人|经办人)\s+)(?P<value>[\u4e00-\u9fff]{2,4})(?![\u4e00-\u9fff])"
        ),
        group="value",
        priority=55,
    ),
    Rule(
        name="organization",
        entity="ORGANIZATION",
        prefix="ORG",
        pattern=_compile(
            r"(?<![\u4e00-\u9fffA-Za-z0-9])[\u4e00-\u9fffA-Za-z0-9（）()]{2,40}(?:有限责任公司|股份有限公司|集团有限公司|有限公司|集团|银行|医院|学校)(?![\u4e00-\u9fffA-Za-z0-9])"
        ),
        priority=50,
    ),
    Rule(
        name="labeled_identifier",
        entity="DOCUMENT_ID",
        prefix="DOCID",
        pattern=_compile(
            r"(?P<label>(?:合同号|订单号|项目编号|工单号|客户编号|员工编号|证件号|发票号|纳税人识别号|税号)\s*[:：]?\s*)(?P<value>[A-Za-z0-9][A-Za-z0-9_.\-/]{4,})"
        ),
        group="value",
        priority=50,
    ),
]


def build_custom_rules(terms: Iterable[str]) -> list[Rule]:
    rules: list[Rule] = []
    for index, term in enumerate(terms, start=1):
        term = term.strip()
        if not term:
            continue
        rules.append(
            Rule(
                name=f"custom_term_{index}",
                entity="CUSTOM_TERM",
                prefix="CUSTOM",
                pattern=_compile(re.escape(term), re.MULTILINE),
                priority=90,
            )
        )
    return rules


def find_sensitive_spans(text: str, custom_terms: Iterable[str] = ()) -> list[Finding]:
    findings: list[Finding] = []
    for rule in [*DEFAULT_RULES, *build_custom_rules(custom_terms)]:
        for match in rule.pattern.finditer(text):
            try:
                start, end = match.span(rule.group)
            except IndexError:
                continue
            if start < 0 or end <= start:
                continue
            value = text[start:end]
            if rule.validator and not rule.validator(value):
                continue
            findings.append(
                Finding(
                    entity=rule.entity,
                    prefix=rule.prefix,
                    value=value,
                    start=start,
                    end=end,
                    rule_name=rule.name,
                    priority=rule.priority,
                )
            )
    return _select_non_overlapping(findings)


def _select_non_overlapping(findings: list[Finding]) -> list[Finding]:
    selected: list[Finding] = []
    for finding in sorted(
        findings,
        key=lambda item: (item.start, -item.priority, -(item.end - item.start)),
    ):
        if any(not (finding.end <= existing.start or finding.start >= existing.end) for existing in selected):
            continue
        selected.append(finding)
    return sorted(selected, key=lambda item: item.start)
