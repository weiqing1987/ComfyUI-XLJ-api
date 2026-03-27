"""ComfyUI-XLJ-api 多节点"""

import importlib
from pathlib import Path

# 节点映射
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

def auto_register_nodes():
    """自动扫描并注册 nodes 目录下的所有节点"""
    nodes_dir = Path(__file__).parent / "nodes"

    if not nodes_dir.exists():
        return

    # 遍历子目录（Grok, Veo3, Sora2, ViduQ, Utils）
    for category_dir in nodes_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith("_"):
            continue

        # 检查是否有 __init__.py
        init_file = category_dir / "__init__.py"
        if init_file.exists():
            try:
                module_path = f".nodes.{category_dir.name}"
                mod = importlib.import_module(module_path, package=__name__)
                cls_map = getattr(mod, "NODE_CLASS_MAPPINGS", {})
                name_map = getattr(mod, "NODE_DISPLAY_NAME_MAPPINGS", {})
                NODE_CLASS_MAPPINGS.update(cls_map)
                NODE_DISPLAY_NAME_MAPPINGS.update(name_map)
                print(f"[ComfyUI-XLJ-api] Loaded {len(cls_map)} nodes from {category_dir.name}")
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] Failed to load {category_dir.name}: {e}")
                import traceback
                traceback.print_exc()

# 自动注册所有节点
auto_register_nodes()

# 前端扩展
WEB_DIRECTORY = None

# 导出
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

print(f"[ComfyUI-XLJ-api] Total loaded: {len(NODE_CLASS_MAPPINGS)} nodes")
print(f"[ComfyUI-XLJ-api] Nodes: {list(NODE_CLASS_MAPPINGS.keys())}")
