# ComfyUI-XLJ-api

AI API 的 ComfyUI 节点插件。

API 站点支持国内和海外两个站点，默认使用海外站点。

导入工作流后，通常只需要填写 `api_key` 就可以直接使用。

## 功能

- Grok 视频生成
- Veo3 文生视频 / 图生视频
- Sora2 图生视频
- ViduQ 文生视频 / 图生视频
- Banana 图像生成 / 多轮对话编辑
- Seedream 即梦图像生成
- GPT-Image 图像生成 (gpt-image-2)
- GPT-Image-2.5 图像生成 (仅海外站点)
- 账号中控：浏览器登录一次，一键创建/查询 API 密钥
- GPT 文本处理
- 视频反推 (VideoReverse)
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

- 节点中提供“海外站点”和“国内站点”两个选项，默认使用“海外站点”
- GPT 文本和 GPT-Image 节点可以直接切换 API 站点
- 也可以通过环境变量 `XLJ_API_BASE` 统一设置 API 地址
- 使用前请先准备对应站点可用的 `api_key`

## API Key 配置

支持三种方式：

1. 在节点的 `api_key` 参数中直接填写
2. 设置环境变量 `XLJ_API_KEY`
3. 在插件目录创建 `.env` 文件：

```env
XLJ_API_KEY=your_api_key_here
XLJ_API_BASE=https://your-api-base.example.com
```

## 密钥中控面板

节点 `XLJ 密钥中控面板`（分类 `XLJ/账号`）可以一站式完成登录和建密钥：

1. 选择「海外站点」或「国内站点」
2. 在面板里填账号和密码，点「登录」，插件会弹出本机浏览器打开站点登录页
3. 在浏览器里完成验证码并点登录，回到 ComfyUI 面板会自动显示已登录
4. 选择模型（例如 `gpt-image-2.5-flare-c`），点「生成密钥」
5. 密钥会显示在面板的 API_KEY 框里，并记成当前密钥；其它节点的 `api_key` 留空时会自动使用它，
   也可以把面板的 `API_KEY` 输出端口连到下游节点的 `api_key` 输入

面板上还有一个「历史密钥」下拉，列出账号里已有的密钥（按当前模型排序，格式是
`模型 | 名称 | sk-xxxx`），选中就直接填进 API_KEY，不用每次重新生成。分组不正常的旧密钥会标
「⚠分组异常」，提示重新生成。

创建密钥时会自动选择分组（站点关闭智能路由后分组必填）：`gpt-image` 系列默认走 `Gpt-Image-1`，
其它模型取账号可用分组里的第一个。面板上的分组下拉会列出账号实际可用的分组，标了「支持当前模型」
的是该模型能用的分组，也可以手动指定。

一个分组通常覆盖多个图像模型（例如 `Gpt-Image-1` 覆盖 3 个图像模型）。把「模型」选成
`该分组支持的图像模型`，生成的密钥会一次性绑定该分组覆盖的全部图像模型，一个 key 就能通吃这个组；
选「不限制」则完全不限制模型，由分组决定可用范围。

登录会话保存在插件目录的 `.auth/` 下（已加入 `.gitignore`），之后运行会复用，不需要反复登录。
浏览器登录依赖 Playwright，插件在首次点击「登录」时会自动安装（约 40MB，只需一次）；
如果自动安装失败，可以手动执行：

```bash
python -m pip install playwright
```

插件使用系统已安装的 Edge 或 Chrome，不需要额外下载浏览器内核。

## 示例工作流

仓库 `workflows/` 目录包含可直接导入的示例：

- `grok+图生视频-API调用.json`
- `sora2+图生视频-API调用.json`
- `veo3+图生视频-API调用.json`
- `viduq+图生视频-API调用.json`
- `banana+参考图出图-API调用.json`
- `seedream+文生图-API调用.json`
- `seedream+参考图出图-API调用.json`
- `gpt-image-2+文生图-API调用.json`
- `gpt-image-2+图生图-API调用.json`
- `gpt-image-2.5+文生图-API调用.json`
- `gpt-image-2.5+图生图-API调用.json`
- `账号中控+创建密钥-API调用.json`（密钥中控面板）
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

- `XLJSeedreamTextToImage` - 文生图
- `XLJSeedreamImageToImage` - 图生图（支持多张参考图）

### GPT

- `XLJGPTTextProcessor`
- `XLJGPTImageTextToImage` - 文生图
- `XLJGPTImageImageToImage` - 图生图/参考图生成

### Utils

- `XLJUploadToImageHost`
- `XLJDownloadVideo`
- `XLJCSVBatchReader`

### MiniMax H3 官方直连

- `XLJMiniMaxH3UploadVideo` - MiniMax H3 专用视频图床，输出公网视频 URL 和源视频时长
- `XLJMiniMaxH3ContextIR` - 使用 MiniMax 官方 H3 Context-IR API 验证 Key，并生成增强后的最终 prompt
- `XLJMiniMaxH3Regenerate2K` - 使用 Context-IR 输出对符合 H3 768P 规格的视频进行 2K 再生成；API Key 由 Context 输出携带，节点本身不再填写 Key

推荐连接：

```text
CreateVideo -> XLJMiniMaxH3UploadVideo -> XLJMiniMaxH3Regenerate2K -> SaveVideo
                                  \-> XLJMiniMaxH3ContextIR -/
```

`XLJMiniMaxH3ContextIR` 的 `duration` 必须对应源视频时长，并且官方只允许 4~15 秒；纯文本输入时 `ratio` 不能使用 `adaptive`。2K 再生成不是通用视频超分，只支持 MiniMax H3 官方生成的 768P 视频。

## 支持模型

### Grok

- `grok-imagine-video`
- `grok-imagine-video-1.5-preview`

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
- `doubao-seedream-5-0-lite-260128`
- `doubao-seedream-4-0-250828`
- `doubao-seedream-4-5-251128`
- `doubao-seededit-3-0-i2i-250628`
- `doubao-seedream-3-0-t2i-250415`

### GPT

- `gpt-5.4`
- `gpt-5.4-pro`
- `gpt-5.4-nano`

### GPT-Image

- `gpt-image-2` - 文生图/图生图

### GPT-Image-2.5

仅在海外站点提供，节点固定使用海外端点，不需要选择 API 站点。

- `gpt-image-2.5-flare-c` - 均衡低延迟，适合批量快速出图
- `gpt-image-2.5-sunburst-c` - 高精度，细节和提示词还原更强
- `XLJGPTImage25TextToImage` - 文生图
- `XLJGPTImage25ImageToImage` - 图生图

## 常见问题

### 节点不显示

重启 ComfyUI，并检查控制台是否出现 `[ComfyUI-XLJ-api]` 日志。

### 工作流导入后不能运行

先确认插件版本是最新的，并确认 API 站点与 API Key 匹配。

### API 调用失败

先检查 `api_key` 是否正确，再检查网络连接是否正常。

## 仓库

- GitHub: `https://github.com/weiqing1987/ComfyUI-XLJ-api`
- API Website: 请在节点中选择对应站点

## License

MIT
