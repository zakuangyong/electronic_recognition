const searchState = {
  loading: false,
  lastQuery: "",
  demoQueries: {}
};

const byId = (id) => document.getElementById(id);

const ui = {
  form: byId("searchForm"),
  query: byId("queryInput"),
  revision: byId("revisionInput"),
  project: byId("projectInput"),
  debug: byId("debugInput"),
  rebuildMode: byId("rebuildMode"),
  button: byId("searchButton"),
  rebuild: byId("rebuildButton"),
  message: byId("searchMessage"),
  status: byId("searchStatus"),
  indexMode: byId("indexMode"),
  indexedDrawings: byId("indexedDrawings"),
  indexedChunks: byId("indexedChunks"),
  vectorPoints: byId("vectorPoints"),
  failedJobs: byId("failedJobs"),
  sqliteState: byId("sqliteState"),
  sqliteDetail: byId("sqliteDetail"),
  embeddingState: byId("embeddingState"),
  embeddingDetail: byId("embeddingDetail"),
  qdrantState: byId("qdrantState"),
  qdrantDetail: byId("qdrantDetail"),
  degradedState: byId("degradedState"),
  degradedDetail: byId("degradedDetail"),
  demoCount: byId("demoCount"),
  demoQueries: byId("demoQueries"),
  total: byId("resultTotal"),
  empty: byId("searchEmpty"),
  list: byId("resultList")
};

document.addEventListener("DOMContentLoaded", () => {
  ui.form.addEventListener("submit", submitSearch);
  ui.rebuild.addEventListener("click", rebuildIndex);
  ui.demoQueries.addEventListener("click", handleDemoClick);
  loadPage();
});

async function loadPage() {
  await Promise.all([loadHealth(), loadDemoQueries()]);
}

async function readJsonOrText(response) {
  const text = await response.text();
  if (!text) return {};
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return { detail: text };
    }
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { detail: text };
  }
}

function errorMessage(payload, fallback) {
  const detail = payload && payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail.message === "string" && detail.message.trim()) {
    return detail.message;
  }
  if (payload && typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  return fallback;
}

function setMessage(message, type = "info") {
  ui.message.textContent = message || "";
  ui.message.classList.remove("info", "success", "error");
  if (message) ui.message.classList.add(type);
  ui.message.setAttribute("role", type === "error" ? "alert" : "status");
  ui.message.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
}

function selectedMode() {
  const field = document.querySelector('input[name="retrievalMode"]:checked');
  return field ? field.value : "hybrid";
}

function setSelectedMode(mode) {
  const field = document.querySelector(`input[name="retrievalMode"][value="${mode}"]`);
  if (field) field.checked = true;
}

function setHealthState(strong, detail, ok, healthyText, errorText, detailText) {
  strong.textContent = ok ? healthyText : errorText;
  detail.textContent = detailText;
}

async function loadHealth() {
  try {
    const response = await fetch("/api/search/health", { cache: "no-store" });
    const payload = await readJsonOrText(response);
    if (!response.ok) throw new Error(errorMessage(payload, "索引状态读取失败"));
    ui.status.classList.remove("error");
    ui.status.classList.add("online");
    ui.status.querySelector("b").textContent = payload.enabled === false ? "检索关闭" : "检索在线";
    ui.indexMode.textContent = modeLabel(payload.mode || "bm25");
    ui.indexedDrawings.textContent = payload.indexed_drawings ?? "--";
    ui.indexedChunks.textContent = payload.indexed_chunks ?? "--";
    ui.vectorPoints.textContent = payload.vector_points ?? "--";
    ui.failedJobs.textContent = payload.failed_jobs ?? "--";
    setSelectedMode(payload.mode || selectedMode());
    setHealthState(
      ui.sqliteState,
      ui.sqliteDetail,
      Boolean(payload.sqlite_available),
      "可用",
      "离线",
      payload.database || "索引数据库"
    );
    setHealthState(
      ui.embeddingState,
      ui.embeddingDetail,
      Boolean(payload.embedding_backend_available),
      "可用",
      "未启用",
      payload.embedding_backend_available ? "Embedding 后端已加载" : "当前未启用语义向量"
    );
    setHealthState(
      ui.qdrantState,
      ui.qdrantDetail,
      Boolean(payload.qdrant_available),
      "可用",
      "离线",
      payload.collection ? `${payload.collection} · ${payload.vector_points || 0} points` : "向量集合未初始化"
    );
    setHealthState(
      ui.degradedState,
      ui.degradedDetail,
      !payload.degraded,
      "完整",
      "降级中",
      payload.degraded ? "当前使用 Exact + BM25 回退链路" : "当前链路支持混合检索"
    );
  } catch (error) {
    ui.status.classList.remove("online");
    ui.status.classList.add("error");
    ui.status.querySelector("b").textContent = "连接失败";
    setMessage(error.message, "error");
  }
}

async function loadDemoQueries() {
  try {
    const response = await fetch("/api/search/demo-queries", { cache: "no-store" });
    const payload = await readJsonOrText(response);
    if (!response.ok) throw new Error(errorMessage(payload, "演示查询集加载失败"));
    searchState.demoQueries = payload || {};
    renderDemoQueries(searchState.demoQueries);
  } catch (error) {
    ui.demoQueries.innerHTML = `<p class="demo-tip">${escapeHtml(error.message)}</p>`;
  }
}

async function submitSearch(event) {
  event.preventDefault();
  const query = ui.query.value.trim();
  if (!query) {
    setMessage("请输入检索内容。", "error");
    ui.query.focus();
    return;
  }
  setLoading(true);
  setMessage("");
  searchState.lastQuery = query;
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        limit: 20,
        debug: ui.debug.checked,
        retrieval_mode: selectedMode(),
        filters: {
          revision: ui.revision.value.trim(),
          project_name: ui.project.value.trim()
        }
      })
    });
    const payload = await readJsonOrText(response);
    if (!response.ok) throw new Error(errorMessage(payload, "检索失败"));
    renderResults(payload);
    await loadHealth();
  } catch (error) {
    setMessage(error.message, "error");
    ui.empty.classList.remove("hidden");
    ui.list.classList.add("hidden");
  } finally {
    setLoading(false);
  }
}

async function rebuildIndex() {
  ui.rebuild.disabled = true;
  setMessage(`正在以 ${modeLabel(ui.rebuildMode.value)} 模式重建索引...`, "info");
  try {
    const response = await fetch("/api/search/rebuild", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        force: true,
        mode: ui.rebuildMode.value
      })
    });
    const payload = await readJsonOrText(response);
    if (!response.ok) throw new Error(errorMessage(payload, "重建索引失败"));
    setMessage(
      `索引完成 ${payload.indexed || 0} 个，跳过 ${payload.skipped || 0} 个，写入 ${payload.vectors || 0} 个向量。`,
      "success"
    );
    await loadHealth();
    if (searchState.lastQuery) ui.form.requestSubmit();
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    ui.rebuild.disabled = false;
  }
}

function setLoading(active) {
  searchState.loading = active;
  ui.button.disabled = active;
  ui.button.classList.toggle("loading", active);
  ui.button.querySelector("span").textContent = active ? "检索中" : "开始检索";
}

function renderDemoQueries(groups) {
  const entries = Object.entries(groups || {}).filter(([, items]) => Array.isArray(items) && items.length);
  ui.demoCount.textContent = `${entries.length} 组`;
  if (!entries.length) {
    ui.demoQueries.innerHTML = `<p class="demo-tip">未找到演示查询集。</p>`;
    return;
  }
  ui.demoQueries.innerHTML = entries.map(([type, items]) => `
    <section class="demo-query-group">
      <h4>${escapeHtml(groupLabel(type))}</h4>
      <div class="demo-query-list">
        ${items.map((item) => `
          <button
            class="demo-query-item"
            type="button"
            data-query="${escapeHtml(item.query)}"
          >
            <strong>${escapeHtml(item.query)}</strong>
            <span>${escapeHtml(item.notes || "")}</span>
          </button>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function handleDemoClick(event) {
  const trigger = event.target.closest(".demo-query-item");
  if (!trigger) return;
  ui.query.value = trigger.dataset.query || "";
  ui.query.focus();
  ui.form.requestSubmit();
}

function renderResults(payload) {
  const items = Array.isArray(payload.items) ? payload.items : [];
  ui.total.textContent = `${payload.total ?? items.length} 条`;
  if (payload.degraded) {
    setMessage(payload.degraded_reason || "当前使用 Exact + BM25 检索。", "info");
  } else {
    setMessage(`${modeLabel(payload.retrieval_mode || selectedMode())} 检索完成。`, "success");
  }
  ui.empty.classList.toggle("hidden", items.length > 0);
  ui.list.classList.toggle("hidden", items.length === 0);
  if (!items.length) {
    ui.empty.innerHTML = `<h3>没有匹配结果</h3><p>换一个图号、元件代号或功能描述再试一次。</p>`;
    ui.list.innerHTML = "";
    return;
  }
  ui.list.innerHTML = items.map((item) => renderResultItem(item, payload)).join("");
}

function renderResultItem(item, payload) {
  const title = item.drawing_title || item.filename || item.result_id;
  const meta = [
    item.drawing_number && `图号 ${item.drawing_number}`,
    item.revision && `版本 ${item.revision}`,
    item.project_name,
    item.system_name
  ].filter(Boolean);
  const pages = Array.isArray(item.matched_pages) && item.matched_pages.length
    ? item.matched_pages.map((page) => `第 ${page} 页`).join("、")
    : "页码未定位";
  const components = tags(item.matched_components || [], "component");
  const combinations = tags(item.matched_combinations || [], "combination");
  const chunkTypes = tags((item.matched_chunk_types || []).map(chunkTypeLabel), "chunk");
  const sources = tags((item.match_sources || []).map(sourceLabel), "source");
  const history = Number(item.collapsed_versions || 0) > 0
    ? `<div class="search-history">已折叠 ${item.collapsed_versions} 个历史版本</div>`
    : "";
  const debugBlock = renderDebug(item.debug || {}, payload);
  return `<article class="search-result-item">
    <header>
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(meta.join(" · ") || item.filename || "")}</p>
      </div>
      <strong>${formatScore(item.score)}</strong>
    </header>
    <div class="search-result-body">
      <p>${escapeHtml(item.snippet || "暂无摘要")}</p>
      <div class="search-result-row">
        <span>${escapeHtml(pages)}</span>
        <span>ID ${escapeHtml(item.result_id || "")}</span>
      </div>
      ${history}
      ${(components || combinations || chunkTypes) ? `<div class="search-tags">${components}${combinations}${chunkTypes}</div>` : ""}
      <div class="search-result-footer">
        <div class="search-tags">${sources}</div>
        <a href="${escapeHtml(item.preview_url || `/api/results/${item.result_id}`)}">查看结果</a>
      </div>
      ${debugBlock}
    </div>
  </article>`;
}

function renderDebug(debug) {
  const hits = Array.isArray(debug.hits) ? debug.hits : [];
  if (!hits.length) return "";
  return `<details class="debug-panel">
    <summary>调试命中</summary>
    <div class="debug-hit-list">
      ${hits.map((hit) => `
        <div class="debug-hit-item">
          <span>${escapeHtml(sourceLabel(hit.source || ""))}</span>
          <span>${escapeHtml(chunkTypeLabel(hit.chunk_type || ""))}</span>
          ${renderSourceRanks(hit.source_ranks || {})}
          <span>RRF ${escapeHtml(formatScore(hit.score))}</span>
        </div>
      `).join("")}
    </div>
  </details>`;
}

function renderSourceRanks(ranks) {
  const entries = Object.entries(ranks || {});
  if (!entries.length) return `<span>rank --</span>`;
  return entries.map(([source, rank]) =>
    `<span>${escapeHtml(sourceLabel(source))} #${escapeHtml(rank)}</span>`
  ).join("");
}

function tags(values, kind) {
  return values.slice(0, 8).map((value) =>
    `<span class="search-tag ${kind}">${escapeHtml(value)}</span>`
  ).join("");
}

function groupLabel(value) {
  return {
    exact: "精确检索",
    keyword: "关键词检索",
    semantic: "语义检索",
    constraint: "组合约束"
  }[value] || value;
}

function modeLabel(value) {
  return {
    bm25: "BM25",
    vector: "Vector",
    hybrid: "Hybrid"
  }[value] || value || "--";
}

function sourceLabel(value) {
  return {
    exact: "精确命中",
    bm25: "BM25",
    dense: "语义命中"
  }[value] || value;
}

function chunkTypeLabel(value) {
  return {
    drawing: "图纸摘要",
    page: "页面块",
    component_group: "元件组",
    component_table: "元件表",
    combination: "组合规则",
    region: "区域块"
  }[value] || value || "未知块";
}

function formatScore(value) {
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(3) : "--";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}
