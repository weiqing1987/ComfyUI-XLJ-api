"""
GPT 文本处理节点集合 - 信陵君 AI
"""

from .gpt import XLJDocumentLoader, XLJGPTTextProcessor

NODE_CLASS_MAPPINGS = {
    "XLJDocumentLoader": XLJDocumentLoader,
    "XLJGPTTextProcessor": XLJGPTTextProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJDocumentLoader": "📄 XLJ 文档加载器",
    "XLJGPTTextProcessor": "📝 XLJ GPT 文本处理器",
}
