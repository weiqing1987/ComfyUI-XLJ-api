"""
GPT image nodes for XLJ API.
"""

import base64
import io
import json
import os
import re

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
    """图生图节点，参考 Luck-gpt2.0 使用 chat/completions endpoint"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_IMAGE_MODELS, {"default": GPT_IMAGE_MODELS[0]}),
                "prompt": ("STRING", {"default": "Edit this image", "multiline": True}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": {
                "image_input": ("IMAGE", {"tooltip": "参考图片1"}),
                "image_input_2": ("IMAGE", {"tooltip": "参考图片2"}),
                "image_input_3": ("IMAGE", {"tooltip": "参考图片3"}),
                "image_input_4": ("IMAGE", {"tooltip": "参考图片4"}),
                "image_input_5": ("IMAGE", {"tooltip": "参考图片5"}),
                "timeout": ("INT", {"default": 60, "min": 30, "max": 300, "tooltip": "超时秒数"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "api_key": "API Key",
            "image_input": "图片1",
            "image_input_2": "图片2",
            "image_input_3": "图片3",
            "image_input_4": "图片4",
            "image_input_5": "图片5",
            "timeout": "超时",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def generate(
        self,
        model_name,
        prompt,
        api_key,
        image_input=None,
        image_input_2=None,
        image_input_3=None,
        image_input_4=None,
        image_input_5=None,
        timeout=60,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 不能为空")

        # 收集图片
        inputs = [image_input, image_input_2, image_input_3, image_input_4, image_input_5]
        image_payloads = []
        for idx, inp in enumerate(inputs, start=1):
            if inp is None:
                continue
            pil_list = comfy_image_to_pil_list(inp)
            if pil_list:
                pil = pil_list[0]
                # 转 PNG bytes
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                buf.seek(0)
                image_payloads.append(buf.getvalue())
                print(f"[ComfyUI-XLJ-api] image[{idx}]: {pil.width}x{pil.height}")

        if not image_payloads:
            raise RuntimeError("至少需要一张参考图片")
        if len(image_payloads) > 5:
            raise RuntimeError(f"图片数量超出限制: {len(image_payloads)} (最多5张)")

        # 构建 messages content (OpenAI 格式)
        content = [{"type": "text", "text": prompt}]
        for image_bytes in image_payloads:
            data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": data_url}})

        # 使用 chat/completions endpoint (参考 Luck)
        endpoint = f"{API_BASE}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }

        print(f"[ComfyUI-XLJ-api] POST {endpoint} images={len(image_payloads)} timeout={timeout}s")
        print(f"[ComfyUI-XLJ-api] prompt: {prompt[:60]}...")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if resp.status_code != 200:
                error_msg = resp.text[:200]
                raise RuntimeError(f"API 错误 {resp.status_code}: {error_msg}")

            data = resp.json()

            # 解析响应 (从 choices[0].message.content 提取图片)
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"API 未返回 choices: {data}")

            message = choices[0].get("message") or {}
            response_content = message.get("content") or ""

            # 提取图片 URL 或 data URL
            image_refs = extract_image_references(response_content)
            if not image_refs:
                raise RuntimeError(f"响应中未找到图片: {response_content[:200]}")

            # 下载/解码第一张图片
            first_ref = image_refs[0]
            if first_ref.startswith("data:"):
                image_tensor = b64_json_to_tensor(first_ref)
            else:
                # 下载 URL
                image_tensor = self._download_image(first_ref, timeout)

            status = f"成功 | model: {model_name} | images: {len(image_payloads)}"
            print(f"[ComfyUI-XLJ-api] 完成")
            return (image_tensor, status)

        except requests.exceptions.Timeout:
            raise RuntimeError(f"请求超时 ({timeout}s)，请重试")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"网络连接失败: {str(e)[:100]}")
        except Exception as e:
            raise RuntimeError(f"生成失败: {str(e)}")

    def _download_image(self, url, timeout):
        """下载图片 URL"""
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return image_bytes_to_tensor(resp.content)


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "XLJ GPT-Image Text to Image",
    "XLJGPTImageImageToImage": "XLJ GPT-Image Image to Image",
}
