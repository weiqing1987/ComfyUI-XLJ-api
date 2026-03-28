"""
ViduQ 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, ensure_list_from_urls, raise_for_bad_status, API_BASE

# 禁用代理
session = requests.Session()
session.trust_env = False


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
            resp = session.post(
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
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://xinlingjunai.cn",
                    "tooltip": "API 地址（已锁定，修改无效）"
                }),
                "wait": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否等待任务完成"
                }),
                "poll_interval_sec": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 60,
                    "tooltip": "轮询间隔 (秒)"
                }),
                "timeout_sec": ("INT", {
                    "default": 1800,
                    "min": 60,
                    "max": 7200,
                    "tooltip": "总超时时间 (秒)"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务 ID",
            "api_key": "API 密钥",
            "api_base": "API 地址",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "总超时"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "query"
    CATEGORY = "XLJ/ViduQ"
    OUTPUT_NODE = True

    def query(self, task_id, api_key="", api_base="", wait=True, poll_interval_sec=10, timeout_sec=1800):
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
        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 轮询间隔：{poll_interval_sec}秒，超时：{timeout_sec}秒")

        def once():
            """单次查询"""
            last_error = None
            for attempt in range(1, 4):
                try:
                    resp = session.get(
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
                        raise RuntimeError(f"ViduQ 视频查询失败：无法解析响应为 JSON - {str(e)}")

                    status = result.get("status", "unknown")
                    video_url = result.get("video_url") or ""
                    enhanced_prompt = result.get("enhanced_prompt", "")

                    return status, video_url, enhanced_prompt

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    last_error = e
                    if attempt < 3:
                        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 网络连接失败，{attempt}/3，1 秒后重试...: {str(e)}")
                        time.sleep(1)
                    else:
                        raise RuntimeError(f"ViduQ 视频查询失败：网络连接问题 - {str(e)}")
                except Exception as e:
                    raise RuntimeError(f"ViduQ 视频查询失败：{str(e)}")
            raise RuntimeError(f"ViduQ 视频查询失败：{str(last_error)}")

        # 不等待模式：只查询一次
        if not wait:
            status, video_url, enhanced_prompt = once()
            print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务状态：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 视频 URL: {video_url}")
            return (task_id, status, video_url, enhanced_prompt)

        # 轮询模式：等待任务完成
        deadline = time.time() + int(timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            status, video_url, enhanced_prompt = once()
            last_status = status

            print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 第 {poll_count} 次查询：状态={status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 视频 URL: {video_url}")

            # 任务完成且有 URL，返回结果
            if status == "completed" and video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务完成！")
                return (task_id, status, video_url, enhanced_prompt)

            # 任务失败
            if status == "failed":
                raise RuntimeError(f"ViduQ 视频生成失败，任务 ID: {task_id}")

            # 继续轮询
            print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务进行中... 已等待 {poll_count * poll_interval_sec}/{timeout_sec} 秒")
            time.sleep(int(poll_interval_sec))

        # 超时
        raise RuntimeError(
            f"ViduQ 视频生成超时（等待了 {timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}，可使用查询节点继续检查状态。"
        )


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
                "wait_timeout_sec": ("INT", {
                    "default": 1800,
                    "min": 60,
                    "max": 7200,
                    "tooltip": "等待超时时间（秒）"
                }),
                "poll_interval_sec": ("INT", {
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
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "增强提示词", "任务 ID")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/ViduQ"
    OUTPUT_NODE = True

    def create_and_wait(self, prompt, model, aspect_ratio, api_key="",
                       image_1="", image_2="", image_urls="",
                       duration=5, negative_prompt="", seed=0,
                       wait_timeout_sec=1800, poll_interval_sec=10):
        """创建 ViduQ 视频并等待完成"""
        creator = XLJViduQCreateVideo()
        task_id, status, enhanced_prompt = creator.create(
            prompt, model, aspect_ratio, api_key,
            image_1, image_2, image_urls,
            duration, negative_prompt, seed
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务已创建：{task_id}，开始等待完成...")

        # 调用查询节点，wait=True 会一直等待直到任务完成
        querier = XLJViduQQueryVideo()
        task_id, status, video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 任务完成！状态：{status}")
        if video_url:
            print(f"[ComfyUI-XLJ-api] 信陵君 ViduQ - 视频 URL: {video_url}")

        return (status, video_url, enhanced_prompt, task_id)


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
