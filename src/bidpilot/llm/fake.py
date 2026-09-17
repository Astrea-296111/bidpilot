import re

from bidpilot.agent.schemas import Evidence
from bidpilot.matching.support import ALIASES, assess


class FakeLLMProvider:
    model_name = "fake-rules-v1 (not a real LLM)"

    async def invoke(self, prompt, payload):
        return "FakeLLM 仅演示证据驱动流程；请查看结构化结果。"

    async def structured(self, task, schema, payload):
        if task == "requirement_analyst":
            result = self.extract(payload)
        elif task == "query_rewrite":
            text = payload["requirement"]["text"]
            terms = [k for k, aliases in ALIASES.items() if any(a in text.lower() for a in aliases)]
            query = " ".join(terms) or text
            # Preserve numeric constraints while removing verbose boilerplate.
            query += " " + " ".join(
                re.findall(r"(?:RTO|RPO|QPS|SLA)\s*[\d.]+|\d+(?:\.\d+)?[%年天]", text, re.I)
            )
            category = payload["requirement"]["category"]
            tool = (
                "get_qualification"
                if category == "qualification"
                else "get_case_study"
                if "案例" in text
                else "get_product_capability"
            )
            keyword = next((k for k in terms if k.startswith("iso") or k == "软件著作权"), query.strip())
            queries = [query.strip()]
            if "技术支持" in text and len(terms) > 1:
                queries.append("技术支持 SLA 维护")
            result = {
                "queries": queries,
                "tool": tool,
                "keyword": keyword,
                "industry": "ecommerce"
                if "电商" in text
                else "manufacturing"
                if "制造" in text
                else "banking",
            }
        elif task == "capability_matcher":
            req = payload["requirement"]
            status, ids, missing = assess(
                req["text"], [Evidence.model_validate(x) for x in payload["evidence"]]
            )
            result = {
                "requirement_id": req["requirement_id"],
                "status": status,
                "confidence": 0.88 if status == "MATCH" else 0.68 if status == "PARTIAL" else 0.55,
                "evidence_ids": ids,
                "explanation": "离线规则根据引用文本核对能力与数值条件；"
                + ("全部已知条件得到支持。" if not missing else "存在未证实条件。"),
                "missing_items": missing,
            }
        elif task == "reviewer":
            issues, retry = [], []
            for item in payload["items"]:
                status, _, _ = assess(
                    item["requirement"]["text"], [Evidence.model_validate(x) for x in item["evidence"]]
                )
                if item["match"]["status"] == "MATCH" and status != "MATCH":
                    issues.append(
                        f"{item['requirement']['requirement_id']}: Evidence does not entail MATCH"
                    )
                    retry.append(item["requirement"]["requirement_id"])
            result = {"passed": not issues, "issues": issues, "retry_requirement_ids": retry}
        elif task == "response_outline":
            titles = {
                "technical": "技术方案",
                "qualification": "企业资质",
                "scoring": "案例与评分响应",
                "delivery": "实施交付与服务",
                "commercial": "商务应答",
                "mandatory": "强制条款响应",
            }
            sections = []
            for cat, title in titles.items():
                reqs = [r for r in payload["requirements"] if r["category"] == cat]
                if reqs:
                    ids = [r["requirement_id"] for r in reqs]
                    sections.append(
                        {
                            "title": title,
                            "requirement_ids": ids,
                            "evidence_ids": sorted(
                                {
                                    e
                                    for m in payload["matches"]
                                    if m["requirement_id"] in ids
                                    for e in m["evidence_ids"]
                                }
                            ),
                        }
                    )
            result = {"sections": sections}
        elif task == "chat":
            ev = payload["evidence"][:2]
            result = {
                "answer": "\n".join(f"[{e['evidence_id']}] {e['chunk_text']}" for e in ev)
                or "没有检索到证据，无法回答。",
                "evidence_ids": [e["evidence_id"] for e in ev],
            }
        else:
            raise ValueError(f"Unknown fake task: {task}")
        return schema.model_validate(result)

    def extract(self, payload):
        requirements, deadline = [], None
        categories = {
            "技术": "technical",
            "资质": "qualification",
            "商务": "commercial",
            "实施": "delivery",
            "服务": "delivery",
            "评分": "scoring",
            "强制": "mandatory",
        }
        for s in payload["sections"]:
            category = next((v for k, v in categories.items() if k in s["title"]), "technical")
            for line in s["text"].splitlines():
                if "截止" in line:
                    match = re.search(r"\d{4}-\d{2}-\d{2}", line)
                    if match:
                        deadline = match.group()
                    continue
                if not re.match(r"^(?:[-•*]|\d+[.、])\s*", line):
                    continue
                text = re.sub(r"^(?:[-•*]|\d+[.、])\s*", "", line).strip()
                weight = re.search(r"[（(](\d+(?:\.\d+)?)分[)）]", text)
                requirements.append(
                    {
                        "requirement_id": f"REQ-{len(requirements) + 1:03}",
                        "text": text,
                        "category": category,
                        "mandatory": any(w in text for w in ["必须", "强制", "不得"]),
                        "weight": float(weight.group(1)) if weight else None,
                        "source_page": s["page"],
                        "source_section": s["title"],
                        "source_quote": text,
                    }
                )
        return {
            "project_name": payload.get("project_name"),
            "deadline": deadline,
            "requirements": requirements,
        }
