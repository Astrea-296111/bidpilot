import json
import os

import requests
import streamlit as st

st.set_page_config(page_title="BidPilot · 投标决策工作台", page_icon="◈", layout="wide")
st.title("BidPilot")
st.caption("Enterprise RFP Intelligence & Bid Decision Agent · AuroraSoft 模拟企业")
api = os.getenv("BIDPILOT_API_URL", "http://127.0.0.1:8000")


def call(method, path, **kwargs):
    response = requests.request(method, api + path, timeout=180, **kwargs)
    if not response.ok:
        raise RuntimeError(f"API {response.status_code}: {response.text[:400]}")
    return response.json()


try:
    health = call("GET", "/api/health")
except Exception as exc:
    st.error(f"后端未连接：{exc}")
    st.info("请先运行 scripts/start_backend.ps1，再刷新页面。")
    st.stop()

with st.sidebar:
    st.subheader("工作空间")
    st.write(f"模式：{health['mode'].upper()}")
    st.write(f"知识文档：{health['documents']}")
    st.caption(health["model"])
    st.warning("企业、证书与招标文件均为模拟数据。Lite 结果用于学习流程。")
    tender_input = st.text_input("恢复已有 Tender ID", value=st.session_state.get("tender_id", ""))
    if st.button("加载任务") and tender_input:
        st.session_state.tender_id = tender_input
        st.rerun()

tabs = st.tabs(["招标分析", "企业知识库", "证据问答"])
with tabs[0]:
    upload = st.file_uploader("上传招标文件", type=["pdf", "docx", "md", "txt"])
    if st.button("上传并开始分析", type="primary", disabled=not upload):
        try:
            result = call(
                "POST", "/api/tenders/upload", files={"file": (upload.name, upload.getvalue())}
            )
            tid = result["id"]
            st.session_state.tender_id = tid
            call("POST", f"/api/tenders/{tid}/analyze")
            with st.status("正在分析 RFP…", expanded=True) as status:
                with requests.get(
                    api + f"/api/tenders/{tid}/analyze/stream", stream=True, timeout=180
                ) as response:
                    response.raise_for_status()
                    event = ""
                    response.encoding = "utf-8"
                    for line in response.iter_lines(decode_unicode=True):
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data = json.loads(line[5:])
                            if event == "node":
                                st.write("阶段：", data["node"])
                            elif event == "progress":
                                st.progress(
                                    data["current"] / data["total"],
                                    text=f"匹配 {data['current']} / {data['total']}",
                                )
                            elif event == "error":
                                raise RuntimeError(data["message"])
                status.update(label="分析结束，请查看结果并进行人工确认", state="complete")
        except Exception as exc:
            st.error(str(exc))
    tid = st.session_state.get("tender_id")
    if tid:
        st.caption(f"Tender ID: {tid}")
        try:
            report = call("GET", f"/api/tenders/{tid}/report")
            c1, c2, c3 = st.columns(3)
            c1.metric("Bid Score", f"{report['decision']['score']:.1f} / 100")
            c2.metric("建议", report["decision"]["recommendation"])
            c3.metric("需求数量", len(report["requirements"]))
            if report["warnings"]:
                st.warning("\n".join(report["warnings"]))
            st.subheader("需求匹配矩阵")
            matches = {m["requirement_id"]: m for m in report["matches"]}
            st.dataframe(
                [
                    {
                        "编号": r["requirement_id"],
                        "需求": r["text"],
                        "类型": r["category"],
                        "强制": r["mandatory"],
                        "匹配": matches[r["requirement_id"]]["status"],
                        "置信度": matches[r["requirement_id"]]["confidence"],
                        "引用": ", ".join(matches[r["requirement_id"]]["evidence_ids"]),
                    }
                    for r in report["requirements"]
                ],
                hide_index=True,
                width="stretch",
            )
            st.subheader("主要缺口与引用")
            for r in report["requirements"]:
                m = matches[r["requirement_id"]]
                with st.expander(f"{m['status']} · {r['requirement_id']} · {r['text']}"):
                    st.write(m["explanation"])
                    if m["missing_items"]:
                        st.write("待补充：", "、".join(m["missing_items"]))
                    st.caption(f"原文位置：{r['source_section']} / 页码 {r['source_page'] or '不适用'}")
                    for eid in m["evidence_ids"]:
                        ev = report["evidence"][eid]
                        st.caption(f"[{eid}] {ev['source']} · {ev['title']}")
                        st.text(ev["chunk_text"])
            st.subheader("应答大纲")
            for i, section in enumerate(report["response_outline"], 1):
                st.write(f"{i}. {section['title']} — {', '.join(section['requirement_ids'])}")
                st.caption("引用：" + ", ".join(section["evidence_ids"]))
            if report["approval_required"]:
                st.info(
                    f"确认保存机会？{report['project_name']} · {report['decision']['score']} 分 · "
                    f"{report['decision']['recommendation']}"
                )
                yes, no = st.columns(2)
                for column, label, approve in [
                    (yes, "Approve · 保存机会", True),
                    (no, "Reject · 不保存", False),
                ]:
                    if column.button(label):
                        result = call("POST", f"/api/tenders/{tid}/review", json={"approve": approve})
                        if result["status"] == "save_failed":
                            st.error("保存失败。请查看报告 warnings。")
                        st.rerun()
            else:
                st.caption("任务状态：" + report["status"])
            st.download_button(
                "下载完整 JSON 报告",
                json.dumps(report, ensure_ascii=False, indent=2),
                file_name="bidpilot-report.json",
                mime="application/json",
            )
        except Exception as exc:
            st.info(str(exc))

with tabs[1]:
    st.dataframe(call("GET", "/api/knowledge/documents"), hide_index=True, width="stretch")
    knowledge = st.file_uploader("新增企业资料", type=["pdf", "docx", "md", "txt"], key="knowledge")
    category = st.selectbox(
        "资料类型",
        ["products", "technical", "certifications", "cases", "services", "company", "historical_bids"],
    )
    if st.button("添加资料并重建索引", disabled=not knowledge):
        try:
            call(
                "POST",
                "/api/knowledge/upload",
                files={"file": (knowledge.name, knowledge.getvalue())},
                data={"category": category},
            )
            st.success(call("POST", "/api/knowledge/reindex"))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

with tabs[2]:
    st.caption("问答引用企业资料；可沿用当前 Tender 上下文，最近四轮对话会被保留。")
    question = st.text_input("问题", placeholder="AuroraSoft 是否支持 Kubernetes 私有化部署？")
    if st.button("检索并回答", disabled=not question):
        try:
            answer = call(
                "POST",
                "/api/chat",
                json={
                    "message": question,
                    "tender_id": st.session_state.get("tender_id"),
                    "thread_id": st.session_state.get("chat_thread"),
                },
            )
            st.session_state.chat_thread = answer["thread_id"]
            st.write(answer["answer"])
            st.caption("引用：" + ", ".join(answer["evidence_ids"]))
        except Exception as exc:
            st.error(str(exc))
