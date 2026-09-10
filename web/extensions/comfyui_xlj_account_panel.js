import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_TYPE = "XLJApiKeyPanel";
const POLL_INTERVAL_MS = 2000;
const STYLE_ID = "xlj-account-panel-style";

function injectStyle() {
    if (document.getElementById(STYLE_ID)) {
        return;
    }
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .xlj-account-panel { display: flex; flex-direction: column; gap: 6px; padding: 4px 0; }
        .xlj-account-panel input {
            width: 100%; box-sizing: border-box; padding: 4px 6px; border-radius: 6px;
            border: 1px solid #4a4a4a; background: #1e1e1e; color: #e8e8e8; font-size: 12px;
        }
        .xlj-account-panel select {
            width: 100%; box-sizing: border-box; padding: 4px 6px; border-radius: 6px;
            border: 1px solid #4a4a4a; background: #1e1e1e; color: #e8e8e8; font-size: 12px;
        }
        .xlj-account-panel .xlj-row { display: flex; gap: 6px; }
        .xlj-account-panel button {
            flex: 1; padding: 5px 8px; border-radius: 6px; border: 1px solid #555;
            background: #2f2f2f; color: #e8e8e8; font-size: 12px; cursor: pointer;
        }
        .xlj-account-panel button:hover { background: #3a3a3a; }
        .xlj-account-panel button:disabled { opacity: 0.5; cursor: default; }
        .xlj-account-panel .xlj-switch {
            display: flex; align-items: center; gap: 6px; font-size: 11px; color: #a9a9a9;
        }
        .xlj-account-panel .xlj-switch input { width: auto; margin: 0; }
        .xlj-account-panel .xlj-status {
            font-size: 11px; color: #a9a9a9; white-space: pre-wrap; word-break: break-all; line-height: 1.35;
        }
        .xlj-account-panel .xlj-status.ok { color: #41d18a; }
        .xlj-account-panel .xlj-status.err { color: #ff6b6b; }
    `;
    document.head.appendChild(style);
}

function findWidget(node, name) {
    return (node.widgets || []).find((widget) => widget.name === name);
}

function readWidget(node, name, fallback = "") {
    const widget = findWidget(node, name);
    return widget ? widget.value : fallback;
}

function writeWidget(node, name, value) {
    const widget = findWidget(node, name);
    if (!widget) {
        return;
    }
    widget.value = value;
    node.setDirtyCanvas(true, true);
}

async function postJson(path, payload) {
    const response = await api.fetchApi(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
    });
    return await response.json();
}

async function getJson(path) {
    const response = await api.fetchApi(path, { method: "GET" });
    return await response.json();
}

function createPanel(node) {
    injectStyle();

    const wrap = document.createElement("div");
    wrap.className = "xlj-account-panel";
    wrap.innerHTML = `
        <input class="xlj-user" placeholder="账号 / 用户名" autocomplete="off">
        <input class="xlj-pass" type="password" placeholder="密码" autocomplete="off">
        <select class="xlj-group"><option value="">自动选择分组</option></select>
        <div class="xlj-row">
            <button class="xlj-login">登录</button>
            <button class="xlj-gen">生成密钥</button>
        </div>
        <div class="xlj-row">
            <button class="xlj-logout">退出登录</button>
        </div>
        <label class="xlj-switch">
            <input type="checkbox" class="xlj-switchbox">
            换号登录（清除浏览器里的登录状态）
        </label>
        <select class="xlj-history"><option value="">选择已有密钥…</option></select>
        <input class="xlj-key" readonly placeholder="生成的密钥会显示在这里">
        <div class="xlj-status">未登录</div>
    `;

    const userInput = wrap.querySelector(".xlj-user");
    const passInput = wrap.querySelector(".xlj-pass");
    const groupSelect = wrap.querySelector(".xlj-group");
    const historySelect = wrap.querySelector(".xlj-history");
    const keyInput = wrap.querySelector(".xlj-key");
    const loginButton = wrap.querySelector(".xlj-login");
    const logoutButton = wrap.querySelector(".xlj-logout");
    const switchBox = wrap.querySelector(".xlj-switchbox");
    const genButton = wrap.querySelector(".xlj-gen");
    const statusLine = wrap.querySelector(".xlj-status");

    const state = {
        timer: null,
        loginDeadline: 0,
        history: [],
        groupImageModels: {},
    };

    function setStatus(text, kind) {
        statusLine.textContent = text;
        statusLine.classList.toggle("ok", kind === "ok");
        statusLine.classList.toggle("err", kind === "err");
    }

    function syncKeyBox() {
        keyInput.value = readWidget(node, "api_key", "");
    }

    async function loadGroups() {
        const site = readWidget(node, "api_site", "");
        const model = readWidget(node, "model", "");
        const current = readWidget(node, "group", "");
        try {
            const payload = await getJson(
                `/xlj/account/groups?api_site=${encodeURIComponent(site)}&model=${encodeURIComponent(model)}`
            );
            const groups = (payload && payload.groups) || [];
            const modelGroups = new Set((payload && payload.model_groups) || []);
            state.groupImageModels = (payload && payload.group_image_models) || {};
            groupSelect.innerHTML = "";
            const autoOption = document.createElement("option");
            autoOption.value = "";
            autoOption.textContent = "自动选择分组";
            groupSelect.appendChild(autoOption);
            for (const group of groups) {
                const option = document.createElement("option");
                option.value = group;
                const imageCount = (state.groupImageModels[group] || []).length;
                const tags = [];
                if (imageCount) {
                    tags.push(`${imageCount} 个图像模型`);
                }
                if (modelGroups.has(group)) {
                    tags.push("支持当前模型");
                }
                option.textContent = tags.length ? `${group}（${tags.join("，")}）` : group;
                groupSelect.appendChild(option);
            }
            groupSelect.value = current && groups.includes(current) ? current : "";
        } catch (error) {
            // 分组列表拿不到时保留「自动」，不影响创建
        }
    }

    async function loadHistory() {
        const site = readWidget(node, "api_site", "");
        const model = readWidget(node, "model", "");
        try {
            const payload = await getJson(
                `/xlj/account/tokens?api_site=${encodeURIComponent(site)}&model=${encodeURIComponent(model)}`
            );
            state.history = (payload && payload.tokens) || [];
        } catch (error) {
            state.history = [];
        }

        historySelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = state.history.length ? "选择已有密钥…" : "没有可用的历史密钥";
        historySelect.appendChild(placeholder);

        for (const token of state.history) {
            const option = document.createElement("option");
            option.value = String(token.id);
            const models = token.models || "不限模型";
            const warn = token.group_warning ? " ⚠分组异常" : "";
            option.textContent = `${models} | ${token.name || "未命名"} | ${token.masked}${warn}`;
            historySelect.appendChild(option);
        }
    }

    function stopPolling() {
        if (state.timer) {
            clearInterval(state.timer);
            state.timer = null;
        }
    }

    function applyStatus(payload) {
        const site = readWidget(node, "api_site", "");
        if (!payload || payload.success === false) {
            setStatus(payload && payload.message ? payload.message : "状态查询失败", "err");
            return true;
        }
        if (payload.state === "running") {
            loginButton.disabled = true;
            setStatus(`[${site}] ${payload.message || "等待浏览器登录…"}`);
            return false;
        }
        loginButton.disabled = false;
        if (payload.state === "logged_in") {
            setStatus(`[${site}] 已登录：${payload.username || "账号"}（ID ${payload.user_id ?? "-"}）`, "ok");
            loadGroups();
            loadHistory();
            return true;
        }
        if (payload.state === "error") {
            setStatus(`[${site}] 登录失败：${payload.message || "未知错误"}`, "err");
            return true;
        }
        setStatus(`[${site}] 未登录`);
        return true;
    }

    async function refreshStatus() {
        const site = readWidget(node, "api_site", "");
        try {
            const payload = await getJson(`/xlj/account/status?api_site=${encodeURIComponent(site)}`);
            return applyStatus(payload);
        } catch (error) {
            setStatus(`状态查询失败：${error}`, "err");
            return true;
        }
    }

    function startPolling() {
        stopPolling();
        state.loginDeadline = Date.now() + 10 * 60 * 1000;
        state.timer = setInterval(async () => {
            const finished = await refreshStatus();
            if (finished) {
                stopPolling();
            } else if (Date.now() > state.loginDeadline) {
                stopPolling();
                loginButton.disabled = false;
                setStatus("等待登录超时，请重新点击「登录」", "err");
            }
        }, POLL_INTERVAL_MS);
    }

    loginButton.addEventListener("click", async () => {
        const username = userInput.value.trim();
        const password = passInput.value;
        if (!username || !password) {
            setStatus("请先填写账号和密码", "err");
            return;
        }
        loginButton.disabled = true;
        setStatus("正在打开浏览器…");
        try {
            const payload = await postJson("/xlj/account/login", {
                api_site: readWidget(node, "api_site", ""),
                username,
                password,
                timeout: 300,
                switch_account: switchBox.checked,
            });
            applyStatus(payload);
            passInput.value = "";
            switchBox.checked = false;
            startPolling();
        } catch (error) {
            loginButton.disabled = false;
            setStatus(`登录请求失败：${error}`, "err");
        }
    });

    logoutButton.addEventListener("click", async () => {
        logoutButton.disabled = true;
        setStatus("正在退出登录并清理缓存…");
        try {
            const payload = await postJson("/xlj/account/logout", {
                api_site: readWidget(node, "api_site", ""),
            });
            if (!payload.success) {
                setStatus(payload.message || "退出登录失败", "err");
                return;
            }
            stopPolling();
            writeWidget(node, "api_key", "");
            syncKeyBox();
            state.history = [];
            historySelect.innerHTML = "";
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "选择已有密钥…";
            historySelect.appendChild(placeholder);
            passInput.value = "";
            setStatus(`${payload.message}\n其它节点里填过的 api_key 需要自己清一下。`, "ok");
            loadGroups();
            loadHistory();
        } catch (error) {
            setStatus(`退出登录失败：${error}`, "err");
        } finally {
            logoutButton.disabled = false;
        }
    });

    genButton.addEventListener("click", async () => {
        genButton.disabled = true;
        setStatus("正在生成密钥…");
        try {
            const payload = await postJson("/xlj/account/create-key", {
                api_site: readWidget(node, "api_site", ""),
                model: readWidget(node, "model", ""),
                key_name: readWidget(node, "key_name", "comfyui"),
                extra_models: readWidget(node, "extra_models", ""),
                unlimited_quota: readWidget(node, "unlimited_quota", true),
                expired_days: readWidget(node, "expired_days", -1),
                group: readWidget(node, "group", ""),
            });
            if (!payload.success) {
                setStatus(payload.message || "生成密钥失败", "err");
                return;
            }
            writeWidget(node, "api_key", payload.api_key || "");
            syncKeyBox();
            loadHistory();
            setStatus(
                `${payload.status || `模型：${payload.model || "-"}`}\n` +
                `密钥已写入 API_KEY 框（并记入历史密钥），其它节点 api_key 留空即可自动使用`,
                "ok"
            );
        } catch (error) {
            setStatus(`生成密钥失败：${error}`, "err");
        } finally {
            genButton.disabled = false;
        }
    });

    const siteWidget = findWidget(node, "api_site");
    if (siteWidget) {
        const previous = siteWidget.callback;
        siteWidget.callback = function () {
            if (typeof previous === "function") {
                previous.apply(this, arguments);
            }
            stopPolling();
            syncKeyBox();
            refreshStatus();
            loadGroups();
            loadHistory();
        };
    }

    const modelWidget = findWidget(node, "model");
    if (modelWidget) {
        const previous = modelWidget.callback;
        modelWidget.callback = function () {
            if (typeof previous === "function") {
                previous.apply(this, arguments);
            }
            loadGroups();
            loadHistory();
        };
    }

    const keyWidget = findWidget(node, "api_key");
    if (keyWidget) {
        const previous = keyWidget.callback;
        keyWidget.callback = function () {
            if (typeof previous === "function") {
                previous.apply(this, arguments);
            }
            syncKeyBox();
        };
    }

    groupSelect.addEventListener("change", () => {
        writeWidget(node, "group", groupSelect.value);
        const models = (state.groupImageModels || {})[groupSelect.value] || [];
        if (models.length) {
            setStatus(
                `分组 ${groupSelect.value} 覆盖 ${models.length} 个图像模型：\n${models.join("，")}\n` +
                `要把它们一次全绑上，把「模型」选成「该分组支持的图像模型」。`,
                "ok"
            );
        }
    });

    historySelect.addEventListener("change", () => {
        const token = state.history.find((item) => String(item.id) === historySelect.value);
        if (!token) {
            return;
        }
        writeWidget(node, "api_key", token.key);
        syncKeyBox();
        setStatus(
            `已选择历史密钥：${token.models || "不限模型"} | ${token.name || "未命名"} | ${token.masked}` +
            (token.group_warning ? `\n注意：该密钥分组 ${token.group} 不是有效分组，建议重新生成` : ""),
            token.group_warning ? "err" : "ok"
        );
    });

    syncKeyBox();
    refreshStatus();
    loadGroups();
    loadHistory();

    return { wrap, stopPolling, syncKeyBox, refreshStatus, loadGroups, loadHistory };
}

app.registerExtension({
    name: "comfyui_xlj_account_panel",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) {
            return;
        }
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) {
                onNodeCreated.apply(this, arguments);
            }
            const node = this;
            const panel = createPanel(node);
            node.addDOMWidget("xlj_account_panel", "xlj_account_panel", panel.wrap, {
                serialize: false,
                hideOnZoom: false,
            });

            const onRemoved = node.onRemoved;
            node.onRemoved = function () {
                panel.stopPolling();
                if (onRemoved) {
                    onRemoved.apply(this, arguments);
                }
            };

            const onConfigure = node.onConfigure;
            node.onConfigure = function () {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }
                panel.syncKeyBox();
            };
        };
    },
});
