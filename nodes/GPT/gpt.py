"""
GPT 文本处理节点 - 信陵君 AI
支持 txt/md/pdf/docx 文档读取和 GPT 文案处理

使用方法：
1. 将文档放入 ComfyUI/input/documents/ 目录（没有就自己建）
2. 在文档下拉框中选择文件
3. 连接到 GPT 文本处理器处理
"""

import os
import json
import re
import typing
import hashlib
import requests
from pathlib import Path

import folder_paths

from ..xlj_utils import env_or, http_headers_json, API_BASE

# 禁用代理
session = requests.Session()
session.trust_env = False

# GPT 模型列表
GPT_MODELS = [
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-nano",
]

# 支持的文档格式
DOC_EXTENSIONS = ('.txt', '.md', '.markdown', '.csv', '.json', '.xml',
                  '.html', '.htm', '.log', '.pdf', '.docx', '.doc',
                  '.epub', '.rtf')

# 系统提示词默认值
DEFAULT_SYSTEM_PROMPT = """你是一个专业的文案编辑和内容处理助手。
请仔细阅读用户提供的文档内容，然后按照以下要求处理：
1. 提取文档的核心内容和关键信息
2. 保持原文的主要观点和逻辑结构
3. 输出清晰、易读的文案格式
4. 如果文档有明确的用途（如报告、文章、说明等），请按相应格式整理输出"""


def get_document_input_dir() -> str:
    """获取文档目录"""
    doc_dir = os.path.join(folder_paths.get_input_directory(), "documents")
    os.makedirs(doc_dir, exist_ok=True)
    return doc_dir


def list_document_files() -> list[str]:
    """列出文档目录中的所有文档文件"""
    doc_dir = get_document_input_dir()
    try:
        files = [f for f in os.listdir(doc_dir)
                 if os.path.isfile(os.path.join(doc_dir, f))
                 and f.lower().endswith(DOC_EXTENSIONS)]
        return sorted(files)
    except Exception:
        return []


def read_text_file(file_path: str) -> str:
    """读取文本文件"""
    for enc in ('utf-8', 'gbk', 'latin-1'):
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(file_path, 'r', encoding='latin-1') as f:
        return f.read()


def read_pdf_file(file_path: str) -> str:
    """读取 PDF 文件"""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        if text_parts:
            return '\n\n---\n\n'.join(text_parts)
    except ImportError:
        pass
    except Exception as e:
        print(f"[ComfyUI-XLJ-api] 信陵君 GPT pdfplumber 读取失败：{e}")

    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        if text_parts:
            return '\n\n---\n\n'.join(text_parts)
    except ImportError:
        pass
    except Exception as e:
        print(f"[ComfyUI-XLJ-api] 信陵君 GPT PyPDF2 读取失败：{e}")

    raise RuntimeError(
        "无法读取 PDF 文件。请安装：pip install pdfplumber"
    )


def read_docx_file(file_path: str) -> str:
    """读取 Word 文档"""
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        if paragraphs:
            return '\n\n'.join(paragraphs)
    except ImportError:
        pass
    except Exception as e:
        print(f"[ComfyUI-XLJ-api] 信陵君 GPT python-docx 读取失败：{e}")

    raise RuntimeError(
        "无法读取 DOCX 文件。请安装：pip install python-docx"
    )


def read_document(file_path: str) -> tuple[str, dict]:
    """根据文件类型读取文档"""
    if not os.path.exists(file_path):
        raise RuntimeError(f"文件不存在：{file_path}")

    ext = Path(file_path).suffix.lower()

    if ext in ['.txt', '.md', '.markdown', '.csv', '.json', '.xml', '.html', '.htm', '.log']:
        text = read_text_file(file_path)
    elif ext == '.pdf':
        text = read_pdf_file(file_path)
    elif ext in ['.docx', '.doc']:
        text = read_docx_file(file_path)
    elif ext == '.epub':
        text = read_epub_file(file_path)
    elif ext == '.rtf':
        text = read_text_file(file_path)
    else:
        raise RuntimeError(f"不支持的文件类型：{ext}，支持 {', '.join(sorted(DOC_EXTENSIONS))}")

    file_size = os.path.getsize(file_path)
    return text, {
        "file_name": Path(file_path).name,
        "file_type": ext.lstrip('.').upper(),
        "file_size": f"{file_size / 1024:.1f} KB" if file_size > 1024 else f"{file_size} B",
        "char_count": len(text),
    }


def read_epub_file(file_path: str) -> str:
    """读取 EPUB 电子书"""
    try:
        from ebooklib import epub
        from ebooklib.epub import EpubHtml
        import html as html_mod
        book = epub.read_epub(file_path)
        text_parts = []
        for item in book.get_items():
            if isinstance(item, EpubHtml):
                content = item.get_content().decode('utf-8', errors='ignore')
                clean = re.sub(r'<[^>]+>', '', content)
                clean = html_mod.unescape(clean).strip()
                if clean:
                    text_parts.append(clean)
        if text_parts:
            return '\n\n---\n\n'.join(text_parts)
    except ImportError:
        pass
    except Exception as e:
        print(f"[ComfyUI-XLJ-api] 信陵君 GPT ebooklib 读取失败：{e}")

    raise RuntimeError("无法读取 EPUB 文件。请安装：pip install ebooklib")


def chunk_text(text: str, max_chars: int = 200000) -> list[str]:
    """将超长文本按段落边界切分"""
    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r'(\n\n+)', text)
    chunks = []
    current = ""

    for part in paragraphs:
        if len(current) + len(part) > max_chars:
            if current.strip():
                chunks.append(current.strip())
            current = part
        else:
            current += part

    if current.strip():
        chunks.append(current.strip())

    final_chunks = []
    for chunk in chunks:
        if len(chunk) > max_chars:
            for i in range(0, len(chunk), max_chars):
                final_chunks.append(chunk[i:i + max_chars])
        else:
            final_chunks.append(chunk)

    return final_chunks


class XLJDocumentLoader:
    """文档加载节点 - 从 input/documents/ 目录加载文档

    使用方法：
    1. 打开 ComfyUI 安装目录下的 input 文件夹
    2. 如果没有 documents 文件夹，新建一个
    3. 把你的 txt/md/pdf/docx 文件复制进去
    4. 在下方下拉框中选择文件
    """

    @classmethod
    def INPUT_TYPES(cls):
        doc_files = list_document_files()
        if not doc_files:
            doc_files = ["[将文件放入 input/documents/ 目录后刷新]"]
        return {
            "required": {
                "document": (doc_files, {
                    "tooltip": "选择要加载的文档文件（需先放入 input/documents/ 目录）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {"document": "文档"}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("文档内容", "文件信息", "字符数")
    FUNCTION = "load"
    CATEGORY = "XLJ/GPT"

    def load(self, document):
        if not document or document.startswith("[将") or not document.strip():
            raise RuntimeError(
                "请将文档文件放入 ComfyUI/input/documents/ 目录\n"
                "支持格式: txt, md, pdf, docx, epub, csv 等"
            )

        doc_dir = get_document_input_dir()
        file_path = os.path.join(doc_dir, document)

        if not os.path.exists(file_path):
            raise RuntimeError(f"文件不存在：{document}")

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 读取文件：{file_path}")
        try:
            doc_content, meta = read_document(file_path)
        except Exception as e:
            raise RuntimeError(f"读取文档失败：{str(e)}")

        if not doc_content or not doc_content.strip():
            raise RuntimeError("文档内容为空")

        file_info = (
            f"文件名: {meta['file_name']} | "
            f"类型: {meta['file_type']} | "
            f"大小: {meta['file_size']}"
        )
        char_count = str(meta["char_count"])

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 文档加载成功：{meta['file_name']} ({meta['char_count']} 字符)")

        return (doc_content, file_info, char_count)

    @classmethod
    def IS_CHANGED(cls, document):
        if not document or document.startswith("[将"):
            return ""
        doc_dir = get_document_input_dir()
        file_path = os.path.join(doc_dir, document)
        if os.path.exists(file_path):
            m = hashlib.sha256()
            with open(file_path, 'rb') as f:
                m.update(f.read())
            return m.digest().hex()
        return ""

    @classmethod
    def VALIDATE_INPUTS(cls, document):
        if not document or document.startswith("[将"):
            return "请先将文档放入 input/documents/ 目录"
        doc_dir = get_document_input_dir()
        file_path = os.path.join(doc_dir, document)
        if not os.path.exists(file_path):
            return f"文件不存在：{document}"
        return True


class XLJGPTTextProcessor:
    """GPT 文本处理节点 - 处理文档并输出文案

    使用方式：
    1. 从 XLJDocumentLoader 节点接入「文档内容」到 text_input
    2. 或直接在 用户提示词 中输入/粘贴文本

    gpt-5.4 系列支持 1M 上下文窗口（约几十万字），小说级别的文档无需分段
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (GPT_MODELS, {
                    "default": GPT_MODELS[0],
                    "tooltip": "选择 GPT 模型"
                }),
                "system_prompt": ("STRING", {
                    "default": DEFAULT_SYSTEM_PROMPT,
                    "multiline": True,
                    "tooltip": "系统提示词 - 指导 AI 如何处理文档"
                }),
                "user_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "用户提示词 - 直接输入文本内容，或留空从 text_input 接入"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 XLJ_API_KEY）"
                }),
            },
            "optional": {
                "text_input": ("STRING", {
                    "default": "",
                    "tooltip": "从文档加载器接入的内容（优先级高于 user_prompt）"
                }),
                "extra_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "额外提示，附加在文档之后"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "温度"
                }),
                "max_tokens": ("INT", {
                    "default": 8000,
                    "min": 100,
                    "max": 128000,
                    "tooltip": "最大输出 token"
                }),
                "enable_chunking": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "分段处理超长文本（一般不需要）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model_name": "模型",
            "system_prompt": "系统提示词",
            "user_prompt": "用户提示词",
            "api_key": "API 密钥",
            "text_input": "文本输入(文档)",
            "extra_prompt": "额外提示",
            "temperature": "温度",
            "max_tokens": "最大 Token",
            "enable_chunking": "启用分段"
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("输出文案", "状态信息")
    FUNCTION = "process"
    CATEGORY = "XLJ/GPT"
    OUTPUT_NODE = True

    def process(self, model_name, system_prompt, user_prompt, api_key="",
                text_input="", extra_prompt="",
                temperature=0.7, max_tokens=8000, enable_chunking=False):

        api_key = env_or(api_key, "XLJ_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 XLJ_API_KEY")

        # 获取文本：text_input 优先，否则用 user_prompt
        if text_input and text_input.strip():
            doc_content = text_input.strip()
            doc_source = "文档加载器"
        elif user_prompt and user_prompt.strip():
            doc_content = user_prompt.strip()
            doc_source = "用户提示词"
        else:
            raise RuntimeError("请在 用户提示词 中输入文本，或从文档加载器接入 text_input")

        doc_length = len(doc_content)
        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 来源: {doc_source} | 长度: {doc_length} 字符")

        chunks = chunk_text(doc_content) if enable_chunking else [doc_content]

        if len(chunks) > 1:
            print(f"[ComfyUI-XLJ-api] 信陵君 GPT 分段处理：{len(chunks)} 个片段")
            return self._process_chunks(model_name, system_prompt, api_key,
                                        chunks, extra_prompt, temperature, max_tokens, doc_length)

        return self._process_single(model_name, system_prompt, api_key, doc_content,
                                    extra_prompt, temperature, max_tokens, doc_length)

    def _process_single(self, model_name, system_prompt, api_key, doc_content,
                        extra_prompt, temperature, max_tokens, doc_length):
        user_content = f"以下是文档内容：\n\n---\n{doc_content}\n---\n"
        if extra_prompt and extra_prompt.strip():
            user_content += f"\n\n额外要求：{extra_prompt.strip()}"

        endpoint = f"{API_BASE}/v1/chat/completions"
        headers = http_headers_json(api_key)

        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 模型={model_name} | 长度={doc_length}")

        resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=300)

        if resp.status_code >= 400:
            try:
                err_data = json.loads(resp.text)
                err_msg = err_data.get("error", {}).get("message", resp.text[:200])
            except Exception:
                err_msg = f"HTTP {resp.status_code} - {resp.text[:200]}"
            raise RuntimeError(f"GPT 处理失败：{err_msg}")

        data = json.loads(resp.text)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("API 返回 choices 为空")

        output_text = choices[0].get("message", {}).get("content", "")
        if not output_text:
            raise RuntimeError("API 返回内容为空")

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        status_info = (
            f"模型: {model_name} | "
            f"输入: {prompt_tokens} tokens | "
            f"输出: {completion_tokens} tokens | "
            f"文档: {doc_length} 字符"
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 成功 | 输出: {len(output_text)} 字符")
        return (output_text, status_info)

    def _process_chunks(self, model_name, system_prompt, api_key, chunks,
                        extra_prompt, temperature, max_tokens, doc_length):
        chunk_prompt = (system_prompt.strip() if system_prompt else "") + \
                       "\n\n注意：这是长文档的一部分，请只处理当前内容。"

        all_outputs = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for i, chunk in enumerate(chunks):
            chunk_label = f"第 {i+1}/{len(chunks)} 部分"
            print(f"[ComfyUI-XLJ-api] 信陵君 GPT {chunk_label} ({len(chunk)} 字符)...")

            user_content = f"以下是文档{chunk_label}：\n\n---\n{chunk}\n---\n"
            if extra_prompt and extra_prompt.strip():
                user_content += f"\n\n额外要求：{extra_prompt.strip()}"

            messages = []
            if chunk_prompt:
                messages.append({"role": "system", "content": chunk_prompt})
            messages.append({"role": "user", "content": user_content})

            endpoint = f"{API_BASE}/v1/chat/completions"
            headers = http_headers_json(api_key)
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            }

            resp = session.post(endpoint, headers=headers, data=json.dumps(payload), timeout=300)
            data = json.loads(resp.text)

            output_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)

            if output_text:
                all_outputs.append(f"--- {chunk_label} ---\n{output_text}")

        combined = "\n\n".join(all_outputs)
        status_info = (
            f"模型: {model_name} | 分段: {len(chunks)} | "
            f"输入: {total_prompt_tokens} tokens | 输出: {total_completion_tokens} tokens | "
            f"文档: {doc_length} 字符"
        )

        print(f"[ComfyUI-XLJ-api] 信陵君 GPT 分段完成 | 输出: {len(combined)} 字符")
        return (combined, status_info)


NODE_CLASS_MAPPINGS = {
    "XLJDocumentLoader": XLJDocumentLoader,
    "XLJGPTTextProcessor": XLJGPTTextProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJDocumentLoader": "📄 XLJ 文档加载器",
    "XLJGPTTextProcessor": "📝 XLJ GPT 文本处理器",
}
