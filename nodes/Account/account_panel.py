"""
XLJ 密钥中控面板。

一个节点走完全流程：选站点 → 填账号密码 → 点「登录」弹出浏览器完成验证码 →
回到面板选模型 → 点「生成密钥」→ 密钥显示在面板上，并通过 API_KEY 输出端口
传给下游节点，下游不用再手动填。

登录接口带图形验证码且客户端加签，无法直接请求，所以登录统一交给
`browser_login.py` 在真实浏览器里完成，节点只负责保存和复用会话 cookie。
"""

import asyncio
import functools
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from ..xlj_utils import API_SITE_OPTIONS, resolve_api_base

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = PLUGIN_ROOT / ".auth"
PROFILE_DIR = AUTH_DIR / "browser_profile"
SESSION_DIR = AUTH_DIR / "sessions"
LOGIN_HELPER = Path(__file__).resolve().parent / "browser_login.py"

BROWSER_CHANNELS = {"edge": "msedge", "chrome": "chrome"}
BROWSER_PATHS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
}

GROUP_MODEL_SENTINEL = "该分组支持的图像模型"

MODEL_OPTIONS = [
    "gpt-image-2.5-flare-c",
    "gpt-image-2.5-sunburst-c",
    "gpt-image-2-c",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    GROUP_MODEL_SENTINEL,
    "不限制",
]

# base -> {"state": running|error, "message": str}
LOGIN_STATE = {}


def default_browser():
    for name, paths in BROWSER_PATHS.items():
        if any(os.path.isfile(path) for path in paths):
            return name
    return "edge"


def _slug(value):
    text = str(value or "").strip()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip("/").replace("/", "_").replace(":", "_") or "site"


def session_path(base):
    return SESSION_DIR / f"session_{_slug(base)}.json"


def load_session(base):
    path = session_path(base)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if data.get("cookies") else None


def save_session(base, session):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(session)
    payload["base"] = base
    payload["saved_at"] = time.time()
    path = session_path(base)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def store_current_api_key(api_key):
    """把最新生成的密钥存下来，各节点的 api_key 留空时会自动使用，实现免填。"""
    if not api_key:
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    (AUTH_DIR / "current_api_key").write_text(api_key.strip(), encoding="utf-8")


def force_switch_marker(base):
    return AUTH_DIR / f"force_switch_{_slug(base)}"


def clear_account_cache(base):
    """退出登录：清掉会话、当前密钥和浏览器登录状态，保证换号时是干净的。"""
    removed = []

    path = session_path(base)
    if path.is_file():
        try:
            path.unlink()
            removed.append("会话")
        except Exception as exc:
            print(f"[ComfyUI-XLJ-api] 删除会话失败：{exc}")

    key_path = AUTH_DIR / "current_api_key"
    if key_path.is_file():
        try:
            key_path.unlink()
            removed.append("当前密钥")
        except Exception as exc:
            print(f"[ComfyUI-XLJ-api] 删除当前密钥失败：{exc}")

    try:
        import shutil
        if PROFILE_DIR.is_dir():
            shutil.rmtree(PROFILE_DIR)
            removed.append("浏览器登录状态")
    except Exception as exc:
        print(f"[ComfyUI-XLJ-api] 浏览器配置未删除（可能正被占用）：{exc}")

    # 即使浏览器配置没删掉，也标记下次登录强制清理，避免继续用旧账号
    try:
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        force_switch_marker(base).write_text("1", encoding="utf-8")
    except Exception as exc:
        print(f"[ComfyUI-XLJ-api] 写入换号标记失败：{exc}")

    LOGIN_STATE.pop(base, None)
    return removed


def session_headers(session):
    return {
        "Accept": "application/json",
        "New-Api-User": str(session.get("user_id") or ""),
    }


def build_http(session):
    http = requests.Session()
    http.trust_env = False
    for cookie in session.get("cookies") or []:
        name = cookie.get("name")
        if not name:
            continue
        http.cookies.set(name, cookie.get("value") or "", domain=cookie.get("domain") or None,
                         path=cookie.get("path") or "/")
    return http


def request_json(base, session, method, path, payload=None, timeout=30):
    http = build_http(session)
    headers = session_headers(session)
    kwargs = {"headers": headers, "timeout": timeout}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        kwargs["data"] = json.dumps(payload)
    resp = http.request(method, base.rstrip("/") + path, **kwargs)
    try:
        return resp.status_code, resp.json()
    except Exception:
        raise RuntimeError(f"接口返回异常（HTTP {resp.status_code}）：{resp.text[:200]}")


def fetch_self(base, session):
    _, body = request_json(base, session, "GET", "/api/user/self")
    if isinstance(body, dict) and body.get("success") and body.get("data"):
        return body["data"]
    return None


def fetch_tokens(base, session):
    _, body = request_json(base, session, "GET", "/api/token/?p=0&size=100")
    if not isinstance(body, dict) or not body.get("success"):
        message = body.get("message") if isinstance(body, dict) else body
        raise RuntimeError(f"读取密钥列表失败：{message}")
    data = body.get("data")
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(data, list):
        return data
    return []


def fetch_public_pricing(base):
    """站点模型广场是公开接口，不需要会话。"""
    resp = requests.get(base.rstrip("/") + "/api/pricing", timeout=30)
    resp.raise_for_status()
    payload = resp.json() or {}
    return payload.get("data") or []


def model_groups(base, model):
    """该模型在站点上支持的分组，顺序按模型广场给出的顺序。"""
    if not model or model == "不限制":
        return []
    try:
        for item in fetch_public_pricing(base):
            if item.get("model_name") == model:
                return [group for group in (item.get("enable_groups") or []) if group]
    except Exception as exc:
        print(f"[ComfyUI-XLJ-api] 读取模型分组失败：{exc}")
    return []


def image_models_by_group(base):
    """分组 -> 该分组覆盖的图像模型列表，数据来自公开的模型广场。"""
    mapping = {}
    try:
        for item in fetch_public_pricing(base):
            if item.get("model_type") != "图像":
                continue
            name = item.get("model_name")
            if not name:
                continue
            for group in item.get("enable_groups") or []:
                mapping.setdefault(group, []).append(name)
    except Exception as exc:
        print(f"[ComfyUI-XLJ-api] 读取分组图像模型失败：{exc}")
    return mapping


_GROUP_META_KEYS = {"current_group", "group_ids", "ratios", "uptime"}


def _extract_group_names(data):
    if isinstance(data, dict):
        return [name for name in data.keys() if name not in _GROUP_META_KEYS]
    if isinstance(data, list):
        names = []
        for item in data:
            name = item if isinstance(item, str) else (item or {}).get("name")
            if name:
                names.append(name)
        return names
    return []


def account_group_info(base, session):
    """
    /api/user/self/groups 返回形如
    {"current_group": "default", "data": {"Gpt-Image-1": ...}, "group_ids": {...}}
    真正的分组名单在 data 里，外层还有 current_group 等元信息。
    """
    info = {"groups": [], "current": ""}
    try:
        _, body = request_json(base, session, "GET", "/api/user/self/groups")
    except Exception:
        body = None

    if isinstance(body, dict) and body.get("success"):
        data = body.get("data")
        if isinstance(data, dict):
            info["current"] = str(data.get("current_group") or "")
            inner = data.get("data")
            info["groups"] = _extract_group_names(inner if inner is not None else data)
        else:
            info["groups"] = _extract_group_names(data)

    if not info["groups"] or not info["current"]:
        try:
            me = fetch_self(base, session) or {}
        except Exception:
            me = {}
        if not info["current"]:
            info["current"] = str(me.get("group") or "")
    return info


def account_groups(base, session):
    return account_group_info(base, session)["groups"]


def pick_group(base, session, model, requested):
    """
    创建密钥必须带分组（站点关闭了智能路由）。留空或填「自动」时按模型推导：
    gpt-image 系列会命中 Gpt-Image-1，其它模型取账号可用分组里的第一个。
    """
    requested = str(requested or "").strip()
    if requested and requested not in ("自动", "auto"):
        return requested

    candidates = model_groups(base, model)
    info = account_group_info(base, session)
    allowed = info["groups"]
    if candidates:
        for group in candidates:
            if group in allowed:
                return group
        return candidates[0]
    if info["current"]:
        return info["current"]
    if allowed:
        return allowed[0]
    return ""


def create_token(base, session, name, models, unlimited_quota, expired_days, group):
    expired_time = -1 if int(expired_days) < 0 else int(time.time()) + int(expired_days) * 86400
    payload = {
        "name": name,
        "remain_quota": 0,
        "expired_time": expired_time,
        "unlimited_quota": bool(unlimited_quota),
        "model_limits_enabled": bool(models),
        "model_limits": ",".join(models),
        "group": group or "",
        "allow_ips": "",
    }
    _, body = request_json(base, session, "POST", "/api/token/", payload=payload, timeout=60)
    if not isinstance(body, dict) or not body.get("success"):
        message = body.get("message") if isinstance(body, dict) else body
        raise RuntimeError(f"创建密钥失败：{message}")
    return payload


def normalize_api_key(token):
    key = str((token or {}).get("key") or "").strip()
    if not key:
        return ""
    return key if key.startswith("sk-") else f"sk-{key}"


def ensure_playwright():
    """没装 playwright 时自动装一次，失败则给出可复制的手动命令。"""
    import importlib
    import importlib.util

    if importlib.util.find_spec("playwright") is not None:
        return

    print("[ComfyUI-XLJ-api] 未检测到 playwright，正在自动安装（约 40MB，只需一次）…")
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "playwright"]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    detail = ""
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            creationflags=creation_flags,
        )
        detail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
    except Exception as exc:
        detail = str(exc)

    importlib.invalidate_caches()
    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError(
            "playwright 未安装，自动安装也没成功。请手动执行：\n"
            f'"{sys.executable}" -m pip install playwright\n{detail}'
        )
    print("[ComfyUI-XLJ-api] playwright 安装完成")


def run_browser_login(base, username, password, timeout_seconds, browser, switch_account=False):
    ensure_playwright()
    channel = BROWSER_CHANNELS.get(browser, "msedge")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(LOGIN_HELPER),
        "--base", base,
        "--profile", str(PROFILE_DIR),
        "--channel", channel,
        "--timeout", str(int(timeout_seconds)),
    ]
    if switch_account:
        command.append("--switch-account")

    env = dict(os.environ)
    if username:
        env["XLJ_LOGIN_USERNAME"] = username
    if password:
        env["XLJ_LOGIN_PASSWORD"] = password

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(timeout_seconds) + 180,
            creationflags=creation_flags,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("等待登录超时，请重新点击「登录」")

    raw = (proc.stdout or "").strip()
    try:
        result = json.loads(raw)
    except Exception:
        detail = (proc.stderr or raw or "").strip()[-400:]
        raise RuntimeError(f"登录脚本返回异常：{detail or '没有输出'}")

    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "登录失败")
    return result


def _login_worker(base, username, password, timeout_seconds, browser, switch_account=False):
    previous = load_session(base) or {}
    try:
        result = run_browser_login(base, username, password, timeout_seconds, browser, switch_account)
        session = {
            "user_id": result.get("user_id"),
            "username": result.get("username") or username,
            "cookies": result.get("cookies") or [],
        }
        path = save_session(base, session)

        switched = bool(previous.get("user_id")) and previous.get("user_id") != session.get("user_id")
        if switched:
            # 换了账号，旧账号的密钥不能继续当当前密钥用
            key_path = AUTH_DIR / "current_api_key"
            try:
                if key_path.is_file():
                    key_path.unlink()
            except Exception as exc:
                print(f"[ComfyUI-XLJ-api] 清理旧账号密钥失败：{exc}")

        message = f"登录成功：{session['username'] or '-'}（{path.name}）"
        if switched:
            message += "，已切换账号并清除旧账号的密钥缓存"
        LOGIN_STATE[base] = {
            "state": "done",
            "message": message,
        }
        print(f"[ComfyUI-XLJ-api] {message}")
    except Exception as exc:
        LOGIN_STATE[base] = {"state": "error", "message": str(exc)}
        print(f"[ComfyUI-XLJ-api] 登录失败：{exc}")


def _create_key_sync(body):
    api_site = body.get("api_site") or API_SITE_OPTIONS[0]
    base = resolve_api_base(api_site)
    session = load_session(base)
    if not session:
        raise RuntimeError("尚未登录，请先点击面板上的「登录」")

    me = fetch_self(base, session)
    if not me:
        raise RuntimeError("登录会话已失效，请重新点击「登录」")

    model = str(body.get("model") or "").strip()
    key_name = str(body.get("key_name") or "comfyui").strip() or "comfyui"
    unlimited_quota = bool(body.get("unlimited_quota", True))
    expired_days = int(body.get("expired_days", -1) or -1)

    if model == GROUP_MODEL_SENTINEL:
        # 一个分组往往覆盖多个图像模型，这里一次性全绑上
        group = pick_group(base, session, "", body.get("group"))
        models = list(image_models_by_group(base).get(group, []))
        if not models:
            raise RuntimeError(
                f"分组「{group or '默认'}」下没有查到图像模型。"
                "请在面板的「分组」里选一个具体分组（例如 Gpt-Image-1），或把模型改成「不限制」。"
            )
    else:
        models = []
        if model and model != "不限制":
            models.append(model)
        for extra in str(body.get("extra_models") or "").split(","):
            extra = extra.strip()
            if extra and extra not in models:
                models.append(extra)
        group = pick_group(base, session, model, body.get("group"))

    create_token(base, session, key_name, models, unlimited_quota, expired_days, group)

    api_key = ""
    for item in sorted(fetch_tokens(base, session), key=lambda x: x.get("id") or 0, reverse=True):
        if (item.get("name") or "") == key_name:
            api_key = normalize_api_key(item)
            break
    if not api_key:
        raise RuntimeError("密钥已创建，但没有从列表里取到密钥值，请在网站上确认")

    scope = ",".join(models) if models else "不限制"
    if model == GROUP_MODEL_SENTINEL:
        model_label = f"{group} 覆盖的 {len(models)} 个图像模型"
    else:
        model_label = model or "不限制"
    status = (
        f"模型：{model_label} | 绑定：{scope} | 分组：{group or '默认'} | 名称：{key_name} | "
        f"额度：{'不限额' if unlimited_quota else '按剩余额度'} | "
        f"有效期：{'永不过期' if expired_days < 0 else str(expired_days) + ' 天'} | 站点：{base}"
    )
    if models:
        # 绑定了模型的密钥不能当作全局兜底，否则其它模型会 403
        status += (
            f"\n注意：该密钥仅限 {scope}，调用其它模型会报 403，因此没有设为自动使用的当前密钥。"
            "要一把通吃，请把「模型」选成「不限制」再生成。"
        )
    else:
        store_current_api_key(api_key)
        status += "\n已设为当前密钥，其它节点 api_key 留空即可自动使用。"
    return {"api_key": api_key, "status": status, "model": model, "key_name": key_name}


def register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception as exc:
        print(f"[ComfyUI-XLJ-api] 无法注册账号面板接口：{exc}")
        return

    routes = getattr(PromptServer.instance, "routes", None)
    if routes is None:
        print("[ComfyUI-XLJ-api] PromptServer 尚未就绪，账号面板接口未注册")
        return

    async def login(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        api_site = body.get("api_site") or API_SITE_OPTIONS[0]
        base = resolve_api_base(api_site)
        state = LOGIN_STATE.get(base)
        if state and state.get("state") == "running":
            return web.json_response({"success": True, "state": "running", "message": state.get("message", "")})

        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        timeout_seconds = int(body.get("timeout") or 300)
        browser = str(body.get("browser") or default_browser())
        switch_account = bool(body.get("switch_account"))

        marker = force_switch_marker(base)
        if marker.is_file():
            switch_account = True
            try:
                marker.unlink()
            except Exception:
                pass

        LOGIN_STATE[base] = {"state": "running", "message": "浏览器已打开，请在浏览器里完成验证码登录"}
        threading.Thread(
            target=_login_worker,
            args=(base, username, password, timeout_seconds, browser, switch_account),
            daemon=True,
        ).start()
        print(f"[ComfyUI-XLJ-api] 已拉起浏览器登录：{base}")
        return web.json_response({"success": True, "state": "running", "message": "浏览器已打开"})

    async def status(request):
        api_site = request.query.get("api_site") or API_SITE_OPTIONS[0]
        base = resolve_api_base(api_site)

        state = LOGIN_STATE.get(base) or {}
        if state.get("state") == "running":
            return web.json_response({"success": True, "state": "running", "message": state.get("message", "")})

        session = load_session(base)
        me = None
        if session:
            try:
                me = await asyncio.get_running_loop().run_in_executor(None, fetch_self, base, session)
            except Exception:
                me = None
        if me:
            return web.json_response({
                "success": True,
                "state": "logged_in",
                "message": state.get("message", ""),
                "username": me.get("username") or "",
                "user_id": me.get("id"),
            })
        if state.get("state") == "error":
            return web.json_response({"success": True, "state": "error", "message": state.get("message", "")})
        return web.json_response({"success": True, "state": "logged_out", "message": "未登录"})

    async def create_key(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, functools.partial(_create_key_sync, body)
            )
            return web.json_response({"success": True, **result})
        except Exception as exc:
            return web.json_response({"success": False, "message": str(exc)})

    async def groups(request):
        api_site = request.query.get("api_site") or API_SITE_OPTIONS[0]
        model = request.query.get("model") or ""
        base = resolve_api_base(api_site)
        session = load_session(base)

        def collect():
            groups = account_groups(base, session) if session else []
            by_group = image_models_by_group(base)
            return {
                "groups": groups,
                "model_groups": model_groups(base, model),
                "group_image_models": {name: by_group.get(name, []) for name in groups if by_group.get(name)},
            }

        try:
            data = await asyncio.get_running_loop().run_in_executor(None, collect)
            return web.json_response({"success": True, **data})
        except Exception as exc:
            return web.json_response({
                "success": False, "message": str(exc), "groups": [], "model_groups": [],
            })

    async def tokens(request):
        api_site = request.query.get("api_site") or API_SITE_OPTIONS[0]
        model = request.query.get("model") or ""
        base = resolve_api_base(api_site)
        session = load_session(base)
        if not session:
            return web.json_response({"success": False, "message": "未登录", "tokens": []})

        def collect():
            info = account_group_info(base, session)
            valid_groups = set(info["groups"])
            # default / current_group 是账号默认路由，属于合法取值
            valid_groups.add("default")
            if info["current"]:
                valid_groups.add(info["current"])
            result = []
            for item in sorted(fetch_tokens(base, session), key=lambda x: x.get("id") or 0, reverse=True):
                key = normalize_api_key(item)
                if not key:
                    continue
                limits = str(item.get("model_limits") or "") if item.get("model_limits_enabled") else ""
                groups = [g for g in str(item.get("group") or "").split(",") if g]
                if limits and model and model in limits:
                    rank = 0          # 专门给当前模型用的密钥排最前
                elif not limits:
                    rank = 1          # 不限模型的通用密钥
                else:
                    rank = 2          # 绑定其它模型的密钥
                result.append({
                    "id": item.get("id"),
                    "name": item.get("name") or "",
                    "key": key,
                    "masked": f"{key[:8]}...{key[-4:]}" if len(key) > 14 else key,
                    "models": limits,
                    "group": item.get("group") or "",
                    "unlimited_quota": bool(item.get("unlimited_quota")),
                    "matches_model": rank == 0,
                    "group_warning": bool(groups) and bool(valid_groups) and any(g not in valid_groups for g in groups),
                    "_rank": rank,
                })
            result.sort(key=lambda x: (x["_rank"], x["group_warning"]))
            for row in result:
                row.pop("_rank", None)
            return result

        try:
            data = await asyncio.get_running_loop().run_in_executor(None, collect)
            return web.json_response({"success": True, "tokens": data})
        except Exception as exc:
            return web.json_response({"success": False, "message": str(exc), "tokens": []})

    async def logout(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        api_site = body.get("api_site") or request.query.get("api_site") or API_SITE_OPTIONS[0]
        base = resolve_api_base(api_site)
        try:
            removed = await asyncio.get_running_loop().run_in_executor(
                None, clear_account_cache, base
            )
        except Exception as exc:
            return web.json_response({"success": False, "message": str(exc)})

        detail = "、".join(removed) if removed else "没有需要清理的内容"
        print(f"[ComfyUI-XLJ-api] 已退出登录：{base}（清理：{detail}）")
        return web.json_response({
            "success": True,
            "state": "logged_out",
            "message": f"已退出登录，清理：{detail}",
        })

    routes.post("/xlj/account/login")(login)
    routes.get("/xlj/account/status")(status)
    routes.post("/xlj/account/create-key")(create_key)
    routes.get("/xlj/account/groups")(groups)
    routes.get("/xlj/account/tokens")(tokens)
    routes.post("/xlj/account/logout")(logout)
    print("[ComfyUI-XLJ-api] 账号面板接口已注册")


register_routes()


class XLJApiKeyPanel:
    """账号登录 + 一键生成密钥的中控面板。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_site": (API_SITE_OPTIONS, {"default": API_SITE_OPTIONS[0], "tooltip": "选择国内或海外站点"}),
                "model": (MODEL_OPTIONS, {"default": MODEL_OPTIONS[0], "tooltip": "要为哪个模型生成密钥"}),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "点击面板上的「生成密钥」后自动填入，可直接连到下游节点的 api_key",
                }),
            },
            "optional": {
                "key_name": ("STRING", {"default": "comfyui", "tooltip": "密钥名称"}),
                "extra_models": ("STRING", {"default": "", "tooltip": "额外绑定的模型，逗号分隔"}),
                "unlimited_quota": ("BOOLEAN", {"default": True, "tooltip": "额度是否不限制"}),
                "expired_days": ("INT", {
                    "default": -1, "min": -1, "max": 3650,
                    "tooltip": "有效天数，-1 表示永不过期",
                }),
                "group": ("STRING", {
                    "default": "",
                    "tooltip": "留空或填「自动」按模型自动选分组（gpt-image 系列默认 Gpt-Image-1），也可手动指定分组名",
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "api_site": "站点",
            "model": "模型",
            "api_key": "API_KEY",
            "key_name": "密钥名称",
            "extra_models": "额外模型",
            "unlimited_quota": "不限额",
            "expired_days": "有效天数",
            "group": "分组",
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("API_KEY", "状态")
    FUNCTION = "run"
    CATEGORY = "XLJ/账号"
    OUTPUT_NODE = True

    def run(self, api_site, model, api_key="", key_name="comfyui", extra_models="",
            unlimited_quota=True, expired_days=-1, group="", unique_id=None):
        base = resolve_api_base(api_site)
        if api_key:
            status = f"站点：{base} | 模型：{model} | 密钥已就绪"
        else:
            status = f"站点：{base} | 模型：{model} | 还没有密钥，请在面板上点击「生成密钥」"
        print(f"[ComfyUI-XLJ-api] {status}")
        return (api_key or "", status)


NODE_CLASS_MAPPINGS = {
    "XLJApiKeyPanel": XLJApiKeyPanel,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJApiKeyPanel": "XLJ 密钥中控面板",
}
