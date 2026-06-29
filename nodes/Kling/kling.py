"""
Kling 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, API_BASE

# 禁用代理
session = requests.Session()
session.trust_env = False


class XLJKlingCreateVideo:
    """创建 Kling 视频生成任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model_name": (["kling-v3", "kling-v1"], {
                    "default": "kling-v3",
                    "tooltip": "选择模型（kling-v3 最强推荐，kling-v1 兼容旧版）"
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
                "mode": (["文生视频", "图生视频", "首尾帧"], {
                    "default": "文生视频",
                    "tooltip": "文生视频无需图片，图生视频需1张参考图，首尾帧需2张参考图"
                }),
                "image_1": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 1 URL（图生视频的首帧 / 首尾帧的首帧）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（首尾帧的尾帧）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 10,
                    "step": 5,
                    "tooltip": "视频时长（秒），5 或 10"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词（可选）"
                }),
                "cfg_scale": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "tooltip": "CFG 引导比例 (0-1)"
                }),
                "sound": (["off", "on"], {
                    "default": "off",
                    "tooltip": "生成视频声音（仅部分模型支持）"
                }),
                "mode_type": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式：std 标准，pro 专业"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model_name": "模型",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "mode": "模式",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG 比例",
            "sound": "声音",
            "mode_type": "生成模式",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "任务类型")
    FUNCTION = "create"
    CATEGORY = "XLJ/Kling"

    def create(self, prompt, model_name, aspect_ratio, api_key="",
               mode="文生视频", image_1="", image_2="",
               duration=5, negative_prompt="", cfg_scale=0.5,
               sound="off", mode_type="std"):
        """创建 Kling 视频生成任务"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        # 根据 mode 选择端点和构建 payload
        is_image = mode in ("图生视频", "首尾帧")

        if is_image:
            if not image_1 or not image_1.strip():
                raise RuntimeError(f"{mode}模式需要提供 image_1（参考图）")
            if mode == "首尾帧" and (not image_2 or not image_2.strip()):
                raise RuntimeError("首尾帧模式需要同时提供 image_1（首帧）和 image_2（尾帧）")

            endpoint = f"{api_base}/kling/v1/videos/image2video"
            payload = {
                "model_name": model_name,
                "image": image_1.strip(),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "cfg_scale": cfg_scale,
                "mode": mode_type,
                "aspect_ratio": aspect_ratio,
                "duration": str(duration),
                "sound": sound,
            }
            if mode == "首尾帧":
                payload["image_tail"] = image_2.strip()

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - {mode}：图生视频端点")
        else:
            endpoint = f"{api_base}/kling/v1/videos/text2video"
            payload = {
                "model_name": model_name,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "cfg_scale": cfg_scale,
                "mode": mode_type,
                "aspect_ratio": aspect_ratio,
                "duration": str(duration),
                "sound": sound,
            }
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - {mode}：文生视频端点")

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling 创建视频任务：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 模型：{model_name}, 时长：{duration}秒")

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
                    err_msg = err_data.get("message", str(err_data))
                except:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Kling 视频创建失败：{err_msg}")

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 原始响应：{response_text[:500]}")
                raise RuntimeError(f"Kling 视频创建失败：无法解析响应为 JSON - {str(e)}")

            # 解析 Kling 响应：{code, message, request_id, data: {task_id, task_status}}
            code = result.get("code", -1)
            if code != 0:
                err_msg = result.get("message", f"错误码 {code}")
                raise RuntimeError(f"Kling 视频创建失败：{err_msg}")

            data = result.get("data", {})
            task_id = data.get("task_id", "")
            task_status = data.get("task_status", "submitted")

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务已创建：{task_id}, 状态：{task_status}")

            # 记录任务类型，供查询节点使用
            video_type = "image2video" if is_image else "text2video"

            return (task_id, task_status, video_type)

        except Exception as e:
            raise RuntimeError(f"Kling 视频创建失败：{str(e)}")


class XLJKlingQueryVideo:
    """查询 Kling 视频生成任务状态"""

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
                "video_type": (["text2video", "image2video"], {
                    "default": "text2video",
                    "tooltip": "任务类型（与创建节点输出类型一致）"
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
            "video_type": "任务类型",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "总超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "query"
    CATEGORY = "XLJ/Kling"
    OUTPUT_NODE = True

    def query(self, task_id, api_key="", video_type="text2video",
              wait=True, poll_interval_sec=10, timeout_sec=1800):
        """查询 Kling 视频生成任务状态"""
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        if not task_id:
            raise RuntimeError("任务 ID 不能为空")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 查询任务：{task_id}, 类型：{video_type}")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 轮询间隔：{poll_interval_sec}秒，超时：{timeout_sec}秒")

        def once():
            """单次查询"""
            last_error = None
            for attempt in range(1, 4):
                try:
                    # Kling 查询端点不同：text2video vs image2video
                    query_endpoint = f"{api_base}/kling/v1/videos/{video_type}/{task_id}"
                    resp = session.get(
                        query_endpoint,
                        headers=headers,
                        timeout=30
                    )

                    response_text = resp.text

                    if resp.status_code >= 400:
                        try:
                            err_data = json.loads(response_text)
                            err_msg = err_data.get("message", str(err_data))
                        except:
                            err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                        raise RuntimeError(f"Kling 视频查询失败：{err_msg}")

                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 原始响应：{response_text[:500]}")
                        raise RuntimeError(f"Kling 视频查询失败：无法解析响应为 JSON - {str(e)}")

                    # Kling 响应格式：{code, message, data: {task_id, task_status, task_info: {video_url}}}
                    code = result.get("code", -1)
                    if code != 0 and code != 20000:
                        err_msg = result.get("message", f"错误码 {code}")
                        # task 不存在也算失败
                        if code == 10002:
                            raise RuntimeError(f"Kling 任务不存在：{task_id}")
                        raise RuntimeError(f"Kling 视频查询失败：{err_msg}")

                    data = result.get("data", result)  # some endpoints return data directly
                    status = data.get("task_status", "unknown")
                    task_info = data.get("task_info", {})

                    # 提取视频 URL（可能在 task_info 或直接在 data）
                    video_url = task_info.get("video_url", "")
                    if not video_url:
                        video_url = data.get("video_url", "")
                    if not video_url:
                        # 也可能在 videos/results 等字段
                        videos = data.get("videos", [])
                        if videos and isinstance(videos, list) and len(videos) > 0:
                            video_url = videos[0].get("url", "")
                    if not video_url:
                        video_url = ""

                    enhanced_prompt = ""

                    if status == "succeed":
                        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务完成响应：{json.dumps(result, ensure_ascii=False)[:500]}")

                    return status, video_url, enhanced_prompt

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    last_error = e
                    if attempt < 3:
                        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 网络连接失败，{attempt}/3，1 秒后重试...: {str(e)}")
                        time.sleep(1)
                    else:
                        raise RuntimeError(f"Kling 视频查询失败：网络连接问题 - {str(e)}")
                except Exception as e:
                    raise RuntimeError(f"Kling 视频查询失败：{str(e)}")
            raise RuntimeError(f"Kling 视频查询失败：{str(last_error)}")

        # 不等待模式：只查询一次
        if not wait:
            status, video_url, enhanced_prompt = once()
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务状态：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")
            return (task_id, status, video_url, enhanced_prompt)

        # 轮询模式：等待任务完成
        deadline = time.time() + int(timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            status, video_url, enhanced_prompt = once()
            last_status = status

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 第 {poll_count} 次查询：状态={status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")

            # 任务完成
            if status == "succeed":
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务完成！")
                if video_url:
                    print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")
                return (task_id, status, video_url or "", enhanced_prompt)

            # 任务失败
            if status == "failed":
                raise RuntimeError(f"Kling 视频生成失败，任务 ID: {task_id}")

            # 继续轮询
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务进行中... 已等待 {poll_count * poll_interval_sec}/{timeout_sec} 秒")
            time.sleep(int(poll_interval_sec))

        # 超时
        raise RuntimeError(
            f"Kling 视频生成超时（等待了 {timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}，可使用查询节点继续检查状态。"
        )


class XLJKlingCreateAndWait:
    """创建 Kling 视频并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model_name": (["kling-v3", "kling-v1"], {
                    "default": "kling-v3",
                    "tooltip": "选择模型（kling-v3 最强推荐，kling-v1 兼容旧版）"
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
                "mode": (["文生视频", "图生视频", "首尾帧"], {
                    "default": "文生视频",
                    "tooltip": "文生视频无需图片，图生视频需1张参考图，首尾帧需2张参考图"
                }),
                "image_1": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 1 URL"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "参考图片 2 URL（首尾帧的尾帧）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 10,
                    "step": 5,
                    "tooltip": "视频时长（秒），5 或 10"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词（可选）"
                }),
                "cfg_scale": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "tooltip": "CFG 引导比例 (0-1)"
                }),
                "sound": (["off", "on"], {
                    "default": "off",
                    "tooltip": "生成视频声音"
                }),
                "mode_type": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式：std 标准，pro 专业"
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
            "model_name": "模型",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "mode": "模式",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG 比例",
            "sound": "声音",
            "mode_type": "生成模式",
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "增强提示词", "任务 ID")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/Kling"
    OUTPUT_NODE = True

    def create_and_wait(self, prompt, model_name, aspect_ratio, api_key="",
                        mode="文生视频", image_1="", image_2="",
                        duration=5, negative_prompt="", cfg_scale=0.5,
                        sound="off", mode_type="std",
                        wait_timeout_sec=1800, poll_interval_sec=10):
        """创建 Kling 视频并等待完成"""
        creator = XLJKlingCreateVideo()
        task_id, status, video_type = creator.create(
            prompt, model_name, aspect_ratio, api_key,
            mode, image_1, image_2,
            duration, negative_prompt, cfg_scale,
            sound, mode_type
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务已创建：{task_id}，开始等待完成...")

        querier = XLJKlingQueryVideo()
        task_id, status, video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            video_type=video_type,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务完成！状态：{status}")
        if video_url:
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")

        return (status, video_url, enhanced_prompt, task_id)


NODE_CLASS_MAPPINGS = {
    "XLJKlingCreateVideo": XLJKlingCreateVideo,
    "XLJKlingQueryVideo": XLJKlingQueryVideo,
    "XLJKlingCreateAndWait": XLJKlingCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJKlingCreateVideo": "🎬 XLJ Kling 创建视频",
    "XLJKlingQueryVideo": "🔍 XLJ Kling 查询任务",
    "XLJKlingCreateAndWait": "⚡ XLJ Kling 一键生成",
}
