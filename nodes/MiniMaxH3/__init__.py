from .minimax_h3_2k import XLJMiniMaxH3ContextIR, XLJMiniMaxH3Regenerate2K
from .video_host import XLJMiniMaxH3UploadVideo

NODE_CLASS_MAPPINGS = {
    "XLJMiniMaxH3ContextIR": XLJMiniMaxH3ContextIR,
    "XLJMiniMaxH3Regenerate2K": XLJMiniMaxH3Regenerate2K,
    "XLJMiniMaxH3UploadVideo": XLJMiniMaxH3UploadVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJMiniMaxH3ContextIR": "MiniMax H3 官方·Context-IR提示词增强",
    "XLJMiniMaxH3Regenerate2K": "MiniMax H3 官方直连·2K视频增强",
    "XLJMiniMaxH3UploadVideo": "MiniMax H3 专用视频图床",
}
