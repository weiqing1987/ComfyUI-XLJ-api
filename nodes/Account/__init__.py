"""
XLJ 账号中控节点。
"""

from .account_panel import XLJApiKeyPanel

NODE_CLASS_MAPPINGS = {
    "XLJApiKeyPanel": XLJApiKeyPanel,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XLJApiKeyPanel": "XLJ 密钥中控面板",
}
