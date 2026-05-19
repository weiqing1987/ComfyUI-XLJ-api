from .happyhorse import (
    XLJHappyHorseImageToVideo,
    XLJHappyHorseQueryTask,
    XLJHappyHorseReferenceToVideo,
    XLJHappyHorseTextToVideo,
    XLJHappyHorseVideoEdit,
)

NODE_CLASS_MAPPINGS = {
    "XLJHappyHorseTextToVideo": XLJHappyHorseTextToVideo,
    "XLJHappyHorseImageToVideo": XLJHappyHorseImageToVideo,
    "XLJHappyHorseReferenceToVideo": XLJHappyHorseReferenceToVideo,
    "XLJHappyHorseVideoEdit": XLJHappyHorseVideoEdit,
    "XLJHappyHorseQueryTask": XLJHappyHorseQueryTask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJHappyHorseTextToVideo": "XLJ HappyHorse 文生视频",
    "XLJHappyHorseImageToVideo": "XLJ HappyHorse 图生视频",
    "XLJHappyHorseReferenceToVideo": "XLJ HappyHorse 参考生视频",
    "XLJHappyHorseVideoEdit": "XLJ HappyHorse 视频编辑",
    "XLJHappyHorseQueryTask": "XLJ HappyHorse 查询任务",
}
