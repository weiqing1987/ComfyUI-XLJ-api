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
    """GPT-Image 图生图节点，参考 Comfyui-Luck 版面"""

    MODELS = ["gpt-image-2-all", "gpt-image-2"]
    API_BASES = [
        "https://yunwu.ai",
        "https://xinlingjunai.cn",
    ]
    ENDPOINTS = [
        "chat_completions (推荐)",
        "images_generations (兼容)",
    ]
    ASPECT_RATIOS = [
        "AUTO",
        "1:1",
        "16:9",
        "9:16",
        "21:9",
        "4:3",
        "3:2",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key (API密钥)": ("STRING", {"default": "", "multiline": False}),
                "prompt (提示词)": ("STRING", {"default": "", "multiline": True}),
                "mode (模式)": (["AUTO", "text2img", "img2img"], {"default": "AUTO"}),
                "model (模型)": (cls.MODELS, {"default": "gpt-image-2-all"}),
                "api_base (接口域名)": (cls.API_BASES, {"default": "https://yunwu.ai"}),
                "endpoint (端点)": (cls.ENDPOINTS, {"default": "chat_completions (推荐)"}),
                "aspect_ratio (宽高比)": (cls.ASPECT_RATIOS, {"default": "AUTO"}),
                "response_format (响应格式)": (["url", "b64_json"], {"default": "url"}),
                "seed (种子)": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 2147483647,
                        "control_after_generate": True,
                    },
                ),
                "timeout_seconds (超时秒数)": ("INT", {"default": 60, "min": 30, "max": 300}),
                "retry_times (重试次数)": ("INT", {"default": 3, "min": 1, "max": 10}),
            },
            "optional": {
                **{f"image_{i:02d}": ("IMAGE",) for i in range(1, 6)},
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "image_urls")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def _collect_images(self, kwargs):
        """收集图片输入"""
        image_payloads = []
        for i in range(1, 6):
            tensor = kwargs.get(f"image_{i:02d}")
            if tensor is None:
                continue
            pil_list = comfy_image_to_pil_list(tensor)
            if pil_list:
                pil = pil_list[0]
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                buf.seek(0)
                image_payloads.append((f"image_{i:02d}.png", buf.getvalue()))
                print(f"[ComfyUI-XLJ-api] image_{i:02d}: {pil.width}x{pil.height}")
        return image_payloads

    def _compose_prompt(self, prompt, aspect_ratio):
        """构建提示词（比例写入提示词前缀）"""
        AUTO_RATIO_PROMPTS = {
            "1:1": "1024×1024 方图 / 1:1 方形构图",
            "16:9": "横版 16:9 / 宽屏 16:9 电影画幅",
            "9:16": "竖版 9:16 / 手机海报 9:16",
            "21:9": "横幅 21:9 超宽银幕",
            "4:3": "4:3 标准画幅",
            "3:2": "3:2 经典画幅",
        }
        clean_prompt = (prompt or "").strip()
        prefix = AUTO_RATIO_PROMPTS.get(aspect_ratio, "") if aspect_ratio != "AUTO" else ""

        if not clean_prompt and not prefix:
            raise ValueError("prompt 不能为空")

        if prefix and clean_prompt:
            return f"{prefix}，{clean_prompt}"
        if prefix:
            return prefix
        return clean_prompt

    def _request_chat_completions(self, api_base, headers, model, prompt, image_payloads, timeout):
        """chat/completions 方式"""
        content = [{"type": "text", "text": prompt}]
        for _, image_bytes in image_payloads:
            data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": data_url}})

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        return session.post(
            f"{api_base}/v1/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )

    def _request_images_generations(self, api_base, headers, model, prompt, image_payloads, timeout):
        """images/generations 方式"""
        # 图片转 base64 数组
        image_list = []
        for _, image_bytes in image_payloads:
            image_list.append(base64.b64encode(image_bytes).decode("utf-8"))

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "image": image_list,
        }
        return session.post(
            f"{api_base}/v1/images/generations",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )

    def _parse_response(self, data, response_format, timeout, endpoint_type):
        """解析响应"""
        image_urls = []

        if endpoint_type == "chat_completions":
            # 从 choices[0].message.content 提取图片
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"API 未返回 choices: {data}")
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            image_refs = extract_image_references(content)
            if not image_refs:
                raise RuntimeError(f"响应中未找到图片: {content[:200]}")
            image_urls.extend(image_refs)
        else:
            # 从 data[].url 或 data[].b64_json 提取
            items = data.get("data") or []
            if not items:
                raise RuntimeError(f"API 未返回图片数据: {data}")
            for item in items:
                if item.get("url"):
                    image_urls.append(item["url"])

        if not image_urls:
            raise RuntimeError(f"未能解析图片: {data}")

        # 下载/解码第一张图片
        first_ref = image_urls[0]
        if first_ref.startswith("data:"):
            image_tensor = b64_json_to_tensor(first_ref)
        else:
            resp = session.get(first_ref, timeout=timeout)
            resp.raise_for_status()
            image_tensor = image_bytes_to_tensor(resp.content)

        return image_tensor, image_urls

    def generate(self, **kwargs):
        api_key = kwargs.get("api_key (API密钥)", "")
        prompt = kwargs.get("prompt (提示词)", "")
        mode = kwargs.get("mode (模式)", "AUTO")
        model = kwargs.get("model (模型)", "gpt-image-2-all")
        api_base = kwargs.get("api_base (接口域名)", "https://yunwu.ai").rstrip("/")
        endpoint = kwargs.get("endpoint (端点)", "chat_completions (推荐)")
        aspect_ratio = kwargs.get("aspect_ratio (宽高比)", "AUTO")
        response_format = kwargs.get("response_format (响应格式)", "url")
        seed = kwargs.get("seed (种子)", 0)
        timeout_seconds = kwargs.get("timeout_seconds (超时秒数)", 60)
        retry_times = kwargs.get("retry_times (重试次数)", 3)

        if not api_key.strip():
            raise ValueError("API Key 不能为空")

        effective_prompt = self._compose_prompt(prompt, aspect_ratio)
        image_payloads = self._collect_images(kwargs)

        print(f"[ComfyUI-XLJ-api] effective prompt: {effective_prompt[:500]}")

        # AUTO 模式自动判断
        if mode == "AUTO":
            actual_mode = "img2img" if image_payloads else "text2img"
        else:
            actual_mode = mode

        if actual_mode == "img2img" and not image_payloads:
            raise ValueError("img2img 模式需要至少一张参考图")

        headers = {"Authorization": f"Bearer {api_key.strip()}"}
        endpoint_type = "chat_completions" if endpoint.startswith("chat_completions") else "generations"

        print(f"[ComfyUI-XLJ-api] endpoint={endpoint}, mode={actual_mode}, model={model}, seed={seed} (not sent to API)")

        last_error = None
        for attempt in range(1, retry_times + 1):
            try:
                if endpoint_type == "chat_completions":
                    response = self._request_chat_completions(
                        api_base, headers, model, effective_prompt, image_payloads, timeout_seconds
                    )
                else:
                    response = self._request_images_generations(
                        api_base, headers, model, effective_prompt, image_payloads, timeout_seconds
                    )

                if response.status_code != 200:
                    last_error = f"API 错误 {response.status_code}: {response.text[:200]}"
                    if response.status_code in (408, 429) or response.status_code >= 500:
                        if attempt < retry_times:
                            import time
                            time.sleep(min(2 ** (attempt - 1), 8))
                            continue
                    raise RuntimeError(last_error)

                data = response.json()
                image_tensor, image_urls = self._parse_response(data, response_format, timeout_seconds, endpoint_type)

                response_info = {
                    "status": "success",
                    "model": model,
                    "endpoint": endpoint,
                    "mode": actual_mode,
                    "api_base": api_base,
                    "aspect_ratio": aspect_ratio,
                    "prompt": effective_prompt,
                    "response_format": response_format,
                    "seed": seed,
                    "seed_note": "seed 仅用于 ComfyUI 控制，不发送给 API",
                    "input_images": len(image_payloads),
                    "output_images": int(image_tensor.shape[0]),
                    "image_urls": image_urls,
                }

                print(f"[ComfyUI-XLJ-api] 生成成功")
                return (
                    image_tensor,
                    json.dumps(response_info, ensure_ascii=False, indent=2),
                    "\n".join(image_urls),
                )

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = str(exc)
                if attempt < retry_times:
                    import time
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < retry_times and ("408" in last_error or "429" in last_error or "5" in last_error[:3]):
                    import time
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                raise RuntimeError(f"生成失败: {last_error}")

        raise RuntimeError(f"连续 {retry_times} 次失败，最后错误: {last_error}")


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "XLJ GPT-Image 图生图",
}
