import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const EXTENSION_NAME = "comfyui_xlj_gpt.runtime_status";
const TARGET_NODE_TYPES = new Set(["XLJGPTImageImageToImage"]);
const STATUS_EVENT = "comfyui_xlj_gpt_status";

const runtimeStateByNodeId = new Map();
let tickerHandle = null;
let styleInjected = false;

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function formatElapsed(seconds) {
    const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
    return `${safe.toFixed(1)}s`;
}

function getNodeById(nodeId) {
    if (!app.graph) {
        return null;
    }
    return app.graph.getNodeById(nodeId);
}

function isTargetNode(node) {
    return !!node && TARGET_NODE_TYPES.has(node.type);
}

function injectStatusBarStyle() {
    if (styleInjected || document.getElementById("xlj-runtime-status-style")) {
        styleInjected = true;
        return;
    }

    const style = document.createElement("style");
    style.id = "xlj-runtime-status-style";
    style.textContent = `
        .xlj-runtime-statusbar {
            box-sizing: border-box;
            width: 100%;
            min-height: 46px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 12px;
            padding: 8px 12px;
            display: flex;
            flex-direction: column;
            gap: 7px;
            background: rgba(255, 255, 255, 0.03);
            color: #e8e8e8;
            font-size: 13px;
            pointer-events: none;
        }

        .xlj-runtime-statusbar .xlj-runtime-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .xlj-runtime-statusbar .xlj-runtime-icon {
            width: 14px;
            height: 14px;
            border-radius: 999px;
            border: 2px solid rgba(255, 255, 255, 0.35);
            border-top-color: #ffffff;
            flex-shrink: 0;
        }

        .xlj-runtime-statusbar .xlj-runtime-label {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .xlj-runtime-statusbar .xlj-runtime-percent {
            font-variant-numeric: tabular-nums;
            font-weight: 700;
            color: #f6f6f6;
            flex-shrink: 0;
        }

        .xlj-runtime-statusbar .xlj-runtime-track {
            width: 100%;
            height: 7px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.14);
            overflow: hidden;
            position: relative;
        }

        .xlj-runtime-statusbar .xlj-runtime-fill {
            height: 100%;
            width: 0%;
            border-radius: 999px;
            background: linear-gradient(90deg, #7ec8ff 0%, #c6e7ff 100%);
            transition: width 0.18s linear;
        }

        .xlj-runtime-statusbar[data-state="running"] .xlj-runtime-icon {
            animation: xlj-spin 0.9s linear infinite;
            border-top-color: #9bd7ff;
        }

        .xlj-runtime-statusbar[data-state="running"] .xlj-runtime-fill {
            background-image:
                linear-gradient(90deg, #6bc3ff 0%, #b8e1ff 100%),
                repeating-linear-gradient(
                    -45deg,
                    rgba(255, 255, 255, 0.16) 0,
                    rgba(255, 255, 255, 0.16) 8px,
                    rgba(255, 255, 255, 0.04) 8px,
                    rgba(255, 255, 255, 0.04) 16px
                );
            background-blend-mode: overlay;
            background-size: auto, 26px 26px;
            animation: xlj-stripes 1s linear infinite;
        }

        .xlj-runtime-statusbar[data-state="success"] .xlj-runtime-icon {
            animation: none;
            border-color: #55d589;
            background: radial-gradient(circle, #55d589 35%, transparent 36%);
        }

        .xlj-runtime-statusbar[data-state="success"] .xlj-runtime-fill {
            background: linear-gradient(90deg, #38c172 0%, #77e8a5 100%);
        }

        .xlj-runtime-statusbar[data-state="error"] .xlj-runtime-icon {
            animation: none;
            border-color: #ff7171;
            background: radial-gradient(circle, #ff7171 35%, transparent 36%);
        }

        .xlj-runtime-statusbar[data-state="error"] .xlj-runtime-fill {
            background: linear-gradient(90deg, #f56565 0%, #ff8f8f 100%);
        }

        .xlj-runtime-statusbar[data-state="idle"] .xlj-runtime-icon {
            animation: none;
        }

        @keyframes xlj-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        @keyframes xlj-stripes {
            from { background-position: 0 0, 0 0; }
            to { background-position: 0 0, 26px 0; }
        }
    `;

    document.head.appendChild(style);
    styleInjected = true;
}

function ensureStatusWidget(node) {
    if (node.__xljRuntimeStatusWidget) {
        return node.__xljRuntimeStatusWidget;
    }

    injectStatusBarStyle();

    const element = document.createElement("div");
    element.className = "xlj-runtime-statusbar";
    element.dataset.state = "idle";

    const row = document.createElement("div");
    row.className = "xlj-runtime-row";
    element.appendChild(row);

    const icon = document.createElement("span");
    icon.className = "xlj-runtime-icon";
    row.appendChild(icon);

    const label = document.createElement("span");
    label.className = "xlj-runtime-label";
    label.textContent = "等待执行";
    row.appendChild(label);

    const percent = document.createElement("span");
    percent.className = "xlj-runtime-percent";
    percent.textContent = "0%";
    row.appendChild(percent);

    const track = document.createElement("div");
    track.className = "xlj-runtime-track";
    element.appendChild(track);

    const fill = document.createElement("div");
    fill.className = "xlj-runtime-fill";
    track.appendChild(fill);

    const widget = node.addDOMWidget(
        "runtime_status_bar",
        "XLJRuntimeStatusBar",
        element,
        { serialize: false, hideOnZoom: false }
    );
    widget.options = { ...(widget.options || {}), serialize: false };

    node.__xljRuntimeStatusWidget = {
        widget,
        element,
        label,
        percent,
        fill,
    };

    node.setDirtyCanvas(true, true);
    return node.__xljRuntimeStatusWidget;
}

function computeProgress(state) {
    const status = state?.status || "idle";
    if (status === "success") {
        return 1;
    }

    const retries = Math.max(1, Number.isFinite(state?.retryTimes) ? state.retryTimes : 1);
    const attempt = Math.max(0, Number.isFinite(state?.attempt) ? state.attempt : 0);
    const completed = Math.max(0, attempt - 1);

    if (status === "idle") {
        return 0;
    }

    if (status === "error") {
        const raw = (completed + 1) / retries;
        return clamp(raw, 0.01, 0.99);
    }

    let inAttempt = 0;
    const timeoutSeconds = Number.isFinite(state?.timeoutSeconds) ? state.timeoutSeconds : 0;
    if (timeoutSeconds > 0 && Number.isFinite(state?.attemptElapsedSeconds)) {
        inAttempt = clamp(state.attemptElapsedSeconds / timeoutSeconds, 0, 0.96);
    } else {
        const pulse = (Date.now() % 1200) / 1200;
        inAttempt = 0.08 + pulse * 0.82;
    }

    const raw = (completed + inAttempt) / retries;
    return clamp(raw, 0.01, 0.99);
}

function renderNodeState(node, state) {
    if (!isTargetNode(node)) {
        return;
    }

    const statusWidget = ensureStatusWidget(node);
    const status = state?.status || "idle";
    const message = state?.message || "等待执行";
    const elapsedSeconds = Number.isFinite(state?.elapsedSeconds) ? state.elapsedSeconds : 0;
    const progress = computeProgress(state);
    const percentText = `${Math.round(progress * 100)}%`;

    let displayText = "等待执行";
    if (status === "running") {
        displayText = `${message} · ${formatElapsed(elapsedSeconds)}`;
    } else if (status === "success") {
        displayText = `完成 · ${formatElapsed(elapsedSeconds)}`;
    } else if (status === "error") {
        displayText = `失败 · ${formatElapsed(elapsedSeconds)}`;
    }

    statusWidget.element.dataset.state = status;
    statusWidget.label.textContent = displayText;
    statusWidget.percent.textContent = percentText;
    statusWidget.fill.style.width = `${(progress * 100).toFixed(1)}%`;

    node.setDirtyCanvas(true, true);
}

function ensureTicker() {
    if (tickerHandle) {
        return;
    }

    tickerHandle = window.setInterval(() => {
        let hasRunningNode = false;

        for (const [nodeId, state] of runtimeStateByNodeId.entries()) {
            if (state.status !== "running") {
                continue;
            }

            hasRunningNode = true;

            if (Number.isFinite(state.startedAtMs)) {
                state.elapsedSeconds = (Date.now() - state.startedAtMs) / 1000;
            }
            if (Number.isFinite(state.attemptStartedAtMs)) {
                state.attemptElapsedSeconds = (Date.now() - state.attemptStartedAtMs) / 1000;
            }

            const node = getNodeById(nodeId);
            if (node) {
                renderNodeState(node, state);
            }
        }

        if (!hasRunningNode) {
            window.clearInterval(tickerHandle);
            tickerHandle = null;
        }
    }, 150);
}

function setStateFromStatusEvent(detail) {
    const nodeId = Number(detail?.node_id);
    if (!Number.isFinite(nodeId)) {
        return;
    }

    const node = getNodeById(nodeId);
    if (!isTargetNode(node)) {
        return;
    }

    const prev = runtimeStateByNodeId.get(nodeId) || {
        status: "idle",
        message: "等待执行",
        elapsedSeconds: 0,
        attemptElapsedSeconds: 0,
        attempt: 0,
        retryTimes: 1,
        timeoutSeconds: 0,
        startedAtMs: null,
        attemptStartedAtMs: null,
    };

    const next = { ...prev };
    const status = detail?.status || prev.status;
    const message = detail?.message || prev.message;
    const elapsedFromServer = Number(detail?.elapsed_seconds);
    const attemptFromServer = Number(detail?.attempt);
    const retryFromServer = Number(detail?.retry_times);
    const timeoutFromServer = Number(detail?.timeout_seconds);

    if (Number.isFinite(attemptFromServer)) {
        next.attempt = Math.max(0, attemptFromServer);
    }
    if (Number.isFinite(retryFromServer) && retryFromServer > 0) {
        next.retryTimes = retryFromServer;
    }
    if (Number.isFinite(timeoutFromServer) && timeoutFromServer > 0) {
        next.timeoutSeconds = timeoutFromServer;
    }

    if (status === "running") {
        const attemptChanged = next.attempt !== prev.attempt || prev.status !== "running";

        next.status = "running";
        next.message = message || "运行中";

        if (Number.isFinite(elapsedFromServer)) {
            next.elapsedSeconds = elapsedFromServer;
            next.startedAtMs = Date.now() - elapsedFromServer * 1000;
        } else if (!Number.isFinite(next.startedAtMs)) {
            next.startedAtMs = Date.now();
        }

        if (attemptChanged || !Number.isFinite(next.attemptStartedAtMs)) {
            next.attemptStartedAtMs = Date.now();
            next.attemptElapsedSeconds = 0;
        }

        ensureTicker();
    } else if (status === "success") {
        next.status = "success";
        next.message = message || "生成完成";
        if (Number.isFinite(elapsedFromServer)) {
            next.elapsedSeconds = elapsedFromServer;
        }
        next.attemptElapsedSeconds = 0;
        next.startedAtMs = null;
        next.attemptStartedAtMs = null;
    } else if (status === "error") {
        next.status = "error";
        next.message = message || "执行失败";
        if (Number.isFinite(elapsedFromServer)) {
            next.elapsedSeconds = elapsedFromServer;
        }
        next.attemptElapsedSeconds = 0;
        next.startedAtMs = null;
        next.attemptStartedAtMs = null;
    } else {
        next.status = "idle";
        next.message = message || "等待执行";
        next.elapsedSeconds = 0;
        next.attemptElapsedSeconds = 0;
        next.attempt = 0;
        next.startedAtMs = null;
        next.attemptStartedAtMs = null;
    }

    runtimeStateByNodeId.set(nodeId, next);
    renderNodeState(node, next);
}

app.registerExtension({
    name: EXTENSION_NAME,
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!TARGET_NODE_TYPES.has(nodeData?.name)) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            ensureStatusWidget(this);
            return result;
        };
    },
    setup() {
        api.addEventListener(STATUS_EVENT, (event) => {
            setStateFromStatusEvent(event?.detail || {});
        });

        api.addEventListener("execution_error", (event) => {
            const detail = event?.detail || {};
            const nodeId = Number(detail.node_id ?? detail.node);
            if (!Number.isFinite(nodeId)) {
                return;
            }

            const node = getNodeById(nodeId);
            if (!isTargetNode(node)) {
                return;
            }

            const prev = runtimeStateByNodeId.get(nodeId);
            setStateFromStatusEvent({
                node_id: nodeId,
                status: "error",
                message: detail.exception_message || "执行失败",
                elapsed_seconds: prev?.elapsedSeconds || 0,
                attempt: prev?.attempt || 0,
                retry_times: prev?.retryTimes || 1,
                timeout_seconds: prev?.timeoutSeconds || 0,
            });
        });
    },
});