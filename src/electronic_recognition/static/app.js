const state = {
  file: null,
  result: null,
  knowledgeItems: [],
  filteredKnowledge: [],
  selectedKnowledgeId: ""
};
const $ = (id) => document.getElementById(id);
const colors = [
  "#1769aa", "#d1495b", "#138a72", "#8a5cf6", "#d97706",
  "#007c91", "#b54708", "#6b7280", "#c026d3", "#4d7c0f"
];

const elements = {
  form: $("analysisForm"), input: $("drawingInput"), drop: $("dropZone"),
  card: $("fileCard"), fileName: $("fileName"), fileSize: $("fileSize"),
  fileType: $("fileType"), remove: $("removeFile"), submit: $("submitButton"),
  message: $("formMessage"), status: $("systemStatus"), model: $("modelName"),
  count: $("componentCount"), referenceLimit: $("referenceLimit"),
  knowledgeCount: $("knowledgePreviewCount"), knowledgeSearch: $("knowledgeSearch"),
  knowledgeFeature: $("knowledgeFeature"), knowledgeGallery: $("knowledgeGallery"),
  knowledgeEmpty: $("knowledgeEmpty"),
  empty: $("emptyState"), loading: $("loadingState"), content: $("resultContent"),
  download: $("downloadButton"), typeTotal: $("typeTotal"),
  instanceTotal: $("instanceTotal"), elapsed: $("elapsedTime"),
  table: $("componentTable"), annotations: $("annotations"),
  titleBlock: $("titleBlockTable"), controlSignal: $("controlSignalContent"),
  json: $("jsonOutput"), warningBox: $("warningBox"),
  warningList: $("warningList")
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindEvents();
  await Promise.all([loadConfig(), loadKnowledge()]);
}

function bindEvents() {
  elements.input.addEventListener("change", () => setFile(elements.input.files[0]));
  ["dragenter", "dragover"].forEach((name) => elements.drop.addEventListener(name, (event) => {
    event.preventDefault(); elements.drop.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => elements.drop.addEventListener(name, (event) => {
    event.preventDefault(); elements.drop.classList.remove("dragging");
  }));
  elements.drop.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
  elements.remove.addEventListener("click", clearFile);
  elements.form.addEventListener("submit", analyze);
  elements.download.addEventListener("click", downloadJson);
  elements.knowledgeSearch.addEventListener("input", applyKnowledgeFilter);
  elements.knowledgeGallery.addEventListener("click", handleKnowledgeSelect);
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => activateTab(tab.dataset.tab))
  );
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    if (!response.ok) throw new Error(config.detail || "配置读取失败");
    elements.status.classList.add("online");
    elements.status.querySelector("b").textContent = "服务在线";
    elements.model.textContent = config.model || "未配置";
    elements.count.textContent = `${config.component_count} 张`;
    elements.referenceLimit.textContent = `${config.reference_batch_size} 张/批`;
    if (!config.api_key_configured) {
      elements.message.textContent = "请先在 .env 中配置模型密钥和模型名称。";
    }
  } catch (error) {
    elements.status.classList.add("error");
    elements.status.querySelector("b").textContent = "连接失败";
    elements.message.textContent = error.message;
  }
}

async function loadKnowledge() {
  try {
    const response = await fetch("/api/knowledge");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "知识库读取失败");
    state.knowledgeItems = (payload.items || []).map((item) => ({
      id: String(item.id || ""),
      label: String(item.label || "未命名"),
      componentType: String(item.component_type || ""),
      imageUrl: String(item.image_url || "")
    }));
    applyKnowledgeFilter();
  } catch (error) {
    state.knowledgeItems = [];
    state.filteredKnowledge = [];
    elements.knowledgeCount.textContent = "不可用";
    elements.knowledgeFeature.classList.add("hidden");
    elements.knowledgeGallery.classList.add("hidden");
    elements.knowledgeEmpty.classList.remove("hidden");
    elements.knowledgeEmpty.textContent = error.message;
  }
}

function setFile(file) {
  if (!file) return;
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["pdf", "png"].includes(extension)) {
    elements.message.textContent = "请选择 PDF 或 PNG 文件。"; return;
  }
  state.file = file;
  elements.fileName.textContent = file.name;
  elements.fileSize.textContent = formatBytes(file.size);
  elements.fileType.textContent = extension.toUpperCase();
  elements.card.classList.remove("hidden");
  elements.drop.classList.add("hidden");
  elements.submit.disabled = false;
  elements.message.textContent = "";
  clearResult();
}

function clearFile() {
  state.file = null; elements.input.value = "";
  elements.card.classList.add("hidden"); elements.drop.classList.remove("hidden");
  elements.submit.disabled = true; clearResult();
}

function clearResult() {
  state.result = null;
  elements.content.classList.add("hidden");
  elements.loading.classList.add("hidden");
  elements.empty.classList.remove("hidden");
  elements.download.classList.add("hidden");
}

function applyKnowledgeFilter() {
  const keyword = elements.knowledgeSearch.value.trim().toLowerCase();
  const filtered = state.knowledgeItems.filter((item) => {
    const searchable = [
      item.id,
      item.label,
      item.componentType
    ].join(" ").toLowerCase();
    return !keyword || searchable.includes(keyword);
  });
  state.filteredKnowledge = filtered;
  if (!filtered.some((item) => item.id === state.selectedKnowledgeId)) {
    state.selectedKnowledgeId = filtered[0]?.id || "";
  }
  renderKnowledgePreview();
}

function renderKnowledgePreview() {
  const total = state.knowledgeItems.length;
  const filtered = state.filteredKnowledge;
  const visibleItems = filtered.slice(0, 24);
  const selected = filtered.find((item) => item.id === state.selectedKnowledgeId) || null;
  elements.knowledgeCount.textContent = total
    ? `${visibleItems.length}/${filtered.length}${filtered.length !== total ? `，共 ${total}` : ""}`
    : "0 项";
  elements.knowledgeEmpty.classList.toggle("hidden", filtered.length > 0);
  elements.knowledgeFeature.classList.toggle("hidden", !selected);
  elements.knowledgeGallery.classList.toggle("hidden", !visibleItems.length);
  if (!filtered.length) {
    elements.knowledgeFeature.innerHTML = "";
    elements.knowledgeGallery.innerHTML = "";
    elements.knowledgeEmpty.textContent = total
      ? "没有匹配的知识库样本。"
      : "当前没有可预览的知识库样本。";
    return;
  }
  if (selected) {
    elements.knowledgeFeature.innerHTML = `<div class="knowledge-image-wrap">
        <img src="${escapeHtml(selected.imageUrl)}" alt="${escapeHtml(selected.label)} 参考图" />
      </div>
      <div class="knowledge-meta">
        <strong>${escapeHtml(selected.label)}</strong>
        <span>${escapeHtml(selected.componentType || "未分类")}</span>
        <small>ID: ${escapeHtml(selected.id)}</small>
      </div>`;
  }
  elements.knowledgeGallery.innerHTML = visibleItems.map((item) => `<button
      class="knowledge-thumb${item.id === state.selectedKnowledgeId ? " active" : ""}"
      type="button"
      data-knowledge-id="${escapeHtml(item.id)}"
      aria-pressed="${item.id === state.selectedKnowledgeId ? "true" : "false"}"
    >
      <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.label)} 缩略图" />
      <span>${escapeHtml(item.label)}</span>
    </button>`).join("");
}

function handleKnowledgeSelect(event) {
  const button = event.target.closest("[data-knowledge-id]");
  if (!button) return;
  state.selectedKnowledgeId = button.dataset.knowledgeId || "";
  renderKnowledgePreview();
}

async function analyze(event) {
  event.preventDefault();
  if (!state.file) return;
  setLoading(true);
  const data = new FormData();
  data.append("drawing", state.file);
  try {
    const response = await fetch("/analyze", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "识别失败");
    state.result = payload; render(payload);
  } catch (error) {
    elements.message.textContent = error.message;
    elements.empty.classList.remove("hidden");
  } finally {
    setLoading(false);
  }
}

function setLoading(active) {
  elements.submit.disabled = active || !state.file;
  elements.submit.classList.toggle("loading", active);
  elements.submit.querySelector("span").textContent = active ? "识别中" : "开始识别";
  if (active) {
    elements.empty.classList.add("hidden");
    elements.content.classList.add("hidden");
    elements.loading.classList.remove("hidden");
    elements.message.textContent = "";
  } else {
    elements.loading.classList.add("hidden");
  }
}

function render(result) {
  const groups = groupComponents(result.detected_components || []);
  const instances = groups.reduce((sum, group) => sum + group.count, 0);
  elements.empty.classList.add("hidden");
  elements.content.classList.remove("hidden");
  elements.download.classList.remove("hidden");
  elements.typeTotal.textContent = groups.length;
  elements.instanceTotal.textContent = instances;
  elements.elapsed.textContent = `${result.meta?.elapsed_seconds ?? "--"} s`;
  elements.table.innerHTML = groups.length
    ? `<table class="component-table">
        <colgroup><col class="sequence"><col class="code"><col class="quantity"><col></colgroup>
        <thead><tr><th>序号</th><th>代号</th><th>元件数量</th><th>元件名称</th></tr></thead>
        <tbody>${groups.map((group, index) => `<tr>
          <td>${index + 1}</td>
          <td class="component-code-cell"><i class="color-key" style="--color:${group.color}"></i><strong class="component-code-text">${formatCodeForWrap(group.code || "未标注")}</strong></td>
          <td><strong>${group.count}</strong></td>
          <td>${escapeHtml(group.label)}</td>
        </tr>`).join("")}</tbody>
      </table>`
    : `<p class="empty-copy">没有识别到元器件。</p>`;
  elements.annotations.innerHTML = (result.preview_pages || []).map(
    (page) => renderPage(page, groups)
  ).join("");
  elements.titleBlock.innerHTML = renderTitleBlock(result.title_block);
  elements.controlSignal.innerHTML = renderControlSignal(
    result.control_signal_configuration
  );
  elements.json.textContent = JSON.stringify(exportableResult(result), null, 2);
  const warnings = result.warnings || [];
  elements.warningBox.classList.toggle("hidden", !warnings.length);
  elements.warningList.innerHTML = warnings.map(
    (warning) => `<li>${escapeHtml(warning)}</li>`
  ).join("");
}

function groupComponents(components) {
  const map = new Map();
  components.forEach((item) => {
    const code = String(item.code || "").trim();
    const label = String(item.label || "未命名").trim();
    const key = `${code.toLowerCase()}|${label.toLowerCase()}`;
    if (!map.has(key)) {
      map.set(key, {
        code, label, color: colors[map.size % colors.length],
        count: 0, instances: []
      });
    }
    const group = map.get(key);
    const regions = normalizeRegions(item.regions);
    group.count += Math.max(Number(item.occurrence_count) || 1, regions.length);
    regions.forEach((region) => group.instances.push({
      page: Number(item.page) || 1, region
    }));
  });
  return [...map.values()];
}

function normalizeRegions(value) {
  if (!Array.isArray(value)) return [];
  const candidates = value.length === 4 ? [value] : value;
  return candidates.filter((region) =>
    Array.isArray(region) && region.length === 4 &&
    region.every((coordinate) => Number.isFinite(Number(coordinate)))
  ).map((region) => region.map((coordinate) =>
    Math.max(0, Math.min(1000, Number(coordinate)))
  )).filter(([x0, y0, x1, y1]) => x1 > x0 && y1 > y0);
}

function renderPage(page, groups) {
  const pageNumber = Number(page.page) || 1;
  const boxes = groups.flatMap((group) =>
    group.instances.filter((item) => item.page === pageNumber).map((item) => {
      const [x0, y0, x1, y1] = item.region;
      return `<div class="component-box" style="--color:${group.color};left:${x0 / 10}%;top:${y0 / 10}%;width:${(x1 - x0) / 10}%;height:${(y1 - y0) / 10}%"></div>`;
    })
  ).join("");
  return `<figure>
    <figcaption>第 ${pageNumber} 页 · ${boxes ? "已标注识别位置" : "无定位框"}</figcaption>
    <div class="page-canvas">
      <img src="${escapeHtml(page.data_url)}" alt="第 ${pageNumber} 页图纸预览" />
      <div class="annotation-layer">${boxes}</div>
    </div>
  </figure>`;
}

function renderTitleBlock(titleBlock) {
  const fields = titleBlock?.fields || {};
  const rows = [
    ["客户名称", fields["客户名称"]],
    ["工程名称", fields["工程名称"]],
    ["系统名称", fields["系统名称"]],
    ["公司名称", fields["公司名称"]],
    ["公司英文名", fields["公司英文名"]],
    ["合同号", fields["合同号"]],
    ["版本号", fields["版本号"]],
    ["图纸名称", fields["图纸名称"]],
    ["总页数", fields["总页数"]],
    ["原理图号", fields["原理图号"]],
    ["当前页", fields["当前页"]]
  ];
  const hasValue = rows.some(([, value]) => String(value || "").trim());
  if (!hasValue) {
    return `<p class="empty-copy">未提取到图签信息。</p>`;
  }
  const source = titleBlock?.text_source ? `<p class="title-block-meta">来源：${escapeHtml(titleBlock.text_source)}</p>` : "";
  return `${source}<table class="component-table title-block-fields">
    <tbody>${rows.map(([label, value]) => `<tr>
      <th>${escapeHtml(label)}</th>
      <td>${escapeHtml(String(value || "").trim() || "--")}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function renderControlSignal(configuration) {
  const signalGroups = Array.isArray(configuration?.signal_inputs)
    ? configuration.signal_inputs : [];
  const controlModes = Array.isArray(configuration?.control_modes)
    ? configuration.control_modes : [];
  if (!signalGroups.length && !controlModes.length) {
    return `<p class="empty-copy">未从 PDF 文本层提取到控制与信号配置信息。</p>`;
  }
  const signalTable = signalGroups.length
    ? `<section class="configuration-section">
        <h4>信号输入</h4>
        <table class="component-table configuration-table">
          <thead><tr><th>分类</th><th>信号项</th></tr></thead>
          <tbody>${signalGroups.map((group) => `<tr>
            <td>${escapeHtml(group.category || "其他")}</td>
            <td><div class="configuration-tags">${(group.items || []).map(
              (item) => `<span>${escapeHtml(item)}</span>`
            ).join("")}</div></td>
          </tr>`).join("")}</tbody>
        </table>
      </section>`
    : "";
  const controllers = [...new Set(controlModes.map(
    (mode) => String(mode.controller || "").trim()
  ).filter(Boolean))];
  const actions = [...new Set(controlModes.map(
    (mode) => String(mode.action || "").trim()
  ).filter(Boolean))];
  const controlTable = controlModes.length
    ? `<section class="configuration-section">
        <h4>控制方式</h4>
        <table class="component-table configuration-table control-matrix">
          <thead><tr><th>控制动作</th>${controllers.map(
            (controller) => `<th>${escapeHtml(controller)}</th>`
          ).join("")}</tr></thead>
          <tbody>${actions.map((action) => `<tr>
            <td>${escapeHtml(action)}</td>${controllers.map((controller) =>
              `<td>${controlModes.some((mode) =>
                String(mode.controller || "").trim() === controller &&
                String(mode.action || "").trim() === action
              ) ? "✓" : "—"}</td>`
            ).join("")}
          </tr>`).join("")}</tbody>
        </table>
      </section>`
    : "";
  const pages = Array.isArray(configuration?.pages)
    ? configuration.pages.map((page) => page.page).filter(Boolean) : [];
  const meta = `<p class="title-block-meta">来源：${escapeHtml(
    configuration?.text_source || "pdf_text"
  )}${pages.length ? ` · 页码：${escapeHtml([...new Set(pages)].join("、"))}` : ""}</p>`;
  return `<div class="configuration-card">${meta}${signalTable}${controlTable}</div>`;
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.classList.toggle("active", tab.dataset.tab === name)
  );
  $("componentsPanel").classList.toggle("hidden", name !== "components");
  $("titleBlockPanel").classList.toggle("hidden", name !== "titleBlock");
  $("controlSignalPanel").classList.toggle("hidden", name !== "controlSignal");
  $("jsonPanel").classList.toggle("hidden", name !== "json");
}

function downloadJson() {
  const payload = JSON.stringify(exportableResult(state.result), null, 2);
  const blob = new Blob([payload], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.result.document.replace(/\.(pdf|png)$/i, "")}-components.json`;
  link.click(); URL.revokeObjectURL(link.href);
}

function exportableResult(result) {
  if (!result) return result;
  const { preview_pages: _previewPages, ...payload } = result;
  return payload;
}

function formatBytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1048576) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1048576).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[character]));
}

function formatCodeForWrap(value) {
  return escapeHtml(value).replace(/([,;])/g, "$1<wbr>");
}
