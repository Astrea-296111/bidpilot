# RAG 实现与可解释边界

代码从 `rag/pipeline.py` 读起。输入企业文档，输出有原文/来源/分类/内容 hash 的 Evidence。RAG 用于非结构化资料，MCP 查询结构化业务记录，两者互补。

1. `documents/parser.py` 抽取可选中文字；PDF 留页码，DOCX 顺序读 paragraph/table，Markdown 留 heading。
2. `rag/chunker.py` 使用 LangChain RecursiveCharacterTextSplitter；500 字符块、80 overlap。块太小丢条件，太大稀释检索；这些数值是起点而非调参最优结果。
3. `rag/embeddings.py` 定义 EmbeddingProvider：Lite hash，Full BGE CPU 或 OpenAI-compatible embedding。缓存 key 包含模型、维度、文本，避免混用模型向量。
4. `rag/vector_store.py` 用真正 QdrantClient；余弦距离比较归一化向量方向。Lite 本地路径与 Full URL 切换使用同一接口。
5. `rag/bm25.py` 保留 ISO27001、RTO、99.95% 等精确技术词，中文采用字和双字片段。BM25 是基于词项/逆文档频率/长度归一化的排序，不理解含义。
6. 双路各 10 个候选；`rrf.py` 实现 `Σ 1/(60+rank)`，按名次融合，不把 BM25 分数与 cosine 生硬相加。
7. RRF Top 8 后可选 CrossEncoder 成对比较 query/chunk，取 4。关闭或不可用时直接保留前 4。
8. Metadata filter 用类别缩小搜索范围。重试放宽范围；它也可能损失跨技术/服务条款的召回，不能只讲好处。

Query Rewrite 位于 Matcher：全模式通过受 Pydantic 约束的 QueryPlan 改写，至多两条 query，并保留数值和单位。Lite 只用显式词汇规则，无法代表 LLM 重写能力。

每条 Requirement 有自己的检索 ID 集合。Reviewer 先检查 `cited ⊆ retrieved_for_requirement`，再复核是否支持结论。有效 ID 只能证明来源真实，不能证明其文本蕴含全部条件。状态定义：全部条件明确满足 MATCH；有能力但部分不足 PARTIAL；没有能力或证据 GAP。

## 参数与实际反例

`EMBEDDING_PROVIDER=auto` 在 Full 选小型中文 BGE；需 `pip install -e ".[models]"` 并允许首次下载。`api` 需要正确配置 API Key、模型和输出维度；维度错误会明确降级，不能悄悄塞进旧 collection。

M034（Kubernetes + 3 年技术支持）在独立匹配评测里被分入 technical，检索只看 technical/products，漏掉 services/maintenance，实际输出 PARTIAL，而标注为 MATCH。这是 filter/复合查询交互的坏例，不是捏造证书。修复方向是子查询分别确定类别或只作 metadata boost；本版保留此反例与真实评测记录。

无 semantic embedding/reranker 实测时必须标 NOT_MEASURED。本次 vector 名称实际为 hash 向量，不能说“BGE Recall 100%”。中文分词、评测查询改写、多语言和独立业务数据是后续改进。
