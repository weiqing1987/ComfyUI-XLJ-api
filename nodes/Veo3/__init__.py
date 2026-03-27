"""Veo3 节点集合 - 心灵俊 AI"""

from .veo3 import XLJVeoText2Video, XLJVeoImage2Video, XLJVeoQueryTask, XLJVeoText2VideoAndWait, XLJVeoImage2VideoAndWait

NODE_CLASS_MAPPINGS = {
    "XLJVeoText2Video": XLJVeoText2Video,
    "XLJVeoImage2Video": XLJVeoImage2Video,
    "XLJVeoQueryTask": XLJVeoQueryTask,
    "XLJVeoText2VideoAndWait": XLJVeoText2VideoAndWait,
    "XLJVeoImage2VideoAndWait": XLJVeoImage2VideoAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJVeoText2Video": "🎬 XLJ Veo 文生视频",
    "XLJVeoImage2Video": "🖼️ XLJ Veo 图生视频",
    "XLJVeoQueryTask": "🔍 XLJ Veo 查询任务",
    "XLJVeoText2VideoAndWait": "⚡ XLJ Veo 一键文生视频",
    "XLJVeoImage2VideoAndWait": "⚡ XLJ Veo 一键图生视频",
}
