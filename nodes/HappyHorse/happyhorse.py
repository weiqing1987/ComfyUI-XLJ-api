import json
import time

import requests

from ..xlj_utils import (
    API_BASE,
    ensure_list_from_urls,
    env_or,
    http_headers_json,
    json_get,
    raise_for_bad_status,
)


session = requests.Session()
session.trust_env = False

CREATE_ENDPOINT = API_BASE.rstrip("/") + "/alibailian/api/v1/services/aigc/video-generation/video-synthesis"
QUERY_ENDPOINT = API_BASE.rstrip("/") + "/alibailian/api/v1/tasks/{task_id}"
SUCCESS_STATUSES = {"SUCCEEDED", "SUCCESS", "COMPLETED"}
FAIL_STATUSES = {"FAILED", "FAIL", "CANCELED", "CANCELLED"}


def _collect_url_list(*direct_values, batch_text=""):
    urls = []
    for value in direct_values:
        value = str(value or "").strip()
        if value and value not in urls:
            urls.append(value)
    for value in ensure_list_from_urls(batch_text):
        if value not in urls:
            urls.append(value)
    return urls


def _build_create_headers(api_key: str) -> dict:
    headers = http_headers_json(api_key)
    headers["X-DashScope-Async"] = "enable"
    return headers


def _extract_error_text(resp: requests.Response) -> str:
    try:
        data = resp.json()
        code = data.get("code") or data.get("error", {}).get("code") or ""
        message = data.get("message") or data.get("error", {}).get("message") or ""
        if code and message:
            return f"{code}: {message}"
        if message:
            return message
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        try:
            return resp.text
        except Exception:
            return ""


def _submit_task(payload: dict, api_key: str, timeout: int, hint: str):
    api_key = env_or(api_key, "XLJ_API_KEY")
    if not api_key:
        raise RuntimeError("API key is required")

    try:
        resp = session.post(
            CREATE_ENDPOINT,
            headers=_build_create_headers(api_key),
            json=payload,
            timeout=int(timeout),
        )
        if resp.status_code == 429:
            raise RuntimeError(f"{hint}: upstream busy (HTTP 429) - {_extract_error_text(resp)}")
        raise_for_bad_status(resp, hint)
        data = resp.json()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"{hint}: {str(exc)}")

    task_id = json_get(data, "output.task_id") or data.get("task_id") or data.get("id") or ""
    status = json_get(data, "output.task_status") or data.get("status") or ""
    request_id = data.get("request_id") or ""

    if not task_id:
        raise RuntimeError(f"{hint}: missing task_id in response: {json.dumps(data, ensure_ascii=False)}")

    return task_id, status, request_id


def _query_once(task_id: str, api_key: str):
    api_key = env_or(api_key, "XLJ_API_KEY")
    if not api_key:
        raise RuntimeError("API key is required")

    endpoint = QUERY_ENDPOINT.format(task_id=task_id)
    try:
        resp = session.get(endpoint, headers=http_headers_json(api_key), timeout=60)
        if resp.status_code == 429:
            raise RuntimeError(f"HappyHorse query failed: upstream busy (HTTP 429) - {_extract_error_text(resp)}")
        raise_for_bad_status(resp, "HappyHorse query failed")
        data = resp.json()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"HappyHorse query failed: {str(exc)}")

    status = json_get(data, "output.task_status") or data.get("status") or ""
    video_url = json_get(data, "output.video_url") or data.get("video_url") or ""
    orig_prompt = json_get(data, "output.orig_prompt") or data.get("orig_prompt") or ""
    actual_prompt = json_get(data, "output.actual_prompt") or data.get("actual_prompt") or ""
    return status, video_url, orig_prompt, actual_prompt, json.dumps(data, ensure_ascii=False)


class XLJHappyHorseTextToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Video prompt"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key"}),
            },
            "optional": {
                "resolution": (["1080P", "720P"], {"default": "1080P", "tooltip": "Output resolution"}),
                "ratio": (
                    ["16:9", "9:16", "1:1", "4:3", "3:4", "4:5", "5:4"],
                    {"default": "16:9", "tooltip": "Output aspect ratio"},
                ),
                "duration": ("INT", {"default": 5, "min": 3, "max": 15, "tooltip": "Duration in seconds"}),
                "watermark": ("BOOLEAN", {"default": True, "tooltip": "Add Happy Horse watermark"}),
                "timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "HTTP timeout"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("task_id", "status", "request_id")
    FUNCTION = "create"
    CATEGORY = "XLJ/HappyHorse"

    def create(self, prompt, api_key="", resolution="1080P", ratio="16:9", duration=5, watermark=True, timeout=120):
        payload = {
            "model": "happyhorse-1.0-t2v",
            "input": {"prompt": str(prompt or "").strip()},
            "parameters": {
                "resolution": resolution,
                "ratio": ratio,
                "duration": int(duration),
                "watermark": bool(watermark),
            },
        }
        return _submit_task(payload, api_key, timeout, "HappyHorse text-to-video failed")


class XLJHappyHorseImageToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "first_frame_url": ("STRING", {"default": "", "tooltip": "First frame image URL"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key"}),
            },
            "optional": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional guide prompt"}),
                "resolution": (["1080P", "720P"], {"default": "1080P", "tooltip": "Output resolution"}),
                "duration": ("INT", {"default": 5, "min": 3, "max": 15, "tooltip": "Duration in seconds"}),
                "watermark": ("BOOLEAN", {"default": True, "tooltip": "Add Happy Horse watermark"}),
                "timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "HTTP timeout"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("task_id", "status", "request_id")
    FUNCTION = "create"
    CATEGORY = "XLJ/HappyHorse"

    def create(self, first_frame_url, api_key="", prompt="", resolution="1080P", duration=5, watermark=True, timeout=120):
        first_frame_url = str(first_frame_url or "").strip()
        if not first_frame_url:
            raise RuntimeError("first_frame_url is required")

        input_obj = {
            "media": [{"type": "first_frame", "url": first_frame_url}],
        }
        prompt = str(prompt or "").strip()
        if prompt:
            input_obj["prompt"] = prompt

        payload = {
            "model": "happyhorse-1.0-i2v",
            "input": input_obj,
            "parameters": {
                "resolution": resolution,
                "duration": int(duration),
                "watermark": bool(watermark),
            },
        }
        return _submit_task(payload, api_key, timeout, "HappyHorse image-to-video failed")


class XLJHappyHorseReferenceToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        optional_reference_inputs = {
            "reference_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Reference image URLs, separated by comma or newline"}),
            "resolution": (["1080P", "720P"], {"default": "1080P", "tooltip": "Output resolution"}),
            "ratio": (
                ["16:9", "9:16", "1:1", "4:3", "3:4"],
                {"default": "16:9", "tooltip": "Output aspect ratio"},
            ),
            "duration": ("INT", {"default": 5, "min": 3, "max": 15, "tooltip": "Duration in seconds"}),
            "watermark": ("BOOLEAN", {"default": True, "tooltip": "Add Happy Horse watermark"}),
            "timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "HTTP timeout"}),
        }
        for index in range(1, 10):
            optional_reference_inputs[f"reference_image_{index}"] = (
                "STRING",
                {"default": "", "tooltip": f"Reference image {index} URL"},
            )

        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Prompt with [Image 1], [Image 2] references"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key"}),
            },
            "optional": optional_reference_inputs,
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("task_id", "status", "request_id")
    FUNCTION = "create"
    CATEGORY = "XLJ/HappyHorse"

    def create(
        self,
        prompt,
        api_key="",
        reference_urls="",
        resolution="1080P",
        ratio="16:9",
        duration=5,
        watermark=True,
        timeout=120,
        reference_image_1="",
        reference_image_2="",
        reference_image_3="",
        reference_image_4="",
        reference_image_5="",
        reference_image_6="",
        reference_image_7="",
        reference_image_8="",
        reference_image_9="",
    ):
        prompt = str(prompt or "").strip()
        if not prompt:
            raise RuntimeError("prompt is required")

        reference_list = _collect_url_list(
            reference_image_1,
            reference_image_2,
            reference_image_3,
            reference_image_4,
            reference_image_5,
            reference_image_6,
            reference_image_7,
            reference_image_8,
            reference_image_9,
            batch_text=reference_urls,
        )
        if not reference_list:
            raise RuntimeError("At least one reference image URL is required")
        if len(reference_list) > 9:
            raise RuntimeError("happyhorse-1.0-r2v supports at most 9 reference images")

        payload = {
            "model": "happyhorse-1.0-r2v",
            "input": {
                "prompt": prompt,
                "media": [{"type": "reference_image", "url": url} for url in reference_list],
            },
            "parameters": {
                "resolution": resolution,
                "ratio": ratio,
                "duration": int(duration),
                "watermark": bool(watermark),
            },
        }
        return _submit_task(payload, api_key, timeout, "HappyHorse reference-to-video failed")


class XLJHappyHorseVideoEdit:
    @classmethod
    def INPUT_TYPES(cls):
        optional_reference_inputs = {
            "reference_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional reference image URLs, separated by comma or newline"}),
            "resolution": (["1080P", "720P"], {"default": "1080P", "tooltip": "Output resolution"}),
            "watermark": ("BOOLEAN", {"default": True, "tooltip": "Add Happy Horse watermark"}),
            "audio_setting": (["auto", "origin"], {"default": "auto", "tooltip": "Keep origin audio or let model decide"}),
            "timeout": ("INT", {"default": 120, "min": 5, "max": 600, "tooltip": "HTTP timeout"}),
        }
        for index in range(1, 6):
            optional_reference_inputs[f"reference_image_{index}"] = (
                "STRING",
                {"default": "", "tooltip": f"Reference image {index} URL"},
            )

        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Edit instruction"}),
                "video_url": ("STRING", {"default": "", "tooltip": "Input video URL"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key"}),
            },
            "optional": optional_reference_inputs,
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("task_id", "status", "request_id")
    FUNCTION = "create"
    CATEGORY = "XLJ/HappyHorse"

    def create(
        self,
        prompt,
        video_url,
        api_key="",
        reference_urls="",
        resolution="1080P",
        watermark=True,
        audio_setting="auto",
        timeout=120,
        reference_image_1="",
        reference_image_2="",
        reference_image_3="",
        reference_image_4="",
        reference_image_5="",
    ):
        prompt = str(prompt or "").strip()
        video_url = str(video_url or "").strip()
        if not prompt:
            raise RuntimeError("prompt is required")
        if not video_url:
            raise RuntimeError("video_url is required")

        reference_list = _collect_url_list(
            reference_image_1,
            reference_image_2,
            reference_image_3,
            reference_image_4,
            reference_image_5,
            batch_text=reference_urls,
        )
        if len(reference_list) > 5:
            raise RuntimeError("happyhorse-1.0-video-edit supports at most 5 reference images")

        media_list = [{"type": "video", "url": video_url}]
        media_list.extend({"type": "reference_image", "url": url} for url in reference_list)

        parameters = {
            "resolution": resolution,
            "watermark": bool(watermark),
        }
        if audio_setting != "auto":
            parameters["audio_setting"] = audio_setting

        payload = {
            "model": "happyhorse-1.0-video-edit",
            "input": {
                "prompt": prompt,
                "media": media_list,
            },
            "parameters": parameters,
        }
        return _submit_task(payload, api_key, timeout, "HappyHorse video-edit failed")


class XLJHappyHorseQueryTask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "Task ID"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key"}),
            },
            "optional": {
                "wait": ("BOOLEAN", {"default": True, "tooltip": "Wait until task finishes"}),
                "poll_interval_sec": ("INT", {"default": 15, "min": 5, "max": 90, "tooltip": "Polling interval"}),
                "timeout_sec": ("INT", {"default": 1800, "min": 60, "max": 9600, "tooltip": "Total wait timeout"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("status", "video_url", "orig_prompt", "actual_prompt", "raw_json")
    FUNCTION = "query"
    CATEGORY = "XLJ/HappyHorse"
    OUTPUT_NODE = True

    def query(self, task_id, api_key="", wait=True, poll_interval_sec=15, timeout_sec=1800):
        task_id = str(task_id or "").strip()
        if not task_id:
            raise RuntimeError("task_id is required")

        if not wait:
            return _query_once(task_id, api_key)

        deadline = time.time() + int(timeout_sec)
        last_status = ""
        last_raw = ""
        while time.time() < deadline:
            status, video_url, orig_prompt, actual_prompt, raw_json = _query_once(task_id, api_key)
            last_status = status
            last_raw = raw_json

            normalized = str(status or "").strip().upper()
            if normalized in SUCCESS_STATUSES and video_url:
                return (status, video_url, orig_prompt, actual_prompt, raw_json)
            if normalized in FAIL_STATUSES:
                raise RuntimeError(f"HappyHorse task failed: {task_id}")

            time.sleep(int(poll_interval_sec))

        raise RuntimeError(
            f"HappyHorse query timed out after {timeout_sec}s; task_id={task_id}, last_status={last_status}, raw={last_raw}"
        )


NODE_CLASS_MAPPINGS = {
    "XLJHappyHorseTextToVideo": XLJHappyHorseTextToVideo,
    "XLJHappyHorseImageToVideo": XLJHappyHorseImageToVideo,
    "XLJHappyHorseReferenceToVideo": XLJHappyHorseReferenceToVideo,
    "XLJHappyHorseVideoEdit": XLJHappyHorseVideoEdit,
    "XLJHappyHorseQueryTask": XLJHappyHorseQueryTask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJHappyHorseTextToVideo": "XLJ HappyHorse 文生视频",
    "XLJHappyHorseImageToVideo": "XLJ HappyHorse 图生视频",
    "XLJHappyHorseReferenceToVideo": "XLJ HappyHorse 参考生视频",
    "XLJHappyHorseVideoEdit": "XLJ HappyHorse 视频编辑",
    "XLJHappyHorseQueryTask": "XLJ HappyHorse 查询任务",
}
