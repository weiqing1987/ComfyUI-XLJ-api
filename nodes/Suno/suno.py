"""Suno music nodes for XLJ API."""

import io
import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import requests

try:
    import folder_paths
except Exception:
    folder_paths = None

from ..xlj_utils import env_or, http_headers_json


session = requests.Session()
session.trust_env = False


SUNO_BASE_URL = "https://xinlingjunai.cn"
TASK_DONE = {"SUCCESS", "success", "completed", "COMPLETE"}
TASK_FAILED = {"FAILURE", "failure", "failed", "ERROR", "error"}
PRESET_NONE = "不添加"

MODEL_SPECS = [
    ("v3.0 (chirp-v3-0 | 最长4分钟)", "chirp-v3-0"),
    ("v3.5 (chirp-v3-5 | 最长4分钟)", "chirp-v3-5"),
    ("v4.0 (chirp-v4 | 最长4分钟)", "chirp-v4"),
    ("v4.5 (chirp-auk | 最长8分钟)", "chirp-auk"),
    ("v5.0 (chirp-v5 | 最长8分钟)", "chirp-v5"),
    ("v5.5 (chirp-fenix | 最长8分钟)", "chirp-fenix"),
]
SUNO_MODEL_LABELS = [label for label, _ in MODEL_SPECS]
SUNO_MODEL_MAP = {label: value for label, value in MODEL_SPECS}
SUNO_MODEL_MAP.update(
    {
        "chirp-v3-0": "chirp-v3-0",
        "chirp-v3-5": "chirp-v3-5",
        "chirp-v4": "chirp-v4",
        "chirp-auk": "chirp-auk",
        "chirp-v5": "chirp-v5",
        "chirp-fenix": "chirp-fenix",
        "chirp-v3-5-upload": "chirp-v3-5-upload",
        "chirp-v3-5-tau": "chirp-v3-5-tau",
        "chirp-v4-tau": "chirp-v4-tau",
    }
)

TEXT_MODEL_LABELS = list(SUNO_MODEL_LABELS)
COVER_MODEL_LABELS = [
    "v3.5 TAU (chirp-v3-5-tau | 翻唱/上传模式)",
    "v4 TAU (chirp-v4-tau | 翻唱/音色一致性)",
]
COVER_MODEL_MAP = {
    "v3.5 TAU (chirp-v3-5-tau | 翻唱/上传模式)": "chirp-v3-5-tau",
    "v4 TAU (chirp-v4-tau | 翻唱/音色一致性)": "chirp-v4-tau",
    "chirp-v3-5-tau": "chirp-v3-5-tau",
    "chirp-v4-tau": "chirp-v4-tau",
}

SUNO_GENERATION_TYPE_LABELS = ["文本", "TEXT"]
SUNO_GENERATION_TYPE_MAP = {
    "文本": "TEXT",
    "TEXT": "TEXT",
}
SUNO_CREATE_MODE_LABELS = ["自定义", "灵感", "custom", "inspire"]
SUNO_CREATE_MODE_MAP = {
    "自定义": "custom",
    "custom": "custom",
    "灵感": "inspire",
    "inspire": "inspire",
}
SUNO_VOCAL_GENDER_LABELS = ["默认", "男声", "女声", "", "m", "f"]
SUNO_VOCAL_GENDER_MAP = {
    "默认": "",
    "": "",
    "男声": "m",
    "m": "m",
    "女声": "f",
    "f": "f",
}
FILE_FORMAT_LABELS = ["MP3", "WAV", "自动", "mp3", "wav", "auto"]
FILE_FORMAT_MAP = {
    "MP3": "mp3",
    "mp3": "mp3",
    "WAV": "wav",
    "wav": "wav",
    "自动": "auto",
    "auto": "auto",
}
SUNO_CREATE_MODES = SUNO_CREATE_MODE_LABELS
SUNO_GENERATION_TYPES = SUNO_GENERATION_TYPE_LABELS
FILE_FORMATS = FILE_FORMAT_LABELS

SUNO_SPATIAL_PRESETS = {
    "声场宽度": {
        PRESET_NONE: "",
        "宽广": "wide stereo, expansive, panoramic",
        "窄场": "mono-ish, narrow stereo, centered",
        "环绕": "immersive, 360-degree, spatial audio",
        "多层空间": "layered reverb, multi-depth, background contrast",
        "紧致": "compact stereo, center-heavy, crushed space",
    },
    "空间距离": {
        PRESET_NONE: "",
        "近场": "intimate, dry vocal, close mic",
        "远场": "reverb-heavy, muffled highs, background",
        "悬浮": "dreamy, weightless, ambient float",
        "突出前景": "present, push forward, crisp",
        "强化后景": "ambient bed, background pad",
    },
    "混响环境": {
        PRESET_NONE: "",
        "干净": "dry signal, upfront, no effects",
        "湿润": "reverb-heavy, ambient wash",
        "房间感": "small room, natural verb",
        "大厅感": "concert hall, lush reverb",
        "教堂感": "reverb tail, sacred, spacious",
        "录音室感": "studio clean, flat room",
        "合成空间": "sci-fi, artificial verb, futuristic echo",
    },
    "立体定位": {
        PRESET_NONE: "",
        "左侧定位": "hard left, stereo panning",
        "右侧定位": "hard right, stereo panning",
        "中央定位": "mono center, main vocal, anchor position",
        "空间移动": "auto-pan, swirling, shifting field",
        "立体声增强": "stereo widener, haas effect, phase delay",
    },
    "空间质感": {
        PRESET_NONE: "",
        "空灵": "bright air, open top end, breathy",
        "密集": "compact, wall of sound, saturated",
        "深邃": "front-back staging, depth perception",
        "光滑空间": "cohesive, polished stereo",
        "空间失真": "broken panning, warped reverb, surreal",
    },
}

COVER_STYLE_PRESETS = {
    "曲风1": {
        PRESET_NONE: "",
        "流行": "pop",
        "国风": "chinese traditional, guofeng",
        "民谣": "folk, acoustic",
        "摇滚": "rock",
        "电子": "electronic",
        "说唱": "hip hop, rap",
        "舞曲": "dance, edm",
        "R&B": "r&b, soul",
    },
    "曲风2": {
        PRESET_NONE: "",
        "抒情": "ballad, emotional",
        "影视感": "cinematic",
        "轻音乐": "light music, easy listening",
        "爵士": "jazz",
        "古典": "classical crossover",
        "氛围": "ambient",
        "朋克": "punk rock",
        "金属": "metal",
    },
    "情绪": {
        PRESET_NONE: "",
        "深情": "emotional, heartfelt",
        "伤感": "sad, melancholic",
        "治愈": "healing, warm",
        "热血": "powerful, passionate",
        "梦幻": "dreamy, ethereal",
        "轻快": "uplifting, bright",
        "浪漫": "romantic",
        "史诗": "epic, grand",
    },
    "人声": {
        PRESET_NONE: "",
        "女声": "female vocal",
        "男声": "male vocal",
        "童声": "child vocal",
        "和声": "layered harmony",
        "气声": "breathy vocal",
        "清亮": "clear vocal",
        "磁性": "warm vocal, rich tone",
    },
    "编曲": {
        PRESET_NONE: "",
        "钢琴主导": "piano driven",
        "吉他主导": "guitar driven",
        "弦乐铺底": "string arrangement",
        "鼓点明显": "strong drums",
        "合成器主导": "synth driven",
        "现场乐队": "live band sound",
        "电影配乐感": "cinematic arrangement",
    },
}

COVER_NEGATIVE_PRESETS = {
    "负面1": {
        PRESET_NONE: "",
        "不要杂音": "noise, distortion, crackle",
        "不要电流声": "electrical buzz, hum",
        "不要跑调": "out of tune, pitchy vocal",
        "不要爆音": "clipping, overload",
        "不要混浊": "muddy mix",
        "不要压缩感过强": "overcompressed, squashed dynamics",
    },
    "负面2": {
        PRESET_NONE: "",
        "不要说唱": "rap",
        "不要嘶吼": "scream vocal, growl",
        "不要过强混响": "excessive reverb",
        "不要机械感": "robotic vocal",
        "不要电子噪声": "harsh digital noise",
        "不要低质伴奏": "low quality backing track",
    },
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_float_text(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return text


def _resolve_model(value: str, mapping: Dict[str, str]) -> str:
    model = mapping.get(_clean_text(value), _clean_text(value))
    if not model:
        raise RuntimeError("model is required")
    return model


def _resolve_value(value: str, mapping: Dict[str, str], field_name: str) -> str:
    resolved = mapping.get(_clean_text(value), _clean_text(value))
    if resolved is None:
        raise RuntimeError(f"{field_name} is required")
    return resolved


def _merge_prompt_parts(parts: List[str]) -> str:
    merged: List[str] = []
    seen = set()
    for part in parts:
        text = _clean_text(part)
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return ", ".join(merged)


def _first_non_empty(item: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_status(payload: Dict[str, Any]) -> str:
    for key in ("status", "state"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "state"):
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _extract_music_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    data = payload.get("data")

    def add_items(value: Any):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidates.append(item)
        elif isinstance(value, dict):
            for key in ("clips", "songs", "musics", "music", "items", "list", "data"):
                nested = value.get(key)
                if isinstance(nested, list):
                    for item in nested:
                        if isinstance(item, dict):
                            candidates.append(item)

    add_items(data)
    if not candidates and isinstance(data, dict):
        add_items(data.get("data"))
    return candidates[:2]


def _extract_result_fields(payload: Dict[str, Any]) -> Dict[str, str]:
    items = _extract_music_items(payload)
    result: Dict[str, str] = {
        "clip_id_1": "",
        "clip_id_2": "",
        "audio_url_1": "",
        "audio_url_2": "",
        "image_url_1": "",
        "image_url_2": "",
        "title_1": "",
        "title_2": "",
    }

    for index, item in enumerate(items, start=1):
        result[f"clip_id_{index}"] = _first_non_empty(item, ["clip_id", "id", "audio_id"])
        result[f"audio_url_{index}"] = _first_non_empty(
            item,
            ["audio_url", "audioUrl", "song_path", "songPath", "media_url", "play_url", "url"],
        )
        result[f"image_url_{index}"] = _first_non_empty(
            item,
            ["image_large_url", "image_url", "imageUrl", "cover_url", "coverUrl"],
        )
        result[f"title_{index}"] = _first_non_empty(item, ["title", "name"])

    return result


def _parse_json_response(resp: requests.Response, hint: str) -> Dict[str, Any]:
    text = resp.text
    if resp.status_code >= 400:
        raise RuntimeError(f"{hint} HTTP {resp.status_code}: {text[:500]}")
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"{hint} invalid json: {exc}; body={text[:500]}")


def _submit_music(payload: Dict[str, Any], api_key: str, api_base: str, timeout: int) -> Dict[str, Any]:
    resp = session.post(
        f"{api_base.rstrip('/')}/suno/submit/music",
        headers=http_headers_json(api_key),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno submit failed")


def _fetch_task(task_id: str, api_key: str, api_base: str, timeout: int) -> Dict[str, Any]:
    resp = session.get(
        f"{api_base.rstrip('/')}/suno/fetch/{task_id}",
        headers=http_headers_json(api_key),
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno fetch failed")


def _fetch_tasks_batch(task_ids: List[str], api_key: str, api_base: str, timeout: int) -> Dict[str, Any]:
    resp = session.post(
        f"{api_base.rstrip('/')}/suno/fetch",
        headers=http_headers_json(api_key),
        data=json.dumps({"ids": task_ids}, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno batch fetch failed")


def _resolve_download_dir() -> Path:
    if folder_paths is not None:
        try:
            return Path(folder_paths.get_output_directory()).resolve() / "xlj_suno_audio"
        except Exception:
            pass
    return Path.cwd() / "output" / "xlj_suno_audio"


def _sanitize_filename(text: str) -> str:
    cleaned = _clean_text(text) or "suno_audio"
    for ch in '<>:"/\\|?*':
        cleaned = cleaned.replace(ch, "_")
    return cleaned[:120].strip(" ._") or "suno_audio"


def _fetch_wav_download(task_id_or_clip_id: str, api_key: str, api_base: str, timeout: int):
    resp = session.get(
        f"{api_base.rstrip('/')}/suno/act/wav/{task_id_or_clip_id}",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        timeout=timeout,
    )
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type:
        payload = _parse_json_response(resp, "Suno wav fetch failed")
        data = payload.get("data")
        if isinstance(data, str) and data.strip():
            return {"kind": "url", "value": data.strip()}
        raise RuntimeError(f"Suno wav fetch missing url: {json.dumps(payload, ensure_ascii=False)}")
    if resp.status_code >= 400:
        raise RuntimeError(f"Suno wav fetch failed HTTP {resp.status_code}: {resp.text[:500]}")
    return {"kind": "bytes", "value": resp.content}


def _audio_to_numpy(audio: Dict[str, Any]) -> tuple[np.ndarray, int]:
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])

    try:
        import torch

        if isinstance(waveform, torch.Tensor):
            waveform = waveform.detach().cpu().numpy()
    except Exception:
        pass

    arr = np.asarray(waveform, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim != 2:
        raise RuntimeError(f"unsupported audio waveform shape: {arr.shape}")
    if arr.shape[0] > 2 and arr.shape[1] <= 2:
        arr = arr.T
    if arr.shape[0] not in (1, 2):
        raise RuntimeError(f"unsupported audio channels: {arr.shape}")
    return arr, sample_rate


def _audio_to_wav_bytes(audio: Dict[str, Any]) -> io.BytesIO:
    arr, sample_rate = _audio_to_numpy(audio)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767.0).astype(np.int16)
    interleaved = pcm.T.reshape(-1)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(arr.shape[0])
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(interleaved.tobytes())
    buf.seek(0)
    return buf


def _audio_to_mp3_bytes(audio: Dict[str, Any]) -> io.BytesIO:
    from pydub import AudioSegment

    arr, sample_rate = _audio_to_numpy(audio)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767.0).astype(np.int16)
    interleaved = pcm.T.reshape(-1)

    segment = AudioSegment(
        data=interleaved.tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=arr.shape[0],
    )
    buf = io.BytesIO()
    segment.export(buf, format="mp3", bitrate="192k")
    buf.seek(0)
    return buf


def _encode_audio_bytes(audio: Dict[str, Any], preferred_format: str):
    fmt = _clean_text(preferred_format).lower() or "mp3"
    if fmt == "auto":
        fmt = "mp3"

    if fmt == "mp3":
        try:
            return _audio_to_mp3_bytes(audio), "mp3", "audio/mpeg"
        except Exception:
            return _audio_to_wav_bytes(audio), "wav", "audio/wav"

    if fmt == "wav":
        return _audio_to_wav_bytes(audio), "wav", "audio/wav"

    raise RuntimeError(f"unsupported audio format: {preferred_format}")


def _request_audio_upload(api_key: str, api_base: str, extension: str, timeout: int) -> Dict[str, Any]:
    resp = session.post(
        f"{api_base.rstrip('/')}/suno/uploads/audio",
        headers=http_headers_json(api_key),
        data=json.dumps({"extension": extension}, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno request audio upload failed")


def _extract_upload_auth(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    upload_id = _clean_text(data.get("id") or data.get("upload_id"))
    upload_url = _clean_text(data.get("url") or data.get("upload_url"))
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    if not upload_id or not upload_url:
        raise RuntimeError(f"audio upload auth missing fields: {json.dumps(payload, ensure_ascii=False)}")
    return {"id": upload_id, "url": upload_url, "fields": fields}


def _upload_audio_file(upload_url: str, fields: Dict[str, Any], filename: str, mime_type: str, file_bytes: io.BytesIO, timeout: int):
    upload_fields = {}
    for key, value in fields.items():
        upload_fields[key] = str(value)

    files = {
        "file": (
            filename,
            file_bytes.getvalue(),
            mime_type,
        )
    }
    resp = session.post(upload_url, data=upload_fields, files=files, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Suno audio file upload failed HTTP {resp.status_code}: {resp.text[:500]}")


def _mark_audio_upload_finished(upload_id: str, api_key: str, api_base: str, filename: str, timeout: int):
    resp = session.post(
        f"{api_base.rstrip('/')}/suno/uploads/audio/{upload_id}/upload-finish",
        headers=http_headers_json(api_key),
        data=json.dumps({"upload_type": "file_upload", "upload_filename": filename}, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Suno audio upload finish failed HTTP {resp.status_code}: {resp.text[:500]}")
    if resp.text.strip():
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}
    return {}


def _fetch_audio_upload_status(upload_id: str, api_key: str, api_base: str, timeout: int) -> Dict[str, Any]:
    resp = session.get(
        f"{api_base.rstrip('/')}/suno/uploads/audio/{upload_id}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"} if api_key else {"Accept": "application/json"},
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno audio upload status failed")


def _wait_audio_upload_complete(upload_id: str, api_key: str, api_base: str, poll_interval_sec: int, timeout_sec: int, request_timeout_sec: int) -> Dict[str, Any]:
    deadline = time.time() + int(timeout_sec)
    last_payload: Dict[str, Any] = {}
    while time.time() < deadline:
        payload = _fetch_audio_upload_status(upload_id, api_key, api_base, int(request_timeout_sec))
        status = _clean_text(payload.get("status") or (payload.get("data") or {}).get("status")).lower()
        error_message = _clean_text(payload.get("error_message") or (payload.get("data") or {}).get("error_message"))
        last_payload = payload
        if status in ("complete", "completed", "success"):
            return payload
        if status in ("failed", "failure", "error") or error_message:
            raise RuntimeError(f"Suno audio upload processing failed: {json.dumps(payload, ensure_ascii=False)}")
        time.sleep(int(poll_interval_sec))
    raise RuntimeError(f"Suno audio upload timed out: {json.dumps(last_payload, ensure_ascii=False)}")


def _initialize_audio_clip(upload_id: str, api_key: str, api_base: str, timeout: int) -> Dict[str, Any]:
    resp = session.post(
        f"{api_base.rstrip('/')}/suno/uploads/audio/{upload_id}/initialize-clip",
        headers=http_headers_json(api_key),
        data=b"{}",
        timeout=timeout,
    )
    return _parse_json_response(resp, "Suno initialize audio clip failed")


def _query_task_once(task_id: str, api_key: str, api_base: str, request_timeout_sec: int):
    try:
        payload = _fetch_task(task_id, api_key, api_base, int(request_timeout_sec))
    except RuntimeError as exc:
        if "task_not_exist" not in str(exc):
            raise
        payload = _fetch_tasks_batch([task_id], api_key, api_base, int(request_timeout_sec))
    status = _normalize_status(payload)
    fields = _extract_result_fields(payload)
    raw = json.dumps(payload, ensure_ascii=False)
    return payload, status, fields, raw


def _wait_task(task_id: str, api_key: str, api_base: str, wait: bool, poll_interval_sec: int, timeout_sec: int, request_timeout_sec: int):
    payload, status, fields, raw = _query_task_once(task_id, api_key, api_base, request_timeout_sec)
    if not wait:
        return status, fields, raw

    deadline = time.time() + int(timeout_sec)
    last_status = status
    last_fields = fields
    last_raw = raw

    while time.time() < deadline:
        if last_status in TASK_DONE and (last_fields["audio_url_1"] or last_fields["clip_id_1"]):
            break
        if last_status in TASK_FAILED:
            raise RuntimeError(f"Suno task failed: {last_raw}")
        time.sleep(int(poll_interval_sec))
        _, last_status, last_fields, last_raw = _query_task_once(task_id, api_key, api_base, request_timeout_sec)

    if last_status not in TASK_DONE and not (last_fields["audio_url_1"] or last_fields["clip_id_1"]):
        raise RuntimeError(f"Suno task timed out, last status={last_status}, task_id={task_id}")

    return last_status, last_fields, last_raw


def _format_query_result(task_id: str, status: str, fields: Dict[str, str], raw: str):
    return (
        task_id,
        status,
        fields["clip_id_1"],
        fields["clip_id_2"],
        fields["audio_url_1"],
        fields["audio_url_2"],
        fields["image_url_1"],
        fields["image_url_2"],
        raw,
    )


def _build_text_music_payload(
    mode: str,
    model: str,
    prompt: str,
    title: str,
    tags: str,
    negative_tags: str,
    generation_type: str,
    gpt_description_prompt: str,
    make_instrumental: bool,
    notify_hook: str,
    vocal_gender: str,
):
    payload: Dict[str, Any] = {
        "mv": _resolve_model(model, SUNO_MODEL_MAP),
        "generation_type": _resolve_value(generation_type, SUNO_GENERATION_TYPE_MAP, "generation_type"),
    }

    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    if negative_tags:
        payload["negative_tags"] = negative_tags
    if notify_hook:
        payload["notify_hook"] = notify_hook

    mode = _resolve_value(mode, SUNO_CREATE_MODE_MAP, "mode")
    if mode == "inspire":
        if not gpt_description_prompt:
            raise RuntimeError("gpt_description_prompt is required in inspire mode")
        payload["gpt_description_prompt"] = gpt_description_prompt
        payload["prompt"] = prompt
        payload["make_instrumental"] = bool(make_instrumental)
        return payload

    if mode != "custom":
        raise RuntimeError(f"unsupported mode: {mode}")
    if not prompt:
        raise RuntimeError("prompt is required in custom mode")

    payload["prompt"] = prompt
    payload["make_instrumental"] = bool(make_instrumental)
    metadata: Dict[str, Any] = {"create_mode": "custom"}
    if vocal_gender:
        metadata["vocal_gender"] = _resolve_value(vocal_gender, SUNO_VOCAL_GENDER_MAP, "vocal_gender")
    payload["metadata"] = metadata
    return payload


def _build_cover_payload(
    model: str,
    cover_clip_id: str,
    prompt: str,
    title: str,
    tags: str,
    negative_tags: str,
    generation_type: str,
    continue_clip_id: str,
    continue_at: str,
    continued_aligned_prompt: str,
    infill_start_s: str,
    infill_end_s: str,
    vocal_gender: str,
    notify_hook: str,
):
    if not cover_clip_id:
        raise RuntimeError("cover_clip_id is required")

    payload: Dict[str, Any] = {
        "mv": _resolve_model(model, COVER_MODEL_MAP),
        "task": "cover",
        "cover_clip_id": cover_clip_id,
        "generation_type": _resolve_value(generation_type, SUNO_GENERATION_TYPE_MAP, "generation_type"),
    }

    if prompt:
        payload["prompt"] = prompt
    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    if negative_tags:
        payload["negative_tags"] = negative_tags
    if notify_hook:
        payload["notify_hook"] = notify_hook
    if continue_clip_id:
        payload["continue_clip_id"] = continue_clip_id
    if continue_at:
        payload["continue_at"] = float(continue_at)
    if continued_aligned_prompt:
        payload["continued_aligned_prompt"] = continued_aligned_prompt
    if infill_start_s:
        payload["infill_start_s"] = float(infill_start_s)
    if infill_end_s:
        payload["infill_end_s"] = float(infill_end_s)
    resolved_vocal_gender = _resolve_value(vocal_gender, SUNO_VOCAL_GENDER_MAP, "vocal_gender")
    if resolved_vocal_gender:
        payload["vocal_gender"] = resolved_vocal_gender

    return payload


class XLJSunoCreateMusic:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (SUNO_CREATE_MODES, {"default": "自定义", "tooltip": "自定义=完整歌词；灵感=灵感模式"}),
                "model": (TEXT_MODEL_LABELS, {"default": "v5.5 (chirp-fenix | 最长8分钟)", "tooltip": "Suno 模型版本"}),
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "歌词或提示词"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key 或环境变量 XLJ_API_KEY"}),
            },
            "optional": {
                "title": ("STRING", {"default": "", "tooltip": "歌曲标题"}),
                "tags": ("STRING", {"default": "", "multiline": True, "tooltip": "风格标签，半角逗号分隔"}),
                "negative_tags": ("STRING", {"default": "", "multiline": True, "tooltip": "不想出现的风格标签"}),
                "generation_type": (SUNO_GENERATION_TYPES, {"default": "文本", "tooltip": "生成类型"}),
                "gpt_description_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "灵感模式描述"}),
                "make_instrumental": ("BOOLEAN", {"default": False, "tooltip": "开启后生成纯音乐"}),
                "api_base": ("STRING", {"default": SUNO_BASE_URL, "tooltip": "接口基础地址"}),
                "notify_hook": ("STRING", {"default": "", "tooltip": "可选回调地址"}),
                "vocal_gender": (SUNO_VOCAL_GENDER_LABELS, {"default": "默认", "tooltip": "可选人声性别"}),
                "submit_timeout_sec": ("INT", {"default": 120, "min": 30, "max": 600, "tooltip": "提交超时秒数"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "mode": "模式",
            "model": "模型",
            "prompt": "歌词/提示词",
            "api_key": "API 密钥",
            "title": "歌曲标题",
            "tags": "风格标签",
            "negative_tags": "排除风格",
            "generation_type": "生成类型",
            "gpt_description_prompt": "灵感描述",
            "make_instrumental": "纯音乐",
            "api_base": "接口地址",
            "notify_hook": "回调地址",
            "vocal_gender": "人声性别",
            "submit_timeout_sec": "提交超时(秒)",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "提交状态", "原始响应")
    FUNCTION = "create"
    CATEGORY = "XLJ/Suno"

    def create(
        self,
        mode,
        model,
        prompt,
        api_key="",
        title="",
        tags="",
        negative_tags="",
        generation_type="TEXT",
        gpt_description_prompt="",
        make_instrumental=False,
        api_base=SUNO_BASE_URL,
        notify_hook="",
        vocal_gender="",
        submit_timeout_sec=120,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")

        payload = _build_text_music_payload(
            mode=_clean_text(mode),
            model=_clean_text(model),
            prompt=prompt or "",
            title=_clean_text(title),
            tags=_clean_text(tags),
            negative_tags=_clean_text(negative_tags),
            generation_type=_clean_text(generation_type) or "TEXT",
            gpt_description_prompt=_clean_text(gpt_description_prompt),
            make_instrumental=bool(make_instrumental),
            notify_hook=_clean_text(notify_hook),
            vocal_gender=_clean_text(vocal_gender),
        )

        result = _submit_music(payload, api_key, api_base, int(submit_timeout_sec))
        task_id = _clean_text(result.get("data") or result.get("task_id"))
        status = _clean_text(result.get("code") or result.get("status") or "submitted")
        if not task_id:
            raise RuntimeError(f"submit response missing task_id: {json.dumps(result, ensure_ascii=False)}")
        return (task_id, status, json.dumps(result, ensure_ascii=False))


class XLJSunoPromptPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "声场宽度": (list(SUNO_SPATIAL_PRESETS["声场宽度"].keys()), {"default": PRESET_NONE}),
                "空间距离": (list(SUNO_SPATIAL_PRESETS["空间距离"].keys()), {"default": PRESET_NONE}),
                "混响环境": (list(SUNO_SPATIAL_PRESETS["混响环境"].keys()), {"default": PRESET_NONE}),
                "立体定位": (list(SUNO_SPATIAL_PRESETS["立体定位"].keys()), {"default": PRESET_NONE}),
                "空间质感": (list(SUNO_SPATIAL_PRESETS["空间质感"].keys()), {"default": PRESET_NONE}),
            },
            "optional": {
                "已有标签": ("STRING", {"default": "", "multiline": True, "tooltip": "可选，与你手写的风格标签合并"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {"已有标签": "已有标签"}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("预设英文标签", "合并后标签")
    FUNCTION = "build"
    CATEGORY = "XLJ/Suno"

    def build(self, 已有标签="", **kwargs):
        preset_parts = []
        for group_name, options in SUNO_SPATIAL_PRESETS.items():
            selected = kwargs.get(group_name, PRESET_NONE)
            english = options.get(selected, "")
            if english:
                preset_parts.append(english)

        preset_tags = _merge_prompt_parts(preset_parts)
        merged_tags = _merge_prompt_parts([已有标签, preset_tags])
        return (preset_tags, merged_tags)


class XLJSunoCoverPromptPreset:
    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for group_name, options in COVER_STYLE_PRESETS.items():
            required[group_name] = (list(options.keys()), {"default": PRESET_NONE})
        optional = {
            "补充风格": ("STRING", {"default": "", "multiline": True, "tooltip": "可选补充风格，支持中文备注"}),
        }
        return {"required": required, "optional": optional}

    @classmethod
    def INPUT_LABELS(cls):
        return {"补充风格": "补充风格"}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("预设风格标签", "合并后风格标签")
    FUNCTION = "build"
    CATEGORY = "XLJ/Suno"

    def build(self, 补充风格="", **kwargs):
        parts = []
        for group_name, options in COVER_STYLE_PRESETS.items():
            selected = kwargs.get(group_name, PRESET_NONE)
            english = options.get(selected, "")
            if english:
                parts.append(english)
        preset_tags = _merge_prompt_parts(parts)
        merged_tags = _merge_prompt_parts([补充风格, preset_tags])
        return (preset_tags, merged_tags)


class XLJSunoCoverNegativePreset:
    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for group_name, options in COVER_NEGATIVE_PRESETS.items():
            required[group_name] = (list(options.keys()), {"default": PRESET_NONE})
        optional = {
            "补充排除项": ("STRING", {"default": "", "multiline": True, "tooltip": "可选补充排除标签"}),
        }
        return {"required": required, "optional": optional}

    @classmethod
    def INPUT_LABELS(cls):
        return {"补充排除项": "补充排除项"}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("预设排除标签", "合并后排除标签")
    FUNCTION = "build"
    CATEGORY = "XLJ/Suno"

    def build(self, 补充排除项="", **kwargs):
        parts = []
        for group_name, options in COVER_NEGATIVE_PRESETS.items():
            selected = kwargs.get(group_name, PRESET_NONE)
            english = options.get(selected, "")
            if english:
                parts.append(english)
        preset_tags = _merge_prompt_parts(parts)
        merged_tags = _merge_prompt_parts([补充排除项, preset_tags])
        return (preset_tags, merged_tags)


class XLJSunoUploadAudioToClip:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO", {"tooltip": "连接 LoadAudio 或其他 AUDIO 节点"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key 或环境变量 XLJ_API_KEY"}),
            },
            "optional": {
                "upload_format": (FILE_FORMAT_LABELS, {"default": "MP3", "tooltip": "优先上传格式"}),
                "filename_prefix": ("STRING", {"default": "suno_cover_source", "tooltip": "上传文件名前缀"}),
                "api_base": ("STRING", {"default": SUNO_BASE_URL, "tooltip": "接口基础地址"}),
                "poll_interval_sec": ("INT", {"default": 5, "min": 2, "max": 30, "tooltip": "上传处理轮询间隔"}),
                "timeout_sec": ("INT", {"default": 600, "min": 60, "max": 3600, "tooltip": "上传处理总超时"}),
                "request_timeout_sec": ("INT", {"default": 120, "min": 30, "max": 600, "tooltip": "单次请求超时"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "audio": "参考音频",
            "api_key": "API 密钥",
            "upload_format": "上传格式",
            "filename_prefix": "文件名前缀",
            "api_base": "接口地址",
            "poll_interval_sec": "轮询间隔(秒)",
            "timeout_sec": "总超时(秒)",
            "request_timeout_sec": "单次请求超时(秒)",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("ClipID", "上传ID", "状态")
    FUNCTION = "upload"
    CATEGORY = "XLJ/Suno"
    OUTPUT_NODE = True

    def upload(
        self,
        audio,
        api_key="",
        upload_format="mp3",
        filename_prefix="suno_cover_source",
        api_base=SUNO_BASE_URL,
        poll_interval_sec=5,
        timeout_sec=600,
        request_timeout_sec=120,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")

        upload_format = _resolve_value(upload_format, FILE_FORMAT_MAP, "upload_format")
        file_bytes, extension, mime_type = _encode_audio_bytes(audio, upload_format)
        safe_prefix = _sanitize_filename(filename_prefix)
        filename = f"{safe_prefix}.{extension}"

        auth_payload = _request_audio_upload(api_key, api_base, extension, int(request_timeout_sec))
        auth = _extract_upload_auth(auth_payload)
        upload_id = auth["id"]
        _upload_audio_file(auth["url"], auth["fields"], filename, mime_type, file_bytes, int(request_timeout_sec))
        _mark_audio_upload_finished(upload_id, api_key, api_base, filename, int(request_timeout_sec))
        _wait_audio_upload_complete(
            upload_id=upload_id,
            api_key=api_key,
            api_base=api_base,
            poll_interval_sec=int(poll_interval_sec),
            timeout_sec=int(timeout_sec),
            request_timeout_sec=int(request_timeout_sec),
        )
        clip_payload = _initialize_audio_clip(upload_id, api_key, api_base, int(request_timeout_sec))
        clip_id = _clean_text(
            clip_payload.get("data")
            or clip_payload.get("clip_id")
            or (clip_payload.get("data") or {}).get("clip_id")
        )
        if not clip_id:
            if isinstance(clip_payload.get("data"), dict):
                clip_id = _clean_text(clip_payload["data"].get("id"))
        if not clip_id:
            raise RuntimeError(f"Suno initialize clip missing clip_id: {json.dumps(clip_payload, ensure_ascii=False)}")
        return (clip_id, upload_id, f"uploaded {extension} -> {clip_id}")


class XLJSunoDownloadAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_url": ("STRING", {"default": "", "tooltip": "音频下载链接"}),
            },
            "optional": {
                "clip_id": ("STRING", {"default": "", "tooltip": "下载 wav 时可选填写"}),
                "api_key": ("STRING", {"default": "", "tooltip": "下载 wav 时可用 API key"}),
                "api_base": ("STRING", {"default": SUNO_BASE_URL, "tooltip": "接口基础地址"}),
                "filename_prefix": ("STRING", {"default": "suno", "tooltip": "输出文件名前缀"}),
                "save_format": (FILE_FORMAT_LABELS, {"default": "MP3", "tooltip": "自动=按链接后缀保存"}),
                "request_timeout_sec": ("INT", {"default": 120, "min": 30, "max": 600, "tooltip": "下载超时"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "audio_url": "音频链接",
            "clip_id": "ClipID",
            "api_key": "API 密钥",
            "api_base": "接口地址",
            "filename_prefix": "文件名前缀",
            "save_format": "保存格式",
            "request_timeout_sec": "下载超时(秒)",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("本地文件路径", "最终下载链接", "状态")
    FUNCTION = "download"
    CATEGORY = "XLJ/Suno"
    OUTPUT_NODE = True

    def download(
        self,
        audio_url,
        clip_id="",
        api_key="",
        api_base=SUNO_BASE_URL,
        filename_prefix="suno",
        save_format="mp3",
        request_timeout_sec=120,
    ):
        audio_url = _clean_text(audio_url)
        clip_id = _clean_text(clip_id)
        api_key = env_or(api_key, "XLJ_API_KEY")
        save_format = _resolve_value(save_format, FILE_FORMAT_MAP, "save_format") or "mp3"

        if not audio_url and not clip_id:
            raise RuntimeError("audio_url 或 clip_id 至少需要一个")

        download_url = audio_url
        binary_content = None
        ext = "mp3"

        if save_format == "wav":
            if not clip_id:
                raise RuntimeError("下载 wav 需要 clip_id")
            wav_result = _fetch_wav_download(clip_id, api_key, api_base, int(request_timeout_sec))
            ext = "wav"
            if wav_result["kind"] == "bytes":
                binary_content = wav_result["value"]
                download_url = f"{api_base.rstrip('/')}/suno/act/wav/{clip_id}"
            else:
                download_url = wav_result["value"]
        elif save_format == "auto":
            ext = "wav" if ".wav" in audio_url.lower() else "mp3"

        if binary_content is None:
            if not download_url:
                raise RuntimeError("没有可用的下载链接")
            resp = session.get(download_url, timeout=int(request_timeout_sec))
            if resp.status_code >= 400:
                raise RuntimeError(f"下载音频失败 HTTP {resp.status_code}: {resp.text[:300]}")
            binary_content = resp.content

        out_dir = _resolve_download_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_prefix = _sanitize_filename(filename_prefix)
        file_path = out_dir / f"{safe_prefix}_{stamp}.{ext}"
        file_path.write_bytes(binary_content)
        return (str(file_path), download_url, f"saved {ext} | {file_path}")


class XLJSunoQueryTask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "tooltip": "Suno task ID"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key 或 XLJ_API_KEY"}),
            },
            "optional": {
                "api_base": ("STRING", {"default": SUNO_BASE_URL, "tooltip": "接口基础地址"}),
                "wait": ("BOOLEAN", {"default": True, "tooltip": "等待直到任务完成"}),
                "poll_interval_sec": ("INT", {"default": 15, "min": 5, "max": 90, "tooltip": "轮询间隔"}),
                "timeout_sec": ("INT", {"default": 1800, "min": 60, "max": 7200, "tooltip": "总超时"}),
                "request_timeout_sec": ("INT", {"default": 120, "min": 30, "max": 600, "tooltip": "单次请求超时"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务ID",
            "api_key": "API 密钥",
            "api_base": "接口地址",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔(秒)",
            "timeout_sec": "总超时(秒)",
            "request_timeout_sec": "单次请求超时(秒)",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "任务状态", "歌曲1 ClipID", "歌曲2 ClipID", "歌曲1 音频URL", "歌曲2 音频URL", "歌曲1 封面URL", "歌曲2 封面URL", "原始响应")
    FUNCTION = "query"
    CATEGORY = "XLJ/Suno"
    OUTPUT_NODE = True

    def query(
        self,
        task_id,
        api_key="",
        api_base=SUNO_BASE_URL,
        wait=True,
        poll_interval_sec=15,
        timeout_sec=1800,
        request_timeout_sec=120,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")
        task_id = _clean_text(task_id)
        if not task_id:
            raise RuntimeError("task_id is required")

        status, fields, raw = _wait_task(
            task_id=task_id,
            api_key=api_key,
            api_base=api_base,
            wait=bool(wait),
            poll_interval_sec=int(poll_interval_sec),
            timeout_sec=int(timeout_sec),
            request_timeout_sec=int(request_timeout_sec),
        )
        return _format_query_result(task_id, status, fields, raw)


class XLJSunoCreateMusicAndWait:
    @classmethod
    def INPUT_TYPES(cls):
        create_inputs = XLJSunoCreateMusic.INPUT_TYPES()
        query_optional = XLJSunoQueryTask.INPUT_TYPES()["optional"]
        return {
            "required": create_inputs["required"],
            "optional": {
                **create_inputs["optional"],
                "wait": query_optional["wait"],
                "poll_interval_sec": query_optional["poll_interval_sec"],
                "timeout_sec": query_optional["timeout_sec"],
                "request_timeout_sec": query_optional["request_timeout_sec"],
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        labels = dict(XLJSunoCreateMusic.INPUT_LABELS())
        labels.update(
            {
                "wait": "等待完成",
                "poll_interval_sec": "轮询间隔(秒)",
                "timeout_sec": "总超时(秒)",
                "request_timeout_sec": "单次请求超时(秒)",
            }
        )
        return labels

    RETURN_TYPES = XLJSunoQueryTask.RETURN_TYPES
    RETURN_NAMES = XLJSunoQueryTask.RETURN_NAMES
    FUNCTION = "run"
    CATEGORY = "XLJ/Suno"
    OUTPUT_NODE = True

    def run(self, **kwargs):
        create_optional = XLJSunoCreateMusic.INPUT_TYPES()["optional"].keys()
        create_required = XLJSunoCreateMusic.INPUT_TYPES()["required"].keys()
        create_kwargs = {k: v for k, v in kwargs.items() if k in create_required or k in create_optional}

        task_id, _, _ = XLJSunoCreateMusic().create(**create_kwargs)
        return XLJSunoQueryTask().query(
            task_id=task_id,
            api_key=create_kwargs.get("api_key", ""),
            api_base=create_kwargs.get("api_base", SUNO_BASE_URL),
            wait=kwargs.get("wait", True),
            poll_interval_sec=kwargs.get("poll_interval_sec", 15),
            timeout_sec=kwargs.get("timeout_sec", 1800),
            request_timeout_sec=kwargs.get("request_timeout_sec", 120),
        )


class XLJSunoCreateCover:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (COVER_MODEL_LABELS, {"default": "v3.5 TAU (chirp-v3-5-tau | 翻唱/上传模式)", "tooltip": "翻唱模型"}),
                "cover_clip_id": ("STRING", {"default": "", "tooltip": "要翻唱的原曲 clip_id 或上传音频 clip_id"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API key 或环境变量 XLJ_API_KEY"}),
            },
            "optional": {
                "prompt": ("STRING", {"default": "翻唱歌词", "multiline": True, "tooltip": "翻唱歌词，不填也可尝试仅按参考音频生成"}),
                "title": ("STRING", {"default": "翻唱歌曲", "tooltip": "歌曲标题"}),
                "tags": ("STRING", {"default": "", "multiline": True, "tooltip": "风格标签，可连接中文预设节点"}),
                "negative_tags": ("STRING", {"default": "", "multiline": True, "tooltip": "负面标签，可连接中文排除预设节点"}),
                "generation_type": (SUNO_GENERATION_TYPES, {"default": "文本", "tooltip": "生成类型"}),
                "continue_clip_id": ("STRING", {"default": "", "tooltip": "可选续写来源 clip_id"}),
                "continue_at": ("STRING", {"default": "", "tooltip": "可选续写时间点，单位秒"}),
                "continued_aligned_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "可选对齐提示词"}),
                "infill_start_s": ("STRING", {"default": "", "tooltip": "可选填充开始秒数"}),
                "infill_end_s": ("STRING", {"default": "", "tooltip": "可选填充结束秒数"}),
                "vocal_gender": (SUNO_VOCAL_GENDER_LABELS, {"default": "默认", "tooltip": "可选人声性别"}),
                "api_base": ("STRING", {"default": SUNO_BASE_URL, "tooltip": "接口基础地址"}),
                "notify_hook": ("STRING", {"default": "", "tooltip": "可选回调地址"}),
                "submit_timeout_sec": ("INT", {"default": 120, "min": 30, "max": 600, "tooltip": "提交超时秒数"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model": "翻唱模型",
            "cover_clip_id": "翻唱源 ClipID",
            "api_key": "API 密钥",
            "prompt": "翻唱歌词",
            "title": "歌曲标题",
            "tags": "风格预设/标签",
            "negative_tags": "负面标签",
            "generation_type": "生成类型",
            "continue_clip_id": "续写 ClipID",
            "continue_at": "续写时间(秒)",
            "continued_aligned_prompt": "对齐提示词",
            "infill_start_s": "填充开始(秒)",
            "infill_end_s": "填充结束(秒)",
            "vocal_gender": "人声性别",
            "api_base": "接口地址",
            "notify_hook": "回调地址",
            "submit_timeout_sec": "提交超时(秒)",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "提交状态", "原始响应")
    FUNCTION = "create"
    CATEGORY = "XLJ/Suno"

    def create(
        self,
        model,
        cover_clip_id,
        api_key="",
        prompt="",
        title="",
        tags="",
        negative_tags="",
        generation_type="TEXT",
        continue_clip_id="",
        continue_at="",
        continued_aligned_prompt="",
        infill_start_s="",
        infill_end_s="",
        vocal_gender="",
        api_base=SUNO_BASE_URL,
        notify_hook="",
        submit_timeout_sec=120,
    ):
        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API key is required")

        payload = _build_cover_payload(
            model=_clean_text(model),
            cover_clip_id=_clean_text(cover_clip_id),
            prompt=prompt or "",
            title=_clean_text(title),
            tags=_clean_text(tags),
            negative_tags=_clean_text(negative_tags),
            generation_type=_clean_text(generation_type) or "TEXT",
            continue_clip_id=_clean_text(continue_clip_id),
            continue_at=_clean_float_text(continue_at),
            continued_aligned_prompt=_clean_text(continued_aligned_prompt),
            infill_start_s=_clean_float_text(infill_start_s),
            infill_end_s=_clean_float_text(infill_end_s),
            vocal_gender=_clean_text(vocal_gender),
            notify_hook=_clean_text(notify_hook),
        )

        result = _submit_music(payload, api_key, api_base, int(submit_timeout_sec))
        task_id = _clean_text(result.get("data") or result.get("task_id"))
        status = _clean_text(result.get("code") or result.get("status") or "submitted")
        if not task_id:
            raise RuntimeError(f"submit response missing task_id: {json.dumps(result, ensure_ascii=False)}")
        return (task_id, status, json.dumps(result, ensure_ascii=False))


class XLJSunoCreateCoverAndWait:
    @classmethod
    def INPUT_TYPES(cls):
        create_inputs = XLJSunoCreateCover.INPUT_TYPES()
        query_optional = XLJSunoQueryTask.INPUT_TYPES()["optional"]
        return {
            "required": create_inputs["required"],
            "optional": {
                **create_inputs["optional"],
                "wait": query_optional["wait"],
                "poll_interval_sec": query_optional["poll_interval_sec"],
                "timeout_sec": query_optional["timeout_sec"],
                "request_timeout_sec": query_optional["request_timeout_sec"],
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        labels = dict(XLJSunoCreateCover.INPUT_LABELS())
        labels.update(
            {
                "wait": "等待完成",
                "poll_interval_sec": "轮询间隔(秒)",
                "timeout_sec": "总超时(秒)",
                "request_timeout_sec": "单次请求超时(秒)",
            }
        )
        return labels

    RETURN_TYPES = XLJSunoQueryTask.RETURN_TYPES
    RETURN_NAMES = XLJSunoQueryTask.RETURN_NAMES
    FUNCTION = "run"
    CATEGORY = "XLJ/Suno"
    OUTPUT_NODE = True

    def run(self, **kwargs):
        create_optional = XLJSunoCreateCover.INPUT_TYPES()["optional"].keys()
        create_required = XLJSunoCreateCover.INPUT_TYPES()["required"].keys()
        create_kwargs = {k: v for k, v in kwargs.items() if k in create_required or k in create_optional}

        task_id, _, _ = XLJSunoCreateCover().create(**create_kwargs)
        return XLJSunoQueryTask().query(
            task_id=task_id,
            api_key=create_kwargs.get("api_key", ""),
            api_base=create_kwargs.get("api_base", SUNO_BASE_URL),
            wait=kwargs.get("wait", True),
            poll_interval_sec=kwargs.get("poll_interval_sec", 15),
            timeout_sec=kwargs.get("timeout_sec", 1800),
            request_timeout_sec=kwargs.get("request_timeout_sec", 120),
        )
