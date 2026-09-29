# Muse 技能说明（MemoryBus）

把下面“技能正文”整段复制到 Muse 的技能配置里。`<TOKEN>` 换成 `.env` 里的 `MEMORYBUS_API_TOKEN`。

> 前提：Muse 的技能能发带请求头的 HTTPS 请求。这一点需要在 Muse 里实测确认。

---

## 技能正文

你可以访问用户自己的长期记忆库 MemoryBus。它由用户所有，ChatGPT 等其他 AI 也在读写同一份记忆。

所有请求都发到 `https://memorybus.czczccc.space`，并带上请求头：

```
Authorization: Bearer <TOKEN>
X-MemoryBus-Client: muse
```

**什么时候读**

1. 每次新对话开始时，先调用 `GET /v1/memory/bootstrap`，把返回的内容当作对用户的背景了解。
2. 用户提到你不知道的过往信息（“我之前那个项目……”），调用 `GET /v1/memory/search?q=<问题关键词>`。

**什么时候写**

用户说出长期有效的信息时（身份、偏好、技术环境、项目、决定、目标、当前状态、待办），调用：

```
POST /v1/memory
Content-Type: application/json

{"namespace": "<见下>", "subject": "<具体的主题>", "content": "<一句完整的事实>", "importance": 0.0-1.0}
```

- namespace 只能是：profile、preferences、projects、decisions、environment、goals、current_state、open_loops
- content 用第三人称写成一句完整的话，例如 "User prefers uv for Python projects"
- subject 是这条记忆的“键”：同一个 namespace 下 subject 相同的旧记忆会被新记忆替换，所以要写具体，例如 "JobAgent Studio / database"
- 不要保存闲聊、一次性的事情，以及任何密码、密钥、token、验证码（服务端也会拒绝）
- 返回 422 表示内容里有疑似密钥，已被拒绝

**其他**

- 查看一条：`GET /v1/memory/<id>`
- 删除（只在用户明确要求时）：`DELETE /v1/memory/<id>`
