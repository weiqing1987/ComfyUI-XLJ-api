"""MiniMax H3 video hosting adapter.

The MiniMax H3 2K API requires a publicly reachable video URL.  This node
accepts ComfyUI's VIDEO type and uploads the encoded file using multipart
``file`` semantics, then normalizes common host response shapes to a URL.
"""
import json
import os
import tempfile
from pathlib import Path

import requests


class XLJMiniMaxH3UploadVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video": ("VIDEO",),
        }, "optional": {
            "upload_url": ("STRING", {"default": "https://imageproxy.zhongzhuan.chat/api/upload"}),
            "timeout_seconds": ("INT", {"default": 300, "min": 10, "max": 1800}),
        }}

    RETURN_TYPES = ("STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("video_url", "source_duration", "upload_info")
    FUNCTION = "upload"
    CATEGORY = "XLJ/MiniMax H3"

    def upload(self, video, upload_url="https://imageproxy.zhongzhuan.chat/api/upload", timeout_seconds=300):
        if video is None:
            raise RuntimeError("没有收到 VIDEO 输入，请连接 CreateVideo 的输出")
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(prefix="minimax_h3_", suffix=".mp4", delete=False) as handle:
                temp_name = handle.name
            video.save_to(temp_name)
            try:
                source_duration = float(video.get_duration())
            except Exception:
                source_duration = 5.0
            path = Path(temp_name)
            if not path.is_file() or path.stat().st_size < 1024:
                raise RuntimeError("VIDEO 编码为空或过小")
            with path.open("rb") as stream:
                response = requests.post(
                    str(upload_url).strip(),
                    files={"file": (path.name, stream, "video/mp4")},
                    headers={"Accept": "application/json"},
                    timeout=int(timeout_seconds),
                )
            response.raise_for_status()
            data = response.json()
            url = self._find_url(data)
            if not url:
                raise RuntimeError("图床响应中没有 URL：" + json.dumps(data, ensure_ascii=False))
            return (url, source_duration, json.dumps({"url": url, "source_duration": source_duration, "response": data}, ensure_ascii=False))
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    @staticmethod
    def _find_url(data):
        if isinstance(data, str) and data.startswith(("http://", "https://")):
            return data
        if isinstance(data, dict):
            for key in ("url", "video_url", "download_url", "file_url", "link"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
            for key in ("data", "result", "file"):
                found = XLJMiniMaxH3UploadVideo._find_url(data.get(key))
                if found:
                    return found
        if isinstance(data, list):
            for item in data:
                found = XLJMiniMaxH3UploadVideo._find_url(item)
                if found:
                    return found
        return ""
