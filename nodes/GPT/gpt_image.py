"""
GPT image nodes for XLJ API.
"""

import base64
import io
import json
import math
import os
import re
import time
from pathlib import Path

import folder_paths
import numpy as np
import requests
import torch
from PIL import Image

from ..xlj_utils import API_BASE, env_or, http_headers_json, to_mask_rgba_pil_from_comfy, to_pil_from_comfy


session = requests.Session()


GPT_IMAGE_MODELS = [
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

QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
OUTPUT_FORMATS = ["png", "jpeg", "webp"]
RESOLUTION_OPTIONS = ["auto", "1K", "2K", "4K"]

EDIT_MODELS = GPT_IMAGE_MODELS
EDIT_ASPECT_RATIOS = ["9:16", "2:3", "3:4", "1:1", "4:3", "3:2", "16:9", "21:9", "auto"]
EDIT_RESOLUTIONS = RESOLUTION_OPTIONS
EDIT_QUALITIES = QUALITY_OPTIONS
EDIT_BACKGROUNDS = ["auto", "transparent", "opaque"]

SIZE_RULES = {
    "min_pixels": 655_360,
    "max_pixels": 8_294_400,
    "max_edge": 3840,
    "multiple": 16,
}

RESOLUTION_TARGETS = {
    "1K": {"long_edge": 1536, "square_edge": 1024},
    "2K": {"long_edge": 2048, "square_edge": 2048},
    "4K": {"long_edge": 3840, "square_edge": 2880},
}


def extract_image_references(text):
    if not text:
        return []

    refs = []
    data_pattern = r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+"
    refs.extend(re.findall(data_pattern, text))

    url_pattern = r"https?://[^\s)\]\"']+\.(?:png|jpg|jpeg|webp)(?:\?[^\s)\]\"']*)?"
    refs.extend(match[0] if isinstance(match, tuple) else match for match in re.findall(url_pattern, text, re.I))

    seen = set()
    unique_refs = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique_refs.append(ref)
    return unique_refs


def image_bytes_to_tensor(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0).float()


def emit_runtime_status(
    node_id,
    status,
    message="",
    elapsed_seconds=0.0,
    attempt=0,
    retry_times=0,
    timeout_seconds=0,
):
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


def parse_aspect_ratio(aspect_ratio: str):
    if not aspect_ratio or aspect_ratio == "auto" or ":" not in str(aspect_ratio):
        return None
    try:
        width_text, height_text = str(aspect_ratio).split(":", 1)
        width_ratio = float(width_text)
        height_ratio = float(height_text)
    except Exception:
        return None
    if width_ratio <= 0 or height_ratio <= 0:
        return None
    return width_ratio / height_ratio


def round_down_multiple(value: float, base: int) -> int:
    return max(base, int(value) // base * base)


def scale_size_to_constraints(width: int, height: int):
    max_edge = SIZE_RULES["max_edge"]
    max_pixels = SIZE_RULES["max_pixels"]
    multiple = SIZE_RULES["multiple"]

    scale = min(
        1.0,
        max_edge / max(width, 1),
        max_edge / max(height, 1),
        math.sqrt(max_pixels / max(width * height, 1)),
    )
    width = round_down_multiple(width * scale, multiple)
    height = round_down_multiple(height * scale, multiple)

    while width > max_edge or height > max_edge or (width * height) > max_pixels:
        width = round_down_multiple(width - multiple, multiple)
        height = round_down_multiple(height - multiple, multiple)

    return width, height


def build_request_size(aspect_ratio: str, resolution: str) -> str:
    if resolution == "auto" or aspect_ratio == "auto":
        return "auto"

    ratio = parse_aspect_ratio(aspect_ratio)
    target = RESOLUTION_TARGETS.get(resolution)
    if ratio is None or target is None:
        return "auto"

    multiple = SIZE_RULES["multiple"]
    min_pixels = SIZE_RULES["min_pixels"]

    if math.isclose(ratio, 1.0, rel_tol=1e-6):
        width = height = target["square_edge"]
    elif ratio > 1.0:
        width = target["long_edge"]
        height = round_down_multiple(width / ratio, multiple)
    else:
        height = target["long_edge"]
        width = round_down_multiple(height * ratio, multiple)

    width, height = scale_size_to_constraints(width, height)
    if width * height < min_pixels:
        return "auto"
    return f"{width}x{height}"


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
            url_match = re.search(r"https?://\S+?\.(?:png|jpg|jpeg|webp|gif)(?:\?\S*)?", content, re.IGNORECASE)
            if url_match:
                return fetch_url_as_base64(url_match.group(0).rstrip(')"\'>'))
            if content.startswith("data:"):
                return _strip_data_uri_prefix(content)
            if len(content) > 200:
                return content

    raise RuntimeError(f"unable to extract image data from response keys: {list(response_data.keys())}")


def save_generated_image_to_output(pil_image: Image.Image, prefix: str) -> str:
    output_dir = Path(folder_paths.get_output_directory()) / "xlj_gpt_image"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{prefix}_{timestamp}_{int(time.time() * 1000) % 1000:03d}.png"
    output_path = output_dir / filename
    pil_image.save(output_path, format="PNG")
    return str(output_path)


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
                "model_name": (GPT_IMAGE_MODELS, {"default": GPT_IMAGE_MODELS[0], "tooltip": "选择 GPT-Image 模型"}),
                "prompt": ("STRING", {"default": "一张海边日落的唯美照片", "multiline": True, "tooltip": "图像生成提示词"}),
                "aspect_ratio": (ASPECT_RATIO_LABELS, {"default": "1:1", "tooltip": "输出宽高比"}),
                "resolution": (RESOLUTION_OPTIONS, {"default": "auto", "tooltip": "输出分辨率档位，按 OpenAI 当前尺寸规则生成合法大小"}),
                "quality": (QUALITY_OPTIONS, {"default": "auto", "tooltip": "生成质量"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"}),
            },
            "optional": {
                "system_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "系统提示词"}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "负面提示词"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647, "tooltip": "保留字段，当前接口不会实际发送"}),
                "style_preset": ("STRING", {"default": "", "tooltip": "风格补充词"}),
                "output_format": (OUTPUT_FORMATS, {"default": "png", "tooltip": "输出格式"}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "aspect_ratio": "宽高比",
            "resolution": "输出分辨率",
            "quality": "质量",
            "api_key": "API 密钥",
            "system_prompt": "系统提示词",
            "negative_prompt": "负面提示词",
            "seed": "随机种子",
            "style_preset": "风格预设",
            "output_format": "输出格式",
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
        resolution,
        quality,
        api_key,
        system_prompt="",
        negative_prompt="",
        seed=0,
        style_preset="",
        output_format="png",
        unique_id=None,
    ):
        start_ts = time.time()
        retry_times = 1
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            emit_runtime_status(unique_id, "error", "API Key 为空", 0.0, 0, retry_times, 600)
            raise RuntimeError("API key is required")

        request_size = build_request_size(aspect_ratio, resolution)
        full_prompt = build_prompt(prompt, system_prompt, negative_prompt, style_preset)

        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "n": 1,
            "quality": quality,
            "output_format": output_format,
        }
        if request_size:
            payload["size"] = request_size

        print(f"[ComfyUI-XLJ-api] GPT-Image text-to-image: {full_prompt[:60]}...")
        print(
            f"[ComfyUI-XLJ-api] model={model_name} ratio={aspect_ratio} resolution={resolution} "
            f"size={request_size} quality={quality} format={output_format}"
        )
        if int(seed or 0) != 0:
            print("[ComfyUI-XLJ-api] seed was provided but is not sent because the current API does not expose it.")

        endpoint = f"{API_BASE}/v1/images/generations"
        headers = http_headers_json(api_key)

        emit_runtime_status(unique_id, "running", "开始请求 GPT-Image", 0.0, 0, retry_times, 600)

        try:
            emit_runtime_status(unique_id, "running", "请求中，等待 API 响应", time.time() - start_ts, 1, retry_times, 600)
            resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=(30, 600))
            response_text = resp.text
            if resp.status_code >= 400:
                raise RuntimeError(parse_error_message(response_text, resp.status_code))

            emit_runtime_status(unique_id, "running", "解析图片", time.time() - start_ts, 1, retry_times, 600)
            response_data = json.loads(response_text)
            image_base64 = extract_image_base64(response_data)
            image_tensor = base64_to_tensor(image_base64)
            saved_path = save_generated_image_to_output(base64_to_pil(image_base64), "gpt_text2img")
            elapsed = time.time() - start_ts
            status = (
                f"model: {model_name} | ratio: {aspect_ratio} | resolution: {resolution} | size: {request_size} | "
                f"quality: {quality} | format: {output_format} | elapsed: {elapsed:.1f}s"
            )
            if int(seed or 0) != 0:
                status += f" | seed_input: {int(seed)} (not sent)"
            status += f" | saved: {saved_path}"
            emit_runtime_status(unique_id, "success", f"生成完成 ({elapsed:.1f}s)", elapsed, 1, retry_times, 600)
            return (image_tensor, status)
        except Exception as exc:
            elapsed = time.time() - start_ts
            emit_runtime_status(unique_id, "error", str(exc), elapsed, 1, retry_times, 600)
            raise RuntimeError(f"GPT-Image text-to-image failed: {exc}")


class XLJGPTImageImageToImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (EDIT_MODELS, {"default": EDIT_MODELS[0], "tooltip": "选择模型"}),
                "prompt": ("STRING", {"default": "将他们合并在一个图片里面", "multiline": True, "tooltip": "图像编辑提示词"}),
                "aspect_ratio": (EDIT_ASPECT_RATIOS, {"default": "1:1", "tooltip": "输出宽高比"}),
                "resolution": (EDIT_RESOLUTIONS, {"default": "1K", "tooltip": "输出分辨率档位，按 OpenAI 当前尺寸规则生成合法大小"}),
                "quality": (EDIT_QUALITIES, {"default": "auto", "tooltip": "生成质量"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"}),
                "timeout_seconds": ("INT", {"default": 180, "min": 30, "max": 1200, "tooltip": "请求超时秒数"}),
            },
            "optional": {
                "background": (EDIT_BACKGROUNDS, {"default": "auto", "tooltip": "背景模式，gpt-image-2 不支持 transparent"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成图片张数（1-10 张）"}),
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

    def generate(
        self,
        model,
        prompt,
        aspect_ratio,
        resolution,
        quality,
        api_key,
        timeout_seconds,
        background="auto",
        n=1,
        unique_id=None,
        image_input=None,
        image_input_2=None,
        image_input_3=None,
        image_input_4=None,
        image_input_5=None,
        image_input_6=None,
        image_input_7=None,
        image_input_8=None,
        image_input_9=None,
        image_input_10=None,
        image_mask=None,
    ):
        start_ts = time.time()
        retry_times = 1

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            emit_runtime_status(unique_id, "error", "API Key 为空", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("API Key 不能为空（在节点填入或设置环境变量 XLJ_API_KEY）")

        effective_prompt = (prompt or "").strip()
        if not effective_prompt:
            emit_runtime_status(unique_id, "error", "提示词为空", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("提示词不能为空")

        size = build_request_size(aspect_ratio, resolution)

        image_payloads = []
        image_inputs = [
            image_input,
            image_input_2,
            image_input_3,
            image_input_4,
            image_input_5,
            image_input_6,
            image_input_7,
            image_input_8,
            image_input_9,
            image_input_10,
        ]
        for index, img in enumerate(image_inputs, 1):
            if img is None:
                continue
            pil_list = comfy_image_to_pil_list(img)
            if not pil_list:
                continue
            pil = pil_list[0]
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            image_payloads.append((f"image_{index}.png", buf.getvalue()))
            print(f"[ComfyUI-XLJ-api] GPT-Image image input {index}: {pil.width}x{pil.height}")

        if not image_payloads:
            emit_runtime_status(unique_id, "error", "至少需要一张图片", 0.0, 0, retry_times, timeout_seconds)
            raise RuntimeError("至少需要连接一张参考图到 image_input")

        mask_bytes = None
        if image_mask is not None:
            try:
                mask_pil = to_mask_rgba_pil_from_comfy(image_mask)
                mbuf = io.BytesIO()
                mask_pil.save(mbuf, format="PNG")
                mask_bytes = mbuf.getvalue()
            except Exception as exc:
                print(f"[ComfyUI-XLJ-api] GPT-Image mask ignored: {exc}")

        endpoint = f"{API_BASE}/v1/images/edits"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        print(
            f"[ComfyUI-XLJ-api] GPT-Image edit | model={model} ratio={aspect_ratio} "
            f"resolution={resolution} size={size} images={len(image_payloads)}"
        )
        emit_runtime_status(unique_id, "running", "开始请求", 0.0, 0, retry_times, timeout_seconds)

        try:
            emit_runtime_status(unique_id, "running", "请求中", time.time() - start_ts, 1, retry_times, timeout_seconds)

            files = [("image", (fname, data, "image/png")) for fname, data in image_payloads]
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
                endpoint,
                headers=headers,
                data=form_data,
                files=files,
                timeout=timeout_seconds,
            )
            if response.status_code != 200:
                raise RuntimeError(f"API 错误 {response.status_code}: {response.text[:300]}")

            data = response.json()
            emit_runtime_status(unique_id, "running", "解析图片", time.time() - start_ts, 1, retry_times, timeout_seconds)

            image_tensor = None
            output_pil = None
            img_data = data.get("data")
            if isinstance(img_data, list) and img_data:
                item = img_data[0]
                b64 = item.get("b64_json")
                if b64:
                    output_pil = base64_to_pil(b64)
                    image_tensor = base64_to_tensor(b64)
                else:
                    img_url = item.get("url")
                    if img_url:
                        dl = session.get(img_url, timeout=timeout_seconds)
                        dl.raise_for_status()
                        output_pil = Image.open(io.BytesIO(dl.content)).convert("RGB")
                        image_tensor = image_bytes_to_tensor(dl.content)

            if image_tensor is None:
                choices = data.get("choices") or []
                if choices:
                    msg_content = (choices[0].get("message") or {}).get("content") or ""
                    refs = extract_image_references(msg_content)
                    if refs:
                        first_ref = refs[0]
                        if first_ref.startswith("data:"):
                            output_pil = base64_to_pil(_strip_data_uri_prefix(first_ref))
                            image_tensor = base64_to_tensor(_strip_data_uri_prefix(first_ref))
                        else:
                            dl = session.get(first_ref, timeout=timeout_seconds)
                            dl.raise_for_status()
                            output_pil = Image.open(io.BytesIO(dl.content)).convert("RGB")
                            image_tensor = image_bytes_to_tensor(dl.content)

            if image_tensor is None:
                raise RuntimeError(f"无法从响应提取图片: {json.dumps(data, ensure_ascii=False)[:300]}")

            elapsed = time.time() - start_ts
            saved_path = ""
            if output_pil is not None:
                saved_path = save_generated_image_to_output(output_pil, "gpt_img2img")
            status = (
                f"model={model} | ratio={aspect_ratio} | resolution={resolution} | "
                f"size={size} | elapsed={elapsed:.1f}s"
            )
            if saved_path:
                status += f" | saved: {saved_path}"
            emit_runtime_status(unique_id, "success", f"生成完成 ({elapsed:.1f}s)", elapsed, 1, retry_times, timeout_seconds)
            return (image_tensor, status)
        except Exception as exc:
            elapsed = time.time() - start_ts
            emit_runtime_status(unique_id, "error", str(exc), elapsed, 1, retry_times, timeout_seconds)
            raise RuntimeError(f"生成失败: {exc}")


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "XLJ GPT-Image 图生图",
}
