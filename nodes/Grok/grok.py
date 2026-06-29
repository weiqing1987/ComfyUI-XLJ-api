"""
Grok 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, ensure_list_from_urls, API_BASE

# 禁用代理
session = requests.Session()
session.trust_env = False


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
                "model": (["grok-imagine-video", "grok-imagine-video-1.5-preview"], {
                    "default": "grok-imagine-video",
                    "tooltip": "选择模型：grok-imagine-video（标准版）或 grok-imagine-video-1.5-preview（预览版）"
                }),
                "aspect_ratio": (["9:16", "16:9", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "resolution": (["360p", "540p", "720p", "1080p"], {
                    "default": "1080p",
                    "tooltip": "视频分辨率"
                }),
                "duration": (["5", "8"], {
                    "default": "5",
                    "tooltip": "视频时长（秒），grok-imagine-video 固定为 5 秒"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://xinlingjunai.cn",
                    "multiline": False,
                    "tooltip": "API 地址（已锁定，修改无效）"
                }),
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
                "motion_mode": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "运动模式（可选，如 normal/fast/slow）"
                }),
                "style": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "视频风格（可选，如 cinematic/anime/realistic）"
                }),
                "sound_effect_switch": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否启用音效"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（0 表示随机）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "duration": "时长",
            "api_key": "API 密钥",
            "api_base": "API 地址",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "image_5": "参考图片 5",
            "image_6": "参考图片 6",
            "image_7": "参考图片 7",
            "image_8": "参考图片 8",
            "image_urls": "参考图片 URL 批量",
            "motion_mode": "运动模式",
            "style": "风格",
            "sound_effect_switch": "音效",
            "seed": "种子",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "增强提示词")
    FUNCTION = "create"
    CATEGORY = "XLJ/Grok"

    def create(self, prompt, model, aspect_ratio, resolution, duration="5", api_key="", api_base="",
               image_1="", image_2="", image_3="", image_4="",
               image_5="", image_6="", image_7="", image_8="",
               image_urls="", motion_mode="", style="", sound_effect_switch=False, seed=0):
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

        # 统一使用 /v1/videos/generations
        endpoint = f"{api_base}/v1/videos/generations"

        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration": int(duration),
        }

        # grok-imagine-video-1.5-preview 强制图生视频，image 参数需为 xaiMediaRef 对象
        # grok-imagine-video 可选图生视频，reference_images 为对象数组
        if model == "grok-imagine-video-1.5-preview":
            if not images:
                raise RuntimeError("grok-imagine-video-1.5-preview 模型必须提供参考图片")
            payload["image"] = {"url": images[0]}
        else:
            if images:
                payload["reference_images"] = [{"url": img} for img in images]

        # 可选参数
        if motion_mode:
            payload["motionMode"] = motion_mode
        if style:
            payload["style"] = style
        if sound_effect_switch:
            payload["soundEffectSwitch"] = True
        if seed > 0:
            payload["seed"] = seed

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 创建视频：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 API Base: {api_base}")
        print(f"[ComfyUI-XLJ-api] 信陵君 模型：{model}, 分辨率：{resolution}, 时长：{duration}s")
        if images:
            print(f"[ComfyUI-XLJ-api] 信陵君 参考图片数量：{len(images)}")
        print(f"[ComfyUI-XLJ-api] 信陵君 端点：/v1/videos/generations")

        try:
            resp = session.post(
                endpoint,
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

            # 新 API 返回 request_id（兼容旧格式的 id）
            task_id = result.get("request_id") or result.get("id") or ""
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt", "")

            if not task_id:
                raise RuntimeError(f"创建响应缺少任务 ID: {json.dumps(result, ensure_ascii=False)}")

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
            "timeout_sec": "总超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "query"
    CATEGORY = "XLJ/Grok"
    OUTPUT_NODE = True

    def query(self, task_id, api_key="", api_base="", wait=True, poll_interval_sec=10, timeout_sec=1800):
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
        print(f"[ComfyUI-XLJ-api] 信陵君 轮询间隔：{poll_interval_sec}秒，超时：{timeout_sec}秒")

        def once():
            """单次查询"""
            last_error = None
            for attempt in range(1, 4):
                try:
                    resp = session.get(
                        f"{api_base}/v1/videos/{task_id}",
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
                        raise RuntimeError(f"Grok 视频查询失败：无法解析响应为 JSON - {str(e)}")

                    # 新 API 响应格式
                    raw_status = result.get("status", "")
                    # 状态映射：done -> completed
                    if raw_status == "done":
                        status = "completed"
                    elif raw_status in ("pending", "in_progress", "running"):
                        status = raw_status
                    elif raw_status:
                        status = raw_status
                    else:
                        # 只有 request_id，任务尚未注册到查询系统
                        status = "pending"

                    video_obj = result.get("video", {})
                    video_url = ""
                    if isinstance(video_obj, dict):
                        video_url = video_obj.get("url", "")
                    elif isinstance(video_obj, str):
                        video_url = video_obj

                    enhanced_prompt = result.get("enhanced_prompt", "")

                    return status, video_url, enhanced_prompt

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    last_error = e
                    if attempt < 3:
                        print(f"[ComfyUI-XLJ-api] Grok 查询网络连接失败，{attempt}/3，1 秒后重试...: {str(e)}")
                        time.sleep(1)
                    else:
                        raise RuntimeError(f"Grok 视频查询失败：网络连接问题 - {str(e)}")
                except Exception as e:
                    raise RuntimeError(f"Grok 视频查询失败：{str(e)}")
            raise RuntimeError(f"Grok 视频查询失败：{str(last_error)}")

        # 不等待模式：只查询一次
        if not wait:
            status, video_url, enhanced_prompt = once()
            print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务状态：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 视频 URL: {video_url}")
            return (task_id, status, video_url, enhanced_prompt)

        # 轮询模式：等待任务完成
        deadline = time.time() + int(timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            status, video_url, enhanced_prompt = once()
            last_status = status

            print(f"[ComfyUI-XLJ-api] 信陵君 Grok 第 {poll_count} 次查询：状态={status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 视频 URL: {video_url}")

            # 任务完成且有 URL，返回结果
            if status == "completed" and video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务完成！")
                return (task_id, status, video_url, enhanced_prompt)

            # 任务失败
            if status == "failed":
                raise RuntimeError(f"Grok 视频生成失败，任务 ID: {task_id}")

            # 继续轮询
            print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务进行中... 已等待 {poll_count * poll_interval_sec}/{timeout_sec} 秒")
            time.sleep(int(poll_interval_sec))

        # 超时
        raise RuntimeError(
            f"Grok 视频生成超时（等待了 {timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}，可使用查询节点继续检查状态。"
        )


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
                "model": (["grok-imagine-video", "grok-imagine-video-1.5-preview"], {
                    "default": "grok-imagine-video",
                    "tooltip": "选择模型：grok-imagine-video（标准版）或 grok-imagine-video-1.5-preview（预览版）"
                }),
                "aspect_ratio": (["9:16", "16:9", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "resolution": (["360p", "540p", "720p", "1080p"], {
                    "default": "1080p",
                    "tooltip": "视频分辨率"
                }),
                "duration": (["5", "8"], {
                    "default": "5",
                    "tooltip": "视频时长（秒），grok-imagine-video 固定为 5 秒"
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
                "motion_mode": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "运动模式（可选，如 normal/fast/slow）"
                }),
                "style": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "视频风格（可选，如 cinematic/anime/realistic）"
                }),
                "sound_effect_switch": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否启用音效"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（0 表示随机）"
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
            "resolution": "分辨率",
            "duration": "时长",
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
            "motion_mode": "运动模式",
            "style": "风格",
            "sound_effect_switch": "音效",
            "seed": "种子",
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "增强提示词", "任务 ID")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/Grok"
    OUTPUT_NODE = True

    def create_and_wait(self, prompt, model, aspect_ratio, resolution, duration="5", api_key="",
                        image_1="", image_2="", image_3="", image_4="",
                        image_5="", image_6="", image_7="", image_8="",
                        image_urls="", motion_mode="", style="", sound_effect_switch=False, seed=0,
                        wait_timeout_sec=1800, poll_interval_sec=10):
        """创建 Grok 视频并等待完成"""
        creator = XLJGrokCreateVideo()
        task_id, status, enhanced_prompt = creator.create(
            prompt=prompt, model=model, aspect_ratio=aspect_ratio,
            resolution=resolution, duration=duration, api_key=api_key,
            image_1=image_1, image_2=image_2, image_3=image_3, image_4=image_4,
            image_5=image_5, image_6=image_6, image_7=image_7, image_8=image_8,
            image_urls=image_urls,
            motion_mode=motion_mode, style=style,
            sound_effect_switch=sound_effect_switch, seed=seed
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务已创建：{task_id}，开始等待完成...")

        # 调用查询节点，wait=True 会一直等待直到任务完成
        querier = XLJGrokQueryVideo()
        task_id, status, video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok 任务完成！状态：{status}")
        if video_url:
            print(f"[ComfyUI-XLJ-api] 信陵君 Grok 视频 URL: {video_url}")

        return (status, video_url, enhanced_prompt, task_id)


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
