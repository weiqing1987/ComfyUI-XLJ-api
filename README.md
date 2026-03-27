# ComfyUI-XLJ-api

**信陵君 AI API ComfyUI 节点插件**

## 功能特性

- 🎬 **Grok 视频生成** - 支持文本生成视频、图片生成视频
- 🚀 **Veo3 视频生成** - 支持文生视频、图生视频
- 🎥 **Sora2 视频生成** - 支持多图片生成视频
- 🎬 **ViduQ 视频生成** - 支持文本/图片生成视频
- 🔍 **任务查询** - 查询视频生成任务状态
- ⚡ **一键生成** - 创建任务并自动等待完成
- 🔄 **自动重试** - 网络连接失败自动重试 3 次
- 📦 **批量处理** - 支持 CSV 批量任务处理

## 安装

1. 将 `ComfyUI-XLJ-api` 文件夹复制到 ComfyUI 的 `custom_nodes` 目录：
   ```
   桌面/ComfyUI-XLJ-api -> ComfyUI/custom_nodes/ComfyUI-XLJ-api
   ```

2. 安装依赖：
   ```bash
   cd ComfyUI-XLJ-api
   pip install -r requirements.txt
   ```

3. 重启 ComfyUI

## API Key 配置

有三种方式配置 API Key：

1. **节点参数**：在每个节点的 `api_key` 字段中直接填写
2. **环境变量**：设置 `XLJ_API_KEY` 环境变量
3. **.env 文件**：在插件目录创建 `.env` 文件，内容为：
   ```
   XLJ_API_KEY=your_api_key_here
   ```

## 节点列表

### Grok 视频生成

| 节点名称 | 功能 | 分类 |
|---------|------|------|
| 🎬 XLJ Grok 创建视频 | 创建视频生成任务 | XLJ/Grok |
| 🔍 XLJ Grok 查询任务 | 查询任务状态 | XLJ/Grok |
| ⚡ XLJ Grok 一键生成 | 创建并等待完成 | XLJ/Grok |
| 📦 XLJ Grok 批量处理器 | CSV 批量处理 | XLJ/Grok |

### Veo3 视频生成

| 节点名称 | 功能 | 分类 |
|---------|------|------|
| 🎬 XLJ Veo 文生视频 | 文本生成视频 | XLJ/Veo3 |
| 🖼️ XLJ Veo 图生视频 | 图片生成视频 | XLJ/Veo3 |
| 🔍 XLJ Veo 查询任务 | 查询任务状态 | XLJ/Veo3 |
| ⚡ XLJ Veo 一键文生视频 | 文生视频并等待 | XLJ/Veo3 |
| ⚡ XLJ Veo 一键图生视频 | 图生视频并等待 | XLJ/Veo3 |

### Sora2 视频生成

| 节点名称 | 功能 | 分类 |
|---------|------|------|
| 🎬 XLJ Sora2 创建视频 | 创建视频生成任务 | XLJ/Sora2 |
| 🔍 XLJ Sora2 查询任务 | 查询任务状态 | XLJ/Sora2 |
| ⚡ XLJ Sora2 一键生成 | 创建并等待完成 | XLJ/Sora2 |

### ViduQ 视频生成

| 节点名称 | 功能 | 分类 |
|---------|------|------|
| 🎬 XLJ ViduQ 创建视频 | 创建视频生成任务 | XLJ/ViduQ |
| 🔍 XLJ ViduQ 查询任务 | 查询任务状态 | XLJ/ViduQ |
| ⚡ XLJ ViduQ 一键生成 | 创建并等待完成 | XLJ/ViduQ |

### Utils 工具

| 节点名称 | 功能 | 分类 |
|---------|------|------|
| 📷 XLJ 上传图片 | 上传图片到图床 | XLJ/Utils |
| 📥 XLJ 下载视频 | 下载视频到本地 | XLJ/Utils |
| 📄 XLJ CSV 批量读取 | 读取 CSV 批量任务 | XLJ/Utils |

## 支持的模型

### Grok
- `grok-video-3` - 标准版
- `grok-video-3-10s` - 10 秒版

### Veo3
- `veo3.1` - Veo 3.1
- `veo3` - Veo 3
- `veo3-fast` - Veo 3 快速版
- `veo3-pro` - Veo 3 专业版
- `veo_3_1-fast` - Veo 3.1 快速版
- `veo_3_1-fast-fl` - Veo 3.1 快速流式版
- `veo_3_1-4K` - Veo 3.1 4K 版
- `veo_3_1-fast-4K` - Veo 3.1 快速 4K 版
- `veo_3_1-fast-components-4K` - Veo 3.1 快速组件 4K 版

### Sora2
- `sora-2` - Sora 2 标准版
- `sora-2-pro` - Sora 2 专业版
- `sora-2-all` - Sora 2 全能版
- `sora-2-pro-all` - Sora 2 专业全能版

### ViduQ
- `viduq2` - ViduQ 2
- `viduq2-pro` - ViduQ 2 专业版
- `viduq2-turbo` - ViduQ 2 加速版
- `viduq3-pro` - ViduQ 3 专业版

## 常见问题

### Q: 节点不显示？
A: 重启 ComfyUI，查看控制台是否有 `[ComfyUI-XLJ-api]` 日志

### Q: API 调用失败？
A: 检查 API Key 是否正确，网络连接是否正常

### Q: 网络连接错误？
A: 节点已内置自动重试机制，会重试 3 次

## 技术支持

- 问题反馈：GitHub Issues

## 许可证

MIT License
