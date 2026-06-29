"""Kling 节点集合 - 信陵君 AI"""

from .kling import XLJKlingCreateVideo, XLJKlingQueryVideo, XLJKlingCreateAndWait

NODE_CLASS_MAPPINGS = {
    "XLJKlingCreateVideo": XLJKlingCreateVideo,
    "XLJKlingQueryVideo": XLJKlingQueryVideo,
    "XLJKlingCreateAndWait": XLJKlingCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJKlingCreateVideo": "🎬 XLJ Kling 创建视频",
    "XLJKlingQueryVideo": "🔍 XLJ Kling 查询任务",
    "XLJKlingCreateAndWait": "⚡ XLJ Kling 一键生成",
}
