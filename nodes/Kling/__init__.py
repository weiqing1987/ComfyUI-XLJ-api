"""Kling 节点集合 - 信陵君 AI"""

from .kling import XLJKlingCreateVideo, XLJKlingQueryVideo, XLJKlingCreateAndWait, XLJKlingCreateAndSave
from .omni import XLJKlingCreateOmniVideo, XLJKlingQueryOmniVideo, XLJKlingCreateOmniAndWait, XLJKlingCreateOmniAndSave

NODE_CLASS_MAPPINGS = {
    "XLJKlingCreateVideo": XLJKlingCreateVideo,
    "XLJKlingQueryVideo": XLJKlingQueryVideo,
    "XLJKlingCreateAndWait": XLJKlingCreateAndWait,
    "XLJKlingCreateAndSave": XLJKlingCreateAndSave,
    "XLJKlingCreateOmniVideo": XLJKlingCreateOmniVideo,
    "XLJKlingQueryOmniVideo": XLJKlingQueryOmniVideo,
    "XLJKlingCreateOmniAndWait": XLJKlingCreateOmniAndWait,
    "XLJKlingCreateOmniAndSave": XLJKlingCreateOmniAndSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJKlingCreateVideo": "🎬 XLJ Kling 创建视频",
    "XLJKlingQueryVideo": "🔍 XLJ Kling 查询任务",
    "XLJKlingCreateAndWait": "⚡ XLJ Kling 一键生成",
    "XLJKlingCreateAndSave": "⚡ XLJ Kling 一键出片",
    "XLJKlingCreateOmniVideo": "🎬 XLJ Kling Omni 创建视频",
    "XLJKlingQueryOmniVideo": "🔍 XLJ Kling Omni 查询任务",
    "XLJKlingCreateOmniAndWait": "⚡ XLJ Kling Omni 一键生成",
    "XLJKlingCreateOmniAndSave": "⚡ XLJ Kling Omni 一键出片",
}
