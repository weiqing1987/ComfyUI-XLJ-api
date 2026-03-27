# CLAUDE.md - ComfyUI-XLJ-api 开发指南

## 项目概述

**ComfyUI-XLJ-api** 是信陵君 AI API 的 ComfyUI 节点插件

## 项目结构

```
ComfyUI-XLJ-api/
├── __init__.py              # 主入口，自动注册节点
├── README.md                # 用户文档
├── requirements.txt         # 依赖
├── nodes/
│   ├── xlj_utils.py         # 共享工具函数
│   ├── Grok/
│   │   ├── __init__.py
│   │   ├── grok.py          # Grok 视频生成节点
│   │   └── batch_processor.py  # Grok 批量处理器
│   ├── Veo3/
│   │   ├── __init__.py
│   │   └── veo3.py          # Veo3 视频生成节点
│   ├── Sora2/
│   │   ├── __init__.py
│   │   └── sora2.py         # Sora2 视频生成节点
│   ├── ViduQ/
│   │   ├── __init__.py
│   │   └── viduq.py         # ViduQ 视频生成节点
│   └── Utils/
│       ├── __init__.py      # 工具节点（上传、下载、CSV 读取）
│       └── csv_reader.py
└── examples/                # 示例文件（可选）
```

## 开发规范

### 1. API 地址锁定

所有节点必须使用 `API_BASE` 常量，定义在 `nodes/xlj_utils.py`：
```python
from ..xlj_utils import API_BASE  # 值为 "https://xinlingjunai.cn"
```

### 2. 日志前缀

所有打印日志使用统一前缀：
```python
print(f"[ComfyUI-XLJ-api] 信陵君 - 描述信息")
```

### 3. 节点结构

每个节点类遵循标准模式：
```python
class XLJNodeName:
    @classmethod
    def INPUT_TYPES(cls): ...

    @classmethod
    def INPUT_LABELS(cls): ...  # 中文标签

    RETURN_TYPES = (...)
    RETURN_NAMES = (...)  # 中文名称
    FUNCTION = "execute"
    CATEGORY = "XLJ/CategoryName"

    def execute(self, ...): ...
```

### 4. 注册节点

在类别的 `__init__.py` 中注册：
```python
NODE_CLASS_MAPPINGS = {
    "XLJNodeName": XLJNodeName,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJNodeName": "🎬 XLJ 显示名称",
}
```

### 5. Emoji 前缀约定

- 🎬 视频生成节点
- 🖼️ 图片相关
- 🔍 查询节点
- ⚡ 一键/快速节点
- 📦 批量处理
- 📷 上传图片
- 📥 下载
- 📄 CSV 读取

## API 端点

```
POST /v1/video/create     # 创建视频任务
GET  /v1/video/query      # 查询任务状态
POST /v1/upload           # 上传图片
```

## 错误处理

- 使用 `RuntimeError` 抛出用户友好错误
- 网络连接错误自动重试 3 次
- 错误信息包含详细上下文

## 测试

```bash
# 验证节点加载
cd ComfyUI-XLJ-api
python -c "import sys; sys.path.insert(0, '.'); from nodes.xlj_utils import API_BASE; print(API_BASE)"
```
