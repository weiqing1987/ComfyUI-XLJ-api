"""
生成 xlj_utils.py 的哈希值
用于验证文件完整性，防止 API 地址被篡改

使用方法：python hash_generator.py
"""

import hashlib
import json
from pathlib import Path

utils_path = Path(__file__).parent / "nodes" / "xlj_utils.py"
config_path = Path(__file__).parent / "config.json"

# 计算哈希
with open(utils_path, 'r', encoding='utf-8') as f:
    content = f.read()

sha256_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

print(f"xlj_utils.py SHA256: {sha256_hash}")

# 更新 config.json
if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config['file_integrity']['xlj_utils.py']['hash'] = sha256_hash

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n已更新 config.json 中的哈希值")
else:
    print(f"\n警告：找不到 config.json，请手动创建配置文件")

print(f"\n下次启动 ComfyUI 时将使用新哈希值进行验证")
