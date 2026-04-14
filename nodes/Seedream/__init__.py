"""
Seedream (即梦) 图像生成节点集合 - 信陵君 AI
"""

from .seedream import XLJSeedreamCreateImage

NODE_CLASS_MAPPINGS = {
    "XLJSeedreamCreateImage": XLJSeedreamCreateImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSeedreamCreateImage": "🖼️ XLJ 即梦 Seedream 图像生成",
}
