"""
Seedream (即梦) 图像生成节点 - 信陵君 AI
支持 doubao-seedream 系列模型的文本生图 / 参考图生图
"""

import io
import json
import base64
import torch
import numpy as np
import requests
from PIL import Image

from ..xlj_utils import env_or, http_headers_json, API_BASE, to_pil_from_comfy

# 禁用代理
session = requests.Session()
session.trust_env = False

# 即梦 Seedream 模型列表
SEEDREAM_MODELS = [
    "doubao-seedream-5-0-260128",
    "doubao-seedream-5-0-lite-260128",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-4-0-250828",
    "doubao-seedream-3-0-t2i-250415",
    "doubao-seededit-3-0-i2i-250628",
]

# 宽高比选项
ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

# 分辨率选项
RESOLUTIONS = ["1K", "2K", "4K"]


def pil_to_base64(pil_image: Image.Image, format: str = "JPEG") -> str:
    """将 PIL 图像转换为 base64 字符串"""
    buffer = io.BytesIO()
    pil_image.save(buffer, format=format, quality=90)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


def base64_to_pil(base64_str: str) -> Image.Image:
    """将 base64 字符串转换为 PIL 图像（兼容 data URI 前缀）"""
    if base64_str.startswith("data:image/"):
        base64_str = base64_str.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def base64_to_tensor(base64_str: str) -> torch.Tensor:
    """将 base64 图像字符串转换为 ComfyUI IMAGE tensor"""
    pil_image = base64_to_pil(base64_str)
    image_np = np.array(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(image_np)[None,]


class XLJSeedreamTextToImage:
    """即梦 Seedream 文生图节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (SEEDREAM_MODELS, {
                    "default": SEEDREAM_MODELS[0],
                    "tooltip": "选择即梦 Seedream 模型"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "图像生成提示词"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "反向提示词"
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "1:1",
                    "tooltip": "图像宽高比"
                }),
                "resolution": (RESOLUTIONS, {
                    "default": "2K",
                    "tooltip": "图像分辨率"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子值，0 为随机"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "api_key": "API 密钥",
            "negative_prompt": "反向提示词",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "seed": "种子值",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态信息")
    FUNCTION = "generate"
    CATEGORY = "XLJ/Seedream"
    OUTPUT_NODE = True

    def generate(self, model_name, prompt, api_key="",
                 negative_prompt="", aspect_ratio="1:1", resolution="2K",
                 seed=0):
        """文生图"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        if not prompt or not prompt.strip():
            raise RuntimeError("提示词不能为空")

        # 处理种子值：0 表示随机
        if seed == 0:
            actual_seed = random.randint(1, 2147483647)
            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 使用随机种子：{actual_seed}")
        else:
            actual_seed = seed
            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 使用固定种子：{actual_seed}")

        api_base = API_BASE
        endpoint = f"{api_base}/v1/images/generations"
        headers = http_headers_json(api_key)

        # 构建请求 payload
        payload = {
            "model": model_name,
            "prompt": prompt.strip(),
        }

        if negative_prompt and negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt.strip()

        payload["size"] = aspect_ratio
        payload["n"] = 1

        if resolution:
            payload["resolution"] = resolution

        print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 文生图：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 模型：{model_name}")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=180
            )

            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except Exception:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Seedream 文生图失败：{err_msg}")

            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 原始响应：{response_text[:500]}")
                raise RuntimeError(f"Seedream 文生图失败：无法解析响应为 JSON - {str(e)}")

            img_data = data.get("data", [])
            if not img_data:
                raise RuntimeError("API 返回的 data 为空")

            image_info = img_data[0]
            image_base64 = image_info.get("b64_json") or image_info.get("image")

            if not image_base64:
                image_url = image_info.get("url")
                if image_url:
                    img_resp = session.get(image_url, timeout=60)
                    image_base64 = base64.b64encode(img_resp.content).decode('utf-8')
                else:
                    raise RuntimeError(f"响应中缺少图像数据：{json.dumps(data, ensure_ascii=False)[:200]}")

            image_tensor = base64_to_tensor(image_base64)

            status_info = f"模型: {model_name} | 种子: {actual_seed} | 宽高比: {aspect_ratio} | 文生图"

            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 文生图成功！")

            return (image_tensor, status_info)

        except Exception as e:
            raise RuntimeError(f"Seedream 文生图失败：{str(e)}")


class XLJSeedreamImageToImage:
    """即梦 Seedream 图生图节点（支持多张参考图）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (SEEDREAM_MODELS, {
                    "default": SEEDREAM_MODELS[0],
                    "tooltip": "选择即梦 Seedream 模型"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "图像生成提示词"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "反向提示词"
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "1:1",
                    "tooltip": "图像宽高比"
                }),
                "resolution": (RESOLUTIONS, {
                    "default": "2K",
                    "tooltip": "图像分辨率"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子值，0 为随机"
                }),
                "image_1": ("IMAGE", {
                    "tooltip": "参考图 1（最多 14 张）"
                }),
                "image_2": ("IMAGE", {
                    "tooltip": "参考图 2"
                }),
                "image_3": ("IMAGE", {
                    "tooltip": "参考图 3"
                }),
                "image_4": ("IMAGE", {
                    "tooltip": "参考图 4"
                }),
                "image_5": ("IMAGE", {
                    "tooltip": "参考图 5"
                }),
                "image_6": ("IMAGE", {
                    "tooltip": "参考图 6"
                }),
                "image_7": ("IMAGE", {
                    "tooltip": "参考图 7"
                }),
                "image_8": ("IMAGE", {
                    "tooltip": "参考图 8"
                }),
                "image_9": ("IMAGE", {
                    "tooltip": "参考图 9"
                }),
                "image_10": ("IMAGE", {
                    "tooltip": "参考图 10"
                }),
                "image_11": ("IMAGE", {
                    "tooltip": "参考图 11"
                }),
                "image_12": ("IMAGE", {
                    "tooltip": "参考图 12"
                }),
                "image_13": ("IMAGE", {
                    "tooltip": "参考图 13"
                }),
                "image_14": ("IMAGE", {
                    "tooltip": "参考图 14"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "api_key": "API 密钥",
            "negative_prompt": "反向提示词",
            "aspect_ratio": "宽高比",
            "resolution": "分辨率",
            "seed": "种子值",
            "image_1": "参考图 1",
            "image_2": "参考图 2",
            "image_3": "参考图 3",
            "image_4": "参考图 4",
            "image_5": "参考图 5",
            "image_6": "参考图 6",
            "image_7": "参考图 7",
            "image_8": "参考图 8",
            "image_9": "参考图 9",
            "image_10": "参考图 10",
            "image_11": "参考图 11",
            "image_12": "参考图 12",
            "image_13": "参考图 13",
            "image_14": "参考图 14",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态信息")
    FUNCTION = "generate"
    CATEGORY = "XLJ/Seedream"
    OUTPUT_NODE = True

    def generate(self, model_name, prompt, api_key="",
                 negative_prompt="", aspect_ratio="1:1", resolution="2K",
                 seed=0, image_1=None, image_2=None, image_3=None,
                 image_4=None, image_5=None, image_6=None, image_7=None,
                 image_8=None, image_9=None, image_10=None, image_11=None,
                 image_12=None, image_13=None, image_14=None):
        """图生图（支持多张参考图，最多 14 张）"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        if not prompt or not prompt.strip():
            raise RuntimeError("提示词不能为空")

        # 处理种子值：0 表示随机
        if seed == 0:
            actual_seed = random.randint(1, 2147483647)
            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 使用随机种子：{actual_seed}")
        else:
            actual_seed = seed
            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 使用固定种子：{actual_seed}")

        api_base = API_BASE
        endpoint = f"{api_base}/v1/images/generations"
        headers = http_headers_json(api_key)

        # 构建请求 payload
        payload = {
            "model": model_name,
            "prompt": prompt.strip(),
        }

        if negative_prompt and negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt.strip()

        payload["size"] = aspect_ratio
        payload["n"] = 1

        if resolution:
            payload["resolution"] = resolution

        # 处理多张参考图（最多 14 张）
        ref_images = []
        for img_tensor in [image_1, image_2, image_3, image_4, image_5,
                           image_6, image_7, image_8, image_9, image_10,
                           image_11, image_12, image_13, image_14]:
            if img_tensor is not None:
                try:
                    pil_img = to_pil_from_comfy(img_tensor)
                    ref_base64 = pil_to_base64(pil_img, format="JPEG")
                    ref_images.append(ref_base64)
                    print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 添加参考图 {len(ref_images)}")
                except Exception as e:
                    print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 警告：转换参考图失败：{e}")

        if ref_images:
            if len(ref_images) == 1:
                payload["image"] = ref_images[0]
            else:
                payload["image"] = ref_images

        print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 图生图：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 模型：{model_name}")
        print(f"[ComfyUI-XLJ-api] 信陵君 参考图片数量：{len(ref_images)}")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=180
            )

            response_text = resp.text

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(response_text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except Exception:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Seedream 图生图失败：{err_msg}")

            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 原始响应：{response_text[:500]}")
                raise RuntimeError(f"Seedream 图生图失败：无法解析响应为 JSON - {str(e)}")

            img_data = data.get("data", [])
            if not img_data:
                raise RuntimeError("API 返回的 data 为空")

            image_info = img_data[0]
            image_base64 = image_info.get("b64_json") or image_info.get("image")

            if not image_base64:
                image_url = image_info.get("url")
                if image_url:
                    img_resp = session.get(image_url, timeout=60)
                    image_base64 = base64.b64encode(img_resp.content).decode('utf-8')
                else:
                    raise RuntimeError(f"响应中缺少图像数据：{json.dumps(data, ensure_ascii=False)[:200]}")

            image_tensor = base64_to_tensor(image_base64)

            status_info = f"模型: {model_name} | 种子: {actual_seed} | 宽高比: {aspect_ratio} | 参考图: {len(ref_images)} 张"

            print(f"[ComfyUI-XLJ-api] 信陵君 Seedream 图生图成功！")

            return (image_tensor, status_info)

        except Exception as e:
            raise RuntimeError(f"Seedream 图生图失败：{str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJSeedreamTextToImage": XLJSeedreamTextToImage,
    "XLJSeedreamImageToImage": XLJSeedreamImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSeedreamTextToImage": "🖼️ XLJ 即梦 Seedream 文生图",
    "XLJSeedreamImageToImage": "🖼️ XLJ 即梦 Seedream 图生图",
}
