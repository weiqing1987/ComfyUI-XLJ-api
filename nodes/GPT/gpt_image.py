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
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_IMAGE_MODELS, {"default": GPT_IMAGE_MODELS[0]}),
                "prompt": ("STRING", {"default": "Transform this image into a watercolor painting", "multiline": True}),
                "aspect_ratio": (ASPECT_RATIO_LABELS, {"default": "1:1"}),
                "quality": (QUALITY_OPTIONS, {"default": "auto"}),
                "mode_type": (MODE_TYPES, {"default": "edit"}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": {
                "image_input": ("IMAGE",),
                "image_input_2": ("IMAGE",),
                "image_input_3": ("IMAGE",),
                "image_input_4": ("IMAGE",),
                "image_input_5": ("IMAGE",),
                "image_input_6": ("IMAGE",),
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "output_format": (OUTPUT_FORMATS, {"default": "png"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "image_mask": ("MASK",),
                "image_weight": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "Model",
            "prompt": "Prompt",
            "aspect_ratio": "Aspect Ratio",
            "quality": "Quality",
            "mode_type": "Mode",
            "api_key": "API Key",
            "image_input": "Image 1",
            "image_input_2": "Image 2",
            "image_input_3": "Image 3",
            "image_input_4": "Image 4",
            "image_input_5": "Image 5",
            "image_input_6": "Image 6",
            "system_prompt": "System Prompt",
            "output_format": "Output Format",
            "seed": "Seed",
            "image_mask": "Mask",
            "image_weight": "Image Weight",
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
        mode_type,
        api_key,
        image_input=None,
        image_input_2=None,
        image_input_3=None,
        image_input_4=None,
        image_input_5=None,
        image_input_6=None,
        system_prompt="",
        output_format="png",
        seed=0,
        image_mask=None,
        image_weight=0.8,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")

        timeout_sec = get_edit_timeout_sec()

        if mode_type == "variation":
            raise RuntimeError("variation is not available for this GPT-Image node")

        reference_pils = collect_reference_pils(
            image_input,
            image_input_2,
            image_input_3,
            image_input_4,
            image_input_5,
            image_input_6,
        )
        if not reference_pils:
            raise RuntimeError("at least one reference image is required")
        if len(reference_pils) > 5:
            raise RuntimeError(f"too many reference images: {len(reference_pils)} (max 5)")

        # 新文档：用 /v1/images/generations + image URL 数组
        request_size = "auto"  # 文档只支持 1024x1024, 1536x1024, 1024x1536
        full_prompt = build_prompt(
            prompt,
            system_prompt,
            default_prompt="Edit the supplied image while preserving key subject details.",
        )

        # 将图片转为 base64 字符串数组（纯 base64，不带 data: 前缀）
        image_base64_list = []

        for idx, pil_image in enumerate(reference_pils, start=1):
            # 压缩图片以减少数据大小
            ref_image = prepare_edit_reference_image(pil_image, "1536x1024")
            buf = io.BytesIO()
            ref_image.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            base64_str = base64.b64encode(buf.read()).decode("utf-8")
            image_base64_list.append(base64_str)
            print(f"[ComfyUI-XLJ-api] image[{idx}]: {ref_image.width}x{ref_image.height} base64_len={len(base64_str)}")

        print(f"[ComfyUI-XLJ-api] GPT-Image image-to-image: {full_prompt[:60]}...")
        print(f"[ComfyUI-XLJ-api] model={model_name} refs={len(reference_pils)} quality={quality}")

        # 使用 /v1/images/generations JSON endpoint
        endpoint = f"{API_BASE}/v1/images/generations"
        headers = http_headers_json(api_key)

        # 按文档格式构建 payload
        # size 只支持 1024x1024, 1536x1024, 1024x1536
        size_options = ["1024x1024", "1536x1024", "1024x1536"]
        # 根据 aspect_ratio 选择合适的 size
        if aspect_ratio in ["1:1", "auto"]:
            selected_size = "1024x1024"
        elif aspect_ratio in ["2:3", "3:4", "4:5", "9:16"]:  #竖版
            selected_size = "1024x1536"
        elif aspect_ratio in ["3:2", "4:3", "5:4", "16:9", "21:9"]:  # 横版
            selected_size = "1536x1024"
        else:
            selected_size = "1024x1024"

        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "n": 1,
            "size": selected_size,
            "image": image_base64_list,  #纯 base64字符串数组
        }

        print(f"[ComfyUI-XLJ-api] POST {endpoint} size={selected_size}")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=(30, int(timeout_sec)),
            )
            response_text = resp.text

            if resp.status_code >= 400:
                raise RuntimeError(parse_error_message(response_text, resp.status_code))

            response_data = json.loads(response_text)
            image_tensor = base64_to_tensor(extract_image_base64(response_data))
            status = (
                f"model: {model_name} | refs: {len(reference_pils)} | "
                f"size: {selected_size} | quality: {quality}"
            )

            print("[ComfyUI-XLJ-api] GPT-Image image-to-image done")
            return (image_tensor, status)
        except Exception as e:
            raise RuntimeError(f"GPT-Image image-to-image failed: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "XLJ GPT-Image Text to Image",
    "XLJGPTImageImageToImage": "XLJ GPT-Image Image to Image",
}
