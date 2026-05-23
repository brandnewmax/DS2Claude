# DS2Claude

把任意支持 Anthropic Messages API 的模型接入 Claude Desktop 的本地透传代理。

- 🔄 **多组热切换** — 一键切换模型平台，无需重启
- 🖥️ **Web 管理界面** — 浏览器里管理所有映射和组
- ⚡ **零延迟** — 本地代理，只替换模型名，不透传额外开销
- 🔑 **自动认证注入** — 代理自动替换 API Key，Claude Desktop 侧随便填

## 原理

```
Claude Desktop Gateway        DS2Claude (:8765)          上游 API
    │                            │                          │
    ├─ POST /v1/messages ──────→│ 替换 model 字段          │
    │  model: claude-opus-4-7   │ claude-opus-4-7          ├─ DeepSeek
    │  x-api-key: (dummy)       │ → deepseek-v4-pro[1m]    │  x-api-key: sk-real
    │                            │                          │
    │←──────── SSE 透传 ────────│←────── SSE 透传 ─────────┤
```

Claude Desktop 的开发者模式 Gateway 只接受 `claude-*` 开头的模型名。DS2Claude 在中间做模型名到真实模型名的映射，然后原样转发到目标 API。协议完整透传，不做任何转换。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 编辑 groups.yaml，填入你的 API Key
#    （文件里有注释，照格式改就行）

# 3. 启动
python3 proxy.py

# 4. 浏览器打开 http://127.0.0.1:8765 管理组和映射

# 5. Claude Desktop → 设置 → 开发者模式 → Gateway
#    Base URL: http://127.0.0.1:8765
#    API Key:  随便填（代理会自动替换）
#    Models:   claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5
```

## 支持的模型平台

| 平台 | 模型 | Anthropic 兼容端点 |
|------|------|-------------------|
| DeepSeek | deepseek-v4-pro[1m], v4-flash | `api.deepseek.com/anthropic` |
| 智谱 GLM | glm-5.1 | `open.bigmodel.cn/api/anthropic` |
| Moonshot Kimi | kimi-for-coding | `api.kimi.com/coding` |
| MiniMax | MiniMax-M2.7 | `api.minimaxi.com/anthropic` |
| 自定义中转 | 任意 | 自定义 |

> 只要服务端实现了 Anthropic Messages API 兼容（`/v1/messages`），都可以接入。添加新平台只需在 `groups.yaml` 里加一段配置。

## 组管理

- 每个「组」是一套独立的模型映射配置
- 可以创建多个组对应不同的模型平台
- **切换组实时生效**，无需重启代理或 Claude Desktop
- 通过 Web UI 或直接编辑 `groups.yaml` 管理

## 安全

- API Key 只存在于本地 `groups.yaml`，不上传任何地方
- 代理只监听 `127.0.0.1:8765`，不接受外部连接
- 转发的 HTTP 头使用白名单机制，避免信息泄露

## 项目结构

```
DS2Claude/
├── proxy.py          # 主程序 (FastAPI)
├── index.html        # Web 管理界面
├── groups.yaml       # 组配置文件
├── requirements.txt  # Python 依赖
└── LICENSE
```

## 技术栈

- Python 3.9+
- FastAPI + uvicorn
- httpx (异步 HTTP 客户端)
- PyYAML
