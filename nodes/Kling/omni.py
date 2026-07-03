"""
Kling Omni 视频生成节点 - 信陵君 AI
V2V（视频到视频）：视频编辑 + 视频参考
"""

import json
import time
from pathlib import Path
from ..xlj_utils import env_or, http_headers_json, API_BASE

from .kling import _parse_create_response, _query_once, session

try:
    import folder_paths
except ImportError:
    folder_paths = None

MODEL_LIST = ["kling-omni-video", "kling-video-o1", "kling-v3-omni"]

OMNI_ENDPOINT = "/kling/v1/videos/omni-video"


def _is_base_mode(refer_type):
    """base 编辑模式：输出时长=输入视频时长，不支持多镜头"""
    return refer_type == "base"


def _validate_omni_duration(refer_type, duration):
    """校验时长：base 模式忽略时长，feature 模式 3~10s"""
    if _is_base_mode(refer_type):
        return duration  # API 忽略此值
    if duration < 3 or duration > 15:
        raise RuntimeError(f"Omni feature 模式时长仅支持 3~15 秒，当前值：{duration}")
    return duration


def _build_omni_payload(model, prompt, video_url, refer_type, keep_original_sound,
                        image_1, image_2, image_3, image_4,
                        element_ids, aspect_ratio, duration, mode_type):
    """构建 Omni 请求 payload"""
    payload = {
        "model_name": model,
        "prompt": prompt,
        "mode": mode_type,
    }

    # video_list
    if video_url and video_url.strip():
        vl = {
            "video_url": video_url.strip(),
            "refer_type": refer_type,
        }
        if keep_original_sound == "yes":
            vl["keep_original_sound"] = "yes"
        payload["video_list"] = [vl]

    # image_list
    imgs = [img.strip() for img in [image_1, image_2, image_3, image_4] if img and img.strip()]
    if imgs:
        payload["image_list"] = [{"image_url": url} for url in imgs]

    # element_list
    if element_ids and element_ids.strip():
        ids = []
        for line in element_ids.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    ids.append({"element_id": int(line)})
                except ValueError:
                    print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 跳过无效 element_id: {line}")
        if ids:
            payload["element_list"] = ids

    if not _is_base_mode(refer_type):
        payload["aspect_ratio"] = aspect_ratio
        payload["duration"] = str(duration)

    return payload


class XLJKlingCreateOmniVideo:
    """创建 Kling Omni 视频生成任务（V2V）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频描述，使用 <<<video_1>>> / <<<image_1>>> / <<<element_1>>> 引用元素"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "model": (MODEL_LIST, {
                    "default": "kling-omni-video",
                    "tooltip": "Omni 模型"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "参考视频 URL（必填）"
                }),
                "refer_type": (["base", "feature"], {
                    "default": "base",
                    "tooltip": "base=视频编辑（修改原视频），feature=视频参考（生成新镜头）"
                }),
                "keep_original_sound": (["no", "yes"], {
                    "default": "no",
                    "tooltip": "是否保留原视频声音"
                }),
                "image_1": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 1 URL（可选，用于 prompt 中引用）"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 2 URL"
                }),
                "image_3": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 3 URL"
                }),
                "image_4": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 4 URL"
                }),
                "element_ids": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "主体库 ID 列表（每行一个数字 ID）"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "宽高比（仅 feature 模式生效）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 3,
                    "max": 15,
                    "step": 1,
                    "tooltip": "视频时长（秒，仅 feature 模式生效）"
                }),
                "mode_type": (["std", "pro"], {
                    "default": "pro",
                    "tooltip": "生成模式：std 标准，pro 专业"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "api_key": "API 密钥",
            "model": "模型",
            "video_url": "参考视频 URL",
            "refer_type": "参考类型",
            "keep_original_sound": "保留原声",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "element_ids": "主体 ID 列表",
            "aspect_ratio": "宽高比",
            "duration": "时长",
            "mode_type": "生成模式",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "任务类型")
    FUNCTION = "create"
    CATEGORY = "XLJ/Kling"

    def create(self, prompt, api_key="",
               model="kling-omni-video",
               video_url="", refer_type="base", keep_original_sound="no",
               image_1="", image_2="", image_3="", image_4="",
               element_ids="", aspect_ratio="16:9", duration=5, mode_type="pro"):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")
        if not video_url or not video_url.strip():
            raise RuntimeError("参考视频 URL（video_url）为必填项")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        refer_type = refer_type.strip().lower()
        duration = _validate_omni_duration(refer_type, duration)

        endpoint = f"{api_base}{OMNI_ENDPOINT}"
        payload = _build_omni_payload(model, prompt, video_url, refer_type, keep_original_sound,
                                      image_1, image_2, image_3, image_4,
                                      element_ids, aspect_ratio, duration, mode_type)

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - V2V 创建任务")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 模型：{model}, 参考类型：{refer_type}")
        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 端点：{endpoint}")

        try:
            resp = session.post(endpoint, json=payload, headers=headers, timeout=60)
            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", err_data.get("message", str(err_data)))
                except:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"Kling Omni 创建失败：{err_msg}")

            task_id, task_status = _parse_create_response(response_text)
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 任务已创建：{task_id}, 状态：{task_status}")

            return (task_id, task_status, "omni-video")

        except Exception as e:
            raise RuntimeError(f"Kling Omni 创建失败：{str(e)}")


class XLJKlingQueryOmniVideo:
    """查询 Kling Omni 视频任务状态"""

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
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "总超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态", "视频 URL", "增强提示词")
    FUNCTION = "query"
    CATEGORY = "XLJ/Kling"
    OUTPUT_NODE = True

    def query(self, task_id, api_key="",
              wait=True, poll_interval_sec=10, timeout_sec=1800):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")
        if not task_id:
            raise RuntimeError("任务 ID 不能为空")

        api_base = API_BASE
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 查询任务：{task_id}")

        if not wait:
            status, video_url = _query_once(api_base, headers, task_id, "omni-video")
            print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 状态：{status}")
            return (task_id, status, video_url, "")

        deadline = time.time() + int(timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            status, video_url = _query_once(api_base, headers, task_id, "omni-video")
            last_status = status

            print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 第 {poll_count} 次查询：{status}")
            if video_url:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 视频 URL: {video_url}")

            if status == "succeed":
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 任务完成！")
                return (task_id, status, video_url or "", "")

            if status == "failed":
                raise RuntimeError(f"Kling Omni 视频生成失败，任务 ID: {task_id}")

            time.sleep(int(poll_interval_sec))

        raise RuntimeError(
            f"Kling Omni 视频生成超时（等待了 {timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}"
        )


class XLJKlingCreateOmniAndWait:
    """创建 Kling Omni 视频并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频描述，使用 <<<video_1>>> / <<<image_1>>> / <<<element_1>>> 引用元素"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "model": (MODEL_LIST, {
                    "default": "kling-omni-video",
                    "tooltip": "Omni 模型"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "参考视频 URL（必填）"
                }),
                "refer_type": (["base", "feature"], {
                    "default": "base",
                    "tooltip": "base=视频编辑，feature=视频参考"
                }),
                "keep_original_sound": (["no", "yes"], {
                    "default": "no",
                    "tooltip": "是否保留原视频声音"
                }),
                "image_1": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 1 URL"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 2 URL"
                }),
                "image_3": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 3 URL"
                }),
                "image_4": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 4 URL"
                }),
                "element_ids": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "主体库 ID 列表（每行一个数字 ID）"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "宽高比（仅 feature 模式生效）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 3,
                    "max": 15,
                    "step": 1,
                    "tooltip": "视频时长（秒，仅 feature 模式生效）"
                }),
                "mode_type": (["std", "pro"], {
                    "default": "pro",
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
            "api_key": "API 密钥",
            "model": "模型",
            "video_url": "参考视频 URL",
            "refer_type": "参考类型",
            "keep_original_sound": "保留原声",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "element_ids": "主体 ID 列表",
            "aspect_ratio": "宽高比",
            "duration": "时长",
            "mode_type": "生成模式",
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "增强提示词", "任务 ID")
    FUNCTION = "create_and_wait"
    CATEGORY = "XLJ/Kling"
    OUTPUT_NODE = True

    def create_and_wait(self, prompt, api_key="",
                        model="kling-omni-video",
                        video_url="", refer_type="base", keep_original_sound="no",
                        image_1="", image_2="", image_3="", image_4="",
                        element_ids="", aspect_ratio="16:9", duration=5, mode_type="pro",
                        wait_timeout_sec=1800, poll_interval_sec=10):
        creator = XLJKlingCreateOmniVideo()
        task_id, status, video_type = creator.create(
            prompt, api_key,
            model, video_url, refer_type, keep_original_sound,
            image_1, image_2, image_3, image_4,
            element_ids, aspect_ratio, duration, mode_type,
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 等待任务完成：{task_id}")

        querier = XLJKlingQueryOmniVideo()
        task_id, status, video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec,
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 完成！")
        return (status, video_url, enhanced_prompt, task_id)


class XLJKlingCreateOmniAndSave:
    """创建 Kling Omni 视频 → 等待完成 → 自动保存到本地（一键出片）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频描述，使用 <<<video_1>>> / <<<image_1>>> / <<<element_1>>> 引用元素"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "model": (MODEL_LIST, {
                    "default": "kling-omni-video",
                    "tooltip": "Omni 模型"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "参考视频 URL（必填）"
                }),
                "refer_type": (["base", "feature"], {
                    "default": "base",
                    "tooltip": "base=视频编辑，feature=视频参考"
                }),
                "keep_original_sound": (["no", "yes"], {
                    "default": "no",
                    "tooltip": "是否保留原视频声音"
                }),
                "image_1": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 1 URL"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 2 URL"
                }),
                "image_3": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 3 URL"
                }),
                "image_4": ("STRING", {
                    "default": "",
                    "tooltip": "参考图片 4 URL"
                }),
                "element_ids": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "主体库 ID 列表（每行一个数字 ID）"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "宽高比（仅 feature 模式生效）"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 3,
                    "max": 15,
                    "step": 1,
                    "tooltip": "视频时长（秒，仅 feature 模式生效）"
                }),
                "mode_type": (["std", "pro"], {
                    "default": "pro",
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
            "api_key": "API 密钥",
            "model": "模型",
            "video_url": "参考视频 URL",
            "refer_type": "参考类型",
            "keep_original_sound": "保留原声",
            "image_1": "参考图片 1",
            "image_2": "参考图片 2",
            "image_3": "参考图片 3",
            "image_4": "参考图片 4",
            "element_ids": "主体 ID 列表",
            "aspect_ratio": "宽高比",
            "duration": "时长",
            "mode_type": "生成模式",
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "本地路径")
    FUNCTION = "create_and_save"
    CATEGORY = "XLJ/Kling"
    OUTPUT_NODE = True

    def create_and_save(self, prompt, api_key="",
                        model="kling-omni-video",
                        video_url="", refer_type="base", keep_original_sound="no",
                        image_1="", image_2="", image_3="", image_4="",
                        element_ids="", aspect_ratio="16:9", duration=5, mode_type="pro",
                        wait_timeout_sec=1800, poll_interval_sec=10):
        creator = XLJKlingCreateOmniVideo()
        task_id, create_status, video_type = creator.create(
            prompt, api_key,
            model, video_url, refer_type, keep_original_sound,
            image_1, image_2, image_3, image_4,
            element_ids, aspect_ratio, duration, mode_type,
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 等待任务完成：{task_id}")

        querier = XLJKlingQueryOmniVideo()
        task_id, status, result_video_url, enhanced_prompt = querier.query(
            task_id=task_id,
            api_key=api_key,
            wait=True,
            poll_interval_sec=poll_interval_sec,
            timeout_sec=wait_timeout_sec,
        )

        local_path = ""
        if result_video_url and status == "succeed":
            import requests as req
            try:
                save_dir = Path(folder_paths.get_output_directory()) / "xlj_video"
                save_dir.mkdir(parents=True, exist_ok=True)
                timestamp = int(time.time())
                filename = f"kling_omni_{timestamp}.mp4"
                file_path = save_dir / filename

                resp = req.get(result_video_url, stream=True, timeout=180)
                resp.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                local_path = str(file_path)
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 视频已保存：{local_path}")

                resolved = file_path.resolve()
                output_dir = Path(folder_paths.get_output_directory()).resolve()
                try:
                    relative = resolved.relative_to(output_dir)
                    preview = {
                        "filename": relative.name,
                        "subfolder": "" if str(relative.parent) == "." else str(relative.parent).replace("\\", "/"),
                        "type": "output",
                    }
                    return {
                        "ui": {"images": [preview], "animated": (True,)},
                        "result": (status, result_video_url, local_path)
                    }
                except ValueError:
                    pass

            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 Kling Omni - 保存失败：{str(e)}")

        return (status, result_video_url, local_path)


NODE_CLASS_MAPPINGS = {
    "XLJKlingCreateOmniVideo": XLJKlingCreateOmniVideo,
    "XLJKlingQueryOmniVideo": XLJKlingQueryOmniVideo,
    "XLJKlingCreateOmniAndWait": XLJKlingCreateOmniAndWait,
    "XLJKlingCreateOmniAndSave": XLJKlingCreateOmniAndSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJKlingCreateOmniVideo": "🎬 XLJ Kling Omni 创建视频",
    "XLJKlingQueryOmniVideo": "🔍 XLJ Kling Omni 查询任务",
    "XLJKlingCreateOmniAndWait": "⚡ XLJ Kling Omni 一键生成",
    "XLJKlingCreateOmniAndSave": "⚡ XLJ Kling Omni 一键出片",
}
