"""
独立运行的 Playwright 辅助脚本。

站点的登录接口开启了图形验证码，无法用账号密码直接请求登录。这个脚本会打开
一个真实浏览器窗口，等用户自己完成验证码并登录成功后，把 cookie 以 JSON
形式输出到 stdout，由节点进程保存下来复用。

注意：这个脚本必须独立进程运行，避免 Playwright 的同步 API 与 ComfyUI 的
事件循环冲突。
"""

import argparse
import json
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    return parser.parse_args()


READ_USER_JS = """
async () => {
  try {
    const raw = window.localStorage.getItem('user');
    const stored = raw ? JSON.parse(raw) : null;
    const userId = stored && stored.id ? String(stored.id) : '';
    const resp = await fetch('/api/user/self', {
      headers: { 'Accept': 'application/json', 'New-Api-User': userId },
      credentials: 'include'
    });
    const body = await resp.json();
    if (body && body.success && body.data) {
      return { user: body.data };
    }
    return null;
  } catch (err) {
    return null;
  }
}
"""


def prefill(page, username, password):
    if username:
        for selector in ('input[name="username"]', 'input#username', 'input[type="text"]'):
            try:
                page.fill(selector, username, timeout=3000)
                break
            except Exception:
                continue
    if password:
        for selector in ('input[name="password"]', 'input#password', 'input[type="password"]'):
            try:
                page.fill(selector, password, timeout=3000)
                break
            except Exception:
                continue


def find_logged_in_user(context):
    for page in reversed(context.pages):
        try:
            result = page.evaluate(READ_USER_JS)
        except Exception:
            continue
        if result and result.get("user"):
            return page, result["user"]
    return None, None


def main():
    args = parse_args()
    output = {"ok": False, "error": "登录未完成"}

    # 账号密码通过环境变量传递，避免出现在进程命令行里。
    username = args.username or os.environ.get("XLJ_LOGIN_USERNAME", "")
    password = args.password or os.environ.get("XLJ_LOGIN_PASSWORD", "")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        output["error"] = f"playwright 未安装：{exc}"
        json.dump(output, sys.stdout, ensure_ascii=False)
        return 2

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=args.profile,
                channel=args.channel,
                headless=False,
                no_viewport=True,
                args=["--start-maximized"],
            )
        except Exception as exc:
            output["error"] = f"浏览器启动失败（{args.channel}）：{exc}"
            json.dump(output, sys.stdout, ensure_ascii=False)
            return 3

        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(args.base.rstrip("/") + "/login", wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print(f"[login] 打开登录页失败：{exc}", file=sys.stderr)
            prefill(page, username, password)

            deadline = time.time() + max(30, args.timeout)
            user = None
            while time.time() < deadline:
                if not context.pages:
                    output["error"] = "浏览器窗口已被关闭，登录未完成"
                    break
                _, user = find_logged_in_user(context)
                if user:
                    break
                time.sleep(2)

            if user:
                cookies = context.cookies()
                output = {
                    "ok": True,
                    "user_id": user.get("id"),
                    "username": user.get("username") or user.get("display_name") or "",
                    "quota": user.get("quota"),
                    "cookies": cookies,
                }
            elif output.get("error") == "登录未完成":
                output["error"] = f"等待登录超时（{args.timeout} 秒）"
        finally:
            try:
                context.close()
            except Exception:
                pass

    json.dump(output, sys.stdout, ensure_ascii=False)
    return 0 if output.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
