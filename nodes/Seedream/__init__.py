"""
Seedream (即梦) 图像生成节点集合 - 信陵君 AI
"""

from .seedream import XLJSeedreamTextToImage, XLJSeedreamImageToImage

NODE_CLASS_MAPPINGS = {
    "XLJSeedreamTextToImage": XLJSeedreamTextToImage,
    "XLJSeedreamImageToImage": XLJSeedreamImageToImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSeedreamTextToImage": "🖼️ XLJ 即梦 Seedream 文生图",
    "XLJSeedreamImageToImage": "🖼️ XLJ 即梦 Seedream 图生图",
}
