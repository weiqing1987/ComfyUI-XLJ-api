"""CSV 批量读取节点 - 信陵君 AI"""

import csv
import os
import json

try:
    import folder_paths
    HAS_FOLDER_PATHS = True
except ImportError:
    HAS_FOLDER_PATHS = False


class XLJCSVBatchReader:
    """CSV 批量任务读取器"""

    @classmethod
    def INPUT_TYPES(cls):
        csv_files = []
        if HAS_FOLDER_PATHS:
            try:
                input_dir = folder_paths.get_input_directory()
                if os.path.exists(input_dir):
                    csv_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.csv')])
            except Exception as e:
                print(f"[ComfyUI-XLJ-api] 无法读取 input 目录：{e}")

        return {
            "required": {},
            "optional": {
                "csv_file": (csv_files if csv_files else [""], {"tooltip": "从 input 目录选择 CSV 文件"}),
                "csv_path": ("STRING", {"default": "", "multiline": False, "tooltip": "或输入完整路径"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("批量任务数据",)
    FUNCTION = "read_csv"
    CATEGORY = "XLJ/Utils"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "csv_file": "CSV 文件",
            "csv_path": "文件路径",
        }

    def read_csv(self, csv_file="", csv_path=""):
        """读取 CSV 文件并返回 JSON 格式的任务列表"""
        file_path = None

        if csv_file and csv_file.strip() and HAS_FOLDER_PATHS:
            try:
                input_dir = folder_paths.get_input_directory()
                file_path = os.path.join(input_dir, csv_file)
            except:
                pass

        if not file_path and csv_path and csv_path.strip():
            file_path = csv_path.strip()

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("CSV 文件不存在，请将文件放到 input 目录或输入完整路径")

        tasks = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                task = dict(row)
                task['_row_number'] = idx
                tasks.append(task)

        if not tasks:
            raise RuntimeError("CSV 文件为空或格式不正确")

        print(f"[ComfyUI-XLJ-api] 信陵君 - 已读取 {len(tasks)} 个任务")
        return (json.dumps(tasks, ensure_ascii=False))


NODE_CLASS_MAPPINGS = {
    "XLJCSVBatchReader": XLJCSVBatchReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJCSVBatchReader": "📄 XLJ CSV 批量读取",
}
