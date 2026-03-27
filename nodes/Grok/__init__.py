"""Grok 节点集合 - 信陵君 AI"""

from .grok import XLJGrokCreateVideo, XLJGrokQueryVideo, XLJGrokCreateAndWait
from .batch_processor import XLJGrokBatchProcessor

NODE_CLASS_MAPPINGS = {
    "XLJGrokCreateVideo": XLJGrokCreateVideo,
    "XLJGrokQueryVideo": XLJGrokQueryVideo,
    "XLJGrokCreateAndWait": XLJGrokCreateAndWait,
    "XLJGrokBatchProcessor": XLJGrokBatchProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJGrokCreateVideo": "🎬 XLJ Grok 创建视频",
    "XLJGrokQueryVideo": "🔍 XLJ Grok 查询任务",
    "XLJGrokCreateAndWait": "⚡ XLJ Grok 一键生成",
    "XLJGrokBatchProcessor": "📦 XLJ Grok 批量处理器",
}
