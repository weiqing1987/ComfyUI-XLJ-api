"""Sora2 节点集合 - 信陵君 AI"""

from .sora2 import XLJSoraCreateVideo, XLJSoraQueryTask, XLJSoraCreateAndWait

NODE_CLASS_MAPPINGS = {
    "XLJSoraCreateVideo": XLJSoraCreateVideo,
    "XLJSoraQueryTask": XLJSoraQueryTask,
    "XLJSoraCreateAndWait": XLJSoraCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSoraCreateVideo": "🎬 XLJ Sora2 创建视频",
    "XLJSoraQueryTask": "🔍 XLJ Sora2 查询任务",
    "XLJSoraCreateAndWait": "⚡ XLJ Sora2 一键生成",
}
