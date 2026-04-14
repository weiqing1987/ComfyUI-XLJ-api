# ComfyUI-XLJ-api

信陵君 AI API 的 ComfyUI 节点插件。

API 站点：`https://xinlingjunai.cn/`

导入工作流后，通常只需要填写 `api_key` 就可以直接使用。

## 功能

- Grok 视频生成
- Veo3 文生视频 / 图生视频
- Sora2 图生视频
- ViduQ 文生视频 / 图生视频
- Banana 图像生成 / 多轮对话编辑
- Seedream 即梦图像生成
- GPT 文本处理
- 查询任务状态
- 一键等待完成
- 视频下载与预览
- CSV 批量处理

## 安装

1. 将 `ComfyUI-XLJ-api` 复制到 `ComfyUI/custom_nodes/ComfyUI-XLJ-api`
2. 安装依赖：

```bash
cd ComfyUI-XLJ-api
pip install -r requirements.txt
```

3. 重启 ComfyUI

## API 站点

- API 网站：`https://xinlingjunai.cn/`
- 使用前请先准备可用的 `api_key`
- 节点里的 `api_base` 请按你的实际接口配置填写

## API Key 配置

支持三种方式：

1. 在节点的 `api_key` 参数中直接填写
2. 设置环境变量 `XLJ_API_KEY`
3. 在插件目录创建 `.env` 文件：

```env
XLJ_API_KEY=your_api_key_here
```

## 示例工作流

仓库 `workflows/` 目录包含可直接导入的示例：

- `grok+图生视频-API调用.json`
- `sora2+图生视频-API调用.json`
- `veo3+图生视频-API调用.json`
- `viduq+图生视频-API调用.json`
- `banana+参考图出图-API调用.json`
- `seedream+参考图出图-API调用.json`
- `gpt+文本处理-API调用.json`

## 节点列表

### Grok

- `XLJGrokCreateVideo`
- `XLJGrokQueryVideo`
- `XLJGrokCreateAndWait`
- `XLJGrokBatchProcessor`

### Veo3

- `XLJVeoText2Video`
- `XLJVeoImage2Video`
- `XLJVeoQueryTask`
- `XLJVeoText2VideoAndWait`
- `XLJVeoImage2VideoAndWait`

### Sora2

- `XLJSoraCreateVideo`
- `XLJSoraQueryTask`
- `XLJSoraCreateAndWait`

### ViduQ

- `XLJViduQCreateVideo`
- `XLJViduQQueryVideo`
- `XLJViduQCreateAndWait`

### Banana

- `XLJBananaCreateImage`
- `XLJBananaMultiTurnChat`

### Seedream

- `XLJSeedreamCreateImage`

### GPT

- `XLJGPTTextProcessor`

### Utils

- `XLJUploadToImageHost`
- `XLJDownloadVideo`
- `XLJCSVBatchReader`

## 支持模型

### Grok

- `grok-video-3`
- `grok-video-3-10s`

### Veo3

- `veo3.1`
- `veo3`
- `veo3-fast`
- `veo3-pro`
- `veo_3_1-fast`
- `veo_3_1-fast-fl`
- `veo_3_1-4K`
- `veo_3_1-fast-4K`
- `veo_3_1-fast-components-4K`

### Sora2

- `sora-2`
- `sora-2-pro`
- `sora-2-all`
- `sora-2-pro-all`

### ViduQ

- `viduq2`
- `viduq2-pro`
- `viduq2-turbo`
- `viduq3-pro`

### Banana

- `gemini-3-pro-image-preview`
- `gemini-2.5-flash-image`
- `gemini-3.1-flash-image-preview`

### Seedream (即梦)

- `doubao-seedream-5-0-260128`
- `doubao-seedream-4-0-250828`
- `doubao-seedream-4-5-251128`
- `doubao-seededit-3-0-i2i-250628`
- `doubao-seedream-3-0-t2i-250415`

### GPT

- `gpt-5.4`
- `gpt-5.4-pro`
- `gpt-5.4-nano`

## 常见问题

### 节点不显示

重启 ComfyUI，并检查控制台是否出现 `[ComfyUI-XLJ-api]` 日志。

### 工作流导入后不能运行

先确认插件版本是最新的，并确认 API 站点使用的是 `https://xinlingjunai.cn/`。

### API 调用失败

先检查 `api_key` 是否正确，再检查网络连接是否正常。

## 仓库

- GitHub: `https://github.com/weiqing1987/ComfyUI-XLJ-api`
- API Website: `https://xinlingjunai.cn/`

## License

MIT
