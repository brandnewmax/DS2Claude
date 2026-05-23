"""
DS2Claude — 把任意模型接入 Claude Desktop 的本地透传代理

协议:   Anthropic Messages API（透传 /v1/messages）
功能:
  - 多组模型映射，热切换（无需重启）
  - HTML 管理界面 → http://127.0.0.1:8765
  - Claude Desktop Gateway → http://127.0.0.1:8765

启动:   python3 proxy.py
配置:   编辑 groups.yaml 或打开 http://127.0.0.1:8765 用 Web UI
"""

import yaml
import httpx
import threading
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, Response, HTMLResponse

ROOT = Path(__file__).parent
GROUPS_FILE = ROOT / "groups.yaml"
INDEX_FILE = ROOT / "index.html"

lock = threading.Lock()
groups: dict = {}
active_name: str = ""
model_map: dict[str, dict] = {}  # {source_model: target_dict}

clients: dict[str, httpx.AsyncClient] = {}

# ── 配置 ─────────────────────────────────────────────────

def _migrate_old_config():
    old = ROOT / "config.yaml"
    if not old.exists():
        return False
    with open(old) as f:
        cfg = yaml.safe_load(f)
    groups = {"deepseek": {"label": "DeepSeek", "mappings": cfg.get("mappings", [])}}
    save_groups({"active": "deepseek", "groups": groups})
    old.rename(ROOT / "config.yaml.bak")
    return True


def load_groups():
    global groups, active_name, model_map
    if not GROUPS_FILE.exists():
        if not _migrate_old_config():
            groups, active_name, model_map = {}, "", {}
            return
    with open(GROUPS_FILE) as f:
        data = yaml.safe_load(f) or {}
    groups = data.get("groups", {})
    active_name = data.get("active", "")
    _apply_active()


def save_groups(data=None):
    if data is None:
        data = {"active": active_name, "groups": groups}
    with open(GROUPS_FILE, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _apply_active():
    global model_map
    group = groups.get(active_name, {})
    model_map = {}
    for m in group.get("mappings", []):
        model_map[m["source"]] = m["target"]


# ── HTTP 客户端池 ────────────────────────────────────────

def get_client(api_base: str) -> httpx.AsyncClient:
    if api_base not in clients:
        clients[api_base] = httpx.AsyncClient(
            base_url=api_base,
            timeout=httpx.Timeout(300.0, connect=15.0),
        )
    return clients[api_base]


# ── FastAPI ──────────────────────────────────────────────

app = FastAPI(title="DS2Claude", version="2.1.0")

# ────────── HTML ─────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    if INDEX_FILE.exists():
        return HTMLResponse(INDEX_FILE.read_text())
    return HTMLResponse("<h2>index.html not found</h2>", status_code=404)


# ────────── 管理 API ─────────────────────────────────────

@app.get("/api/state")
async def get_state():
    return {
        "active": active_name,
        "groups": groups,
        "model_map": {k: v for k, v in model_map.items()},
    }


@app.post("/api/groups/{name}")
async def create_group(name: str, body: dict):
    global active_name
    with lock:
        if name in groups:
            return JSONResponse({"error": f"group '{name}' already exists"}, status_code=409)
        groups[name] = {
            "label": body.get("label", name),
            "mappings": body.get("mappings", []),
        }
        if not active_name:
            active_name = name
            _apply_active()
        save_groups()
    return {"ok": True, "name": name}


@app.put("/api/groups/{name}")
async def update_group(name: str, body: dict):
    with lock:
        if name not in groups:
            return JSONResponse({"error": "group not found"}, status_code=404)
        if "label" in body:
            groups[name]["label"] = body["label"]
        if "mappings" in body:
            groups[name]["mappings"] = body["mappings"]
        if active_name == name:
            _apply_active()
        save_groups()
    return {"ok": True}


@app.delete("/api/groups/{name}")
async def delete_group(name: str):
    global active_name
    with lock:
        if name not in groups:
            return JSONResponse({"error": "group not found"}, status_code=404)
        del groups[name]
        if active_name == name:
            active_name = next(iter(groups), "")
            _apply_active()
        save_groups()
    return {"ok": True}


@app.post("/api/activate/{name}")
async def activate_group(name: str):
    global active_name
    with lock:
        if name not in groups:
            return JSONResponse({"error": "group not found"}, status_code=404)
        active_name = name
        _apply_active()
        save_groups()
    return {"ok": True, "active": name, "model_map": {k: v for k, v in model_map.items()}}


# ────────── 健康检查 ─────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_group": active_name,
        "mappings": {k: f"{v['model']} ({v['api_base']})" for k, v in model_map.items()},
    }


# ────────── Token 计数 ──────────────────────────────────
# 先尝试真实转发到上游，上游不支持则 fallback 到本地估算


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    body = await request.json()
    source = body.get("model", "")
    target_cfg = model_map.get(source)

    if target_cfg is None:
        return JSONResponse({"input_tokens": _estimate_tokens(body)})

    # 替换模型名后尝试真实转发
    body["model"] = target_cfg["model"]
    headers = {}
    for key, val in request.headers.items():
        if key.lower() in FORWARD_HEADERS:
            headers[key] = val
    headers["x-api-key"] = target_cfg["api_key"]
    if "anthropic-version" not in headers:
        headers["anthropic-version"] = "2023-06-01"

    client = get_client(target_cfg["api_base"])
    try:
        resp = await client.post(
            "/v1/messages/count_tokens",
            json=body,
            headers=headers,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        if resp.status_code == 200:
            return JSONResponse(content=resp.json(), status_code=200)
    except Exception:
        pass

    # 上游不支持，fallback 到本地估算
    return JSONResponse({"input_tokens": _estimate_tokens(body)})


@app.get("/v1/messages/count_tokens")
async def count_tokens_get():
    return JSONResponse({"input_tokens": 0})


def _estimate_tokens(body: dict) -> int:
    """粗略估算 token 数：英文 ~4 chars/token，中文 ~1.5 chars/token"""
    chars = 0
    system = body.get("system")
    if isinstance(system, str):
        chars += len(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and "text" in block:
                chars += len(block["text"])
    for msg in body.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    chars += len(block["text"])
    for tool in body.get("tools", []):
        chars += len(str(tool))
    return max(1, int(chars / 3.5))


# ────────── 透传代理 ─────────────────────────────────────

# 只转发安全头，避免泄露和冲突
FORWARD_HEADERS = {
    "content-type", "accept", "accept-encoding",
    "anthropic-version", "anthropic-beta",
    "user-agent",
    "x-stainless-lang", "x-stainless-package-version",
    "x-stainless-os", "x-stainless-arch",
    "x-stainless-runtime", "x-stainless-runtime-version",
}

# Anthropic 流式 SSE content-type
SSE_TYPE = "text/event-stream"


@app.api_route("/{path:path}", methods=["POST", "GET", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    # ── 只处理 JSON body ──
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()

    if not isinstance(body, dict) or "model" not in body:
        return JSONResponse({
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "request must be JSON with a 'model' field. POST to /v1/messages",
            },
        }, status_code=400)

    # ── 模型名映射 ──
    source = body["model"]
    target_cfg = model_map.get(source)
    if target_cfg is None:
        return JSONResponse({
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": f"unknown model '{source}'. active group: {active_name}, available: {list(model_map.keys())}",
            },
        }, status_code=400)
    body["model"] = target_cfg["model"]

    # ── 构建转发 headers ──
    headers = {}
    for key, val in request.headers.items():
        if key.lower() in FORWARD_HEADERS:
            headers[key] = val

    # 注入目标 API 的认证（Anthropic 协议用 x-api-key）
    headers["x-api-key"] = target_cfg["api_key"]

    # 确保 anthropic-version 存在
    if "anthropic-version" not in headers:
        headers["anthropic-version"] = "2023-06-01"

    # ── 转发 ──
    stream = body.get("stream", False)
    client = get_client(target_cfg["api_base"])

    req = client.build_request(
        method=request.method,
        url=f"/{path}",
        json=body,
        headers=headers,
        timeout=httpx.Timeout(300.0, connect=15.0),
    )

    if stream:
        async def sse_stream():
            resp = await client.send(req, stream=True)
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()

        return StreamingResponse(
            sse_stream(),
            media_type=SSE_TYPE,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        resp = await client.send(req)
        resp_ct = resp.headers.get("content-type", "")
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception:
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp_ct or "text/plain",
            )


# ── 入口 ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    load_groups()
    # 兼容旧 config.yaml 二次检查
    if not GROUPS_FILE.exists():
        _migrate_old_config()
        load_groups()

    print(f"\n  DS2Claude v2.1 → http://127.0.0.1:8765")
    print(f"  协议: Anthropic Messages API (透传)")
    print(f"  管理: http://127.0.0.1:8765/")
    print(f"  激活组: {active_name}  ({len(model_map)} 个映射)")
    for src, tgt in model_map.items():
        print(f"    {src}  →  {tgt['model']}  ({tgt['api_base']})")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
