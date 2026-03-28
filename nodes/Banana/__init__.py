"""
Banana 图像生成节点集合 - 信陵君 AI
"""

from .banana import XLJBananaCreateImage, XLJBananaMultiTurnChat

NODE_CLASS_MAPPINGS = {
    "XLJBananaCreateImage": XLJBananaCreateImage,
    "XLJBananaMultiTurnChat": XLJBananaMultiTurnChat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJBananaCreateImage": "🍌 XLJ Banana 图像生成",
    "XLJBananaMultiTurnChat": "🍌 XLJ Banana 多轮对话",
}
