import { app } from "../../../scripts/app.js";

const EXTENSION_NAME = "comfyui_xlj_suno.labels";

const LABEL_MAP = {
    XLJSunoCreateMusic: {
        mode: "模式",
        model: "模型",
        prompt: "歌词/提示词",
        api_key: "API 密钥",
        title: "歌曲标题",
        tags: "风格标签",
        negative_tags: "排除风格",
        generation_type: "生成类型",
        gpt_description_prompt: "灵感描述",
        make_instrumental: "纯音乐",
        api_base: "接口地址",
        notify_hook: "回调地址",
        vocal_gender: "人声性别",
        submit_timeout_sec: "提交超时(秒)",
    },
    XLJSunoCreateMusicAndWait: {
        mode: "模式",
        model: "模型",
        prompt: "歌词/提示词",
        api_key: "API 密钥",
        title: "歌曲标题",
        tags: "风格标签",
        negative_tags: "排除风格",
        generation_type: "生成类型",
        gpt_description_prompt: "灵感描述",
        make_instrumental: "纯音乐",
        api_base: "接口地址",
        notify_hook: "回调地址",
        vocal_gender: "人声性别",
        submit_timeout_sec: "提交超时(秒)",
        wait: "等待完成",
        poll_interval_sec: "轮询间隔(秒)",
        timeout_sec: "总超时(秒)",
        request_timeout_sec: "单次请求超时(秒)",
    },
    XLJSunoCreateCover: {
        model: "翻唱模型",
        cover_clip_id: "翻唱源 ClipID",
        api_key: "API 密钥",
        prompt: "翻唱歌词",
        title: "歌曲标题",
        tags: "风格预设/标签",
        negative_tags: "负面标签",
        generation_type: "生成类型",
        continue_clip_id: "续写 ClipID",
        continue_at: "续写时间(秒)",
        continued_aligned_prompt: "对齐提示词",
        infill_start_s: "填充开始(秒)",
        infill_end_s: "填充结束(秒)",
        vocal_gender: "人声性别",
        api_base: "接口地址",
        notify_hook: "回调地址",
        submit_timeout_sec: "提交超时(秒)",
    },
    XLJSunoCreateCoverAndWait: {
        model: "翻唱模型",
        cover_clip_id: "翻唱源 ClipID",
        api_key: "API 密钥",
        prompt: "翻唱歌词",
        title: "歌曲标题",
        tags: "风格预设/标签",
        negative_tags: "负面标签",
        generation_type: "生成类型",
        continue_clip_id: "续写 ClipID",
        continue_at: "续写时间(秒)",
        continued_aligned_prompt: "对齐提示词",
        infill_start_s: "填充开始(秒)",
        infill_end_s: "填充结束(秒)",
        vocal_gender: "人声性别",
        api_base: "接口地址",
        notify_hook: "回调地址",
        submit_timeout_sec: "提交超时(秒)",
        wait: "等待完成",
        poll_interval_sec: "轮询间隔(秒)",
        timeout_sec: "总超时(秒)",
        request_timeout_sec: "单次请求超时(秒)",
    },
    XLJSunoUploadAudioToClip: {
        audio: "参考音频",
        api_key: "API 密钥",
        upload_format: "上传格式",
        filename_prefix: "文件名前缀",
        api_base: "接口地址",
        poll_interval_sec: "轮询间隔(秒)",
        timeout_sec: "总超时(秒)",
        request_timeout_sec: "单次请求超时(秒)",
    },
    XLJSunoDownloadAudio: {
        audio_url: "音频链接",
        clip_id: "ClipID",
        api_key: "API 密钥",
        api_base: "接口地址",
        filename_prefix: "文件名前缀",
        save_format: "保存格式",
        request_timeout_sec: "下载超时(秒)",
    },
    XLJSunoQueryTask: {
        task_id: "任务ID",
        api_key: "API 密钥",
        api_base: "接口地址",
        wait: "等待完成",
        poll_interval_sec: "轮询间隔(秒)",
        timeout_sec: "总超时(秒)",
        request_timeout_sec: "单次请求超时(秒)",
    },
    XLJSunoPromptPreset: {
        "已有标签": "已有标签",
    },
    XLJSunoCoverPromptPreset: {
        "补充风格": "补充风格",
    },
    XLJSunoCoverNegativePreset: {
        "补充排除项": "补充排除项",
    },
};

function applyNodeLabels(node) {
    if (!node || !node.type) {
        return;
    }

    const labels = LABEL_MAP[node.type];
    if (!labels) {
        return;
    }

    for (const input of node.inputs || []) {
        const label = labels[input.name];
        if (label) {
            input.label = label;
        }
    }

    for (const widget of node.widgets || []) {
        const label = labels[widget.name];
        if (label) {
            widget.label = label;
        }
    }

    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: EXTENSION_NAME,
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!LABEL_MAP[nodeData?.name]) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            applyNodeLabels(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            applyNodeLabels(this);
            return result;
        };
    },
    setup() {
        const refresh = () => {
            for (const node of app.graph?._nodes || []) {
                applyNodeLabels(node);
            }
        };

        queueMicrotask(refresh);
        setTimeout(refresh, 200);
        setTimeout(refresh, 1000);
    },
});
