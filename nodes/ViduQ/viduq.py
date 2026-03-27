"""
ViduQ 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, ensure_list_from_urls, raise_for_bad_status, API_BASE


class XLJViduQCreateVideo:
    """创建 ViduQ 视频生成任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["viduq2", "viduq2-pro", "viduq2-turbo", "viduq3-pro"], {
                    "default": "viduq2",
                    "tooltip": "选择模型"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
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
                    "tooltip": "参考图片 1 URL（首帧）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（尾帧）"
                }),
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片 URL 批量输入（多个用逗号、分号或换行分隔）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 15,
                    "tooltip": "视频时长（秒）"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词（可选）"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（0 为随机）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_urls": "参考图片 URL 批量",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "seed": "随机种子",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "增强提示词")
    FUNCTION = "create"
    CATEGORY = "XLJ/ViduQ"

    def create(self, prompt, model, aspect_ratio, api_key="",
               image_1="", image_2="", image_urls="",
               duration=5, negative_prompt="", seed=0):
        """创建 ViduQ 视频生成任务"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        # 锁定 API 地址
        api_base = API_BASE
        headers = http_headers_json(api_key)

        # 收集所有图片 URL
        images = []
        if image_1 and image_1.strip():
            images.append(image_1.strip())
        if image_2 and image_2.strip():
            images.append(image_2.strip())
        if image_urls:
            batch_images = ensure_list_from_urls(image_urls)
            images.extend(batch_images)

        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }

        if images:
            payload["images"] = images

        if negative_prompt and negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt.strip()

        if seed > 0:
            payload["seed"] = seed

        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ 创建视频任务：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 模型：{model}, 时长：{duration}秒")
        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 参考图片数量：{len(images)}")

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
                raise RuntimeError(f"ViduQ 视频创建失败：{err_msg}")

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 原始响应：{response_text[:500]}")
                raise RuntimeError(f"ViduQ 视频创建失败：无法解析响应为 JSON - {str(e)}，响应内容：{response_text[:200]}")

            task_id = result.get("id", "")
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt", "")

            print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务已创建：{task_id}, 状态：{status}")

            return (task_id, status, enhanced_prompt)

        except Exception as e:
            raise RuntimeError(f"ViduQ 视频创建失败：{str(e)}")


class XLJViduQQueryVideo:
    """查询 ViduQ 视频生成任务状态"""

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
    CATEGORY = "XLJ/ViduQ"

    def query(self, task_id, api_key="", retry_count=3):
        """查询 ViduQ 视频生成任务状态"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        if not task_id:
            raise RuntimeError("任务 ID 不能为空")

        # 锁定 API 地址
        api_base = API_BASE
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 查询任务：{task_id}")

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
                    raise RuntimeError(f"ViduQ 视频查询失败：{err_msg}")

                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError as e:
                    print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 原始响应：{response_text[:500]}")
                    raise RuntimeError(f"ViduQ 视频查询失败：无法解析响应为 JSON - {str(e)}，响应内容：{response_text[:200]}")

                status = result.get("status", "unknown")
                video_url = result.get("video_url") or ""
                enhanced_prompt = result.get("enhanced_prompt", "")

                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务状态：{status}")
                if video_url:
                    print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 视频 URL: {video_url}")

                return (task_id, status, video_url, enhanced_prompt)

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < retry_count:
                    print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 网络连接失败，{attempt}/{retry_count}，1 秒后重试...: {str(e)}")
                    time.sleep(1)
                else:
                    raise RuntimeError(f"ViduQ 视频查询失败：网络连接问题 - {str(e)}，请检查网络或稍后重试")
            except Exception as e:
                raise RuntimeError(f"ViduQ 视频查询失败：{str(e)}")

        raise RuntimeError(f"ViduQ 视频查询失败：{str(last_error)}")


class XLJViduQCreateAndWait:
    """创建 ViduQ 视频并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["viduq2", "viduq2-pro", "viduq2-turbo", "viduq3-pro"], {
                    "default": "viduq2",
                    "tooltip": "选择模型"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
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
                    "tooltip": "参考图片 1 URL（首帧）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（尾帧）"
                }),
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片 URL 批量输入"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 15,
                    "tooltip": "视频时长（秒）"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词（可选）"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（0 为随机）"
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
            "api_key": "API 密钥",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_urls": "参考图片 URL 批量",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "seed": "随机种子",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/ViduQ"

    def create_and_wait(self, prompt, model, aspect_ratio, api_key="",
                       image_1="", image_2="", image_urls="",
                       duration=5, negative_prompt="", seed=0,
                       max_wait_time=600, poll_interval=10):
        """创建 ViduQ 视频并等待完成"""
        creator = XLJViduQCreateVideo()
        task_id, status, enhanced_prompt = creator.create(
            prompt, model, aspect_ratio, api_key,
            image_1, image_2, image_urls,
            duration, negative_prompt, seed
        )

        if status in ["completed", "failed"]:
            querier = XLJViduQQueryVideo()
            return querier.query(task_id, api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 等待视频生成完成，最多等待 {max_wait_time} 秒...")

        querier = XLJViduQQueryVideo()
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                task_id, status, video_url, enhanced_prompt = querier.query(task_id, api_key)

                if status == "completed":
                    print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 视频生成完成！")
                    return (task_id, status, video_url, enhanced_prompt)
                elif status == "failed":
                    raise RuntimeError(f"ViduQ 视频生成失败，任务 ID: {task_id}")

                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务进行中... 已等待 {elapsed}/{max_wait_time} 秒")

            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 查询出错：{str(e)}")

        raise RuntimeError(
            f"ViduQ 视频生成超时（等待了 {max_wait_time} 秒）。"
            f"任务 ID: {task_id}，可使用查询节点继续检查状态。"
        )


NODE_CLASS_MAPPINGS = {
    "XLJViduQCreateVideo": XLJViduQCreateVideo,
    "XLJViduQQueryVideo": XLJViduQQueryVideo,
    "XLJViduQCreateAndWait": XLJViduQCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJViduQCreateVideo": "🎬 XLJ ViduQ 创建视频",
    "XLJViduQQueryVideo": "🔍 XLJ ViduQ 查询任务",
    "XLJViduQCreateAndWait": "⚡ XLJ ViduQ 一键生成",
}
