"""Suno nodes for XLJ API."""

from .suno import (
    XLJSunoCreateMusic,
    XLJSunoCreateCover,
    XLJSunoCreateCoverAndWait,
    XLJSunoCoverNegativePreset,
    XLJSunoCoverPromptPreset,
    XLJSunoDownloadAudio,
    XLJSunoPromptPreset,
    XLJSunoQueryTask,
    XLJSunoCreateMusicAndWait,
    XLJSunoUploadAudioToClip,
)

NODE_CLASS_MAPPINGS = {
    "XLJSunoCreateMusic": XLJSunoCreateMusic,
    "XLJSunoCreateCover": XLJSunoCreateCover,
    "XLJSunoCreateCoverAndWait": XLJSunoCreateCoverAndWait,
    "XLJSunoCoverPromptPreset": XLJSunoCoverPromptPreset,
    "XLJSunoCoverNegativePreset": XLJSunoCoverNegativePreset,
    "XLJSunoUploadAudioToClip": XLJSunoUploadAudioToClip,
    "XLJSunoDownloadAudio": XLJSunoDownloadAudio,
    "XLJSunoPromptPreset": XLJSunoPromptPreset,
    "XLJSunoQueryTask": XLJSunoQueryTask,
    "XLJSunoCreateMusicAndWait": XLJSunoCreateMusicAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJSunoCreateMusic": "XLJ Suno 文生音乐",
    "XLJSunoCreateCover": "XLJ Suno 翻唱",
    "XLJSunoCreateCoverAndWait": "XLJ Suno 翻唱一键生成",
    "XLJSunoCoverPromptPreset": "XLJ Suno 翻唱风格预设",
    "XLJSunoCoverNegativePreset": "XLJ Suno 翻唱负面预设",
    "XLJSunoUploadAudioToClip": "XLJ Suno 上传音频转ClipID",
    "XLJSunoDownloadAudio": "XLJ Suno 下载音频",
    "XLJSunoPromptPreset": "XLJ Suno 提示词预设",
    "XLJSunoQueryTask": "XLJ Suno 查询任务",
    "XLJSunoCreateMusicAndWait": "XLJ Suno 文生音乐一键生成",
}
