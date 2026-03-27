"""
Sora2 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import (env_or, ensure_list_from_urls,
                         http_headers_json, raise_for_bad_status, json_get, API_BASE)


class XLJSoraCreateVideo:
    """创建 Sora 视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("STRING", {"default": "", "multiline": False, "tooltip": "图片 URL 列表，逗号分隔"}),
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "视频提示词"}),
                "model": (["sora-2", "sora-2-pro", "sora-2-all", "sora-2-pro-all"], {"default": "sora-2", "tooltip": "模型选择"}),
                "duration_sora2": (["10", "15"], {"default": "10", "tooltip": "sora-2 时长 (秒)"}),
                "duration_sora2pro": (["15", "25"], {"default": "15", "tooltip": "sora-2-pro 时长 (秒)"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API 密钥"}),
            },
            "optional": {
                "orientation": (["portrait", "landscape"], {"default": "portrait", "tooltip": "视频方向：竖屏/横屏"}),
                "size": (["small", "large"], {"default": "large", "tooltip": "视频尺寸"}),
                "watermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加水印"}),
                "timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "超时时间 (秒)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("任务 ID", "状态", "状态更新时间")
    FUNCTION = "create"
    CATEGORY = "XLJ/Sora2"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "images": "图片列表",
            "prompt": "提示词",
            "model": "模型",
            "duration_sora2": "sora-2 时长",
            "duration_sora2pro": "sora-2-pro 时长",
            "api_key": "API 密钥",
            "orientation": "方向",
            "size": "尺寸",
            "watermark": "水印",
            "timeout": "超时",
        }

    def create(self, images, prompt, model="sora-2", duration_sora2="10", duration_sora2pro="15",
               api_key="", orientation="portrait", size="large", watermark=False, timeout=120):
        api_key = env_or(api_key, "XLJ_API_KEY")
        endpoint = API_BASE.rstrip("/") + "/v1/video/create"

        images_list = ensure_list_from_urls(images)
        if not images_list:
            raise RuntimeError("请至少提供一个图片 URL")

        # 根据模型选择时长
        duration = int(duration_sora2) if model in ["sora-2", "sora-2-all"] else int(duration_sora2pro)

        payload = {
            "images": images_list,
            "model": model,
            "orientation": orientation,
            "prompt": prompt,
            "size": size,
            "duration": duration,
            "watermark": bool(watermark),
        }

        try:
            resp = requests.post(endpoint, headers=http_headers_json(api_key), data=json.dumps(payload), timeout=int(timeout))
            raise_for_bad_status(resp, "Sora create failed")
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"创建视频失败：{str(e)}")

        task_id = data.get("id") or data.get("task_id") or ""
        status = data.get("status") or ""
        status_update_time = int(data.get("status_update_time") or 0)

        if not task_id:
            raise RuntimeError(f"创建响应缺少任务 ID: {json.dumps(data, ensure_ascii=False)}")

        return (task_id, status, status_update_time)


class XLJSoraQueryTask:
    """查询 Sora 视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "任务 ID"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API 密钥"}),
            },
            "optional": {
                "wait": ("BOOLEAN", {"default": True, "tooltip": "是否等待任务完成"}),
                "poll_interval_sec": ("INT", {"default": 15, "min": 5, "max": 90, "tooltip": "轮询间隔 (秒)"}),
                "timeout_sec": ("INT", {"default": 1200, "min": 600, "max": 9600, "tooltip": "总超时时间 (秒)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "GIF URL", "缩略图 URL", "原始响应 JSON")
    FUNCTION = "query"
    CATEGORY = "XLJ/Sora2"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务 ID",
            "api_key": "API 密钥",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "总超时",
        }

    def query(self, task_id, api_key="", wait=True, poll_interval_sec=5, timeout_sec=600):
        api_key = env_or(api_key, "XLJ_API_KEY")
        endpoint = API_BASE.rstrip("/") + "/v1/video/query"

        def once():
            last_err = None
            for attempt in range(3):
                try:
                    resp = requests.get(endpoint, headers=http_headers_json(api_key), params={"id": task_id}, timeout=60)
                    raise_for_bad_status(resp, "Sora query failed")
                    data = resp.json()
                    status = data.get("status") or json_get(data, "detail.status") or ""
                    video_url = data.get("video_url") or json_get(data, "detail.url") or json_get(data, "detail.downloadable_url") or ""
                    gif_url = json_get(data, "detail.gif_url") or json_get(data, "detail.encodings.gif.path") or ""
                    thumbnail_url = data.get("thumbnail_url") or json_get(data, "detail.encodings.thumbnail.path") or ""
                    return status, video_url, gif_url, thumbnail_url, json.dumps(data, ensure_ascii=False)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    last_err = e
                    if attempt < 2:
                        print(f"[ComfyUI-XLJ-api] 信陵君 Sora 网络连接失败，{attempt + 1}/3，1 秒后重试...: {str(e)}")
                        time.sleep(1)
                    else:
                        raise RuntimeError(f"查询失败：网络连接问题 - {str(e)}，请检查网络或稍后重试")
                except Exception as e:
                    raise RuntimeError(f"查询失败：{str(e)}")
            raise RuntimeError(f"查询失败：{str(last_err)}")

        if not wait:
            return once()

        print(f"[ComfyUI-XLJ-api] 信陵君 Sora - 开始轮询任务 {task_id}，超时 {timeout_sec} 秒，间隔 {poll_interval_sec} 秒")
        deadline = time.time() + int(timeout_sec)
        last_raw = ""
        poll_count = 0
        while time.time() < deadline:
            poll_count += 1
            status, video_url, gif_url, thumbnail_url, raw = once()
            last_raw = raw
            print(f"[ComfyUI-XLJ-api] 信陵君 Sora - 第 {poll_count} 次查询：状态={status}")
            if status in ("completed", "failed"):
                print(f"[ComfyUI-XLJ-api] 信陵君 Sora - 任务完成：{status}")
                return (status, video_url, gif_url, thumbnail_url, raw)
            time.sleep(int(poll_interval_sec))

        print(f"[ComfyUI-XLJ-api] 信陵君 Sora - 轮询超时")
        return ("timeout", "", "", "", last_raw or json.dumps({"error": "timeout"}, ensure_ascii=False))


class XLJSoraCreateAndWait:
    """一键创建 Sora 视频并等待"""

    @classmethod
    def INPUT_TYPES(cls):
        inputs = XLJSoraCreateVideo.INPUT_TYPES()
        query_inputs = XLJSoraQueryTask.INPUT_TYPES()["optional"]
        inputs["optional"].update(query_inputs)
        inputs["optional"].pop("task_id", None)
        inputs["optional"].pop("wait", None)
        return inputs

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "GIF URL", "缩略图 URL", "任务 ID")
    FUNCTION = "run"
    CATEGORY = "XLJ/Sora2"

    def run(self, **kwargs):
        creator_kwargs = {k: v for k, v in kwargs.items() if k in XLJSoraCreateVideo.INPUT_TYPES()["required"] or k in XLJSoraCreateVideo.INPUT_TYPES()["optional"]}
        querier_kwargs = {k: v for k, v in kwargs.items() if k in XLJSoraQueryTask.INPUT_TYPES()["optional"]}

        creator = XLJSoraCreateVideo()
        task_id, _, _ = creator.create(**creator_kwargs)

        querier_kwargs["api_key"] = creator_kwargs.get("api_key", "")

        querier = XLJSoraQueryTask()
        status, video_url, gif_url, thumbnail_url, _ = querier.query(task_id=task_id, wait=True, **querier_kwargs)

        return (status, video_url, gif_url, thumbnail_url, task_id)


NODE_CLASS_MAPPINGS = {
    "XLJSoraCreateVideo": XLJSoraCreateVideo,
    "XLJSoraQueryTask": XLJSoraQueryTask,
    "XLJSoraCreateAndWait": XLJSoraCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSoraCreateVideo": "🎬 XLJ Sora2 创建视频",
    "XLJSoraQueryTask": "🔍 XLJ Sora2 查询任务",
    "XLJSoraCreateAndWait": "⚡ XLJ Sora2 一键生成",
}
