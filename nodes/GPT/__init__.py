"""
GPT text and image nodes for XLJ API.
"""

from .gpt import XLJDocumentLoader, XLJGPTTextProcessor
from .gpt_image import XLJGPTImageImageToImage, XLJGPTImageTextToImage

NODE_CLASS_MAPPINGS = {
    "XLJDocumentLoader": XLJDocumentLoader,
    "XLJGPTTextProcessor": XLJGPTTextProcessor,
    "XLJGPTImageTextToImage": XLJGPTImageTextToImage,
    "XLJGPTImageImageToImage": XLJGPTImageImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJDocumentLoader": "XLJ Document Loader",
    "XLJGPTTextProcessor": "XLJ GPT Text Processor",
    "XLJGPTImageTextToImage": "XLJ GPT-Image Text to Image",
    "XLJGPTImageImageToImage": "XLJ GPT-Image Image to Image",
}
