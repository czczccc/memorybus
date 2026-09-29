# MemoryBus — Product Requirements Document

**Version:** 0.1  
**Status:** MVP 已完成（2026-09-29），ChatGPT 与 Muse 均已实测通过  
**Product Type:** Personal AI Infrastructure  
**Repository:** `memorybus`

---

# 1. Product Overview

## 1.1 Product Name

**MemoryBus**

## 1.2 One-line Description

MemoryBus is a user-owned persistent memory layer that allows multiple AI assistants, agents, and LLM applications to share the same long-term user context.

中文：

> MemoryBus 是一个由用户自己拥有的 AI 长期记忆层，让 ChatGPT、Muse、Claude、Codex、Pi 等不同 AI 共享同一份长期记忆。

---

# 2. Background

当前不同 AI 产品都有各自独立的记忆系统：

- ChatGPT Memory
- Muse Memory
- Claude Projects / Context
- Gemini Memory
- Agent 自己的数据库
- Codex / Claude Code 项目上下文

这些记忆彼此隔离。

用户在 ChatGPT 中建立了大量长期上下文之后，切换到 Muse、Claude 或其他 Agent 时，需要重新解释：

- 自己是谁
- 正在做什么
- 技术环境
- 当前项目
- 长期目标
- 偏好
- 已经做出的决定

导致：

```text
ChatGPT knows me
       ↓
Switch AI
       ↓
AI knows nothing
       ↓
Explain everything again
```

另外，各 AI 对同一用户可能产生互相冲突的记忆。

例如：

```text
ChatGPT:
User is building JobAgent Studio.

Muse:
User is building another project.

Claude:
No context.
```

MemoryBus 希望解决这一问题。

---

# 3. Product Vision

长期目标：

```text
              User
                │
                ▼
          ┌───────────┐
          │ MemoryBus │
          └─────┬─────┘
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
 ChatGPT      Muse       Claude
     │          │          │
     ▼          ▼          ▼
   Codex       Pi       Other Agents
```

MemoryBus 成为：

> 用户个人 AI 生态中的 Canonical Memory Store。

AI 可以更换。

模型可以更换。

客户端可以更换。

但用户的长期记忆属于用户自己。

---

# 4. Core Principles

## 4.1 User-owned

记忆归用户所有，而不是归某个 AI 平台所有。

用户可以：

- 查看
- 修改
- 删除
- 导出
- 导入
- 迁移

全部记忆。

## 4.2 AI-independent

MemoryBus 不绑定：

- OpenAI
- Anthropic
- Muse
- Google
- 某个模型
- 某个 Agent Framework

任何 AI 都可以通过标准接口读取 MemoryBus。

## 4.3 Memory ≠ Chat History

MemoryBus 不保存所有聊天记录。

它保存的是从聊天中提取出的：

> Durable Knowledge

例如：

```text
User uses Windows + WSL for development.
```

而不是：

```text
2026-09-30 00:31
User: Windows WSL 怎么配置？
Assistant: ...
```

## 4.4 Canonical Source of Truth

MemoryBus 是长期记忆的权威来源。

各 AI 自己的 Memory：

```text
ChatGPT Memory
Muse Memory
Claude Context
```

视为：

```text
Local Cache
```

MemoryBus：

```text
Canonical Store
```

---

# 5. Target Users

第一阶段主要服务：

### AI Heavy Users

同时使用多个 AI：

- ChatGPT
- Claude
- Muse
- Gemini
- Codex

并希望这些 AI 都了解自己的用户。

### Developers

开发：

- AI Agents
- Coding Agents
- MCP
- Personal AI
- AI Workspace

希望提供持久用户上下文。

### AI-native Individuals

希望构建自己的：

> Personal AI OS

的人群。

---

# 6. Primary Use Cases

## UC-01 — 新 AI 快速认识用户

用户第一次接入一个新的 AI。

AI 调用：

```text
memory.bootstrap()
```

MemoryBus 返回：

```text
User Profile
Current Projects
Preferences
Environment
Goals
Recent Decisions
```

AI 不需要用户重新介绍自己。

## UC-02 — 跨 AI 共享项目上下文

用户在 ChatGPT 中说：

```text
我决定 JobAgent Studio 使用 Next.js + PostgreSQL。
```

MemoryBus 写入：

```text
project: JobAgent Studio

decision:
Frontend = Next.js
Database = PostgreSQL
```

之后在 Muse 中询问：

```text
我之前那个 JobAgent 项目数据库用什么来着？
```

Muse 查询：

```text
memory.search("JobAgent database")
```

返回：

```text
PostgreSQL
```

---

# 7. Memory Lifecycle

完整生命周期：

```text
Conversation
      │
      ▼
Memory Candidate Extraction
      │
      ▼
Importance Classification
      │
      ├──── transient ────► discard
      │
      ▼
Durable Memory
      │
      ▼
Conflict Detection
      │
      ├── new
      ├── merge
      ├── update
      └── supersede
      │
      ▼
Canonical Memory Store
```

---

# 8. Memory Types

MVP 使用以下 Memory Namespace。

## profile

相对稳定的用户背景。

例如：

```text
preferred_name
occupation
education
language
```

## preferences

长期偏好。

例如：

```text
preferred programming language
preferred response style
preferred development workflow
```

## projects

正在进行或过去的项目。

例如：

```text
JobAgent Studio
MemoryBus
Portfolio
```

## decisions

已经做出的重要决定。

例如：

```text
JobAgent uses PostgreSQL.
```

## environment

长期技术环境。

例如：

```text
Windows
WSL Ubuntu
VPS
Node.js
Docker
```

## goals

长期目标。

例如：

```text
Build AI-native products.
```

## current_state

可能随时间变化的状态。

例如：

```text
Current primary project = MemoryBus.
```

## open_loops

尚未解决的事情。

例如：

```text
Need to implement Muse connector.
```

---

# 9. Memory Object

基础数据结构：

```json
{
  "id": "mem_01JXYZ",
  "namespace": "projects",
  "subject": "MemoryBus",
  "content": "User is building a cross-AI personal memory infrastructure.",
  "source": {
    "provider": "chatgpt",
    "conversation_id": null
  },
  "confidence": 0.96,
  "importance": 0.91,
  "status": "active",
  "created_at": "2026-09-30T00:00:00Z",
  "updated_at": "2026-09-30T00:00:00Z",
  "expires_at": null,
  "supersedes": null,
  "metadata": {}
}
```

---

# 10. Core APIs

MVP 需要实现以下核心能力。

## bootstrap

```text
memory.bootstrap()
```

返回适合新会话使用的 Memory Packet。

## search

```text
memory.search(query)
```

根据当前问题检索相关记忆。

参数：

```json
{
  "query": "JobAgent database",
  "limit": 10
}
```

## get

```text
memory.get(id)
```

获取完整记忆。

## upsert

```text
memory.upsert()
```

创建或更新记忆。

## delete

```text
memory.delete(id)
```

删除记忆。

## list

```text
memory.list(namespace)
```

列出某个类型的记忆。

## recent

```text
memory.recent()
```

返回近期发生变化的长期记忆。

---

# 11. MCP Server

MemoryBus MVP 首先提供 MCP 接口。

Server：

```text
memorybus-mcp
```

Tools：

```text
memory_bootstrap
memory_search
memory_get
memory_list
memory_upsert
memory_delete
memory_recent
```

地址：`https://<域名>/mcp`（Streamable HTTP）。

认证：OAuth 2.1，由服务端代理 GitHub 登录，只放行 `ALLOWED_GITHUB_LOGINS` 中的账号。ChatGPT 连接器在首次连接时完成授权。

## 11.1 REST API

给不支持 MCP 的客户端（例如 Muse 技能、脚本）使用，与 MCP 共用同一套 Memory Core 和存储。

认证：`Authorization: Bearer <MEMORYBUS_API_TOKEN>`。可选请求头 `X-MemoryBus-Client: <名称>`，写入事件日志。

```text
GET    /v1/memory/bootstrap
GET    /v1/memory/search?q=
GET    /v1/memory?namespace=
GET    /v1/memory/recent
GET    /v1/memory/{id}
POST   /v1/memory
PUT    /v1/memory/{id}
DELETE /v1/memory/{id}
GET    /v1/memory/events
GET    /v1/memory/export?format=json|md
```

MCP Client 可以包括：

```text
ChatGPT
Claude
Claude Code
Codex
Pi
Hermes
Cursor
Other Agents
```

---

# 12. Session Bootstrap

MemoryBus 不要求每一轮对话都查询数据库。

新会话开始时调用：

```text
memory_bootstrap
```

生成：

```text
Memory Packet
```

示例：

```json
{
  "profile": [],
  "active_projects": [],
  "preferences": [],
  "recent_decisions": [],
  "current_state": [],
  "open_loops": []
}
```

推荐控制在：

```text
500–2000 tokens
```

避免长期记忆无限污染上下文。

---

# 13. Retrieval Strategy

当当前问题需要更多历史上下文时：

```text
Current Message
      │
      ▼
Query Generator
      │
      ▼
Memory Search
      │
      ├── metadata filtering
      │
      ├── semantic search
      │
      └── recency / importance ranking
      │
      ▼
Relevant Memories
```

初始排序：

```text
score =
semantic_similarity
× importance
× freshness
× confidence
```

---

# 14. Memory Writing

不允许所有信息自动进入长期记忆。

写入前必须经过 Memory Candidate 判断。

### 不保存

```text
我今天吃炸鸡。
```

### 保存

```text
以后我的 Python 项目默认使用 uv。
```

### 保存并替换旧记忆

```text
我已经不做 JobAgent Studio 了。
```

---

# 15. Conflict Resolution

MemoryBus 必须支持记忆冲突。

例如旧记忆：

```text
Primary project = JobAgent Studio
```

新记忆：

```text
Primary project = MemoryBus
```

不能简单新增两条。

应该产生：

```text
JobAgent Studio
status = superseded
```

以及：

```text
MemoryBus
status = active
```

保留历史，但默认检索只返回 active。

---

# 16. Security

MemoryBus 默认禁止保存：

- API Key
- Password
- Cookie
- Session Token
- OAuth Token
- Credit Card
- CVV
- Verification Code
- SSH Private Key
- Recovery Phrase

Secret Detector 应在 Memory Write Pipeline 前执行，并且在调用 Embedding API 之前执行，保证疑似密钥不会发送给第三方。

接口认证：

```text
MCP   → OAuth 2.1（GitHub 登录，账号白名单）
REST  → Bearer Token
```

未配置 OAuth 时，服务拒绝在非 localhost 地址上开放 `/mcp`。

```text
Candidate
   ↓
Secret Detection
   ↓
Safe?
 ├── no → reject
 └── yes
       ↓
 Memory Store
```

---

# 17. Storage

MVP 推荐：

```text
PostgreSQL
+
pgvector
```

主要表：

```text
memories
memory_relations
memory_events
sources
```

PostgreSQL 保存结构化数据。

pgvector 用于：

```text
semantic retrieval
```

Embedding：

```text
Provider   = 硅基流动 SiliconFlow（OpenAI 兼容接口）
Model      = Qwen/Qwen3-VL-Embedding-8B
Dimensions = 1024
Timeout    = 10s，超时或失败时回退到关键词检索
```

向量维度在建表时固定，更换模型或维度后需执行 `memorybus reembed --all`。未配置 Embedding 时写入的记忆没有向量，配置后执行 `memorybus reembed` 补齐。

---

# 18. Architecture

```text
                    AI Clients

      ChatGPT   Muse   Claude   Codex   Pi
          │       │       │       │      │
          └───┬───┴───┬───┴───────┴──────┘
              │       │
     MCP + OAuth    REST + Bearer Token
     (ChatGPT 等)    (Muse 技能等)
              │       │
              └───┬───┘
                  │
                 ┌────────▼────────┐
                 │   MemoryBus     │
                 │      API        │
                 └────────┬────────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
        Retrieval     Memory       Conflict
         Engine       Writer       Resolver
              │           │           │
              └───────────┼───────────┘
                          │
                 PostgreSQL
                          │
                       pgvector
```

---

# 19. MVP Scope

Version 0.1 只完成（以下均已实现）：

- PostgreSQL memory store
- pgvector semantic search
- CRUD API
- MCP Server
- bootstrap
- search
- upsert
- delete
- memory namespaces
- basic conflict detection
- secret filtering
- Markdown export
- JSON export
- REST API + Bearer Token（为 Muse 新增）
- OAuth 2.1 via GitHub（为 ChatGPT 新增）

暂时不做：

- 完整 Web UI
- 手机 App
- 自动同步所有聊天
- 多用户 SaaS
- 浏览器扩展
- 完整知识图谱
- 多 Agent collaboration

---

# 20. MVP CLI

提供：

```bash
memorybus init
```

创建数据库。

```bash
memorybus add
```

添加记忆。

```bash
memorybus search "JobAgent"
```

查询记忆。

```bash
memorybus export
```

导出：

```text
memory.json
memory.md
```

```bash
memorybus reembed [--all]
```

给没有向量的记忆补算 Embedding；`--all` 在更换模型后重算全部。

```bash
memorybus list | token | serve
```

列出记忆、生成随机 token、启动服务。

---

# 21. Minimal Dashboard

后续提供 Web UI：

```text
MemoryBus

Overview

Memories
├── Profile
├── Preferences
├── Projects
├── Decisions
├── Environment
├── Goals
└── Open Loops

Connections
├── ChatGPT
├── Muse
├── Claude
├── Codex
└── MCP Clients

Activity
```

用户可以直接修改任何 Memory。

---

# 22. ChatGPT Integration

第一阶段：

```text
ChatGPT
   │
   ▼
MemoryBus MCP
```

核心工作流：

```text
New conversation
        ↓
memory_bootstrap
        ↓
Relevant Memory Packet
        ↓
Conversation
```

需要更多上下文时：

```text
memory_search
```

出现重要长期信息时：

```text
memory_upsert
```

接入方式：ChatGPT 设置 → 应用与连接器 → 开发者模式 → 新建连接器，URL 填 `https://<域名>/mcp`，认证选 OAuth，按提示完成 GitHub 授权。

---

# 23. Muse Integration

目标：

```text
Muse
 │
 ▼
MemoryBus Connector
```

如果 Muse 无法保证每轮调用外部 Memory：

采用：

```text
Session Bootstrap
+
On-demand Retrieval
+
Important Memory Write-back
```

MemoryBus 不依赖 Muse 自身 Memory 的具体实现。

实现方式：Muse 技能通过 REST API（Bearer Token）调用 MemoryBus，技能说明见 `docs/muse-skill.md`：

```text
新会话        → GET  /v1/memory/bootstrap
需要历史上下文 → GET  /v1/memory/search
重要长期信息   → POST /v1/memory
```

---

# 24. Import

支持从其他 AI 导入长期记忆。

格式：

```text
ChatGPT Memory Export
        ↓
Memory Parser
        ↓
Normalize
        ↓
Deduplication
        ↓
MemoryBus
```

同样支持：

```text
Muse Memory
Claude Memory
Markdown
JSON
```

---

# 25. Export

至少支持：

```text
JSON
Markdown
```

未来：

```text
PAM
SQLite
Obsidian
Notion
```

确保用户永远可以离开 MemoryBus。

---

# 26. Observability

每次读取和写入都记录：

```text
Memory Event
```

例如：

```text
2026-09-30

ChatGPT
SEARCH
"JobAgent architecture"

Returned:
mem_123
mem_532
```

以及：

```text
Muse

WRITE

Changed:
Primary project

From:
JobAgent

To:
MemoryBus
```

用户可以知道：

> 哪个 AI 读取了什么、修改了什么。

---

# 27. Success Metrics

MVP 不以 DAU 为核心指标。

核心指标：

### Memory Retrieval Precision

检索出来的 Memory 是否真正相关。

### Memory Conflict Rate

AI 是否获得互相冲突的记忆。

### Re-explanation Reduction

用户需要重新解释自身背景的次数。

理想目标：

```text
减少 ≥ 80%
```

### Memory Portability

用户能否完整导出所有 Memory。

目标：

```text
100%
```

---

# 28. Development Milestones

## Phase 0

状态：✅

Repository bootstrap

```text
README
PRD
architecture
database schema
```

## Phase 1

状态：✅

Memory Core

```text
PostgreSQL
Memory CRUD
Namespaces
```

## Phase 2

状态：✅

Retrieval

```text
Embeddings
pgvector
Ranking
```

## Phase 3

状态：✅

MCP

实现：

```text
memory_bootstrap
memory_search
memory_upsert
memory_delete
```

## Phase 4

状态：🟡 部分完成：Secret 检测、去重合并、按 subject 替换已实现；候选提取与重要性判断暂由调用方 AI 完成

Memory Intelligence

实现：

```text
Memory Candidate Extraction
Importance Classification
Conflict Resolution
Secret Detection
```

## Phase 5

状态：✅

ChatGPT Integration

完成真实 Chat 测试。

## Phase 6

状态：✅

Muse Integration

完成第二 AI Provider 接入。

此时第一次证明：

> 同一份长期记忆可以跨两个 AI 产品使用。

---

# 29. Definition of MVP Done

MemoryBus v0.1 完成需要满足：

1. 用户能够创建长期记忆。
2. MemoryBus 可以语义搜索记忆。
3. ChatGPT 可以通过 MCP 查询 MemoryBus。
4. 第二个 AI Client 可以查询同一 MemoryBus。
5. 两个 AI 能读取同一条用户记忆。
6. 一个 AI 更新记忆后，另一个 AI 可以读取更新结果。
7. 用户可以修改和删除任意 Memory。
8. 用户可以完整导出所有数据。
9. Secret 不会被写入 Memory。
10. MemoryBus 可以本地 Self-host。

满足这十项，即认为：

```text
MemoryBus MVP = Done
```

---

# 30. Long-term Direction

MemoryBus 最终不应该只是：

> Shared Memory Database

而应该逐渐成为：

> Personal Context Infrastructure for AI.

未来模型：

```text
Identity
   │
Preferences
   │
Projects
   │
Relationships
   │
Decisions
   │
Knowledge
   │
History
   │
Goals
   │
MemoryBus
   │
Any AI
```

最终用户不再：

> 为每个 AI 单独培养记忆。

而是：

> AI 接入用户自己的 Context Layer。
