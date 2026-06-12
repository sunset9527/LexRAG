---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 7640128155851817256-data_volume/files/所有对话/主对话/项目一_法律RAG智能体/README.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 3225281852086232#1781935849009
    ReservedCode2: ""
---
# 法律RAG智能体知识增强系统

基于结构化RAG + 多跳推理 + 法条自校验的垂直领域法律问答系统

## 📋 项目简介

通用RAG在法律场景会产生"幻觉法条"的严重问题。本系统通过**六大深度技术点**确保每个回答都有法条支撑且经过一致性验证，有效降低法律问答中的错误风险。

## 🏗️ 系统架构

```
用户法律咨询
    ↓
┌─────────────────────────────┐
│   法律意图识别               │
│   (问法条？问案例？问适用？)  │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│   结构化检索                 │
│   ├─ 法条检索(按条/款/项)    │
│   ├─ 案例检索(相似判例)      │
│   └─ 知识图谱(法条引用关系)  │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│   多跳法律推理               │
│   (链式引用多个法条)         │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│   答案生成 + 法条引用标注     │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│   【自校验】Agent核对        │
│   回答内容与引用法条一致性    │
│   ├─ 一致 → 输出            │
│   └─ 不一致 → 重新检索+修正 │
└─────────────────────────────┘
```

## 🎯 六大深度点

| 深度点 | 描述 | 技术实现 |
|--------|------|----------|
| **1. 法律文档结构化切分** | 按编/章/节/条/款/项切分，不按字符数 | 自研LawParser + StructuredLawChunker |
| **2. 法律知识图谱** | 法条间的引用关系建模 | NetworkX有向图 + 多跳BFS检索 |
| **3. 多跳法律推理** | 复杂问题链式引用多个法条 | LangChain ReAct + 子问题拆解 |
| **4. 法条引用校验** | 每个回答标注具体法条，Agent自检一致性 | LLM验证 + 原文比对 |
| **5. 法律时效性管理** | 法条有修订历史，匹配适用版本 | VersionManager + 生效日期过滤 |
| **6. 查询意图路由** | 问法条/问案例/问适用走不同检索链路 | LLM分类 + 条件路由 |

## 🆚 与通用RAG对比

| 对比维度 | 通用RAG | 法律RAG智能体 |
|----------|---------|---------------|
| 切分方式 | 按字符数/段落切分 | 按法律层级结构切分 |
| 幻觉风险 | 高（可能捏造法条） | 低（每条结论强制引用法条） |
| 引用准确性 | 无校验 | 自校验+修正机制 |
| 推理能力 | 单跳检索 | 多跳链式推理 |
| 知识关联 | 无 | 法条引用图谱建模 |
| 时效性 | 无 | 版本管理+废止过滤 |

## 🛠️ 技术栈

| 组件 | 技术选型 |
|------|----------|
| **LLM** | DeepSeek API (支持结构化输出) |
| **编排框架** | LangGraph (推理流程编排+条件分支) |
| **检索框架** | LangChain (文档加载+检索链) |
| **向量数据库** | Chroma (法条向量库) |
| **知识图谱** | NetworkX (轻量替代Neo4j) |
| **后端API** | FastAPI |
| **前端界面** | Streamlit |
| **Python版本** | 3.11+ |

## 📁 项目结构

```
项目一_法律RAG智能体/
├── README.md              # 项目文档
├── requirements.txt        # 依赖列表
├── config.py               # 配置文件
├── main.py                 # Streamlit入口
├── api.py                  # FastAPI后端
├── src/
│   ├── __init__.py
│   ├── ingestion/           # 文档解析模块
│   │   ├── law_parser.py   # 法律文档结构化解析
│   │   ├── chunker.py      # 结构化切分器
│   │   └── indexer.py      # 向量索引构建
│   ├── retrieval/           # 检索模块
│   │   ├── intent_router.py # 查询意图识别+路由
│   │   ├── law_retriever.py # 法条检索
│   │   ├── case_retriever.py # 案例检索
│   │   └── graph_retriever.py # 知识图谱检索
│   ├── reasoning/           # 推理模块
│   │   ├── multi_hop.py    # 多跳法律推理
│   │   └── self_verify.py  # 法条引用自校验
│   ├── graph/               # 图谱模块
│   │   ├── law_graph.py    # 法律知识图谱
│   │   └── builder.py      # 图谱构建
│   ├── agent/               # Agent模块
│   │   ├── workflow.py     # LangGraph主工作流
│   │   ├── nodes.py        # 工作流节点
│   │   └── state.py        # 状态定义
│   └── utils/              # 工具模块
│       └── version_manager.py # 法条版本管理
├── data/
│   ├── laws/               # 示例法律文档
│   ├── cases/              # 示例案例
│   └── law_graph.json      # 预构建的法条引用图谱
└── tests/                  # 测试文件
    ├── test_structured_chunking.py
    ├── test_intent_router.py
    ├── test_multi_hop.py
    └── test_self_verify.py
```

## 🚀 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API Key

```bash
# 设置DeepSeek API Key
export DEEPSEEK_API_KEY="your-api-key"

# 或者创建 .env 文件
echo "DEEPSEEK_API_KEY=your-api-key" > .env
```

### 3. 构建索引（首次运行）

```python
from src.ingestion.law_parser import LawParser
from src.ingestion.chunker import StructuredLawChunker
from src.ingestion.indexer import LawIndexer

# 解析法律文档
parser = LawParser()
articles = parser.parse_law_content(open("data/laws/民法典合同编摘录.txt").read(), "民法典")

# 切分
chunker = StructuredLawChunker()
chunks = chunker.chunk_articles(articles)

# 构建索引
indexer = LawIndexer("./data/chroma_db")
indexer.build_index(chunks)
```

### 4. 启动服务

**方式一：仅启动API**
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

**方式二：启动完整Web界面**
```bash
streamlit run main.py --server.port 8501
```

### 5. API调用示例

```python
import requests

# 问答
response = requests.post("http://localhost:8000/query", json={
    "query": "合同成立需要满足哪些条件？"
})
result = response.json()
print(result["answer"])
print(result["citations"])
```

## 📝 API接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 根路径 |
| `/health` | GET | 健康检查 |
| `/query` | POST | 法律问答 |
| `/upload` | POST | 上传法律文档 |
| `/graph` | GET | 获取知识图谱 |
| `/graph/query` | POST | 查询图谱 |
| `/verify/{query_id}` | GET | 验证查询结果 |

## 🧪 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试
pytest tests/test_intent_router.py -v
```

## 📊 示例问题

- "合同成立需要满足哪些条件？"
- "什么是格式条款？哪些格式条款无效？"
- "要约和承诺有什么区别？"
- "定金和订金有什么法律区别？"
- "民法典第143条规定了什么？"

## ⚠️ 注意事项

1. **API Key配置**：必须配置有效的DeepSeek API Key才能正常运行
2. **首次索引**：首次运行时需要构建向量索引，后续可跳过
3. **法律数据**：可替换data/laws/目录下的法律文档
4. **版本管理**：法条修订后需更新版本信息

## 📄 License

MIT License

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
