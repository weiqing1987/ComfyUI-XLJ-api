"""
Utils 工具节点 - 信陵君 AI
"""

import json
import os
import time
import subprocess
import requests
from pathlib import Path
import folder_paths
from ..xlj_utils import to_pil_from_comfy, save_image_to_buffer, http_headers_multipart, API_BASE
from .csv_reader import XLJCSVBatchReader

UPLOAD_FALLBACK_URL = "https://imageproxy.zhongzhuan.chat/api/upload"

def _candidate_upload_urls(upload_url: str = None):
    raw = (upload_url or "").strip()
    if raw:
        return [raw]
    return [UPLOAD_FALLBACK_URL]


def _parse_upload_response(resp):
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"上传接口返回非 JSON：HTTP {resp.status_code} - {resp.text[:300]}")
    url = data.get("url", "")
    created = str(data.get("created", ""))
    if not url:
        raise RuntimeError(f"上传响应缺少 url 字段：{json.dumps(data, ensure_ascii=False)}")
    return url, created, data


def _upload_with_fallback(files, upload_url=None, timeout=30, headers=None, label="文件"):
    last_error = None
    request_timeout = (10, max(300, int(timeout)))
    for url in _candidate_upload_urls(upload_url):
        try:
            print(f"[ComfyUI-XLJ-api] 信陵君 - 尝试上传{label}：{url}")
            resp = requests.post(
                url,
                headers=headers or {},
                files=files,
                timeout=request_timeout,
                proxies={"http": None, "https": None},
            )
            if resp.status_code == 404 and "Invalid URL" in resp.text:
                raise RuntimeError(f"接口不存在：HTTP 404 - {resp.text[:200]}")
            resp.raise_for_status()
            parsed_url, created, data = _parse_upload_response(resp)
            print(f"[ComfyUI-XLJ-api] 信陵君 - 上传{label}成功：{parsed_url}")
            return parsed_url, created, data, url
        except Exception as e:
            last_error = f"{url} -> {repr(e)}"
            print(f"[ComfyUI-XLJ-api] 信陵君 - 上传{label}失败：{last_error}")
            continue
    raise RuntimeError(f"上传{label}失败，已尝试所有候选地址。最后错误：{last_error}")


def _extract_source_video_path(video_info):
    if not isinstance(video_info, dict):
        return None
    candidates = []
    source_path = str(video_info.get("source_path", "") or "").strip()
    source_filename = str(video_info.get("source_filename", "") or "").strip()
    if source_path:
        candidates.append(Path(source_path))
    if source_filename:
        candidates.append(Path(folder_paths.get_input_directory()) / source_filename)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _transcode_source_video_preserve_audio(source_path: Path, temp_path: Path, source_width: int = 0, source_height: int = 0):
    probe = None
    try:
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_streams', '-print_format', 'json', str(source_path)],
            capture_output=True, text=True, timeout=60
        )
    except Exception:
        probe = None
    target_fps = 30
    max_width = 720
    src_w = int(source_width or 0)
    src_h = int(source_height or 0)
    if probe and probe.returncode == 0:
        try:
            data = json.loads(probe.stdout)
            for s in data.get('streams', []):
                if s.get('codec_type') == 'video':
                    src_w = int(s.get('width') or src_w or 0)
                    src_h = int(s.get('height') or src_h or 0)
                    break
        except Exception:
            pass
    if src_w > max_width:
        target_w = max_width
        target_h = max(2, int(round((src_h * target_w / src_w) / 2) * 2)) if src_h else -2
    else:
        target_w = src_w if src_w else max_width
        target_h = src_h if src_h and src_h % 2 == 0 else (src_h - 1 if src_h else -2)
    vf = f'scale={target_w}:{target_h},fps={target_fps}' if target_h != -2 else f'scale={target_w}:-2,fps={target_fps}'
    cmd = [
        'ffmpeg', '-y', '-i', str(source_path),
        '-vf', vf,
        '-c:v', 'libx264', '-crf', '32', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '96k',
        '-movflags', '+faststart',
        str(temp_path)
    ]
    print(f"[ComfyUI-XLJ-api] 信陵君 - 使用原视频保留音轨压缩：source={source_path}, target={target_w}x{target_h}, fps={target_fps}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f'ffmpeg 保留音轨压缩失败: {proc.stderr[:500]}')


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
            url, created, _data, _used_url = _upload_with_fallback(
                files=files,
                upload_url=upload_url,
                timeout=timeout,
                headers=http_headers_multipart(),
                label="图片"
            )
        except Exception as e:
            raise RuntimeError(f"上传失败：{str(e)}")

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

    def download(self, video_url, save_dir="", filename="", timeout=180):
        import os
        import time
        from pathlib import Path

        if not video_url or video_url.strip() == "":
            print("[ComfyUI-XLJ-api] 信陵君 下载失败：视频 URL 为空")
            print("[ComfyUI-XLJ-api] 信陵君 请确认:")
            print("[ComfyUI-XLJ-api] 信陵君 1. 查询节点返回的状态是否为 'completed'")
            print("[ComfyUI-XLJ-api] 信陵君 2. 查询节点的'视频 URL'输出是否已连接")
            return ("", "error: video_url is empty")

        # 默认保存到 ComfyUI 输出目录
        if not save_dir:
            save_dir = str(Path(folder_paths.get_output_directory()) / "xlj_video")
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        # 生成文件名（自动补 .mp4 后缀）
        if not filename:
            timestamp = int(time.time())
            filename = f"video_{timestamp}.mp4"
        elif not filename.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
            filename += ".mp4"

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


class XLJUploadVideo:
    """上传视频到图床，返回可访问的 URL"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "video": ("IMAGE", {"tooltip": "要上传的视频帧（可选；若提供 video_info/source_path 可不接）"}),
                "video_info": ("VHS_VIDEOINFO", {
                    "tooltip": "来自 VHS_LoadVideo 的视频信息（推荐，支持保留音轨）"
                }),
                "upload_url": ("STRING", {"default": f"{API_BASE}/v1/upload", "tooltip": "图床 API 地址"}),
                "format": (["mp4", "webm", "mov", "avi"], {"default": "mp4", "tooltip": "视频格式"}),
                "quality": ("INT", {"default": 100, "min": 1, "max": 100, "tooltip": "视频质量 (1-100)"}),
                "timeout": ("INT", {"default": 30, "min": 1, "max": 300, "tooltip": "超时时间 (秒)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("视频 URL", "文件名")
    FUNCTION = "upload"
    CATEGORY = "XLJ/Utils"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "video": "视频",
            "upload_url": "图床 URL",
            "format": "格式",
            "quality": "质量",
            "timeout": "超时",
        }

    def upload(self, video=None, video_info=None, upload_url=None, format="mp4", quality=100, timeout=30):
        import numpy as np
        import torch

        if upload_url is None:
            upload_url = f"{API_BASE}/v1/upload"

        temp_dir = folder_paths.get_temp_directory()
        timestamp = int(time.time())
        temp_path = Path(temp_dir) / f"xlj_upload_{timestamp}.{format}"

        source_path = _extract_source_video_path(video_info)
        frames = None
        h = w = 0
        if video is not None:
            frames = video.cpu().numpy()
            frames = (np.clip(frames, 0, 1) * 255).astype(np.uint8)
            h, w = frames.shape[1:3]
        elif not source_path:
            raise RuntimeError("视频上传失败：未提供 video 帧输入，也未从 video_info 中拿到 source_path")

        if source_path:
            try:
                _transcode_source_video_preserve_audio(
                    source_path,
                    temp_path,
                    source_width=(video_info or {}).get('source_width', 0),
                    source_height=(video_info or {}).get('source_height', 0),
                )
                print(f"[ComfyUI-XLJ-api] 信陵君 - 视频编码完成（preserve-audio）：{temp_path.name}")
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 - 保留音轨压缩失败，回退到无音轨重编码：{repr(e)}")
                source_path = None

        if not source_path:
            # 用 imageio-ffmpeg 编码（无法保留原音轨时，仅上传压缩视频）
            target_fps = 12
            max_width = 720
            if w > max_width:
                target_w = max_width
                target_h = max(2, int(round((h * target_w / w) / 2) * 2))
            else:
                target_w = w
                target_h = h if h % 2 == 0 else h - 1
            print(f"[ComfyUI-XLJ-api] 信陵君 - 压缩参数：src={w}x{h}, target={target_w}x{target_h}, fps={target_fps}")
            try:
                import imageio
                writer = imageio.get_writer(
                    str(temp_path),
                    fps=target_fps,
                    codec='libx264',
                    ffmpeg_params=['-vf', f'scale={target_w}:{target_h}', '-crf', '32', '-preset', 'veryfast', '-movflags', '+faststart']
                )
                step = max(1, int(round(24 / target_fps)))
                for idx, frame in enumerate(frames):
                    if idx % step == 0:
                        writer.append_data(frame)
                writer.close()
                print(f"[ComfyUI-XLJ-api] 信陵君 - 视频编码完成（imageio）：{temp_path.name}")
            except Exception:
                # fallback: 直接调 ffmpeg
                try:
                    import subprocess as _sp
                    cmd = ['ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{w}x{h}', '-r', '24', '-i', '-',
                           '-vf', f'scale={target_w}:{target_h},fps={target_fps}',
                           '-an', '-c:v', 'libx264', '-crf', '32', '-preset', 'veryfast',
                           '-movflags', '+faststart', str(temp_path)]
                    proc = _sp.Popen(cmd, stdin=_sp.PIPE, stderr=_sp.PIPE)
                    proc.stdin.write(frames.tobytes())
                    proc.stdin.close()
                    proc.wait()
                    if proc.returncode != 0:
                        raise RuntimeError(f"ffmpeg error: {proc.stderr.read().decode(errors='ignore')[:400]}")
                    print(f"[ComfyUI-XLJ-api] 信陵君 - 视频编码完成（ffmpeg）：{temp_path.name}")
                except FileNotFoundError:
                    # fallback: OpenCV
                    try:
                        import cv2
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        writer = cv2.VideoWriter(str(temp_path), fourcc, target_fps, (target_w, target_h))
                        step = max(1, int(round(24 / target_fps)))
                        for idx, frame in enumerate(frames):
                            if idx % step == 0:
                                resized = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (target_w, target_h))
                                writer.write(resized)
                        writer.release()
                        if os.path.getsize(temp_path) > 1024:
                            print(f"[ComfyUI-XLJ-api] 信陵君 - 视频编码完成（cv2/mp4v）：{temp_path.name}")
                        else:
                            raise RuntimeError('cv2 编码输出过小')
                    except ImportError:
                        raise RuntimeError("需要安装 imageio-ffmpeg 或 opencv-python 来编码视频")

        # 验证编码文件
        if not os.path.isfile(temp_path) or os.path.getsize(temp_path) < 1024:
            raise RuntimeError(f"视频编码失败，文件为空或过小：{temp_path}")

        filename = temp_path.name
        print(f"[ComfyUI-XLJ-api] 信陵君 - 视频编码完成：{filename}")

        try:
            mime_map = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "avi": "video/x-msvideo"}
            file_size = os.path.getsize(temp_path)
            mime = mime_map.get(format, "video/mp4")
            print(f"[ComfyUI-XLJ-api] 信陵君 - 视频上传准备：path={temp_path}, size={file_size} bytes, mime={mime}, upload_url={upload_url}")

            used_url = _candidate_upload_urls(upload_url)[0]
            cmd = [
                'curl.exe', '-sS', '--connect-timeout', '10', '--max-time', str(max(300, int(timeout))),
                '-X', 'POST', used_url,
                '-H', 'Accept: application/json',
                '-F', f'file=@{temp_path};type={mime}'
            ]
            print(f"[ComfyUI-XLJ-api] 信陵君 - 调用 curl 上传视频：{used_url}")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"curl 上传失败：returncode={proc.returncode}, stderr={proc.stderr[:500]}")
            try:
                data = json.loads(proc.stdout)
            except Exception:
                raise RuntimeError(f"curl 上传返回非 JSON：{proc.stdout[:500]}")
            url = data.get('url', '')
            if not url:
                raise RuntimeError(f"curl 上传响应缺少 url 字段：{json.dumps(data, ensure_ascii=False)}")
        except Exception as e:
            raise RuntimeError(f"视频上传失败：{str(e)}")
        finally:
            if temp_path.exists():
                try: temp_path.unlink()
                except: pass

        print(f"[ComfyUI-XLJ-api] 信陵君 - 视频上传成功：{url} (via {used_url})")
        return (url, filename)


NODE_CLASS_MAPPINGS = {
    "XLJUploadToImageHost": XLJUploadToImageHost,
    "XLJDownloadVideo": XLJDownloadVideo,
    "XLJUploadVideo": XLJUploadVideo,
    "XLJCSVBatchReader": XLJCSVBatchReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJUploadToImageHost": "📷 XLJ 上传图片",
    "XLJDownloadVideo": "📥 XLJ 下载视频",
    "XLJUploadVideo": "📹 XLJ 上传视频",
    "XLJCSVBatchReader": "📄 XLJ CSV 批量读取",
}
