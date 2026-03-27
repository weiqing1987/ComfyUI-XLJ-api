"""ViduQ 节点集合 - 信陵君 AI"""

from .viduq import XLJViduQCreateVideo, XLJViduQQueryVideo, XLJViduQCreateAndWait

NODE_CLASS_MAPPINGS = {
    "XLJViduQCreateVideo": XLJViduQCreateVideo,
    "XLJViduQQueryVideo": XLJViduQQueryVideo,
    "XLJViduQCreateAndWait": XLJViduQCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJViduQCreateVideo": "🎬 XLJ ViduQ 创建视频",
    "XLJViduQQueryVideo": "🔍 XLJ ViduQ 查询任务",
    "XLJViduQCreateAndWait": "⚡ XLJ ViduQ 一键生成",
}
