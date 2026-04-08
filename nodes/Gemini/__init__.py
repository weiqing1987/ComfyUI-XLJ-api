"""
Gemini 文本生成节点 - 信陵君 AI
基于 Gemini 模型的文本生成，支持多模态输入
兼容 ComfyUI 核心 GeminiNode 参数格式
"""

import io
import json
import base64
import numpy as np
import requests
from PIL import Image

from ..xlj_utils import env_or, http_headers_json, API_BASE, to_pil_from_comfy

# 禁用代理
session = requests.Session()
session.trust_env = False


def pil_to_base64(pil_image: Image.Image, format: str = "JPEG") -> str:
    """将 PIL 图像转换为 base64 字符串"""
    buffer = io.BytesIO()
    pil_image.save(buffer, format=format, quality=90)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


class XLJGeminiText:
    """Gemini 文本生成节点 - 兼容原始 GeminiNode 格式"""

    @classmethod
    def INPUT_TYPES(cls):
        # 模型列表与原始 GeminiNode 一致
        model_list = [
            "gemini-2.5-pro-preview-05-06",
            "gemini-2.5-flash-preview-04-17",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-3-pro-preview",
            "gemini-3-1-pro",
            "gemini-3-1-flash-lite",
        ]
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "文本提示词"
                }),
                "model": (model_list, {
                    "default": "gemini-2.5-flash",
                    "tooltip": "选择 Gemini 模型"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFFF,
                    "control_after_generate": True,
                    "tooltip": "随机种子值"
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "图像输入（可选）"
                }),
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "系统提示词"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    FUNCTION = "generate"
    CATEGORY = "XLJ/Gemini"
    OUTPUT_NODE = True

    def generate(self, prompt, model, seed=0, images=None, system_prompt="", api_key=""):
        """生成文本 - 兼容原始 GeminiNode 接口"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        # 处理种子值
        actual_seed = seed if seed != 0 else random.randint(1, 2147483647)
        print(f"[ComfyUI-XLJ-api] 信陵君 Gemini 种子：{actual_seed}")

        api_base = API_BASE
        endpoint = f"{api_base}/v1beta/models/{model}:generateContent"
        headers = http_headers_json(api_key)

        # 准备内容
        contents = []

        # 添加图像
        if images is not None:
            try:
                batch_size = images.shape[0] if hasattr(images, 'shape') else 1
                for i in range(min(batch_size, 10)):
                    pil_img = to_pil_from_comfy(images, index=i)
                    base64_str = pil_to_base64(pil_img, format="JPEG")
                    contents.append({
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_str
                        }
                    })
                    print(f"[ComfyUI-XLJ-api] 添加图像 {i+1}")
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 图像转换警告：{e}")

        # 添加文本
        contents.append({"text": prompt})

        # 构建请求
        payload = {
            "contents": [{"parts": contents}],
            "generationConfig": {
                "seed": int(actual_seed)
            }
        }

        if system_prompt and system_prompt.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt.strip()}]
            }

        print(f"[ComfyUI-XLJ-api] Gemini 文本生成: {prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 模型: {model}")

        try:
            resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=120)

            if resp.status_code >= 400:
                try:
                    err_data = json.loads(resp.text)
                    err_msg = err_data.get("error", {}).get("message", str(err_data))
                except:
                    err_msg = f"HTTP {resp.status_code}"
                raise RuntimeError(f"Gemini 生成失败: {err_msg}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("API 返回空响应")

            parts = candidates[0].get("content", {}).get("parts", [])
            output_text = "".join(p.get("text", "") for p in parts if "text" in p)

            if not output_text:
                raise RuntimeError("响应中缺少文本数据")

            print(f"[ComfyUI-XLJ-api] 生成成功，输出长度: {len(output_text)}")
            return (output_text,)

        except Exception as e:
            raise RuntimeError(f"Gemini 生成失败: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJGeminiText": XLJGeminiText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGeminiText": "Google Gemini",
}