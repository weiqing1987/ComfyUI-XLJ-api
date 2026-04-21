"""
GPT 文本处理 + 图像生成节点集合 - 信陵君 AI
"""

from .gpt import XLJDocumentLoader, XLJGPTTextProcessor
from .gpt_image import XLJGPTImageTextToImage, XLJGPTImageImageToImage

NODE_CLASS_MAPPINGS = {
    "XLJDocumentLoader": XLJDocumentLoader,
    "XLJGPTTextProcessor": XLJGPTTextProcessor,
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJDocumentLoader": "📄 XLJ 文档加载器",
    "XLJGPTTextProcessor": "📝 XLJ GPT 文本处理器",
    "XLJGPTImageTextToImage": "🖼️ XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "🖼️ XLJ GPT-Image 图生图",
}
