"""
Grok 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, ensure_list_from_urls, API_BASE


class XLJGrokCreateVideo:
    """创建 Grok 视频生成任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3", "grok-video-3-10s"], {
                    "default": "grok-video-3",
                    "tooltip": "选择模型：grok-video-3（标准版）或 grok-video-3-10s（10 秒版）"
                }),
                "aspect_ratio": (["9:16", "16:9", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "1080P",
                    "tooltip": "视频分辨率"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "image_1": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 1 URL（首帧/主要参考）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（尾帧）"
                }),
                "image_3": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 3 URL（元素参考）"
                }),
                "image_4": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 4 URL"
                }),
                "image_5": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 5 URL"
                }),
                "image_6": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 6 URL"
                }),
                "image_7": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 7 URL"
                }),
                "image_8": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 8 URL"
                }),
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片 URL 批量输入（多个用逗号、分号或换行分隔）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "api_key": "API 密钥",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "image_5": "参考图片 5",
            "image_6": "参考图片 6",
            "image_7": "参考图片 7",
            "image_8": "参考图片 8",
            "image_urls": "参考图片 URL 批量"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "增强提示词")
    FUNCTION = "create"
    CATEGORY = "XLJ/Grok"

    def create(self, prompt, model, aspect_ratio, size, api_key="",
               image_1="", image_2="", image_3="", image_4="",
               image_5="", image_6="", image_7="", image_8="",
               image_urls=""):
        """创建 Grok 视频生成任务"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        # 锁定 API 地址
        api_base = API_BASE
        headers = http_headers_json(api_key)

        # 收集所有图片 URL
        images = []
        for img in [image_1, image_2, image_3, image_4, image_5, image_6, image_7, image_8]:
            if img and img.strip():
                images.append(img.strip())
        if image_urls:
            batch_images = ensure_list_from_urls(image_urls)
            images.extend(batch_images)

        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "size": size,
            "images": images
        }

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 创建视频任务：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 API Base: {api_base}")
        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 参考图片数量：{len(images)}")

        try:
            resp = requests.post(
                f"{api_base}/v1/video/create",
                json=payload,
                headers=headers,
                timeout=30
            )

            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Grok 视频创建失败：{err_msg}")

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 原始响应：{response_text[:500]}")
                raise RuntimeError(f"Grok 视频创建失败：无法解析响应为 JSON - {str(e)}，响应内容：{response_text[:200]}")

            task_id = result.get("id", "")
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt", "")

            print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务已创建：{task_id}, 状态：{status}")

            return (task_id, status, enhanced_prompt)

        except Exception as e:
            raise RuntimeError(f"Grok 视频创建失败：{str(e)}")


class XLJGrokQueryVideo:
    """查询 Grok 视频生成任务状态"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {
                    "default": "",
                    "tooltip": "任务 ID"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务 ID",
            "api_key": "API 密钥"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "query"
    CATEGORY = "XLJ/Grok"

    def query(self, task_id, api_key="", retry_count=3):
        """查询 Grok 视频生成任务状态"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        if not task_id:
            raise RuntimeError("任务 ID 不能为空")

        # 锁定 API 地址
        api_base = API_BASE
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 查询任务：{task_id}")
        print(f"[ComfyUI-XLJ-api] 信陵君 API Base: {api_base}")

        last_error = None
        for attempt in range(1, retry_count + 1):
            try:
                resp = requests.get(
                    f"{api_base}/v1/video/query",
                    params={"id": task_id},
                    headers=headers,
                    timeout=30
                )

                response_text = resp.text

                if resp.status_code >= 400:
                    try:
                        err_data = json.loads(response_text)
                        err_msg = err_data.get("error", {}).get("message", str(err_data))
                    except:
                        err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                    raise RuntimeError(f"Grok 视频查询失败：{err_msg}")

                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError as e:
                    print(f"[ComfyUI-XLJ-api] 原始响应：{response_text[:500]}")
                    raise RuntimeError(f"Grok 视频查询失败：无法解析响应为 JSON - {str(e)}，响应内容：{response_text[:200]}")

                status = result.get("status", "unknown")
                video_url = result.get("video_url") or ""
                enhanced_prompt = result.get("enhanced_prompt", "")

                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务状态：{status}")
                if video_url:
                    print(f"[ComfyUI-XLJ-api] 信陵君 Grok 视频 URL: {video_url}")

                return (task_id, status, video_url, enhanced_prompt)

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < retry_count:
                    print(f"[ComfyUI-XLJ-api] Grok 查询网络连接失败，{attempt}/{retry_count}，1 秒后重试...: {str(e)}")
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Grok 视频查询失败：网络连接问题 - {str(e)}，请检查网络或稍后重试")
            except Exception as e:
                raise RuntimeError(f"Grok 视频查询失败：{str(e)}")

        raise RuntimeError(f"Grok 视频查询失败：{str(last_error)}")


class XLJGrokCreateAndWait:
    """创建 Grok 视频并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3", "grok-video-3-10s"], {
                    "default": "grok-video-3",
                    "tooltip": "选择模型：grok-video-3（标准版）或 grok-video-3-10s（10 秒版）"
                }),
                "aspect_ratio": (["9:16", "16:9", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "1080P",
                    "tooltip": "视频分辨率"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "image_1": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 1 URL（首帧/主要参考）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（尾帧）"
                }),
                "image_3": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 3 URL（元素参考）"
                }),
                "image_4": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 4 URL"
                }),
                "image_5": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 5 URL"
                }),
                "image_6": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 6 URL"
                }),
                "image_7": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 7 URL"
                }),
                "image_8": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 8 URL"
                }),
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片 URL 批量输入（多个用逗号、分号或换行分隔）"
                }),
                "max_wait_time": ("INT", {
                    "default": 600,
                    "min": 60,
                    "max": 1800,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 60,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "api_key": "API 密钥",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "image_5": "参考图片 5",
            "image_6": "参考图片 6",
            "image_7": "参考图片 7",
            "image_8": "参考图片 8",
            "image_urls": "参考图片 URL 批量",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/Grok"

    def create_and_wait(self, prompt, model, aspect_ratio, size, api_key="",
                       image_1="", image_2="", image_3="", image_4="",
                       image_5="", image_6="", image_7="", image_8="",
                       image_urls="",
                       max_wait_time=600, poll_interval=10):
        """创建 Grok 视频并等待完成"""
        creator = XLJGrokCreateVideo()
        task_id, status, enhanced_prompt = creator.create(
            prompt, model, aspect_ratio, size, api_key,
            image_1, image_2, image_3, image_4,
            image_5, image_6, image_7, image_8,
            image_urls
        )

        if status in ["completed", "failed"]:
            querier = XLJGrokQueryVideo()
            return querier.query(task_id, api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 等待视频生成完成，最多等待 {max_wait_time} 秒...")

        querier = XLJGrokQueryVideo()
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                task_id, status, video_url, enhanced_prompt = querier.query(task_id, api_key)

                if status == "completed":
                    print(f"[ComfyUI-XLJ-api] 信陵君 Grok 视频生成完成！")
                    return (task_id, status, video_url, enhanced_prompt)
                elif status == "failed":
                    raise RuntimeError(f"Grok 视频生成失败，任务 ID: {task_id}")

                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务进行中... 已等待 {elapsed}/{max_wait_time} 秒")

            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 查询出错：{str(e)}")

        raise RuntimeError(
            f"Grok 视频生成超时（等待了 {max_wait_time} 秒）。"
            f"任务 ID: {task_id}，可使用查询节点继续检查状态。"
        )


NODE_CLASS_MAPPINGS = {
    "XLJGrokCreateVideo": XLJGrokCreateVideo,
    "XLJGrokQueryVideo": XLJGrokQueryVideo,
    "XLJGrokCreateAndWait": XLJGrokCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGrokCreateVideo": "🎬 XLJ Grok 创建视频",
    "XLJGrokQueryVideo": "🔍 XLJ Grok 查询任务",
    "XLJGrokCreateAndWait": "⚡ XLJ Grok 一键生成",
}
