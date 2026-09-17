"""Conservative, explicitly limited evidence rules for the offline demonstration.

The real model uses structured judgments, then the Reviewer applies citation gates.
These rules never read evaluation labels or company seed answers.
"""

import re

ALIASES = {
    "kubernetes": ["kubernetes", "k8s"],
    "私有化": ["私有化", "本地部署"],
    "高可用": ["高可用", "故障切换"],
    "iso27001": ["iso27001", "iso 27001"],
    "iso9001": ["iso9001", "iso 9001"],
    "iso20000": ["iso20000", "iso 20000"],
    "soc2": ["soc2", "soc 2"],
    "软件著作权": ["软件著作权"],
    "rbac": ["rbac", "角色权限"],
    "审计": ["审计"],
    "数据脱敏": ["数据脱敏"],
    "prometheus": ["prometheus"],
    "opentelemetry": ["opentelemetry"],
    "api限流": ["api限流", "api 限流"],
    "oidc": ["oidc"],
    "saml": ["saml"],
    "银行案例": ["银行案例", "银行项目案例"],
    "电商案例": ["电商案例", "电商项目案例"],
    "制造案例": ["制造案例", "制造项目案例"],
    "etl": ["etl"],
    "sql": ["sql"],
    "多租户": ["多租户"],
    "7x24": ["7x24", "7×24"],
    "培训": ["培训"],
    "固定总价": ["固定总价"],
    "分期付款": ["分期付款"],
}
METRICS = [
    (r"rto\s*(?:不超过|<=|≤)?\s*(\d+(?:\.\d+)?)\s*分钟", "rto", "max"),
    (r"rpo\s*(?:不超过|<=|≤)?\s*(\d+(?:\.\d+)?)\s*分钟", "rpo", "max"),
    (r"(?:qps\s*(?:不少于|>=|≥)?\s*)(\d+)", "qps", "min"),
    (r"(?:可用性|sla)\s*(?:不低于|>=|≥)?\s*(\d+(?:\.\d+)?)%", "sla", "min"),
    (r"(?:技术支持|维护)\s*(?:不少于|>=|≥)?\s*(\d+)\s*年", "support_years", "min"),
    (r"交付\s*(?:不超过|<=|≤)?\s*(\d+)\s*天", "delivery_days", "max"),
]


def assess(text, evidence):
    text = text.casefold()
    facts = []
    for e in evidence:
        for line in e.chunk_text.casefold().splitlines():
            if any(x in line for x in ["不支持", "未取得", "尚未", "不具备", "不承诺"]):
                continue
            facts.append((e.evidence_id, line))
    checks, citations, missing = [], set(), []
    for key, aliases in ALIASES.items():
        if not any(a in text for a in aliases):
            continue
        supported = [(eid, line) for eid, line in facts if any(a in line for a in aliases)]
        checks.append(bool(supported))
        if supported:
            citations.add(supported[0][0])
        else:
            missing.append(key)
    for pattern, name, direction in METRICS:
        required = re.search(pattern, text)
        if not required:
            continue
        threshold = float(required.group(1))
        options = [(eid, float(m.group(1))) for eid, line in facts if (m := re.search(pattern, line))]
        good = [
            (eid, v) for eid, v in options if (v <= threshold if direction == "max" else v >= threshold)
        ]
        checks.append(bool(good))
        if good:
            citations.add(good[0][0])
        else:
            missing.append(f"{name}={threshold}")
            if options:
                citations.add(options[0][0])
    if not checks:
        return "GAP", [], ["规则模型不能判断此条款，需人工或真实模型复核"]
    status = "MATCH" if all(checks) else "PARTIAL" if any(checks) or citations else "GAP"
    return status, sorted(citations), missing
