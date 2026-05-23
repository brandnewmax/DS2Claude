# DS2Claude

本地 Anthropic Messages API 透传代理。让 Claude Desktop 开发者模式接入任意兼容 Anthropic 协议的第三方模型。

## 原理

```
Claude Desktop Gateway          DS2Claude (:8765)              上游 API
    │                              │                              │
    ├─ POST /v1/messages ────────→├─ 替换 model 字段 ──────────→├─ DeepSeek
    │  model: claude-opus-4-7     │  claude-opus-4-7             │  deepseek-v4-pro[1m]
    │  x-api-key: (dummy)         │  → deepseek-v4-pro[1m]       │  x-api-key: sk-real-key
    │  anthropic-version: ...     │                              │
    │                              │←─ 透传 SSE 流 ──────────────┤
    │←─ 透传 SSE 流 ──────────────┤                              │
```

- **协议**: Anthropic Messages API（`/v1/messages`），完整透传，不转换
- **认证**: 自动注入 `x-api-key`，剥掉 Claude Desktop 发来的 auth
- **流式**: SSE 零缓冲透传，加了 `X-Accel-Buffering: no` 防止反向代理缓冲
- **模型名替换**: 只改 body 里的 `model` 字段，其余全部原样转发

## 项目结构

```
DS2Claude/
├── proxy.py          # 主程序
├── index.html        # Web 管理界面
├── groups.yaml       # 组配置（4 个官方平台 + 1 个自定义示例）
├── requirements.txt
└── CLAUDE.md
```

## 快速开始

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 编辑 groups.yaml 填入你的 API Key

# 3. 启动
python3 proxy.py

# 4. 浏览器 → http://127.0.0.1:8765  管理组和映射

# 5. Claude Desktop → 开发者模式 → Gateway
#    Base URL: http://127.0.0.1:8765
#    API Key:  随便填一个（代理会自动替换为真实 key）
#    Models:   claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5
```

## 组配置

| 组名 | 模型 | Base URL |
|------|------|----------|
| `deepseek` | deepseek-v4-pro[1m] / v4-flash | api.deepseek.com/anthropic |
| `glm` | glm-5.1 | open.bigmodel.cn/api/anthropic |
| `kimi` | kimi-for-coding | api.kimi.com/coding |
| `minimax` | MiniMax-M2.7 | api.minimaxi.com/anthropic |
| `custom` | 任意 Anthropic 兼容模型 | 自定义 |

添加新平台只需在 `groups.yaml` 里加一个组。

## 协议细节

- **必须头**: `x-api-key`（认证）, `anthropic-version: 2023-06-01`
- **流式**: `text/event-stream`，事件: `message_start/delta/stop`, `content_block_start/delta/stop`, `ping`
- **count_tokens**: 先尝试真实转发到上游，上游不支持则自动 fallback 本地估算
- **模型名规范**: DeepSeek 用 `[1m]` 后缀开 1M 上下文。代理只做替换不做转换
- **超时**: 连接 15s，请求 300s

## 安全

- 代理只监听 `127.0.0.1`，不接受外部连接
- 转发头使用白名单机制（只传 content-type / accept / anthropic-* / stainless-*）
- API Key 只存在于本地 `groups.yaml`，不上传任何地方

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 管理界面 |
| GET | `/api/state` | 完整状态 |
| POST | `/api/groups/{name}` | 创建组 |
| PUT | `/api/groups/{name}` | 更新组 |
| DELETE | `/api/groups/{name}` | 删除组 |
| POST | `/api/activate/{name}` | 切换激活组（热切换） |
| GET | `/health` | 健康检查 + 当前激活组 |
| * | `/{path}` | 透传代理（Anthropic 协议） |
