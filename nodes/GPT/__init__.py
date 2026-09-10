"""
GPT text and image nodes for XLJ API.
"""

from .gpt import XLJDocumentLoader, XLJGPTTextProcessor
from .gpt_image import (
    XLJGPTImage25ImageToImage,
    XLJGPTImage25TextToImage,
    XLJGPTImageImageToImage,
    XLJGPTImageTextToImage,
)

NODE_CLASS_MAPPINGS = {
    "XLJDocumentLoader": XLJDocumentLoader,
    "XLJGPTTextProcessor": XLJGPTTextProcessor,
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
    "XLJGPTImage25TextToImage": XLJGPTImage25TextToImage,
    "XLJGPTImage25ImageToImage": XLJGPTImage25ImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJDocumentLoader": "XLJ 文档加载器",
    "XLJGPTTextProcessor": "XLJ GPT 文本处理",
    "XLJGPTImageTextToImage": "XLJ GPT-Image 文生图",
    "XLJGPTImageImageToImage": "XLJ GPT-Image 图生图",
    "XLJGPTImage25TextToImage": "XLJ GPT-Image-2.5 文生图",
    "XLJGPTImage25ImageToImage": "XLJ GPT-Image-2.5 图生图",
}
