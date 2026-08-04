"""MiniMax H3 official 2K regeneration node.

The API calls intentionally bypass XLJ's proxy and use api.minimaxi.com.
"""
import base64
import json
import os
import tempfile
import time
from pathlib import Path

import requests

try:
    from comfy_api.latest import VideoFromFile
except Exception:
    VideoFromFile = None


class XLJMiniMaxH3Regenerate2K:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "base_video_url": ("STRING", {"multiline": False, "default": ""}),
            "prompt": ("STRING", {"multiline": True, "default": ""}),
            "api_key": ("STRING", {"default": "", "multiline": False}),
        }, "optional": {
            "first_frame_url": ("STRING", {"default": ""}),
            "last_frame_url": ("STRING", {"default": ""}),
            "duration": ("INT", {"default": 5, "min": 1, "max": 10}),
            "ratio": (["adaptive", "16:9", "9:16", "1:1"], {"default": "adaptive"}),
            "api_base": ("STRING", {"default": "https://api.minimaxi.com"}),
            "poll_interval": ("FLOAT", {"default": 5.0, "min": 1.0, "max": 60.0}),
            "timeout_seconds": ("INT", {"default": 1800, "min": 30, "max": 7200}),
        }}

    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_info")
    FUNCTION = "generate"
    CATEGORY = "XLJ/MiniMax H3"

    @staticmethod
    def _video_url(value):
        value = str(value or "").strip()
        if not value:
            raise ValueError("请连接 XLJUploadVideo 的视频 URL，或填写本地 MP4 路径")
        if value.startswith(("http://", "https://", "data:video/")):
            return value
        path = Path(os.path.expanduser(value))
        if not path.is_file():
            raise ValueError(f"视频文件不存在：{path}")
        mime = "video/mp4" if path.suffix.lower() == ".mp4" else "video/*"
        return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode())

    @staticmethod
    def _content(prompt, first, last):
        content = [{"type": "text", "text": prompt}]
        if first:
            content.append({"type": "image_url", "image_url": {"url": first}, "role": "first_frame"})
        if last:
            content.append({"type": "image_url", "image_url": {"url": last}, "role": "last_frame"})
        return content

    @staticmethod
    def _task_id(data):
        return data.get("task_id") or data.get("task", {}).get("task_id") or data.get("task", {}).get("id")

    def _poll(self, session, base, key, task_id, interval, timeout):
        end = time.time() + timeout
        headers = {"Authorization": "Bearer " + key}
        try:
            import comfy.utils
            pbar = comfy.utils.ProgressBar(100)
        except Exception:
            pbar = None
        while time.time() < end:
            response = session.get(f"{base}/v2/query/video_generation/{task_id}", headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            task = data.get("task", data)
            status = str(task.get("status", data.get("status", ""))).upper()
            if pbar is not None:
                pbar.update_absolute(min(99, pbar.current + 5))
            if status in {"SUCCEEDED", "SUCCESS", "COMPLETED"}:
                url = task.get("content", {}).get("url") or data.get("content", {}).get("url")
                if not url:
                    raise RuntimeError("任务成功但响应中没有视频 URL：" + json.dumps(data, ensure_ascii=False))
                return url, data
            if status in {"FAILED", "FAIL", "CANCELED", "CANCELLED"}:
                raise RuntimeError("MiniMax H3 任务失败：" + json.dumps(data, ensure_ascii=False))
            time.sleep(interval)
        raise TimeoutError(f"MiniMax H3 查询超时（{timeout} 秒），task_id={task_id}")

    def generate(self, base_video_url, prompt, api_key, first_frame_url="", last_frame_url="",
                 duration=5, ratio="adaptive", api_base="https://api.minimaxi.com",
                 poll_interval=5.0, timeout_seconds=1800):
        key = str(api_key or os.getenv("MINIMAX_API_KEY", "")).strip()
        if not key:
            raise ValueError("请填写 MiniMax API Key，或设置 MINIMAX_API_KEY")
        base = api_base.rstrip("/")
        session = requests.Session()
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        context = {"model": "MiniMax-H3", "content": self._content(prompt, first_frame_url.strip(), last_frame_url.strip()),
                   "duration": int(duration), "ratio": ratio}
        response = session.post(f"{base}/v2/h3_context_ir", headers=headers, json=context, timeout=120)
        response.raise_for_status()
        context_data = response.json()
        context_id = self._task_id(context_data)
        if not context_id:
            raise RuntimeError("Context-IR 未返回 task_id：" + json.dumps(context_data, ensure_ascii=False))
        _, context_result = self._poll(session, base, key, context_id, poll_interval, timeout_seconds)
        expanded = context_result.get("task", {}).get("content", {}).get("text") or prompt
        regen = {"model": "MiniMax-H3", "content": self._content(expanded, first_frame_url.strip(), last_frame_url.strip()) +
                 [{"type": "video_url", "video_url": {"url": self._video_url(base_video_url)}, "role": "base_video"}],
                 "resolution": "2K"}
        response = session.post(f"{base}/v2/video_regeneration", headers=headers, json=regen, timeout=120)
        response.raise_for_status()
        regen_data = response.json()
        regen_id = self._task_id(regen_data)
        if not regen_id:
            raise RuntimeError("2K 重生成未返回 task_id：" + json.dumps(regen_data, ensure_ascii=False))
        url, result = self._poll(session, base, key, regen_id, poll_interval, timeout_seconds)
        if VideoFromFile is None:
            raise RuntimeError("当前 ComfyUI 不支持 VIDEO 输出，请升级到包含 VideoFromFile 的版本")
        output_path = Path(tempfile.gettempdir()) / f"minimax_h3_2k_{regen_id}.mp4"
        with session.get(url, stream=True, timeout=180) as download:
            download.raise_for_status()
            with output_path.open("wb") as stream:
                for chunk in download.iter_content(1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        video = VideoFromFile(str(output_path))
        info = json.dumps({"context_task_id": context_id, "regeneration_task_id": regen_id, "response": result}, ensure_ascii=False)
        return (video, url, info)
