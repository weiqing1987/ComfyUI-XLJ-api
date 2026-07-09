"""
Grok Imagine Video Editing 节点 - 信陵君 AI
xAI 视频编辑：基于已有视频 + 文字描述进行编辑
"""

import json
import time
import requests
from pathlib import Path
from ..xlj_utils import env_or, http_headers_json, API_BASE

try:
    import folder_paths
except ImportError:
    folder_paths = None

session = requests.Session()
session.trust_env = False


def _build_edit_payload(model, prompt, video_url, aspect_ratio, resolution, image_1, image_2, image_3, image_4):
    """构建视频编辑请求 payload"""
    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "video": {
            "url": video_url.strip(),
        },
    }

    # reference_images
    imgs = [img.strip() for img in [image_1, image_2, image_3, image_4] if img and img.strip()]
    if imgs:
        payload["reference_images"] = [{"url": url} for url in imgs]

    return payload


def _collect_images(image_1, image_2, image_3, image_4):
    """收集非空参考图片 URL"""
    return [img.strip() for img in [image_1, image_2, image_3, image_4] if img and img.strip()]


_IMAGE_INPUTS = {
    "image_1": ("STRING", {
        "default": "", "tooltip": "参考图片 1 URL（可选，作为视频编辑的风格参考）"
    }),
    "image_2": ("STRING", {
        "default": "", "tooltip": "参考图片 2 URL"
    }),
    "image_3": ("STRING", {
        "default": "", "tooltip": "参考图片 3 URL"
    }),
    "image_4": ("STRING", {
        "default": "", "tooltip": "参考图片 4 URL"
    }),
}

_IMAGE_LABELS = {
    "image_1": "参考图片 1",
    "image_2": "参考图片 2",
    "image_3": "参考图片 3",
    "image_4": "参考图片 4",
}


class XLJGrokCreateEditVideo:
    """创建 Grok Imagine 视频编辑任务（V2V）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频编辑描述，如「把衣服换成红色」「添加下雨效果」"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "源视频 URL（必填），需为可公开访问的 MP4 链接"
                }),
            },
            "optional": {
                "model": (["grok-imagine-video", "grok-imagine-video-1.5-preview"], {
                    "default": "grok-imagine-video",
                    "tooltip": "模型，grok-imagine-video 支持视频编辑"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "resolution": (["360p", "540p", "720p", "1080p"], {
                    "default": "720p",
                    "tooltip": "视频分辨率"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
                **_IMAGE_INPUTS,
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "编辑提示词",
            "video_url": "视频 URL",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "api_key": "API 密钥",
            **_IMAGE_LABELS,
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("任务 ID", "状态")
    FUNCTION = "create"
    CATEGORY = "XLJ/Grok"

    def create(self, prompt, video_url, model="grok-imagine-video", aspect_ratio="16:9", resolution="720p", api_key="",
               image_1="", image_2="", image_3="", image_4=""):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")
        if not video_url or not video_url.strip():
            raise RuntimeError("视频 URL（video_url）为必填项")
        if not prompt or not prompt.strip():
            raise RuntimeError("编辑提示词（prompt）为必填项")

        api_base = API_BASE
        headers = http_headers_json(api_key)
        payload = _build_edit_payload(model, prompt, video_url, aspect_ratio, resolution, image_1, image_2, image_3, image_4)
        endpoint = f"{api_base}/v1/videos/edits"

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 创建视频编辑任务")
        print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 模型：{model}")
        print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 提示词：{prompt[:80]}...")
        imgs = _collect_images(image_1, image_2, image_3, image_4)
        if imgs:
            print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 参考图片数量：{len(imgs)}")

        try:
            resp = session.post(endpoint, json=payload, headers=headers, timeout=30)
            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", err_data.get("message", str(err_data)))
                except:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"Grok 视频编辑创建失败：{err_msg}")

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Grok 视频编辑创建失败：返回非 JSON - {str(e)}，响应：{response_text[:200]}")

            task_id = result.get("request_id") or result.get("id") or ""
            status = result.get("status", "pending")

            if not task_id:
                raise RuntimeError(f"创建响应缺少任务 ID: {json.dumps(result, ensure_ascii=False)}")

            print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 任务已创建：{task_id}, 状态：{status}")
            return (task_id, status)

        except Exception as e:
            raise RuntimeError(f"Grok 视频编辑创建失败：{str(e)}")


class XLJGrokEditAndWait:
    """创建 Grok 视频编辑任务并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频编辑描述"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "源视频 URL（必填）"
                }),
            },
            "optional": {
                "model": (["grok-imagine-video", "grok-imagine-video-1.5-preview"], {
                    "default": "grok-imagine-video",
                    "tooltip": "模型"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "resolution": (["360p", "540p", "720p", "1080p"], {
                    "default": "720p",
                    "tooltip": "视频分辨率"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
                **_IMAGE_INPUTS,
                "wait_timeout_sec": ("INT", {
                    "default": 300,
                    "min": 60,
                    "max": 1200,
                    "step": 10,
                    "tooltip": "等待超时时间（秒），视频编辑通常较快"
                }),
                "poll_interval_sec": ("INT", {
                    "default": 5,
                    "min": 3,
                    "max": 30,
                    "step": 1,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "编辑提示词",
            "video_url": "视频 URL",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "api_key": "API 密钥",
            **_IMAGE_LABELS,
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "任务 ID")
    FUNCTION = "edit_and_wait"
    CATEGORY = "XLJ/Grok"
    OUTPUT_NODE = True

    def edit_and_wait(self, prompt, video_url, model="grok-imagine-video", aspect_ratio="16:9", resolution="720p", api_key="",
                      image_1="", image_2="", image_3="", image_4="",
                      wait_timeout_sec=300, poll_interval_sec=5):
        creator = XLJGrokCreateEditVideo()
        task_id, create_status = creator.create(
            prompt, video_url, model, aspect_ratio, resolution, api_key,
            image_1, image_2, image_3, image_4,
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 等待任务完成：{task_id}")

        api_key = env_or(api_key, "XLJ_API_KEY")
        headers = http_headers_json(api_key)
        api_base = API_BASE

        deadline = time.time() + int(wait_timeout_sec)
        poll_count = 0
        last_status = ""

        while time.time() < deadline:
            poll_count += 1
            try:
                resp = session.get(
                    f"{api_base}/v1/videos/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                result = resp.json()
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 查询失败：{repr(e)}")
                time.sleep(int(poll_interval_sec))
                continue

            raw_status = result.get("status", "pending")
            if raw_status == "done":
                raw_status = "succeed"
            last_status = raw_status

            video_obj = result.get("video", {})
            video_url_result = video_obj.get("url", "") if isinstance(video_obj, dict) else (video_obj if isinstance(video_obj, str) else "")

            print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 第 {poll_count} 次查询：{raw_status}")

            if raw_status == "succeed" and video_url_result:
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 视频编辑完成！")
                return (raw_status, video_url_result, task_id)

            if raw_status in ("failed", "expired"):
                raise RuntimeError(f"Grok 视频编辑失败，任务 ID: {task_id}，状态：{raw_status}")

            time.sleep(int(poll_interval_sec))

        raise RuntimeError(
            f"Grok 视频编辑超时（等待了 {wait_timeout_sec} 秒）。"
            f"任务 ID: {task_id}，最后状态：{last_status}"
        )


class XLJGrokEditAndSave:
    """创建 Grok 视频编辑 → 等待完成 → 自动保存到本地（一键出片）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频编辑描述"
                }),
                "video_url": ("STRING", {
                    "default": "",
                    "tooltip": "源视频 URL（必填）"
                }),
            },
            "optional": {
                "model": (["grok-imagine-video", "grok-imagine-video-1.5-preview"], {
                    "default": "grok-imagine-video",
                    "tooltip": "模型"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1", "2:3", "3:2"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "resolution": (["360p", "540p", "720p", "1080p"], {
                    "default": "720p",
                    "tooltip": "视频分辨率"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
                **_IMAGE_INPUTS,
                "save_dir": ("STRING", {
                    "default": "output/xlj_video",
                    "tooltip": "保存目录"
                }),
                "filename": ("STRING", {
                    "default": "",
                    "tooltip": "文件名（留空自动生成）"
                }),
                "wait_timeout_sec": ("INT", {
                    "default": 300,
                    "min": 60,
                    "max": 1200,
                    "step": 10,
                    "tooltip": "等待超时时间（秒）"
                }),
                "poll_interval_sec": ("INT", {
                    "default": 5,
                    "min": 3,
                    "max": 30,
                    "step": 1,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "编辑提示词",
            "video_url": "视频 URL",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "api_key": "API 密钥",
            **_IMAGE_LABELS,
            "save_dir": "保存目录",
            "filename": "文件名",
            "wait_timeout_sec": "等待超时",
            "poll_interval_sec": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频 URL", "本地路径")
    FUNCTION = "edit_and_save"
    CATEGORY = "XLJ/Grok"
    OUTPUT_NODE = True

    def edit_and_save(self, prompt, video_url, model="grok-imagine-video", aspect_ratio="16:9", resolution="720p", api_key="",
                      image_1="", image_2="", image_3="", image_4="",
                      save_dir="", filename="", wait_timeout_sec=300, poll_interval_sec=5):
        import os

        edit_wait = XLJGrokEditAndWait()
        status, result_video_url, task_id = edit_wait.edit_and_wait(
            prompt=prompt,
            video_url=video_url,
            model=model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            api_key=api_key,
            image_1=image_1, image_2=image_2, image_3=image_3, image_4=image_4,
            wait_timeout_sec=wait_timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )

        local_path = ""
        if result_video_url and status == "succeed":
            import requests as req
            try:
                if not save_dir:
                    save_dir = str(Path(folder_paths.get_output_directory()) / "xlj_video")
                save_path = Path(save_dir)
                save_path.mkdir(parents=True, exist_ok=True)

                if not filename:
                    timestamp = int(time.time())
                    filename = f"grok_edit_{timestamp}.mp4"
                elif not filename.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
                    filename += ".mp4"

                file_path = save_path / filename
                resp = req.get(result_video_url, stream=True, timeout=180)
                resp.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                local_path = str(file_path)
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 视频已保存：{local_path}")

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
                print(f"[ComfyUI-XLJ-api] 信陵君 Grok Edit - 保存失败：{str(e)}")

        return (status, result_video_url, local_path)


NODE_CLASS_MAPPINGS = {
    "XLJGrokCreateEditVideo": XLJGrokCreateEditVideo,
    "XLJGrokEditAndWait": XLJGrokEditAndWait,
    "XLJGrokEditAndSave": XLJGrokEditAndSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGrokCreateEditVideo": "✂️ XLJ Grok 视频编辑",
    "XLJGrokEditAndWait": "⚡ XLJ Grok 编辑一键生成",
    "XLJGrokEditAndSave": "⚡ XLJ Grok 编辑一键出片",
}
