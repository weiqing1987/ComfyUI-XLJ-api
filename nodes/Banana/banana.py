"""
Banana 图像生成节点 - 信陵君 AI
基于 Gemini 模型的图像生成
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


def pil_to_base64(pil_image: Image.Image, format: str = "JPEG") -> str:
    """将 PIL 图像转换为 base64 字符串"""
    buffer = io.BytesIO()
    pil_image.save(buffer, format=format, quality=90)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


def base64_to_pil(base64_str: str) -> Image.Image:
    """将 base64 字符串转换为 PIL 图像"""
    image_bytes = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


class XLJBananaCreateImage:
    """创建 Banana 图像生成任务"""

    @classmethod
    def INPUT_TYPES(cls):
        model_list = ["gemini-3-pro-image-preview", "gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"]
        return {
            "required": {
                "model_name": (model_list, {
                    "default": model_list[0],
                    "tooltip": "选择 Gemini 模型"
                }),
                "prompt": ("STRING", {
                    "default": "A futuristic nano banana dish",
                    "multiline": True,
                    "tooltip": "图像生成提示词"
                }),
                "aspect_ratio": (["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"], {
                    "default": "1:1",
                    "tooltip": "图像宽高比"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "系统提示词，用于指导 AI 的行为和风格"
                }),
                "image_1": ("IMAGE", {
                    "tooltip": "参考图 1"
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
                "image_size": (["1K", "2K", "4K"], {
                    "default": "2K",
                    "tooltip": "图像尺寸，只对 gemini-3-pro-image-preview 和 gemini-3.1-flash-image-preview 起作用"
                }),
                "temperature": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "生成温度"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子值，0 为随机（INT32 范围）"
                }),
                "use_search": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "启用网络搜索增强（仅 gemini-3-pro-image-preview 和 gemini-3.1-flash-image-preview 支持）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "aspect_ratio": "宽高比",
            "api_key": "API 密钥",
            "system_prompt": "系统提示词",
            "image_1": "参考图 1",
            "image_2": "参考图 2",
            "image_3": "参考图 3",
            "image_4": "参考图 4",
            "image_5": "参考图 5",
            "image_6": "参考图 6",
            "image_size": "尺寸",
            "temperature": "温度",
            "seed": "种子值",
            "use_search": "启用搜索"
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("图像", "思考过程", "引用来源")
    FUNCTION = "generate"
    CATEGORY = "XLJ/Banana"
    OUTPUT_NODE = True

    def generate(self, model_name, prompt, aspect_ratio="1:1", api_key="",
                 system_prompt="", image_1=None, image_2=None, image_3=None,
                 image_4=None, image_5=None, image_6=None, image_size="2K",
                 temperature=1.0, seed=0, use_search=True):
        """生成图像"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        # 处理种子值：0 表示随机
        if seed == 0:
            actual_seed = random.randint(1, 2147483647)
            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 使用随机种子：{actual_seed}")
        else:
            actual_seed = seed
            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 使用固定种子：{actual_seed}")

        # 锁定 API 地址
        api_base = API_BASE

        # 准备参考图像（转换为 base64）
        reference_images_base64 = []
        for img_tensor in [image_1, image_2, image_3, image_4, image_5, image_6]:
            if img_tensor is not None:
                try:
                    pil_img = to_pil_from_comfy(img_tensor)
                    base64_str = pil_to_base64(pil_img, format="JPEG")
                    reference_images_base64.append(base64_str)
                    print(f"[ComfyUI-XLJ-api] 信陵君 Banana 添加参考图 {len(reference_images_base64)}")
                except Exception as e:
                    print(f"[ComfyUI-XLJ-api] 信陵君 Banana 警告：转换参考图失败：{e}")

        # 构建请求 - 使用 Gemini 原生端点
        endpoint = f"{api_base}/v1beta/models/{model_name}:generateContent"
        headers = http_headers_json(api_key)

        # 构建 contents（Gemini API 格式）
        contents = []

        # 添加参考图像
        for img_base64 in reference_images_base64:
            contents.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_base64
                }
            })

        # 添加文本提示词
        contents.append({"text": prompt})

        # 构建 generation_config
        generation_config = {
            "temperature": float(temperature),
            "response_modalities": ["TEXT", "IMAGE"],
            "seed": int(actual_seed)
        }

        # 根据模型类型添加不同的配置
        if model_name in ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview"]:
            generation_config["imageConfig"] = {
                "aspectRatio": aspect_ratio,
                "imageSize": image_size
            }
        elif model_name == "gemini-2.5-flash-image":
            generation_config["imageConfig"] = {
                "aspectRatio": aspect_ratio
            }

        # 构建请求 payload
        payload = {
            "contents": [{"parts": contents}],
            "generationConfig": generation_config
        }

        # 添加系统提示词
        if system_prompt and system_prompt.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt.strip()}]
            }

        # 如果启用搜索，添加 tools
        if use_search and model_name in ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview"]:
            payload["tools"] = [{"googleSearch": {}}]

        print(f"[ComfyUI-XLJ-api] 信陵君 Banana 生成图像：{prompt[:50]}...")
        print(f"[ComfyUI-XLJ-api] 信陵君 API Base: {api_base}")
        print(f"[ComfyUI-XLJ-api] 信陵君 模型：{model_name}")
        print(f"[ComfyUI-XLJ-api] 信陵君 参考图片数量：{len(reference_images_base64)}")

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
                except:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Banana 图像生成失败：{err_msg}")

            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"[ComfyUI-XLJ-api] 原始响应：{response_text[:500]}")
                raise RuntimeError(f"Banana 图像生成失败：无法解析响应为 JSON - {str(e)}")

            # 解析响应
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("API 返回的 candidates 为空")

            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            # 提取图像和文本
            image_base64 = None
            thinking = ""

            for part in parts:
                if "inlineData" in part or "inline_data" in part:
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    image_base64 = inline_data.get("data")
                elif "text" in part:
                    thinking += part.get("text", "")

            if not image_base64:
                raise RuntimeError(f"响应中缺少图像数据：{json.dumps(data, ensure_ascii=False)[:200]}")

            # 提取 grounding 信息
            grounding_metadata = candidate.get("groundingMetadata", {})
            grounding_sources = self._extract_grounding_info(grounding_metadata, thinking)

            # 解码图像
            pil_image = base64_to_pil(image_base64)

            # 转换为 tensor
            image_np = np.array(pil_image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_np)[None,]

            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 图像生成成功！")

            return (image_tensor, thinking, grounding_sources)

        except Exception as e:
            raise RuntimeError(f"Banana 图像生成失败：{str(e)}")

    def _extract_grounding_info(self, grounding_metadata, text_content):
        """提取 grounding 信息"""
        if not grounding_metadata:
            return text_content

        lines = [text_content, "\n\n----\n## Grounding Sources\n"]

        # 提取搜索查询
        web_search_queries = grounding_metadata.get("webSearchQueries", [])
        if web_search_queries:
            lines.append(f"\n**Web Search Queries:** {', '.join(web_search_queries)}\n")

        # 提取 grounding chunks
        grounding_chunks = grounding_metadata.get("groundingChunks", [])
        if grounding_chunks:
            lines.append("\n### Sources\n")
            for i, chunk in enumerate(grounding_chunks, start=1):
                web = chunk.get("web", {})
                uri = web.get("uri", "")
                title = web.get("title", "Source")
                lines.append(f"{i}. [{title}]({uri})\n")

        return "".join(lines)


class XLJBananaMultiTurnChat:
    """Banana 多轮对话图像生成节点"""

    def __init__(self):
        self.conversation_history = []
        self.last_image_base64 = None

    @classmethod
    def INPUT_TYPES(cls):
        model_list = ["gemini-3-pro-image-preview", "gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"]
        return {
            "required": {
                "model_name": (model_list, {
                    "default": model_list[0],
                    "tooltip": "选择 Gemini 模型"
                }),
                "prompt": ("STRING", {
                    "default": "Create an image of a clear perfume bottle sitting on a vanity.",
                    "multiline": True,
                    "tooltip": "对话提示词"
                }),
                "reset_chat": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "重置对话历史"
                }),
                "aspect_ratio": (["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"], {
                    "default": "1:1",
                    "tooltip": "图像宽高比"
                }),
                "image_size": (["1K", "2K", "4K"], {
                    "default": "2K",
                    "tooltip": "图像尺寸，只对 gemini-3-pro-image-preview 和 gemini-3.1-flash-image-preview 起作用"
                }),
                "temperature": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "生成温度"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子值，0 为随机"
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "系统提示词"
                }),
                "image_input": ("IMAGE", {
                    "tooltip": "初始参考图像"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "prompt": "提示词",
            "reset_chat": "重置对话",
            "aspect_ratio": "宽高比",
            "image_size": "尺寸",
            "temperature": "温度",
            "seed": "种子值",
            "system_prompt": "系统提示词",
            "image_input": "参考图",
            "api_key": "API 密钥"
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图像", "响应文本", "元数据", "对话历史")
    FUNCTION = "generate_multiturn_image"
    CATEGORY = "XLJ/Banana"
    OUTPUT_NODE = True

    def generate_multiturn_image(self, model_name, prompt, reset_chat=False,
                                  aspect_ratio="1:1", image_size="2K", temperature=1.0,
                                  seed=0, system_prompt="", image_input=None, api_key=""):
        """多轮对话图像生成"""
        import random

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        # 重置对话
        if reset_chat:
            self.conversation_history = []
            self.last_image_base64 = None
            print("[ComfyUI-XLJ-api] 信陵君 Banana 对话已重置")

        # 处理种子值
        if seed == 0:
            actual_seed = random.randint(1, 2147483647)
            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 使用随机种子：{actual_seed}")
        else:
            actual_seed = seed
            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 使用固定种子：{actual_seed}")

        api_base = API_BASE
        endpoint = f"{api_base}/v1beta/models/{model_name}:streamGenerateContent"
        headers = http_headers_json(api_key)

        # 构建 contents
        contents = []

        # 添加历史对话
        for msg in self.conversation_history:
            parts = []
            if "image_base64" in msg:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": msg["image_base64"]
                    }
                })
            parts.append({"text": msg["content"]})
            contents.append({"role": msg["role"], "parts": parts})

        # 添加当前消息
        current_parts = []

        # 1. 如果是首次对话且有输入图像
        if len(self.conversation_history) == 0 and image_input is not None:
            try:
                pil_img = to_pil_from_comfy(image_input)
                image_base64 = pil_to_base64(pil_img, format="JPEG")
                current_parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 信陵君 Banana 警告：转换输入图像失败：{e}")
        # 2. 如果有上一轮生成的图像
        elif self.last_image_base64:
            current_parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": self.last_image_base64
                }
            })

        current_parts.append({"text": prompt})
        contents.append({"role": "user", "parts": current_parts})

        # 构建 generation_config
        generation_config = {
            "temperature": float(temperature),
            "response_modalities": ["TEXT", "IMAGE"],
            "seed": int(actual_seed)
        }

        if model_name in ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview"]:
            generation_config["imageConfig"] = {
                "aspectRatio": aspect_ratio,
                "imageSize": image_size
            }
        elif model_name == "gemini-2.5-flash-image":
            generation_config["imageConfig"] = {
                "aspectRatio": aspect_ratio
            }

        payload = {
            "contents": contents,
            "generationConfig": generation_config
        }

        if system_prompt and system_prompt.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt.strip()}]
            }

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
                except:
                    err_msg = f"HTTP {resp.status_code} - 响应内容：{response_text[:200]}"
                raise RuntimeError(f"Banana 多轮对话生成失败：{err_msg}")

            data = json.loads(response_text)

            # 解析响应
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("API 返回的 candidates 为空")

            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            image_base64 = None
            response_text_content = ""

            for part in parts:
                if "inlineData" in part or "inline_data" in part:
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    image_base64 = inline_data.get("data")
                elif "text" in part:
                    response_text_content += part.get("text", "")

            if not image_base64:
                raise RuntimeError(f"响应中缺少图像数据")

            finish_reason = candidate.get("finishReason", "UNKNOWN")
            metadata = f"Finish Reason: {finish_reason}"

            # 解码图像
            pil_image = base64_to_pil(image_base64)

            # 更新对话历史
            user_msg = {"role": "user", "content": prompt}
            if len(self.conversation_history) == 0 and image_input is not None:
                pil_img = to_pil_from_comfy(image_input)
                user_msg["image_base64"] = pil_to_base64(pil_img, format="JPEG")
            elif self.last_image_base64:
                user_msg["image_base64"] = self.last_image_base64

            self.conversation_history.append(user_msg)
            self.conversation_history.append({
                "role": "model",
                "content": response_text_content if response_text_content else "Image generated",
                "image_base64": image_base64
            })
            self.last_image_base64 = image_base64

            # 转换为 tensor
            image_np = np.array(pil_image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_np)[None,]

            # 格式化对话历史
            chat_history_display = []
            for msg in self.conversation_history:
                display_msg = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                if "image_base64" in msg:
                    display_msg["has_image"] = True
                chat_history_display.append(display_msg)

            chat_history_str = json.dumps(chat_history_display, ensure_ascii=False, indent=2)

            print(f"[ComfyUI-XLJ-api] 信陵君 Banana 多轮对话图像生成成功！")

            return (image_tensor, response_text_content, metadata, chat_history_str)

        except Exception as e:
            raise RuntimeError(f"Banana 多轮对话生成失败：{str(e)}")


NODE_CLASS_MAPPINGS = {
    "XLJBananaCreateImage": XLJBananaCreateImage,
    "XLJBananaMultiTurnChat": XLJBananaMultiTurnChat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJBananaCreateImage": "🍌 XLJ Banana 图像生成",
    "XLJBananaMultiTurnChat": "🍌 XLJ Banana 多轮对话",
}
