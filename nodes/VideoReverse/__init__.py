"""
VideoReverse 视频反推节点 - 信陵君 AI
使用 Gemini 2.5 Pro 分析视频并生成 Seedance 提示词
"""

import io
import json
import base64
import os
import tempfile
import requests
from pathlib import Path
from typing import List, Optional

# 禁用代理
session = requests.Session()
session.trust_env = False

# Seedance 系统提示词
SEEDANCE_SYSTEM_PROMPT = """You are an expert video analysis AI specialized in creating detailed prompts for Seedance video generation model.

## Your Task
Analyze the provided video and generate a comprehensive prompt that can be used to recreate a similar video using Seedance.

## Output Format
Generate your response in the following structured format:

### SCENE DESCRIPTION
[Detailed description of the main scene/setting]

### CAMERA WORK
- Movement Type: [static/zoom in/zoom out/pan left/pan right/tilt up/tilt down/tracking shot/aerial view/dolly shot/crane shot]
- Movement Speed: [slow/medium/fast]
- Movement Direction: [description of camera motion direction]

### SUBJECT
- Main Subject: [detailed description of primary subject(s)]
- Appearance: [clothing, colors, textures, physical features]
- Position: [where in frame, composition]

### ACTION & MOTION
- Primary Action: [main movement or action in the video]
- Motion Quality: [smooth/jerky/graceful/energetic/subtle]
- Speed: [very slow/slow/moderate/fast/very fast]
- Temporal Flow: [how the action progresses over time]

### ENVIRONMENT
- Setting: [location, background elements]
- Lighting: [natural/artificial, direction, quality - golden hour/overhead/dramatic/soft/harsh]
- Atmosphere: [mood, weather, time of day]
- Color Palette: [dominant colors and color mood]

### STYLE
- Visual Style: [cinematic/documentary/anime/realistic/3D render/vintage/modern]
- Film Quality: [4K/HD/grainy/clean/vintage film look]
- Aspect Ratio Suggestion: [16:9/9:16/1:1/21:9]

### AUDIOVISUAL ELEMENTS
- Sound Impression: [ambient sounds, music mood if apparent]
- Rhythm: [editing pace, beats per minute feel]

### FINAL SEEDANCE PROMPT
[Combine all above elements into a single, optimized prompt for Seedance. Use this structure:
"[Camera movement] shot of [subject description], [action/motion], [environment/setting], [lighting], [style/mood]"

Example output format:
"A slow zoom in on a woman with flowing red hair standing on a cliff at sunset, wind gently moving her dress, cinematic lighting, peaceful atmosphere, golden hour, 4K quality"

IMPORTANT GUIDELINES:
1. Be specific and concrete - avoid abstract concepts
2. Use visual descriptors that Seedance can understand
3. Include temporal words for motion (slowly, gracefully, rapidly)
4. Keep the final prompt between 50-150 words
5. Prioritize the most visually impactful elements
6. Use professional filmmaking terminology
7. Describe what you actually SEE, not what you infer"""

SEEDANCE_SYSTEM_PROMPT_SIMPLE = """You are a video analysis expert. Analyze the video and create a prompt for Seedance video generation.

Output a single optimized prompt following this structure:
"[Camera movement] of [subject] [action] in [environment], [lighting], [style]"

Include:
- Camera: zoom in/out, pan, tracking, aerial, static
- Subject: detailed visual description
- Action: what's happening, motion quality
- Environment: setting, background
- Lighting: golden hour, cinematic, soft, dramatic
- Style: cinematic, realistic, documentary, etc.

Be specific and visual. 50-150 words."""


class XLJVideoReverse:
    """视频反推节点 - 分析视频生成 Seedance 提示词"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "视频文件路径或 URL"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Gemini API 密钥"
                }),
            },
            "optional": {
                "model": (["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"], {
                    "default": "gemini-2.5-pro",
                    "tooltip": "选择 Gemini 模型"
                }),
                "system_prompt_type": (["detailed", "simple"], {
                    "default": "detailed",
                    "tooltip": "系统提示词类型：detailed（详细分析）或 simple（简洁输出）"
                }),
                "custom_system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "自定义系统提示词（留空使用默认）"
                }),
                "user_prompt": ("STRING", {
                    "default": "Please analyze this video and generate a Seedance prompt.",
                    "multiline": True,
                    "tooltip": "用户提示词"
                }),
                "max_frames": ("INT", {
                    "default": 10,
                    "min": 1,
                    "max": 100,
                    "tooltip": "最大提取帧数（用于长视频）"
                }),
                "frame_interval": ("INT", {
                    "default": 30,
                    "min": 1,
                    "max": 300,
                    "tooltip": "帧提取间隔（每隔多少帧提取一帧）"
                }),
                "max_video_duration": ("INT", {
                    "default": 60,
                    "min": 5,
                    "max": 600,
                    "tooltip": "视频最大分析时长（秒），超时将分段处理"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "生成温度"
                }),
                "api_base": ("STRING", {
                    "default": "https://generativelanguage.googleapis.com",
                    "tooltip": "Gemini API 地址"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "video_path": "视频路径/URL",
            "api_key": "API 密钥",
            "model": "模型",
            "system_prompt_type": "提示词类型",
            "custom_system_prompt": "自定义系统提示词",
            "user_prompt": "用户提示词",
            "max_frames": "最大帧数",
            "frame_interval": "帧间隔",
            "max_video_duration": "最大时长(秒)",
            "temperature": "温度",
            "api_base": "API 地址"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("Seedance 提示词", "详细分析", "帧数信息", "原始响应")
    FUNCTION = "analyze"
    CATEGORY = "XLJ/VideoReverse"
    OUTPUT_NODE = True

    def analyze(self, video_path, api_key, model="gemini-2.5-pro",
                system_prompt_type="detailed", custom_system_prompt="",
                user_prompt="Please analyze this video and generate a Seedance prompt.",
                max_frames=10, frame_interval=30, max_video_duration=60,
                temperature=0.7, api_base="https://generativelanguage.googleapis.com"):
        """分析视频并生成 Seedance 提示词"""

        if not api_key:
            raise RuntimeError("API Key 未配置")

        if not video_path or not video_path.strip():
            raise RuntimeError("视频路径不能为空")

        # 选择系统提示词
        if custom_system_prompt and custom_system_prompt.strip():
            system_prompt = custom_system_prompt.strip()
        elif system_prompt_type == "detailed":
            system_prompt = SEEDANCE_SYSTEM_PROMPT
        else:
            system_prompt = SEEDANCE_SYSTEM_PROMPT_SIMPLE

        # 判断是 URL 还是本地文件
        video_url = None
        local_path = None

        if video_path.startswith("http://") or video_path.startswith("https://"):
            video_url = video_path
            print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 处理远程视频: {video_url}")
        else:
            local_path = Path(video_path)
            if not local_path.exists():
                raise RuntimeError(f"视频文件不存在: {video_path}")
            print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 处理本地视频: {local_path}")

        # 获取视频信息并提取帧
        frames_info = ""
        video_parts = []

        try:
            if video_url:
                # 直接使用 URL
                video_parts = self._prepare_video_from_url(video_url, api_key, api_base)
                frames_info = f"Video URL: {video_url}"
            else:
                # 本地文件
                video_parts, frames_info = self._prepare_video_from_local(
                    str(local_path), max_frames, frame_interval, max_video_duration
                )
        except Exception as e:
            print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 警告：视频准备失败，尝试直接上传: {e}")
            if local_path:
                video_parts = self._upload_video_direct(str(local_path), api_key, api_base)
                frames_info = f"Direct upload: {local_path.name}"

        # 调用 Gemini API
        result = self._call_gemini_api(
            api_key=api_key,
            api_base=api_base,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            video_parts=video_parts,
            temperature=temperature
        )

        # 解析结果
        seedance_prompt = self._extract_seedance_prompt(result)
        detailed_analysis = result

        print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 分析完成")
        print(f"[ComfyUI-XLJ-api] 信陵君 Seedance 提示词: {seedance_prompt[:100]}...")

        return (seedance_prompt, detailed_analysis, frames_info, result)

    def _prepare_video_from_url(self, video_url: str, api_key: str, api_base: str) -> list:
        """准备远程视频（使用 Gemini 的 file API）"""
        # 对于 Gemini，可以直接使用 URL 或需要先上传
        # 这里返回 URL 格式的 part
        return [{"text": f"Video URL: {video_url}"}]

    def _prepare_video_from_local(self, video_path: str, max_frames: int,
                                   frame_interval: int, max_duration: int) -> tuple:
        """从本地视频提取帧"""
        try:
            import cv2
        except ImportError:
            raise RuntimeError("需要安装 opencv-python: pip install opencv-python")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 视频信息: FPS={fps}, 总帧数={total_frames}, 时长={duration:.1f}s")

        # 提取帧
        frames = []
        frame_count = 0
        extracted_count = 0

        while extracted_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                # 转换为 base64
                _, buffer = cv2.imencode('.jpg', frame)
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                frames.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": frame_base64
                    }
                })
                extracted_count += 1
                print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 提取帧 {extracted_count}/{max_frames}")

            frame_count += 1

            # 检查时长限制
            if frame_count / fps > max_duration:
                print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 达到时长限制 {max_duration}s")
                break

        cap.release()

        frames_info = f"提取帧数: {len(frames)}/{max_frames}, 原始时长: {duration:.1f}s, FPS: {fps:.1f}"
        return frames, frames_info

    def _upload_video_direct(self, video_path: str, api_key: str, api_base: str) -> list:
        """直接上传视频文件到 Gemini"""
        # 读取视频文件
        with open(video_path, 'rb') as f:
            video_data = f.read()

        video_base64 = base64.b64encode(video_data).decode('utf-8')

        # 获取 MIME 类型
        mime_type = "video/mp4"
        if video_path.lower().endswith(".webm"):
            mime_type = "video/webm"
        elif video_path.lower().endswith(".mov"):
            mime_type = "video/quicktime"

        return [{
            "inline_data": {
                "mime_type": mime_type,
                "data": video_base64
            }
        }]

    def _call_gemini_api(self, api_key: str, api_base: str, model: str,
                         system_prompt: str, user_prompt: str,
                         video_parts: list, temperature: float) -> str:
        """调用 Gemini API"""

        endpoint = f"{api_base}/v1beta/models/{model}:generateContent?key={api_key}"

        # 构建 contents
        parts = video_parts.copy()
        parts.append({"text": user_prompt})

        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096
            },
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            }
        }

        headers = {"Content-Type": "application/json"}

        print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 调用 Gemini API: {model}")

        try:
            resp = session.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=300  # 5分钟超时
            )

            if resp.status_code >= 400:
                error_text = resp.text
                try:
                    err_data = json.loads(error_text)
                    err_msg = err_data.get("error", {}).get("message", error_text)
                except:
                    err_msg = error_text
                raise RuntimeError(f"Gemini API 错误: {err_msg}")

            data = resp.json()
            candidates = data.get("candidates", [])

            if not candidates:
                raise RuntimeError("Gemini API 返回空响应")

            # 提取文本
            result_text = ""
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    result_text += part["text"]

            return result_text

        except requests.exceptions.Timeout:
            raise RuntimeError("Gemini API 请求超时")
        except Exception as e:
            raise RuntimeError(f"Gemini API 调用失败: {str(e)}")

    def _extract_seedance_prompt(self, analysis: str) -> str:
        """从分析结果中提取 Seedance 提示词"""
        # 尝试提取 FINAL SEEDANCE PROMPT 部分
        import re

        # 查找 "### FINAL SEEDANCE PROMPT" 后的内容
        pattern = r'###\s*FINAL\s+SEEDANCE\s+PROMPT\s*\n(.+?)(?=###|$)'
        match = re.search(pattern, analysis, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # 如果没有找到特定格式，返回整个分析（取前500字符）
        return analysis.strip()


class XLJVideoReverseBatch:
    """批量视频反推节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_paths": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频路径列表（每行一个）"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Gemini API 密钥"
                }),
            },
            "optional": {
                "model": (["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"], {
                    "default": "gemini-2.5-pro"
                }),
                "system_prompt_type": (["detailed", "simple"], {
                    "default": "simple"
                }),
                "delay_between_requests": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 60,
                    "tooltip": "请求间隔（秒）"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("提示词列表", "处理报告")
    FUNCTION = "analyze_batch"
    CATEGORY = "XLJ/VideoReverse"
    OUTPUT_NODE = True

    def analyze_batch(self, video_paths, api_key, model="gemini-2.5-pro",
                      system_prompt_type="simple", delay_between_requests=2):
        """批量分析视频"""

        import time

        if not api_key:
            raise RuntimeError("API Key 未配置")

        paths = [p.strip() for p in video_paths.strip().split('\n') if p.strip()]

        if not paths:
            raise RuntimeError("视频路径列表为空")

        results = []
        reports = []

        single_node = XLJVideoReverse()

        for i, path in enumerate(paths):
            print(f"[ComfyUI-XLJ-api] 信陵君 VideoReverse 批量处理 {i+1}/{len(paths)}: {path}")

            try:
                prompt, analysis, frames_info, raw = single_node.analyze(
                    video_path=path,
                    api_key=api_key,
                    model=model,
                    system_prompt_type=system_prompt_type
                )
                results.append(f"[{i+1}] {path}\n{prompt}")
                reports.append(f"[{i+1}] 成功: {path}")
            except Exception as e:
                results.append(f"[{i+1}] {path}\n错误: {str(e)}")
                reports.append(f"[{i+1}] 失败: {path} - {str(e)}")

            # 延迟
            if i < len(paths) - 1 and delay_between_requests > 0:
                time.sleep(delay_between_requests)

        return ("\n\n---\n\n".join(results), "\n".join(reports))


NODE_CLASS_MAPPINGS = {
    "XLJVideoReverse": XLJVideoReverse,
    "XLJVideoReverseBatch": XLJVideoReverseBatch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJVideoReverse": "🎬 XLJ 视频反推 (Seedance)",
    "XLJVideoReverseBatch": "📦 XLJ 视频反推批量",
}