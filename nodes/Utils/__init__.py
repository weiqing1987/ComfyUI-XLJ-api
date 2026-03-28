"""
Utils 工具节点 - 信陵君 AI
"""

import json
import requests
from pathlib import Path
import folder_paths
from ..xlj_utils import to_pil_from_comfy, save_image_to_buffer, http_headers_multipart, API_BASE
from .csv_reader import XLJCSVBatchReader


def _build_video_preview_result(file_path: Path):
    resolved = file_path.resolve()
    base_dirs = (
        ("output", Path(folder_paths.get_output_directory()).resolve()),
        ("temp", Path(folder_paths.get_temp_directory()).resolve()),
        ("input", Path(folder_paths.get_input_directory()).resolve()),
    )

    for folder_type, base_dir in base_dirs:
        try:
            relative_path = resolved.relative_to(base_dir)
        except ValueError:
            continue

        subfolder = "" if str(relative_path.parent) == "." else str(relative_path.parent).replace("\\", "/")
        return {
            "filename": relative_path.name,
            "subfolder": subfolder,
            "type": folder_type,
        }

    return None


class XLJUploadToImageHost:
    """上传图片到临时图床"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "要上传的图片"}),
            },
            "optional": {
                "upload_url": ("STRING", {"default": "https://imageproxy.zhongzhuan.chat/api/upload", "tooltip": "图床 API 地址"}),
                "format": (["jpeg", "png", "webp"], {"default": "jpeg", "tooltip": "图片格式"}),
                "quality": ("INT", {"default": 100, "min": 1, "max": 100, "tooltip": "图片质量 (1-100)"}),
                "timeout": ("INT", {"default": 30, "min": 1, "max": 300, "tooltip": "超时时间 (秒)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("图片 URL", "创建时间")
    FUNCTION = "upload"
    CATEGORY = "XLJ/Utils"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image": "图片",
            "upload_url": "图床 URL",
            "format": "格式",
            "quality": "质量",
            "timeout": "超时",
        }

    def upload(self, image, upload_url="https://imageproxy.zhongzhuan.chat/api/upload", format="jpeg", quality=100, timeout=30):
        pil = to_pil_from_comfy(image, index=0)
        buf = save_image_to_buffer(pil, fmt=format, quality=quality)

        files = {
            "file": (
                f"image.{'jpg' if format == 'jpeg' else format}",
                buf,
                f"image/{format}"
            )
        }

        try:
            resp = requests.post(upload_url, headers=http_headers_multipart(), files=files, timeout=int(timeout))
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"上传失败：{str(e)}")

        url = data.get("url", "")
        created = str(data.get("created", ""))
        if not url:
            raise RuntimeError(f"上传响应缺少 url 字段：{json.dumps(data, ensure_ascii=False)}")
        return (url, created)


class XLJDownloadVideo:
    """下载视频到本地"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {"default": "", "tooltip": "视频 URL"}),
            },
            "optional": {
                "save_dir": ("STRING", {"default": "output/xlj_video", "tooltip": "保存目录"}),
                "filename": ("STRING", {"default": "", "tooltip": "文件名（留空自动生成）"}),
                "timeout": ("INT", {"default": 180, "min": 10, "max": 600, "tooltip": "超时时间 (秒)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("本地路径", "状态")
    FUNCTION = "download"
    CATEGORY = "XLJ/Utils"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "video_url": "视频 URL",
            "save_dir": "保存目录",
            "filename": "文件名",
            "timeout": "超时",
        }

    def download(self, video_url, save_dir="output/xlj_video", filename="", timeout=180):
        import os
        import time
        from pathlib import Path

        if not video_url or video_url.strip() == "":
            print("[ComfyUI-XLJ-api] 信陵君 下载失败：视频 URL 为空")
            print("[ComfyUI-XLJ-api] 信陵君 请确认:")
            print("[ComfyUI-XLJ-api] 信陵君 1. 查询节点返回的状态是否为 'completed'")
            print("[ComfyUI-XLJ-api] 信陵君 2. 查询节点的'视频 URL'输出是否已连接")
            return ("", "error: video_url is empty")

        # 创建保存目录
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        if not filename:
            timestamp = int(time.time())
            filename = f"video_{timestamp}.mp4"

        file_path = save_path / filename

        try:
            resp = requests.get(video_url, stream=True, timeout=int(timeout))
            resp.raise_for_status()

            with open(file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"[ComfyUI-XLJ-api] 信陵君 视频已保存到：{file_path}")
            preview_result = _build_video_preview_result(file_path)
            if preview_result is not None:
                return {
                    "ui": {
                        "images": [preview_result],
                        "animated": (True,),
                    },
                    "result": (str(file_path), "success")
                }
            return (str(file_path), "success")

        except Exception as e:
            raise RuntimeError(f"下载失败：{str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJUploadToImageHost": XLJUploadToImageHost,
    "XLJDownloadVideo": XLJDownloadVideo,
    "XLJCSVBatchReader": XLJCSVBatchReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJUploadToImageHost": "📷 XLJ 上传图片",
    "XLJDownloadVideo": "📥 XLJ 下载视频",
    "XLJCSVBatchReader": "📄 XLJ CSV 批量读取",
}
