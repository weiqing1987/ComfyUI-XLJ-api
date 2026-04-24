"""
GPT image nodes for XLJ API.
"""

import base64
import io
import json
import os
import re
import time

import numpy as np
import requests
import torch
from PIL import Image

from ..xlj_utils import (
    API_BASE,
    env_or,
    http_headers_json,
    http_headers_multipart,
    save_image_to_buffer,
    to_mask_rgba_pil_from_comfy,
    to_pil_from_comfy,
)

def extract_image_references(text):
    """从文本提取图片 URL 和 data URL (从 Luck 项目借鉴)"""
    if not text:
        return []
    refs = []
    # data URL pattern
    data_pattern = r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+"
    refs.extend(re.findall(data_pattern, text))
    # URL pattern
    url_pattern = r"https?://[^\s)\]\"']+\.(?:png|jpg|jpeg|webp)(?:\?[^\s)\]\"']*)?"
    refs.extend(match[0] if isinstance(match, tuple) else match for match in re.findall(url_pattern, text, re.I))
    # deduplicate
    seen = set()
    unique_refs = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique_refs.append(ref)
    return unique_refs


def image_bytes_to_tensor(image_bytes):
    """图片 bytes 转 ComfyUI tensor"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0).float()


session = requests.Session()
session.trust_env = False


def emit_runtime_status(
    node_id,
    status,
    message="",
    elapsed_seconds=0.0,
    attempt=0,
    retry_times=0,
    timeout_seconds=0,
):
    """Send runtime status to the ComfyUI frontend extension."""
    if node_id in (None, ""):
        return
    try:
        from server import PromptServer

        if PromptServer.instance is None:
            return

        PromptServer.instance.send_sync(
            "comfyui_xlj_gpt_status",
            {
                "node_id": str(node_id),
                "status": status,
                "message": message,
                "elapsed_seconds": float(elapsed_seconds),
                "attempt": int(attempt),
                "retry_times": int(retry_times),
                "timeout_seconds": int(timeout_seconds),
                "timestamp": time.time(),
            },
        )
    except Exception:
        pass


GPT_IMAGE_MODELS = [
    "gpt-image-2-all",
    "gpt-image-2",
]

ASPECT_RATIO_LABELS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
    "auto",
]

TEXT_ASPECT_RATIO_TO_SIZE = {
    "1:1": "2048x2048",
    "2:3": "2160x3840",
    "3:2": "3840x2160",
    "3:4": "2160x2880",
    "4:3": "2880x2160",
    "4:5": "2160x2704",
    "5:4": "2704x2160",
    "9:16": "2160x3840",
    "16:9": "3840x2160",
    "21:9": "3360x1440",
    "auto": "auto",
}

EDIT_ASPECT_RATIO_TO_SIZE = {
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
    "3:4": "1024x1536",
    "4:3": "1536x1024",
    "4:5": "1024x1536",
    "5:4": "1536x1024",
    "9:16": "1024x1536",
    "16:9": "1536x1024",
    "21:9": "1536x1024",
    "auto": "auto",
}

QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
OUTPUT_FORMATS = ["png", "jpeg", "webp"]
MODE_TYPES = ["edit", "reference", "variation"]

# ===== 图生图 /v1/images/edits 专用常量 =====
EDIT_MODELS = [
    "gpt-image-2-all",
    "gpt-image-2",
]

EDIT_ASPECT_RATIOS = ["9:16", "2:3", "3:4", "1:1", "4:3", "3:2", "16:9", "21:9", "auto"]
EDIT_RESOLUTIONS = ["1K", "2K"]
EDIT_QUALITIES = ["auto", "low", "medium", "high"]
EDIT_BACKGROUNDS = ["auto", "transparent", "opaque"]

EDIT_SIZE_MAP = {
    "1K": {
        "1:1":  "1024x1024",
        "16:9": "1536x1024",
        "9:16": "1024x1536",
        "3:2":  "1536x1024",
        "2:3":  "1024x1536",
        "4:3":  "1536x1024",
        "3:4":  "1024x1536",
        "21:9": "1536x1024",
        "auto": "auto",
    },
    "2K": {
        "1:1":  "2048x2048",
        "16:9": "2048x1152",
        "9:16": "1152x2048",
        "3:2":  "2048x1365",
        "2:3":  "1365x2048",
        "4:3":  "2048x1536",
        "3:4":  "1536x2048",
        "21:9": "2048x858",
        "auto": "auto",
    },
}


def _strip_data_uri_prefix(base64_str: str) -> str:
    if base64_str.startswith("data:"):
        sep_pos = base64_str.find(",")
        if sep_pos >= 0:
            return base64_str[sep_pos + 1:]
    return base64_str


def _safe_convert_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg
    if img.mode in ("LA", "P"):
        return img.convert("RGB")
    if img.mode in ("L", "RGB", "I", "F"):
        return img.convert("RGB")
    return img.convert("RGB")


def base64_to_pil(base64_str: str) -> Image.Image:
    base64_str = _strip_data_uri_prefix(base64_str)
    try:
        image_bytes = base64.b64decode(base64_str)
    except Exception:
        clean = base64_str.replace("\n", "").replace("\r", "").replace(" ", "")
        image_bytes = base64.b64decode(clean)
    img = Image.open(io.BytesIO(image_bytes))
    img.load()
    return _safe_convert_rgb(img)


def base64_to_tensor(base64_str: str) -> torch.Tensor:
    pil_image = base64_to_pil(base64_str)
    image_np = np.array(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(image_np)[None,]


def comfy_image_to_pil_list(image_any):
    if image_any is None:
        return []

    if isinstance(image_any, torch.Tensor) and image_any.dim() == 4:
        return [to_pil_from_comfy(image_any, index=i) for i in range(image_any.shape[0])]

    if isinstance(image_any, np.ndarray) and image_any.ndim == 4:
        return [to_pil_from_comfy(image_any, index=i) for i in range(image_any.shape[0])]

    return [to_pil_from_comfy(image_any)]


def collect_reference_pils(*image_inputs):
    images = []
    for image_any in image_inputs:
        images.extend(comfy_image_to_pil_list(image_any))
    return images


def pil_to_upload_file(pil_image: Image.Image, filename: str, fmt: str):
    fmt = fmt.lower().strip()
    mime = {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }[fmt]
    buf = save_image_to_buffer(pil_image, fmt, quality=90)
    return (filename, buf, mime)


def parse_size_string(size_text: str):
    if not size_text or size_text == "auto" or "x" not in size_text:
        return None
    try:
        width_text, height_text = str(size_text).lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def prepare_edit_reference_image(pil_image: Image.Image, request_size: str) -> Image.Image:
    image = _safe_convert_rgb(pil_image)
    target_size = parse_size_string(request_size)
    if target_size is None:
        return image

    max_width, max_height = target_size
    if image.width <= max_width and image.height <= max_height:
        return image

    resized = image.copy()
    resized.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return resized


def get_edit_timeout_sec() -> int:
    raw_value = str(os.environ.get("XLJ_GPT_IMAGE_TIMEOUT_SEC", "600")).strip()
    try:
        timeout_sec = int(raw_value)
    except Exception:
        timeout_sec = 600
    return max(60, min(timeout_sec, 1800))


def get_edit_retry_timeout_sec(total_timeout_sec: int) -> int:
    return max(60, min(120, max(60, int(total_timeout_sec) // 3)))


def fetch_url_as_base64(image_url: str) -> str:
    image_resp = session.get(image_url, timeout=60)
    image_resp.raise_for_status()
    return base64.b64encode(image_resp.content).decode("utf-8")


def extract_image_base64(response_data: dict) -> str:
    img_data = response_data.get("data", [])
    if img_data:
        image_base64 = img_data[0].get("b64_json")
        if image_base64:
            return image_base64

        image_url = img_data[0].get("url")
        if image_url:
            return fetch_url_as_base64(image_url)

    choices = response_data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if content:
            content = content.strip()
            url_match = re.search(
                r"https?://\S+?\.(?:png|jpg|jpeg|webp|gif)(?:\?\S*)?",
                content,
                re.IGNORECASE,
            )
            if url_match:
                return fetch_url_as_base64(url_match.group(0).rstrip(')"\'>'))
            if content.startswith("data:"):
                return _strip_data_uri_prefix(content)
            if len(content) > 200:
                return content

    raise RuntimeError(f"unable to extract image data from response keys: {list(response_data.keys())}")


def build_prompt(
    prompt: str,
    system_prompt: str = "",
    negative_prompt: str = "",
    style_preset: str = "",
    default_prompt: str = "",
) -> str:
    full_prompt = "" if prompt is None else str(prompt).strip()
    if not full_prompt:
        full_prompt = str(default_prompt or "").strip()
    if not full_prompt:
        raise RuntimeError("prompt is required")

    if style_preset and style_preset.strip():
        full_prompt = f"{full_prompt}, {style_preset.strip()} style"
    if negative_prompt and negative_prompt.strip():
        full_prompt = f"{full_prompt}, without {negative_prompt.strip()}"
    if system_prompt and system_prompt.strip():
        full_prompt = f"{system_prompt.strip()}\n\n{full_prompt}"

    return full_prompt


def parse_error_message(response_text: str, status_code: int) -> str:
    try:
        err_data = json.loads(response_text)
    except Exception:
        return f"HTTP {status_code} - {response_text[:200]}"

    if isinstance(err_data, dict):
        error_obj = err_data.get("error")
        if isinstance(error_obj, dict) and error_obj.get("message"):
            return str(error_obj["message"])
        if err_data.get("errorMessage"):
            return str(err_data["errorMessage"])
    return str(err_data)


class XLJGPTImageTextToImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_IMAGE_MODELS, {"default": GPT_IMAGE_MODELS[0]}),
                "prompt": ("STRING", {"default": "A beautiful sunset over the ocean", "multiline": True}),
                "aspect_ratio": (ASPECT_RATIO_LABELS, {"default": "1:1"}),
                "quality": (QUALITY_OPTIONS, {"default": "auto"}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": {
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "style_preset": ("STRING", {"default": ""}),
                "output_format": (OUTPUT_FORMATS, {"default": "png"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "Model",
            "prompt": "Prompt",
            "aspect_ratio": "Aspect Ratio",
            "quality": "Quality",
            "api_key": "API Key",
            "system_prompt": "System Prompt",
            "negative_prompt": "Negative Prompt",
            "seed": "Seed",
            "style_preset": "Style Preset",
            "output_format": "Output Format",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def generate(
        self,
        model_name,
        prompt,
        aspect_ratio,
        quality,
        api_key,
        system_prompt="",
        negative_prompt="",
        seed=0,
        style_preset="",
        output_format="png",
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")

        request_size = TEXT_ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "auto")
        full_prompt = build_prompt(prompt, system_prompt, negative_prompt, style_preset)

        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "n": 1,
            "quality": quality,
            "format": output_format,
        }
        if request_size:
            payload["size"] = request_size

        print(f"[ComfyUI-XLJ-api] GPT-Image text-to-image: {full_prompt[:60]}...")
        print(
            f"[ComfyUI-XLJ-api] model={model_name} ratio={aspect_ratio} size={request_size} "
            f"quality={quality} format={output_format}"
        )
        if int(seed or 0) != 0:
            print("[ComfyUI-XLJ-api] seed was provided but is not sent because the current Apifox doc does not define it.")

        endpoint = f"{API_BASE}/v1/images/generations"
        headers = http_headers_json(api_key)

        try:
            resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=(30, 300))
            response_text = resp.text

            if resp.status_code >= 400:
                raise RuntimeError(f"GPT-Image text-to-image failed: {parse_error_message(response_text, resp.status_code)}")

            response_data = json.loads(response_text)
            image_tensor = base64_to_tensor(extract_image_base64(response_data))
            status = (
                f"model: {model_name} | ratio: {aspect_ratio} | size: {request_size} | "
                f"quality: {quality} | format: {output_format}"
            )
            if int(seed or 0) != 0:
                status += f" | seed_input: {int(seed)} (not sent)"

            print("[ComfyUI-XLJ-api] GPT-Image text-to-image done")
            return (image_tensor, status)
        except Exception as e:
            raise RuntimeError(f"GPT-Image text-to-image failed: {str(e)}")


class XLJGPTImageImageToImage:
    """GPT-Image 图生图节点 — POST /v1/images/edits (multipart/form-data)"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (EDIT_MODELS, {"default": EDIT_MODELS[0], "tooltip": "选择模型"}),
                "prompt": ("STRING", {"default": "将他们合并在一个图片里面", "multiline": True, "tooltip": "图像编辑提示词"}),
                "aspect_ratio": (EDIT_ASPECT_RATIOS, {"default": "1:1", "tooltip": "输出宽高比"}),
                "resolution": (EDIT_RESOLUTIONS, {"default": "1K", "tooltip": "输出分辨率"}),
                "quality": (EDIT_QUALITIES, {"default": "auto", "tooltip": "生成质量"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"}),
                "timeout_seconds": ("INT", {"default": 180, "min": 30, "max": 1200, "tooltip": "请求超时秒数"}),
                "retry_times": ("INT", {"default": 3, "min": 1, "max": 10, "tooltip": "失败重试次数"}),
            },
            "optional": {
                "background": (EDIT_BACKGROUNDS, {"default": "auto", "tooltip": "背景透明度（仅 gpt-image-1 支持）"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成图片张数（1-10张）"}),
                "image_input": ("IMAGE", {"tooltip": "参考图片 1"}),
                "image_input_2": ("IMAGE", {"tooltip": "参考图片 2"}),
                "image_input_3": ("IMAGE", {"tooltip": "参考图片 3"}),
                "image_input_4": ("IMAGE", {"tooltip": "参考图片 4"}),
                "image_input_5": ("IMAGE", {"tooltip": "参考图片 5"}),
                "image_input_6": ("IMAGE", {"tooltip": "参考图片 6"}),
                "image_input_7": ("IMAGE", {"tooltip": "参考图片 7"}),
                "image_input_8": ("IMAGE", {"tooltip": "参考图片 8"}),
                "image_input_9": ("IMAGE", {"tooltip": "参考图片 9"}),
                "image_input_10": ("IMAGE", {"tooltip": "参考图片 10"}),
                "image_mask": ("MASK", {"tooltip": "遮罩（透明区域=可编辑）"}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model": "模型",
            "prompt": "提示词",
            "aspect_ratio": "宽高比",
            "resolution": "输出分辨率",
            "quality": "质量",
            "api_key": "API 密钥",
            "timeout_seconds": "超时(秒)",
            "retry_times": "重试次数",
            "background": "背景",
            "n": "生成图片张数",
            "image_input": "图片1",
            "image_input_2": "图片2",
            "image_input_3": "图片3",
            "image_input_4": "图片4",
            "image_input_5": "图片5",
            "image_input_6": "图片6",
            "image_input_7": "图片7",
            "image_input_8": "图片8",
            "image_input_9": "图片9",
            "image_input_10": "图片10",
            "image_mask": "遮罩",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def generate(self, model, prompt, aspect_ratio, resolution, quality, api_key,
                 timeout_seconds, retry_times,
                 background="auto", n=1,
                 unique_id=None,
                 image_input=None, image_input_2=None, image_input_3=None,
                 image_input_4=None, image_input_5=None, image_input_6=None,
                 image_input_7=None, image_input_8=None, image_input_9=None,
                 image_input_10=None,
                 image_mask=None):

        start_ts = time.time()

        # --- API Key ---
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            emit_runtime_status(unique_id, "error", "API Key 为空", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("API Key 不能为空（在节点填入或设置环境变量 XLJ_API_KEY）")

        # --- prompt ---
        effective_prompt = (prompt or "").strip()
        if not effective_prompt:
            emit_runtime_status(unique_id, "error", "提示词为空", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("提示词不能为空")

        # --- size = 宽高比 × 分辨率 ---
        size = EDIT_SIZE_MAP.get(resolution, EDIT_SIZE_MAP["1K"]).get(aspect_ratio, "auto")

        # --- 收集图片（multipart files） ---
        image_payloads = []
        for i, img in enumerate([image_input, image_input_2, image_input_3, image_input_4, image_input_5, image_input_6, image_input_7, image_input_8, image_input_9, image_input_10], 1):
            if img is not None:
                pil_list = comfy_image_to_pil_list(img)
                if pil_list:
                    pil = pil_list[0]
                    buf = io.BytesIO()
                    pil.save(buf, format="PNG")
                    buf.seek(0)
                    image_payloads.append((f"image_{i}.png", buf.getvalue()))
                    print(f"[ComfyUI-XLJ-api] 信陵君 图片{i}: {pil.width}x{pil.height}")

        if not image_payloads:
            emit_runtime_status(unique_id, "error", "至少需要一张图片", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("至少需要连接一张参考图到 image_input")

        # --- mask 处理 ---
        mask_bytes = None
        if image_mask is not None:
            try:
                mask_pil = to_mask_rgba_pil_from_comfy(image_mask)
                mbuf = io.BytesIO()
                mask_pil.save(mbuf, format="PNG")
                mask_bytes = mbuf.getvalue()
                print("[ComfyUI-XLJ-api] 信陵君 已添加遮罩")
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 遮罩处理失败，已忽略: {e}")

        # --- 锁定 API 地址 ---
        endpoint = f"{API_BASE}/v1/images/edits"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT-Image 编辑 | model={model} ratio={aspect_ratio} "
              f"res={resolution} size={size} images={len(image_payloads)}")

        emit_runtime_status(unique_id, "running", "开始请求", 0.0, 0, retry_times, timeout_seconds)

        last_error = None
        for attempt in range(1, retry_times + 1):
            try:
                emit_runtime_status(
                    unique_id, "running",
                    f"请求中 ({attempt}/{retry_times})",
                    time.time() - start_ts, attempt, retry_times, timeout_seconds,
                )

                # --- multipart/form-data ---
                files = []
                for fname, b in image_payloads:
                    files.append(("image", (fname, b, "image/png")))
                if mask_bytes is not None:
                    files.append(("mask", ("mask.png", mask_bytes, "image/png")))

                form_data = {
                    "prompt": effective_prompt,
                    "model": model,
                    "n": str(int(n)),
                    "quality": quality,
                }
                if size and size != "auto":
                    form_data["size"] = size
                if background and background != "auto":
                    form_data["background"] = background

                response = session.post(
                    endpoint, headers=headers,
                    data=form_data, files=files,
                    timeout=timeout_seconds,
                )

                if response.status_code != 200:
                    last_error = f"API 错误 {response.status_code}: {response.text[:300]}"
                    if response.status_code in (408, 429) or response.status_code >= 500:
                        if attempt < retry_times:
                            emit_runtime_status(
                                unique_id, "running",
                                f"API 返回 {response.status_code}，重试 ({attempt}/{retry_times})",
                                time.time() - start_ts, attempt, retry_times, timeout_seconds,
                            )
                            time.sleep(min(2 ** (attempt - 1), 8))
                            continue
                    raise RuntimeError(last_error)

                data = response.json()
                emit_runtime_status(
                    unique_id, "running", "解析图片",
                    time.time() - start_ts, attempt, retry_times, timeout_seconds,
                )

                # --- 解析响应（兼容 data[].b64_json/url 和 choices[].message.content）---
                image_tensor = None

                img_data = data.get("data")
                if isinstance(img_data, list) and img_data:
                    item = img_data[0]
                    b64 = item.get("b64_json")
                    if b64:
                        image_tensor = base64_to_tensor(b64)
                    else:
                        img_url = item.get("url")
                        if img_url:
                            dl = session.get(img_url, timeout=timeout_seconds)
                            dl.raise_for_status()
                            image_tensor = image_bytes_to_tensor(dl.content)

                if image_tensor is None:
                    choices = data.get("choices") or []
                    if choices:
                        msg_content = (choices[0].get("message") or {}).get("content") or ""
                        refs = extract_image_references(msg_content)
                        if refs:
                            first_ref = refs[0]
                            if first_ref.startswith("data:"):
                                image_tensor = base64_to_tensor(_strip_data_uri_prefix(first_ref))
                            else:
                                dl = session.get(first_ref, timeout=timeout_seconds)
                                dl.raise_for_status()
                                image_tensor = image_bytes_to_tensor(dl.content)

                if image_tensor is None:
                    raise RuntimeError(f"无法从响应提取图片: {json.dumps(data, ensure_ascii=False)[:300]}")

                elapsed = time.time() - start_ts
                status = (f"model={model} | ratio={aspect_ratio} | res={resolution} | "
                          f"size={size} | elapsed={elapsed:.1f}s")
                emit_runtime_status(
                    unique_id, "success",
                    f"生成完成 ({elapsed:.1f}s)",
                    elapsed, attempt, retry_times, timeout_seconds,
                )
                print(f"[ComfyUI-XLJ-api] 信陵君 GPT-Image 编辑成功 {elapsed:.1f}s")
                return (image_tensor, status)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = str(exc)
                if attempt < retry_times:
                    emit_runtime_status(
                        unique_id, "running",
                        f"网络超时，重试 ({attempt}/{retry_times})",
                        time.time() - start_ts, attempt, retry_times, timeout_seconds,
                    )
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < retry_times:
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                emit_runtime_status(
                    unique_id, "error", last_error,
                    time.time() - start_ts, attempt, retry_times, timeout_seconds,
                )
                raise RuntimeError(f"生成失败: {last_error}")

        elapsed = time.time() - start_ts
        emit_runtime_status(
            unique_id, "error",
            f"连续 {retry_times} 次失败",
            elapsed, retry_times, retry_times, timeout_seconds,
        )
        raise RuntimeError(f"连续 {retry_times} 次失败: {last_error}")


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "XLJ GPT-Image 图生图",
}
