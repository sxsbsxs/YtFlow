const $ = (id) => document.getElementById(id);
const state = { items: [], filter: "all", toastTimer: null };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}
function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || !Number.isFinite(Number(bytes))) return "大小计算中";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(bytes), index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
  return value.toFixed(index === 0 ? 0 : 1) + " " + units[index];
}
function formatSpeed(value) { return value ? formatBytes(value) + "/s" : "—"; }
function formatEta(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const seconds = Math.max(0, Number(value));
  return seconds >= 3600 ? Math.floor(seconds / 3600) + "小时" + Math.floor((seconds % 3600) / 60) + "分" :
    seconds >= 60 ? Math.floor(seconds / 60) + "分" + Math.floor(seconds % 60) + "秒" : Math.floor(seconds) + "秒";
}
function showToast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => $("toast").classList.remove("show"), 2600);
}
let csrfToken = null;
let refreshingAuth = false;

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 && !refreshingAuth) {
    refreshingAuth = true;
    showLogin("登录状态已过期，请重新登录。");
    refreshingAuth = false;
  }
  if (!response.ok) throw new Error(body.detail || "请求失败，请检查服务状态。");
  return body;
}

function showLogin(message = "") {
  csrfToken = null;
  $("app-shell").classList.add("hidden");
  $("login-screen").classList.remove("hidden");
  $("login-error").textContent = message;
  $("login-error").classList.toggle("hidden", !message);
}
function showApp(username) {
  $("login-screen").classList.add("hidden");
  $("app-shell").classList.remove("hidden");
  $("signed-user").textContent = username || "管理员";
  refresh();
  refreshFiles();
}
async function checkSession() {
  try {
    const status = await fetch("/api/auth/status", { credentials: "same-origin", cache: "no-store" }).then((r) => r.json());
    if (status.authenticated) {
      csrfToken = status.csrf_token;
      showApp(status.username);
    } else {
      showLogin();
    }
  } catch (_) {
    showLogin("无法连接到 YtFlow 服务，请检查服务器状态。");
  }
}
function statusLabel(status) {
  return ({ queued: "排队中", downloading: "下载中", processing: "处理中", completed: "已完成", failed: "失败", cancelled: "已取消" })[status] || status;
}
function visibleItems() {
  if (state.filter === "active") return state.items.filter((x) => ["queued", "downloading", "processing"].includes(x.status));
  if (state.filter === "completed") return state.items.filter((x) => x.status === "completed");
  if (state.filter === "failed") return state.items.filter((x) => x.status === "failed" || x.status === "cancelled");
  return state.items;
}
function render() {
  const list = $("task-list");
  $("task-total").textContent = state.items.length;
  $("all-count").textContent = state.items.length;
  const items = visibleItems();
  if (!items.length) {
    const label = state.filter === "all" ? "还没有下载任务" : "这里暂时没有任务";
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">↓</div><strong>' + label + '</strong><span>在上方粘贴一个视频链接，开始你的第一次下载。</span></div>';
    return;
  }
  list.innerHTML = items.map((item) => {
    const active = ["queued", "downloading", "processing"].includes(item.status);
    const progress = Math.max(0, Math.min(100, Number(item.progress) || 0));
    const subtitle = item.mode === "audio" ? item.audio_format.toUpperCase() + " 音频" : item.quality === "best" ? "最高可用画质" : item.quality;
    const detail = item.status === "failed" ? item.message : item.status === "completed" ? "文件已保存到服务器下载目录" :
      item.status === "queued" ? "等待空闲下载线程" : item.message;
    const action = active ? '<button class="small-action danger" data-cancel="' + escapeHtml(item.id) + '">取消</button>' :
      item.status === "failed" || item.status === "cancelled" ? '<button class="small-action" data-retry="' + escapeHtml(item.id) + '">重新下载</button>' : "";
    const thumb = item.thumbnail ? '<img class="task-thumb" src="' + escapeHtml(item.thumbnail) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' :
      '<div class="task-thumb task-placeholder">▶</div>';
    const progressBar = '<div class="progress-track"><div class="progress-fill" style="width:' + progress + '%"></div></div>';
    const metrics = active ? '<div class="task-bottom"><span>' + formatSpeed(item.speed) + ' · 剩余 ' + formatEta(item.eta) + '</span><span>' + progress.toFixed(1) + '%</span></div>' :
      '<div class="task-bottom"><span>' + escapeHtml(detail) + '</span><span>' + progress.toFixed(0) + '%</span></div>';
    return '<article class="task-card">' + thumb +
      '<div class="task-main"><div class="task-title" title="' + escapeHtml(item.title) + '">' + escapeHtml(item.title) + '</div>' +
      '<div class="task-sub"><span>' + escapeHtml(subtitle) + '</span><span>·</span><span>' + escapeHtml(item.id) + '</span></div>' +
      progressBar + metrics + '</div><div class="task-actions"><span class="task-state ' + escapeHtml(item.status) + '">' + statusLabel(item.status) + '</span>' + action + '</div></article>';
  }).join("");
}
async function refresh() {
  try {
    const data = await api("/api/downloads");
    state.items = data.items || [];
    render();
  } catch (error) {
    showToast(error.message);
  }
}
$("download-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("add-button");
  button.disabled = true;
  button.innerHTML = '<span>◌</span> 正在解析…';
  $("form-error").classList.add("hidden");
  try {
    const payload = {
      url: $("url-input").value.trim(),
      mode: $("mode-select").value,
      quality: $("quality-select").value,
      audio_format: $("audio-select").value,
      playlist: $("playlist-select").value === "true"
    };
    const info = await api("/api/inspect", { method: "POST", body: JSON.stringify({ url: payload.url }) });
    payload.title = info.title || payload.url;
    payload.thumbnail = info.thumbnail || null;
    const job = await api("/api/downloads", { method: "POST", body: JSON.stringify(payload) });
    state.items.unshift(job);
    $("preview-card").classList.add("hidden");
    $("url-input").value = "";
    document.querySelectorAll("[data-filter]").forEach((tab) => tab.classList.toggle("active", tab.dataset.filter === "all"));
    state.filter = "all";
    render();
    showToast("下载任务已添加");
    refresh();
  } catch (error) {
    $("form-error").textContent = error.message;
    $("form-error").classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>↓</span> 解析并添加任务';
  }
});
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("login-button");
  button.disabled = true;
  button.textContent = "正在验证…";
  $("login-error").classList.add("hidden");
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("login-username").value.trim(),
        password: $("login-password").value
      })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "登录失败。");
    $("login-password").value = "";
    csrfToken = result.csrf_token;
    const status = await fetch("/api/auth/status", { credentials: "same-origin", cache: "no-store" }).then((r) => r.json());
    if (!status.authenticated) throw new Error("会话创建失败，请重新登录。");
    csrfToken = status.csrf_token;
    showApp(status.username);
  } catch (error) {
    $("login-error").textContent = error.message;
    $("login-error").classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.innerHTML = '安全登录 <span>→</span>';
  }
});
$("logout-button").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
    $("login-password").value = "";
    showLogin("你已安全退出登录。");
  } catch (error) {
    showToast(error.message);
  }
});

$("paste-button").addEventListener("click", async () => {
  try {
    $("url-input").value = await navigator.clipboard.readText();
    $("url-input").focus();
  } catch (_) { $("url-input").focus(); showToast("浏览器未授予剪贴板权限，请长按输入框粘贴。"); }
});
$("mode-select").addEventListener("change", () => {
  const audio = $("mode-select").value === "audio";
  $("quality-field").classList.toggle("hidden", audio);
  $("audio-field").classList.toggle("hidden", !audio);
});
$("preview-close").addEventListener("click", () => $("preview-card").classList.add("hidden"));
$("refresh-button").addEventListener("click", refresh);
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item.dataset.filter === state.filter));
  render();
}));
$("task-list").addEventListener("click", async (event) => {
  const cancelId = event.target.dataset.cancel;
  const retryId = event.target.dataset.retry;
  if (cancelId) {
    try { await api("/api/downloads/" + encodeURIComponent(cancelId), { method: "DELETE" }); await refresh(); showToast("已发送取消请求"); }
    catch (error) { showToast(error.message); }
  }
  if (retryId) {
    try {
      await api("/api/downloads/" + encodeURIComponent(retryId) + "/retry", { method: "POST" });
      showToast("已创建重试任务");
      await refresh();
    } catch (error) {
      showToast(error.message);
    }
  }
});
$("theme-toggle").addEventListener("click", () => {
  document.body.classList.toggle("light");
  localStorage.setItem("ytflow-theme", document.body.classList.contains("light") ? "light" : "dark");
});
async function refreshFiles() {
  try {
    const data = await api("/api/files");
    const items = data.items || [];
    $("file-count").textContent = items.length;
    if (!items.length) {
      $("files-list").innerHTML = '<div class="files-empty">下载完成的文件会显示在这里。</div>';
      return;
    }
    $("files-list").innerHTML = items.map((file) => {
      const href = "/api/files/" + encodeURIComponent(file.name);
      const modified = file.modified ? new Date(file.modified * 1000).toLocaleString() : "";
      return '<article class="file-row"><div class="file-info"><div class="file-name" title="' + escapeHtml(file.name) + '">' +
        escapeHtml(file.name) + '</div><div class="file-meta">' + formatBytes(file.size) + (modified ? " · " + escapeHtml(modified) : "") +
        '</div></div><a class="file-download" href="' + href + '" download>下载文件 ↓</a></article>';
    }).join("");
  } catch (error) {
    $("files-list").innerHTML = '<div class="files-empty">暂时无法读取文件列表。</div>';
  }
}
$("refresh-files").addEventListener("click", refreshFiles);
if (localStorage.getItem("ytflow-theme") === "light") document.body.classList.add("light");
checkSession();
setInterval(() => {
  if (!$("app-shell").classList.contains("hidden")) refresh();
}, 1800);
setInterval(() => {
  if (!$("app-shell").classList.contains("hidden")) refreshFiles();
}, 6000);
