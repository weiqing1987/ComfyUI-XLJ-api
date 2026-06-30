"""
Kling 视频生成节点 - 信陵君 AI
"""

import json
import time
import requests
from ..xlj_utils import env_or, http_headers_json, API_BASE

session = requests.Session()
session.trust_env = False

# 模型配置：显示名 → {API内部模型名, 端点路径格式, 时长上限}
MODEL_CONFIG = {
    "kling-3.0-turbo": {
        "model_key": "kling-3.0-turbo",
        "t2v_endpoint": "/kling/text-to-video/kling-3.0-turbo",
        "i2v_endpoint": "/kling/image-to-video/kling-3.0-turbo",
        "use_old_api": False,      # 新格式：模型名在URL路径中
        "max_duration": 10,
    },
    "kling-v2-5-turbo(最高10s)": {
        "model_key": "kling-v2-5-turbo",
        "t2v_endpoint": "/kling/v1/videos/text2video",
        "i2v_endpoint": "/kling/v1/videos/image2video",
        "use_old_api": True,       # 旧格式：model_name 参数
        "max_duration": 10,
    },
    "kling-v1": {
        "model_key": "kling-v1",
        "t2v_endpoint": "/kling/v1/videos/text2video",
        "i2v_endpoint": "/kling/v1/videos/image2video",
        "use_old_api": True,
        "max_duration": 10,
    },
    "kling-v1-6": {
        "model_key": "kling-v1-6",
        "t2v_endpoint": "",
        "i2v_endpoint": "/kling/v1/videos/multi-image2video",
        "use_old_api": True,
        "max_duration": 10,
    },
}


def _build_endpoint(api_base, model_display, mode_text):
    """根据模型和模式构建正确的端点和 payload"""
    # 多图参考使用独立端点和固定模型
    if mode_text == "多图参考":
        cfg = MODEL_CONFIG.get("kling-v1-6")
        endpoint = f"{api_base}{cfg['i2v_endpoint']}"
        return endpoint, cfg, False

    cfg = MODEL_CONFIG.get(model_display)
    if not cfg:
        raise RuntimeError(f"未知模型：{model_display}")

    is_image = mode_text in ("图生视频", "首尾帧")
    if is_image:
        if not cfg["i2v_endpoint"]:
            raise RuntimeError(f"{model_display} 不支持图生视频")
        endpoint = f"{api_base}{cfg['i2v_endpoint']}"
    else:
        endpoint = f"{api_base}{cfg['t2v_endpoint']}"

    return endpoint, cfg, is_image


def _build_payload(cfg, is_image, prompt, aspect_ratio, duration,
                   negative_prompt, cfg_scale, sound, mode_type,
                   image_1="", image_2="", mode_text="", image_list="",
                   resolution="720p"):
    """构建请求 payload"""
    # 多图参考：使用 image_list 参数
    if mode_text == "多图参考":
        urls = [url.strip() for url in image_list.split("\n") if url.strip()]
        if not urls:
            raise RuntimeError("多图参考模式需要提供 image_list（图片URL列表）")
        payload = {
            "model_name": "kling-v1-6",
            "prompt": prompt,
            "image_list": [{"image": url} for url in urls],
            "cfg_scale": cfg_scale,
            "mode": mode_type,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration),
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        return payload

    if cfg["use_old_api"]:
        # 旧格式：/kling/v1/videos/{action} + model_name 参数
        payload = {
            "model_name": cfg["model_key"],
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
            "mode": mode_type,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration),
            "sound": sound,
        }
        if is_image:
            payload["image"] = image_1.strip()
            if mode_text == "首尾帧":
                payload["image_tail"] = image_2.strip()
    else:
        # 新格式：/kling/{action}/{model}，模型在URL路径中
        # Kling 3.0 Turbo 使用 contents 数组格式
        contents = []
        if is_image:
            if image_1.strip():
                contents.append({
                    "type": "first_frame",
                    "url": image_1.strip()
                })
        contents.append({
            "type": "prompt",
            "text": prompt
        })
        payload = {
            "contents": contents,
            "settings": {
                "duration": duration,
            }
        }
        if resolution and not cfg.get("use_old_api", True):
            payload["settings"]["resolution"] = resolution
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if mode_text == "首尾帧" and image_2.strip():
            payload["image_tail"] = image_2.strip()
    return payload


def _parse_create_response(response_text):
    """解析创建响应，支持多字段获取 task_id"""
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Kling 响应解析失败：{str(e)}，内容：{response_text[:200]}")

    code = result.get("code", -1)
    if code != 0:
        err_msg = result.get("message", f"错误码 {code}")
        raise RuntimeError(f"Kling 创建失败：{err_msg}")

    data = result.get("data", {})
    if not data:
        # 兼容 response 直接包含 task_id 的格式
        task_id = result.get("task_id", result.get("id", ""))
        task_status = result.get("task_status", result.get("status", "submitted"))
    else:
        # 尝试多种字段名
        task_id = data.get("task_id") or data.get("id") or ""
        task_status = data.get("task_status") or data.get("status") or "submitted"
    return task_id, task_status


def _query_once(api_base, headers, task_id, video_type):
    """单次查询任务状态，自动跟随 301 跳转"""
    last_error = None
    for attempt in range(1, 4):
        try:
            query_endpoint = f"{api_base}/kling/v1/videos/{video_type}/{task_id}"
            resp = session.get(
                query_endpoint,
                headers=headers,
                timeout=30,
                allow_redirects=True,  # Kling 查询返回 301 需要跟随
            )

            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("message", str(err_data))
                except:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"Kling 查询失败：{err_msg}")

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Kling 查询响应解析失败：{str(e)}")

            code = result.get("code", -1)
            if code != 0:
                err_msg = result.get("message", f"错误码 {code}")
                raise RuntimeError(f"Kling 查询失败：{err_msg}")

            data = result.get("data", {})
            status = data.get("task_status", "unknown")

            # 提取视频 URL
            video_url = ""
            task_info = data.get("task_info", {})
            if isinstance(task_info, dict):
                video_url = task_info.get("video_url", "")
            if not video_url:
                video_url = data.get("video_url", "")
            if not video_url:
                videos = data.get("videos", [])
                if isinstance(videos, list) and len(videos) > 0:
                    video_url = videos[0].get("url", "")

            if status == "succeed":
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 完成响应：{json.dumps(result, ensure_ascii=False)[:500]}")

            return status, video_url

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = e
            if attempt < 3:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 网络重试 {attempt}/3：{str(e)}")
                time.sleep(1)
            else:
                raise RuntimeError(f"Kling 查询失败：网络连接问题 - {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Kling 查询失败：{str(e)}")

    raise RuntimeError(f"Kling 查询失败：{str(last_error)}")


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
                "model": (list(MODEL_CONFIG.keys()), {
                    "default": "kling-3.0-turbo",
                    "tooltip": "选择模型（kling-3.0-turbo 最强，v2-5-turbo 最高10秒）"
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
                "mode": (["文生视频", "图生视频", "首尾帧", "多图参考"], {
                    "default": "文生视频",
                    "tooltip": "文生视频无需图片，图生视频需1张参考图，首尾帧需2张参考图，多图参考需提供图片URL列表"
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
                "image_list": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "多图参考的图片 URL 列表（每行一个URL，仅多图参考模式使用）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 10,
                    "step": 5,
                    "tooltip": "视频时长（秒），v2-5-turbo 最高 10 秒"
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
                "resolution": (["720p", "1080p"], {
                    "default": "720p",
                    "tooltip": "视频分辨率（仅 kling-3.0-turbo 支持）"
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
            "model": "模型",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "mode": "模式",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_list": "多图 URL 列表",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG 比例",
            "resolution": "分辨率",
            "sound": "声音",
            "mode_type": "生成模式",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "任务类型")
    FUNCTION = "create"
    CATEGORY = "XLJ/Kling"

    def create(self, prompt, model, aspect_ratio, api_key="",
               mode="文生视频", image_1="", image_2="",
               duration=5, negative_prompt="", cfg_scale=0.5,
               sound="off", mode_type="std", image_list="", resolution="720p"):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        is_multi_image = mode == "多图参考"
        is_image = mode in ("图生视频", "首尾帧") or is_multi_image

        if is_multi_image:
            # 多图参考：不依赖具体模型选择，使用 image_list
            urls = [url.strip() for url in image_list.split("\n") if url.strip()]
            if not urls:
                raise RuntimeError("多图参考模式需要提供 image_list（图片URL列表）")
            endpoint, cfg, _ = _build_endpoint(api_base, model, mode)
        else:
            cfg = MODEL_CONFIG.get(model)
            if not cfg:
                raise RuntimeError(f"未知模型：{model}")

            if is_image:
                if not image_1 or not image_1.strip():
                    raise RuntimeError(f"{mode}需要提供 image_1（参考图）")
                if mode == "首尾帧" and (not image_2 or not image_2.strip()):
                    raise RuntimeError("首尾帧需要同时提供 image_1（首帧）和 image_2（尾帧）")

            endpoint, _, _ = _build_endpoint(api_base, model, mode)

        payload = _build_payload(cfg if not is_multi_image else MODEL_CONFIG["kling-v1-6"],
                                 is_image, prompt, aspect_ratio, duration,
                                 negative_prompt, cfg_scale, sound, mode_type,
                                 image_1, image_2, mode, image_list, resolution)

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - {mode} 创建任务")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 模型：{model}, 时长：{duration}秒")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 端点：{endpoint}")

        try:
            resp = session.post(endpoint, json=payload, headers=headers, timeout=30)
            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", err_data.get("message", str(err_data)))
                except:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"Kling 创建失败：{err_msg}")

            task_id, task_status = _parse_create_response(response_text)
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务已创建：{task_id}, 状态：{task_status}")

            if is_multi_image:
                video_type = "multi-image2video"
            elif is_image:
                video_type = "image2video"
            else:
                video_type = "text2video"
            return (task_id, task_status, video_type)

        except Exception as e:
            raise RuntimeError(f"Kling 创建失败：{str(e)}")


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
                "video_type": ("STRING", {
                    "default": "text2video",
                    "tooltip": "任务类型（与创建节点输出一致）：text2video / image2video / multi-image2video"
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
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")
        if not task_id:
            raise RuntimeError("任务 ID 不能为空")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 查询任务：{task_id}")

        if not wait:
            status, video_url = _query_once(api_base, headers, task_id, video_type)
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 状态：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")
            return (task_id, status, video_url, "")

        deadline = time.time() + int(timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            status, video_url = _query_once(api_base, headers, task_id, video_type)
            last_status = status

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 第 {poll_count} 次查询：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 视频 URL: {video_url}")

            if status == "succeed":
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 任务完成！")
                return (task_id, status, video_url or "", "")

            if status == "failed":
                raise RuntimeError(f"Kling 视频生成失败，任务 ID: {task_id}")

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 进行中... 已等待 {poll_count * poll_interval_sec}/{timeout_sec} 秒")
            time.sleep(int(poll_interval_sec))

        raise RuntimeError(
            f"Kling 视频生成超时（等待了 {timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}"
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
                "model": (list(MODEL_CONFIG.keys()), {
                    "default": "kling-3.0-turbo",
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
                "mode": (["文生视频", "图生视频", "首尾帧", "多图参考"], {
                    "default": "文生视频",
                    "tooltip": "文生视频无需图片，图生视频需1张参考图，首尾帧需2张参考图，多图参考需提供图片URL列表"
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
                "image_list": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "多图参考的图片 URL 列表（每行一个URL，仅多图参考模式使用）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 5,
                    "max": 10,
                    "step": 5,
                    "tooltip": "视频时长（秒），v2-5-turbo 最高 10 秒"
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
                "resolution": (["720p", "1080p"], {
                    "default": "720p",
                    "tooltip": "视频分辨率（仅 kling-3.0-turbo 支持）"
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
            "model": "模型",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "mode": "模式",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_list": "多图 URL 列表",
            "duration": "时长",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG 比例",
            "resolution": "分辨率",
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

    def create_and_wait(self, prompt, model, aspect_ratio, api_key="",
                        mode="文生视频", image_1="", image_2="",
                        duration=5, negative_prompt="", cfg_scale=0.5,
                        sound="off", mode_type="std",
                        wait_timeout_sec=1800, poll_interval_sec=10,
                        image_list="", resolution="720p"):
        creator = XLJKlingCreateVideo()
        task_id, status, video_type = creator.create(
            prompt, model, aspect_ratio, api_key,
            mode, image_1, image_2,
            duration, negative_prompt, cfg_scale,
            sound, mode_type, image_list, resolution
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 等待任务完成：{task_id}")

        querier = XLJKlingQueryVideo()
        task_id, status, video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            video_type=video_type,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling - 完成！状态：{status}")
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
