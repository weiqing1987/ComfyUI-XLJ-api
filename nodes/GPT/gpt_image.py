"""
GPT Image 图像生成节点 - 信陵君 AI
基于 OpenAI Images API 语义实现文生图与图生图。
"""

import base64
import io
import json

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

# 禁用代理
session = requests.Session()
session.trust_env = False

# GPT Image 模型列表
GPT_IMAGE_MODELS = [
    "gpt-image-2-all",
    "gpt-image-2",
]

# GPT Image 支持的尺寸选项（按 API 文档）
SIZE_OPTIONS = [
    "auto",
    "1024x1024",
    "1536x1024",  # 横版 3:2
    "1024x1536",  # 竖版 2:3
    "1792x1024",  # 横版 16:9 (dall-e-3)
    "1024x1792",  # 竖版 9:16 (dall-e-3)
]

# UI 显示的比例标签 -> 实际尺寸映射
ASPECT_RATIO_TO_SIZE = {
    "auto": "auto",
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
    "9:16": "1024x1792",
    "16:9": "1792x1024",
}

ASPECT_RATIO_LABELS = list(ASPECT_RATIO_TO_SIZE.keys())
OUTPUT_FORMATS = ["jpeg", "png", "webp"]
MODE_TYPES = ["edit", "variation", "reference"]


def pil_to_base64(pil_image: Image.Image, format: str = "JPEG") -> str:
    """将 PIL 图像转换为 base64 字符串。"""
    fmt = format.upper()
    buffer = io.BytesIO()
    save_kwargs = {}
    if fmt in ("JPEG", "WEBP"):
        save_kwargs["quality"] = 90
    pil_image.save(buffer, format=fmt, **save_kwargs)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def pil_to_data_url(pil_image: Image.Image, format: str = "JPEG") -> str:
    """将 PIL 图像转换为 data URL。"""
    fmt = format.upper()
    mime = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(fmt, "application/octet-stream")
    return f"data:{mime};base64,{pil_to_base64(pil_image, format=fmt)}"


def _strip_data_uri_prefix(base64_str: str) -> str:
    """去除 data URI 前缀。"""
    if base64_str.startswith("data:"):
        sep_pos = base64_str.find(",")
        if sep_pos >= 0:
            return base64_str[sep_pos + 1:]
    return base64_str


def _safe_convert_rgb(img: Image.Image) -> Image.Image:
    """安全转换为 RGB，处理透明通道。"""
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg
    if img.mode in ("LA", "La"):
        bg = Image.new("L", img.size, 255)
        bg.paste(img, mask=img.split()[-1])
        return bg.convert("RGB")
    if img.mode == "P":
        return img.convert("RGBA").convert("RGB")
    if img.mode in ("L", "RGB", "I", "F"):
        return img.convert("RGB")
    return img.convert("RGB")


def base64_to_pil(base64_str: str) -> Image.Image:
    """将 base64 字符串转换为 PIL 图像。"""
    base64_str = _strip_data_uri_prefix(base64_str)
    try:
        image_bytes = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        return _safe_convert_rgb(img)
    except Exception:
        clean = base64_str.replace("\n", "").replace("\r", "").replace(" ", "")
        image_bytes = base64.b64decode(clean)
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        return _safe_convert_rgb(img)


def base64_to_tensor(base64_str: str) -> torch.Tensor:
    """将 base64 图像字符串转换为 ComfyUI IMAGE tensor。"""
    pil_image = base64_to_pil(base64_str)
    image_np = np.array(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(image_np)[None,]


def comfy_image_to_pil_list(image_any):
    """将 ComfyUI IMAGE 输入展开为 PIL 图像列表，支持 batch。"""
    if image_any is None:
        return []

    if isinstance(image_any, torch.Tensor) and image_any.dim() == 4:
        return [to_pil_from_comfy(image_any, index=i) for i in range(image_any.shape[0])]

    if isinstance(image_any, np.ndarray) and image_any.ndim == 4:
        return [to_pil_from_comfy(image_any, index=i) for i in range(image_any.shape[0])]

    return [to_pil_from_comfy(image_any)]


def collect_reference_images(*image_inputs):
    """收集一个或多个 ComfyUI IMAGE 输入并转换为 images 数组。"""
    images = []
    for image_any in image_inputs:
        for pil_img in comfy_image_to_pil_list(image_any):
            images.append({"image_url": pil_to_data_url(pil_img, format="JPEG")})
    return images


def collect_reference_pils(*image_inputs):
    """收集一个或多个 ComfyUI IMAGE 输入并转换为 PIL 图像列表。"""
    images = []
    for image_any in image_inputs:
        images.extend(comfy_image_to_pil_list(image_any))
    return images


def pil_to_upload_file(pil_image: Image.Image, filename: str, fmt: str):
    """将 PIL 图像转换为 requests multipart 文件项。"""
    fmt = fmt.lower().strip()
    mime = {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }[fmt]
    buf = save_image_to_buffer(pil_image, fmt, quality=90)
    return (filename, buf, mime)


def _fetch_image_base64(image_info: dict) -> str:
    """从 API 返回中提取图像 base64 数据。"""
    image_base64 = image_info.get("b64_json")
    if image_base64:
        return image_base64

    image_url = image_info.get("url")
    if image_url:
        img_resp = session.get(image_url, timeout=60)
        img_resp.raise_for_status()
        return base64.b64encode(img_resp.content).decode("utf-8")

    raise RuntimeError("响应中缺少图像数据")


def _input_fidelity_from_weight(image_weight: float) -> str:
    """将旧的权重参数兼容映射为文档中的 input_fidelity。"""
    return "high" if float(image_weight) >= 0.5 else "low"


class XLJGPTImageTextToImage:
    """GPT Image 文生图节点。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_IMAGE_MODELS, {
                    "default": GPT_IMAGE_MODELS[0],
                    "tooltip": "选择 GPT Image 模型"
                }),
                "prompt": ("STRING", {
                    "default": "A beautiful sunset over the ocean with golden light reflecting on the waves",
                    "multiline": True,
                    "tooltip": "图像生成提示词"
                }),
                "aspect_ratio": (ASPECT_RATIO_LABELS, {
                    "default": "1:1",
                    "tooltip": "图像宽高比"
                }),
                "quality": (["low", "medium", "high"], {
                    "default": "high",
                    "tooltip": "质量：low=快/细节少，medium=均衡，high=慢/细节丰富"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥"
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "附加到提示词前的系统说明"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "反向提示词，将拼接进 prompt"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "种子值，0 为随机"
                }),
                "style_preset": ("STRING", {
                    "default": "",
                    "tooltip": "风格预设，将拼接进 prompt"
                }),
                "output_format": (OUTPUT_FORMATS, {
                    "default": "jpeg",
                    "tooltip": "输出图像格式"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "aspect_ratio": "宽高比",
            "quality": "质量",
            "api_key": "API 密钥",
            "system_prompt": "系统提示词",
            "negative_prompt": "反向提示词",
            "seed": "种子值",
            "style_preset": "风格预设",
            "output_format": "输出格式",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态信息")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def generate(self, model_name, prompt, aspect_ratio, quality, api_key,
                 system_prompt="", negative_prompt="", seed=0, style_preset="",
                 output_format="jpeg"):
        """文生图。"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        if not prompt or not prompt.strip():
            raise RuntimeError("提示词不能为空")

        seed = int(seed or 0)
        actual_seed = random.randint(1, 2147483647) if seed == 0 else seed

        actual_size = ASPECT_RATIO_TO_SIZE.get(aspect_ratio, ASPECT_RATIO_TO_SIZE["1:1"])

        full_prompt = prompt.strip()
        if style_preset and style_preset.strip():
            full_prompt = f"{full_prompt}, {style_preset.strip()} style"
        if negative_prompt and negative_prompt.strip():
            full_prompt = f"{full_prompt}, without {negative_prompt.strip()}"
        if system_prompt and system_prompt.strip():
            full_prompt = f"{system_prompt.strip()}\n\n{full_prompt}"

        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "n": 1,
            "size": actual_size,
            "quality": quality,
        }
        if output_format:
            payload["output_format"] = output_format
        if actual_seed != 0:
            payload["seed"] = actual_seed

        endpoint = f"{API_BASE}/v1/images/generations"
        headers = http_headers_json(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT-Image 文生图：{prompt[:60]}...")
        print(
            f"[ComfyUI-XLJ-api] 信陵君 模型：{model_name} | 比例：{aspect_ratio}({actual_size}) | "
            f"质量：{quality} | 格式：{output_format}"
        )

        try:
            resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=180)
            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except Exception:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"GPT-Image 文生图失败：{err_msg}")

            data = json.loads(response_text)
            img_data = data.get("data", [])
            if not img_data:
                raise RuntimeError("API 返回的 data 为空")

            image_info = img_data[0]
            image_tensor = base64_to_tensor(_fetch_image_base64(image_info))

            revised_prompt = image_info.get("revised_prompt", "")
            status_info = (
                f"模型: {model_name} | 种子: {actual_seed} | 比例: {aspect_ratio}({actual_size}) | "
                f"质量: {quality} | 格式: {output_format}"
            )
            if revised_prompt:
                status_info += f"\n优化提示: {revised_prompt[:100]}..."

            print("[ComfyUI-XLJ-api] 信陵君 GPT-Image 文生图成功")
            return (image_tensor, status_info)

        except Exception as e:
            raise RuntimeError(f"GPT-Image 文生图失败：{str(e)}")


class XLJGPTImageImageToImage:
    """GPT Image 图生图/参考图生成节点。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_IMAGE_MODELS, {
                    "default": GPT_IMAGE_MODELS[0],
                    "tooltip": "选择 GPT Image 模型"
                }),
                "prompt": ("STRING", {
                    "default": "Transform this into a watercolor painting style",
                    "multiline": True,
                    "tooltip": "图像编辑提示词"
                }),
                "aspect_ratio": (ASPECT_RATIO_LABELS, {
                    "default": "1:1",
                    "tooltip": "输出图像宽高比"
                }),
                "quality": (["low", "medium", "high"], {
                    "default": "high",
                    "tooltip": "质量：low=快/细节少，medium=均衡，high=慢/细节丰富"
                }),
                "mode_type": (MODE_TYPES, {
                    "default": "edit",
                    "tooltip": "edit/reference 使用 /v1/images/edits；variation 按官方文档仅 DALL-E 2 支持"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥"
                }),
            },
            "optional": {
                "image_input": ("IMAGE", {
                    "tooltip": "参考图像 1，支持批量 IMAGE"
                }),
                "image_input_2": ("IMAGE", {
                    "tooltip": "参考图像 2，支持批量 IMAGE"
                }),
                "image_input_3": ("IMAGE", {
                    "tooltip": "参考图像 3，支持批量 IMAGE"
                }),
                "image_input_4": ("IMAGE", {
                    "tooltip": "参考图像 4，支持批量 IMAGE"
                }),
                "image_input_5": ("IMAGE", {
                    "tooltip": "参考图像 5，支持批量 IMAGE"
                }),
                "image_input_6": ("IMAGE", {
                    "tooltip": "参考图像 6，支持批量 IMAGE"
                }),
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "附加到提示词前的系统说明"
                }),
                "output_format": (OUTPUT_FORMATS, {
                    "default": "jpeg",
                    "tooltip": "输出图像格式"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "种子值，0 为随机。该字段不是 OpenAI 文档字段，代理服务可能自行兼容。"
                }),
                "image_mask": ("MASK", {
                    "tooltip": "编辑遮罩（可选，白色区域为编辑区域）"
                }),
                "image_weight": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "兼容旧工作流的参考强度，将映射到 input_fidelity：>=0.5 为 high，否则为 low"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "aspect_ratio": "宽高比",
            "quality": "质量",
            "mode_type": "模式",
            "api_key": "API 密钥",
            "image_input": "参考图像 1",
            "image_input_2": "参考图像 2",
            "image_input_3": "参考图像 3",
            "image_input_4": "参考图像 4",
            "image_input_5": "参考图像 5",
            "image_input_6": "参考图像 6",
            "system_prompt": "系统提示词",
            "output_format": "输出格式",
            "seed": "种子值",
            "image_mask": "编辑遮罩",
            "image_weight": "参考强度",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态信息")
    FUNCTION = "generate"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def generate(self, model_name, prompt, aspect_ratio, quality, mode_type, api_key,
                 image_input=None, image_input_2=None, image_input_3=None,
                 image_input_4=None, image_input_5=None, image_input_6=None,
                 system_prompt="", output_format="jpeg", seed=0,
                 image_mask=None, image_weight=0.8):
        """图生图 - 使用 /v1/images/edits multipart/form-data。"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        if mode_type == "variation":
            raise RuntimeError(
                "根据 OpenAI 官方文档，/v1/images/variations 仅支持 dall-e-2。"
                "当前 GPT-Image 节点不支持 variation 模式，请改用 edit/reference。"
            )

        reference_pils = collect_reference_pils(
            image_input,
            image_input_2,
            image_input_3,
            image_input_4,
            image_input_5,
            image_input_6,
        )
        if not reference_pils:
            raise RuntimeError("参考图像不能为空，请至少连接一张图像")
        if len(reference_pils) > 16:
            raise RuntimeError(f"根据官方文档，GPT Image 最多支持 16 张参考图，当前传入 {len(reference_pils)} 张")

        seed = int(seed or 0)
        actual_seed = random.randint(1, 2147483647) if seed == 0 else seed
        actual_size = ASPECT_RATIO_TO_SIZE.get(aspect_ratio, ASPECT_RATIO_TO_SIZE["1:1"])

        full_prompt = prompt.strip() if prompt and prompt.strip() else "Edit the supplied image while preserving key subject details."
        if system_prompt and system_prompt.strip():
            full_prompt = f"{system_prompt.strip()}\n\n{full_prompt}"

        # multipart/form-data 字段
        files = []
        for idx, pil_img in enumerate(reference_pils, start=1):
            files.append((
                "image",
                pil_to_upload_file(pil_img, f"image_{idx}.png", "png"),
            ))

        if image_mask is not None:
            try:
                pil_mask = to_mask_rgba_pil_from_comfy(image_mask)
                files.append((
                    "mask",
                    pil_to_upload_file(pil_mask, "mask.png", "png"),
                ))
            except Exception as e:
                raise RuntimeError(f"编辑遮罩转换失败：{e}")

        form_fields = {
            "model": model_name,
            "prompt": full_prompt,
            "n": "1",
            "size": actual_size,
            "quality": quality,
        }

        endpoint = f"{API_BASE}/v1/images/edits"
        headers = http_headers_multipart(api_key)

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT-Image 图生图：{prompt[:60]}...")
        print(
            f"[ComfyUI-XLJ-api] 信陵君 模型：{model_name} | 参考图：{len(reference_pils)} 张 | "
            f"尺寸：{actual_size} | 质量：{quality}"
        )
        print(f"[ComfyUI-XLJ-api] 信陵君 正在请求 {endpoint} ...")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                data=form_fields,
                files=files,
                timeout=(30, 300),
            )
            print(f"[ComfyUI-XLJ-api] 信陵君 收到响应 HTTP {resp.status_code}")
            response_text = resp.text
            print(f"[ComfyUI-XLJ-api] 信陵君 响应前500字符：{response_text[:500]}")

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except Exception:
                    err_msg = f"HTTP {resp.status_code} - {response_text[:200]}"
                raise RuntimeError(f"GPT-Image 图生图失败：{err_msg}")

            data = json.loads(response_text)

            # 兼容两种响应格式
            image_base64 = None
            image_url = None

            # 格式1: choices[0].message.content (chat completion 格式)
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    # content 可能是 URL、markdown ![](url)、data URI、或纯 base64
                    content = content.strip()
                    import re
                    url_match = re.search(r'https?://\S+?\.(?:png|jpg|jpeg|webp|gif)(?:\?\S*)?', content, re.IGNORECASE)
                    if url_match:
                        image_url = url_match.group(0).rstrip(')"\'>')
                    elif content.startswith("data:") or (len(content) > 200 and not content.startswith("http")):
                        image_base64 = content
                    elif content.startswith("http"):
                        image_url = content

            # 格式2: data[0] 标准 images 格式
            if not image_base64 and not image_url:
                img_data = data.get("data", [])
                if img_data:
                    image_base64 = img_data[0].get("b64_json")
                    if not image_base64:
                        image_url = img_data[0].get("url")

            # 如果是 URL，下载它
            if image_url and not image_base64:
                print(f"[ComfyUI-XLJ-api] 信陵君 下载图像：{image_url[:100]}")
                img_resp = session.get(image_url, timeout=60)
                img_resp.raise_for_status()
                image_base64 = base64.b64encode(img_resp.content).decode("utf-8")

            if not image_base64:
                raise RuntimeError(f"无法从响应中提取图像数据，响应结构：{list(data.keys())}，内容片段：{response_text[:300]}")

            image_tensor = base64_to_tensor(image_base64)

            status_info = (
                f"模型: {model_name} | 种子: {actual_seed} | 参考图: {len(reference_pils)} 张 | "
                f"尺寸: {actual_size} | 质量: {quality}"
            )

            print("[ComfyUI-XLJ-api] 信陵君 GPT-Image 图生图成功")
            return (image_tensor, status_info)

        except Exception as e:
            raise RuntimeError(f"GPT-Image 图生图失败：{str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGPTImageTextToImage": "🖼️ XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "🖼️ XLJ GPT-Image 图生图",
}
