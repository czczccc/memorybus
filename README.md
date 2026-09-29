# MemoryBus

MemoryBus 是由用户自己掌控的 AI 长期记忆层，让 ChatGPT、Muse 等多个 AI 共享同一份长期记忆。

- 产品需求：[docs/prd.md](docs/prd.md)
- 架构说明：[docs/architecture.md](docs/architecture.md)
- Muse 技能说明：[docs/muse-skill.md](docs/muse-skill.md)

## 两个入口

| 入口 | 地址 | 认证 | 给谁用 |
|---|---|---|---|
| MCP | `https://<域名>/mcp` | OAuth（GitHub 登录，只允许指定账号） | ChatGPT 网页端（Developer Mode 连接器）、Claude、Cursor 等 |
| REST | `https://<域名>/v1/memory/...` | `Authorization: Bearer <MEMORYBUS_API_TOKEN>` | Muse 技能、脚本 |

MCP 工具：`memory_bootstrap` `memory_search` `memory_get` `memory_list` `memory_recent` `memory_upsert` `memory_delete`

REST：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/memory/bootstrap` | 新会话用的 Memory Packet |
| GET | `/v1/memory/search?q=` | 搜索 |
| GET | `/v1/memory?namespace=` | 列出 |
| GET | `/v1/memory/recent` | 最近变化 |
| GET | `/v1/memory/{id}` | 获取一条 |
| POST | `/v1/memory` | 新建（自动去重、按 subject 替换旧记忆） |
| PUT | `/v1/memory/{id}` | 原地修改 |
| DELETE | `/v1/memory/{id}` | 删除 |
| GET | `/v1/memory/events` | 读写日志 |
| GET | `/v1/memory/export?format=json\|md` | 导出 |

## 部署（VPS + Docker）

1. 把域名的 A 记录指向 VPS，并开放 80、443 端口。
2. 在 GitHub 创建 OAuth App：Homepage 填 `https://<域名>`，回调地址填 `https://<域名>/auth/callback`。
3. 在服务器上执行：

   ```bash
   git clone https://github.com/czczccc/memorybus && cd memorybus
   cp .env.example .env
   # 编辑 .env：POSTGRES_PASSWORD（DATABASE_URL 里的密码要一起改）、
   # MEMORYBUS_API_TOKEN、JWT_SIGNING_KEY（都可以用下面的命令生成）、
   # GITHUB_CLIENT_ID、GITHUB_CLIENT_SECRET、EMBEDDING_API_KEY
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   docker compose up -d --build
   curl https://<域名>/healthz
   ```

   Caddy 会自动申请 HTTPS 证书。

4. **ChatGPT**：设置 → 应用与连接器 → 高级设置，打开开发者模式，然后新建连接器。URL 填 `https://<域名>/mcp`，认证方式选 OAuth，按提示跳转到 GitHub 授权即可。具体菜单名称以 ChatGPT 当前界面为准。
5. **Muse**：把 [docs/muse-skill.md](docs/muse-skill.md) 的技能正文复制进去，并填入 token。

如果 `EMBEDDING_API_KEY` 留空，服务也能启动，只是只用关键词搜索。之后补上 key，新写入的记忆就会带向量；之前写入的旧记忆可以用下面的命令补齐：

```bash
docker compose exec app uv run --no-sync memorybus reembed        # 只补没有向量的
docker compose exec app uv run --no-sync memorybus reembed --all  # 换了模型后全部重算
```

## 本地开发

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)，以及带 pgvector 的 PostgreSQL。

```bash
uv sync
docker compose up -d db          # 或使用本机已有的 PostgreSQL + pgvector
export DATABASE_URL=postgresql://memorybus:<密码>@localhost:5432/memorybus

uv run memorybus init
uv run memorybus add preferences "User prefers uv for Python projects" --subject "python packaging"
uv run memorybus search "python"
uv run memorybus list --all
uv run memorybus export          # 写入 export/memory.json 和 export/memory.md
uv run memorybus serve           # http://localhost:8000
```

未配置 `GITHUB_CLIENT_ID` 时，`/mcp` 不需要登录，只适合在本机调试。

测试（需要一个空的测试库）：

```bash
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/memorybus_test uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests
```
