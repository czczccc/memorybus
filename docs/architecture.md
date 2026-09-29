# MemoryBus 架构（v0.1）

一套存储，两个入口：

```text
   ChatGPT 网页端                        Muse / 其他简单客户端
          │                                   │
   MCP (Streamable HTTP)               REST (JSON)
   OAuth 2.1 via GitHub 登录            Authorization: Bearer <token>
          │                                   │
          ▼                                   ▼
 ┌──────────────────────────────────────────────────────┐
 │ app.py  (FastAPI)                                     │
 │   /mcp, /authorize, /token, /auth/callback,           │
 │   /.well-known/*          ← mcp_server.py (FastMCP)   │
 │   /v1/memory/*            ← rest.py                   │
 └───────────────────────────┬──────────────────────────┘
                             ▼
 ┌──────────────────────────────────────────────────────┐
 │ service.py  MemoryService（与协议无关）                 │
 │   bootstrap · search · get · list · recent            │
 │   upsert（Secret 检测 → 去重合并 → 按 subject 替换）   │
 │   delete · export · events                            │
 │ secret_filter.py · embeddings.py                      │
 └───────────────────────────┬──────────────────────────┘
                             ▼
             PostgreSQL + pgvector (schema.sql)
     memories · memory_relations · memory_events · sources
```

## 关键规则

- **冲突处理（PRD §15）**：`upsert` 默认 `mode=auto`。同 namespace 下内容相同（或向量相似度 ≥ 0.97）的记忆会被合并；subject 相同（忽略大小写）的 active 记忆会被标为 `superseded`，新记忆的 `supersedes` 指向它，同时在 `memory_relations` 里记一条 `supersedes`。`mode=new` 表示总是新增；传 `supersedes=<id>` 可以显式指定要替换哪条。
- **Secret 过滤（PRD §16）**：写入前先做检测，并且在调用 embedding 接口之前完成，所以疑似密钥的内容不会被发给第三方。被拒绝的写入会记一条 `REJECT` 事件，但不会保存内容。
- **检索排序（PRD §13）**：`相关度 × (0.5+0.5·importance) × freshness × (0.5+0.5·confidence)`。其中 freshness 以 180 天为半衰期，取值在 0.5–1 之间。相关度取向量相似度与关键词命中率中较高的那个；没有配置 embedding key 时只走关键词搜索（中文按双字切分）。
- **Bootstrap（PRD §12）**：各 namespace 轮流取条目，按估算的 token 数截断，默认上限 2000。这样单个 namespace 条目很多时也不会挤掉其他部分。
- **可观测（PRD §26）**：每次读写都会写入 `memory_events`，记录来源（`mcp:<客户端名>` / `rest:<X-MemoryBus-Client>` / `cli`）、动作和涉及的 id，写操作还会记录修改前后的内容。
- **向量维度**：由 `EMBEDDING_DIMENSIONS` 决定，默认 1024，建表时写死。启动时如果发现与现有表不一致，会直接报错，不会悄悄写坏数据。

## 与 PRD 的差异

- PRD §18 的架构图只画了 MCP 一个入口，这里补上了给 Muse 用的 REST 入口。
- PRD 没有写认证方式：MCP 走 GitHub OAuth，只允许 `ALLOWED_GITHUB_LOGINS` 里的账号；REST 走固定的 Bearer token。
- PRD §11 的工具列表里没有 `memory_list`，这里补上了，和 §10 的 `list` API 对应。
- 记忆候选提取和重要性判断（PRD §7、§14）目前交给调用方的大模型来做，靠工具说明引导；服务端只负责 Secret 过滤、去重和冲突处理。
