const state = {
  file: null,
  result: null,
  analysisToken: 0
};
const LAST_RESULT_KEY = "electronic-recognition:last-result-id";
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
  count: $("componentCount"), customRuleCount: $("customRuleCount"),
  referenceLimit: $("referenceLimit"),
  empty: $("emptyState"), loading: $("loadingState"), content: $("resultContent"),
  download: $("downloadButton"), typeTotal: $("typeTotal"),
  instanceTotal: $("instanceTotal"), elapsed: $("elapsedTime"),
  table: $("componentTable"), annotations: $("annotations"),
  combinations: $("combinationContent"),
  titleBlock: $("titleBlockTable"), controlSignal: $("controlSignalContent"),
  componentTableInfo: $("componentTableInfo"),
  intermediateProcess: $("intermediateProcessContent"),
  recognitionLog: $("recognitionLog"),
  recognitionLogList: $("recognitionLogList"),
  recognitionLogLatest: $("recognitionLogLatest"),
  recognitionLogCount: $("recognitionLogCount")
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindEvents();
  await Promise.all([loadConfig(), restoreLastResult()]);
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
  document.querySelectorAll(".tab").forEach((tab) => {
    const panel = $(`${tab.dataset.tab}Panel`);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", tab.classList.contains("active"));
    if (panel) {
      tab.setAttribute("aria-controls", panel.id);
      panel.setAttribute("role", "tabpanel");
    }
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });
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
    elements.customRuleCount.textContent = `${config.custom_rule_count || 0} 条`;
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
  state.analysisToken += 1;
  state.file = null; elements.input.value = "";
  elements.card.classList.add("hidden"); elements.drop.classList.remove("hidden");
  elements.submit.disabled = true;
  sessionStorage.removeItem(LAST_RESULT_KEY);
  clearResult();
}

function clearResult() {
  state.result = null;
  elements.content.classList.add("hidden");
  elements.loading.classList.add("hidden");
  elements.empty.classList.remove("hidden");
  elements.download.classList.add("hidden");
}

async function analyze(event) {
  event.preventDefault();
  if (!state.file) return;
  const token = ++state.analysisToken;
  setLoading(true);
  const data = new FormData();
  data.append("drawing", state.file);
  try {
    const response = await fetch("/analyze", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) {
      const message = errorMessage(payload, "识别失败");
      if (payload?.detail?.result_id) {
        sessionStorage.setItem(
          LAST_RESULT_KEY,
          String(payload.detail.result_id)
        );
        const failed = await loadSavedResult(payload.detail);
        state.result = failed; render(failed);
        elements.message.textContent = message;
        return;
      }
      throw new Error(message);
    }
    if (payload?.result_id) {
      sessionStorage.setItem(LAST_RESULT_KEY, String(payload.result_id));
    }
    const result = await waitForAnalysis(payload, token);
    if (token !== state.analysisToken) return;
    state.result = result; render(result);
    if (result.status === "failed") {
      elements.message.textContent =
        result.warnings?.[0] || "识别任务失败，请展开日志查看详情。";
    }
  } catch (error) {
    if (token !== state.analysisToken) return;
    elements.message.textContent = error.message;
    elements.empty.classList.remove("hidden");
  } finally {
    if (token === state.analysisToken) setLoading(false);
  }
}

async function restoreLastResult() {
  const restoreToken = state.analysisToken;
  const queryResultId = new URLSearchParams(window.location.search).get(
    "result_id"
  );
  const resultId = queryResultId || sessionStorage.getItem(LAST_RESULT_KEY);
  if (!resultId) return;
  try {
    const manifestResponse = await fetch(
      `/api/results/${encodeURIComponent(resultId)}/manifest`,
      { cache: "no-store" }
    );
    if (restoreToken !== state.analysisToken) return;
    if (manifestResponse.ok) {
      const manifest = await manifestResponse.json();
      if (manifest.status === "running") {
        const token = ++state.analysisToken;
        setLoading(true);
        try {
          const result = await waitForAnalysis({
            result_id: resultId,
            result_url: `/api/results/${encodeURIComponent(resultId)}`,
            steps_url: `/api/results/${encodeURIComponent(resultId)}/steps`
          }, token);
          if (token !== state.analysisToken) return;
          state.result = result;
          render(result);
        } finally {
          if (token === state.analysisToken) setLoading(false);
        }
        return;
      }
    }
    const result = await loadSavedResult({
      result_id: resultId,
      result_url: `/api/results/${encodeURIComponent(resultId)}`
    });
    if (restoreToken !== state.analysisToken) return;
    state.result = result;
    render(result);
  } catch (error) {
    if (restoreToken !== state.analysisToken) return;
    if (
      !queryResultId &&
      sessionStorage.getItem(LAST_RESULT_KEY) === resultId
    ) {
      sessionStorage.removeItem(LAST_RESULT_KEY);
    }
    elements.message.textContent = `最近一次识别结果恢复失败：${error.message}`;
  }
}

async function waitForAnalysis(payload, token) {
  if (!payload?.result_id) return payload;
  const stepsUrl = payload.steps_url ||
    `/api/results/${encodeURIComponent(payload.result_id)}/steps`;
  while (token === state.analysisToken) {
    try {
      const response = await fetch(stepsUrl, { cache: "no-store" });
      const progress = await response.json();
      if (response.ok) {
        renderRecognitionLogs(progress.steps?.recognition_log || []);
        if (progress.status === "complete" || progress.status === "failed") {
          return loadSavedResult(payload);
        }
      }
    } catch {
      // A transient polling error should not cancel the server-side task.
    }
    await delay(900);
  }
  throw new Error("识别任务已取消。");
}

async function loadSavedResult(payload) {
  if (!payload?.result_id) {
    return payload;
  }
  const url = payload.result_url || `/api/results/${encodeURIComponent(payload.result_id)}`;
  const response = await fetch(url);
  const saved = await response.json();
  if (!response.ok) throw new Error(errorMessage(saved, "识别结果读取失败"));
  return hydrateSavedSteps(saved);
}

async function hydrateSavedSteps(result) {
  if (!result?.result_id) {
    return result;
  }
  try {
    const response = await fetch(`/api/results/${encodeURIComponent(result.result_id)}/steps`);
    const payload = await response.json();
    if (response.ok) {
      result.persisted_steps = payload;
      result.recognition_steps = {
        ...(result.recognition_steps || {}),
        ...(payload.steps || {})
      };
    }
  } catch {
    // Steps are a diagnostic convenience; the main result can still render.
  }
  return result;
}

function errorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) {
    return detail.result_id
      ? `${detail.message}（结果ID：${detail.result_id}）`
      : detail.message;
  }
  return fallback;
}

function setLoading(active) {
  elements.submit.disabled = active || !state.file;
  elements.submit.classList.toggle("loading", active);
  elements.submit.querySelector("span").textContent = active ? "识别中" : "开始识别";
  if (active) {
    elements.recognitionLog.open = false;
    renderRecognitionLogs([
      {
        time: new Date().toISOString(),
        level: "info",
        message: "正在上传图纸并创建识别任务。"
      }
    ]);
    elements.empty.classList.add("hidden");
    elements.content.classList.add("hidden");
    elements.loading.classList.remove("hidden");
    elements.message.textContent = "";
  } else {
    elements.loading.classList.add("hidden");
  }
}

function renderRecognitionLogs(logs) {
  const entries = Array.isArray(logs) ? logs : [];
  elements.recognitionLogCount.textContent = String(entries.length);
  elements.recognitionLogLatest.textContent = entries.length
    ? String(entries[entries.length - 1].message || "正在识别")
    : "等待任务启动";
  elements.recognitionLogList.innerHTML = entries.map((entry) => {
    const level = ["warning", "error"].includes(entry.level)
      ? entry.level : "info";
    const time = formatLogTime(entry.time);
    return `<li class="${level}">
      <time datetime="${escapeHtml(entry.time || "")}">${escapeHtml(time)}</time>
      <span>${escapeHtml(entry.message || "")}</span>
    </li>`;
  }).join("");
  if (elements.recognitionLog.open) {
    elements.recognitionLogList.scrollTop =
      elements.recognitionLogList.scrollHeight;
  }
}

function formatLogTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(date);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function render(result) {
  if (result?.result_id) {
    sessionStorage.setItem(LAST_RESULT_KEY, String(result.result_id));
  }
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
  elements.combinations.innerHTML = renderCombinations(
    result.detected_combinations || []
  );
  elements.titleBlock.innerHTML = renderTitleBlock(result.title_block);
  elements.controlSignal.innerHTML = renderControlSignal(
    result.control_signal_configuration
  );
  elements.componentTableInfo.innerHTML = renderComponentTableInfo(
    result.component_table
  );
  elements.intermediateProcess.innerHTML = renderIntermediateProcess(result, groups);
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
  return `<figure id="page-${pageNumber}">
    <figcaption>第 ${pageNumber} 页 · ${boxes ? "已标注识别位置" : "无定位框"}</figcaption>
    <div class="page-canvas">
      <img src="${escapeHtml(page.data_url)}" alt="第 ${pageNumber} 页图纸预览" />
      <div class="annotation-layer">${boxes}</div>
    </div>
  </figure>`;
}

function renderCombinations(combinations) {
  if (!Array.isArray(combinations) || !combinations.length) {
    return `<p class="empty-copy">当前图纸未匹配到已配置的组合元件规则。</p>`;
  }
  return `<div class="combination-grid">${combinations.map((item) => {
    const confidence = Math.round((Number(item.confidence) || 0) * 100);
    const pages = Array.isArray(item.pages) && item.pages.length
      ? `第 ${item.pages.join("、")} 页`
      : "跨页或未定位";
    const members = Array.isArray(item.members) ? item.members : [];
    const evidence = Array.isArray(item.evidence) ? item.evidence : [];
    return `<article class="combination-card">
      <header>
        <div>
          <span class="combination-rule">${escapeHtml(item.rule_id || "rule")}</span>
          <h4>${escapeHtml(item.name || "组合元件")}</h4>
        </div>
        <span class="combination-confidence" aria-label="置信度 ${confidence}%">${confidence}%</span>
      </header>
      <div class="combination-meta">
        <span>组合代号 <strong>${formatCodeForWrap(item.group_code || "--")}</strong></span>
        <span>物理组合数 <strong>${escapeHtml(item.physical_quantity || 1)}</strong></span>
        <span>位置 <strong>${escapeHtml(pages)}</strong></span>
      </div>
      <div class="combination-members">
        ${members.map((member) => `<div class="combination-member">
          <span>${escapeHtml(member.role || "成员")}</span>
          <strong>${formatCodeForWrap((member.codes || []).join(",") || "--")}</strong>
          <small>${escapeHtml((member.labels || []).join("；") || "由规则推断")}</small>
          <b>× ${escapeHtml(member.quantity || 1)}</b>
        </div>`).join("")}
      </div>
      ${evidence.length ? `<ul class="combination-evidence">${evidence.map(
        (text) => `<li>${escapeHtml(text)}</li>`
      ).join("")}</ul>` : ""}
    </article>`;
  }).join("")}</div>`;
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

function renderComponentTableInfo(componentTable) {
  const rows = Array.isArray(componentTable?.rows) ? componentTable.rows : [];
  if (!rows.length) {
    return `<p class="empty-copy">未从 PDF 文本层提取到图纸表格信息。</p>`;
  }
  const columns = ["序号", "代号", "元件名称", "规格型号", "数量", "备注"];
  const pages = Array.isArray(componentTable?.pages)
    ? componentTable.pages.map((page) => page.page).filter(Boolean) : [];
  const meta = `<p class="title-block-meta">来源：${escapeHtml(
    componentTable?.text_source || "pdf_text"
  )}${pages.length ? ` · 页码：${escapeHtml([...new Set(pages)].join("、"))}` : ""} · ${rows.length} 行</p>`;
  return `<div class="component-table-info-card">${meta}
    <div class="component-table-info-wrap">
      <table class="component-table drawing-table">
        <colgroup>
          <col class="sequence"><col class="code"><col class="name">
          <col class="model"><col class="quantity"><col class="note">
        </colgroup>
        <thead><tr>${columns.map((column) =>
          `<th>${escapeHtml(column)}</th>`
        ).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${columns.map((column) =>
          `<td>${escapeHtml(String(row?.[column] || "").trim() || "--")}</td>`
        ).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  </div>`;
}

function renderLabelComparison(result, groups) {
  const titleFields = result.title_block?.fields || {};
  const tableRows = Array.isArray(result.component_table?.rows)
    ? result.component_table.rows : [];
  const recognitionRows = groups.map((group) => ({
    code: normalizeCompareText(group.code),
    rawCode: group.code,
    label: group.label,
    count: group.count
  }));
  const comparisons = tableRows.map((row) => {
    const tagCode = normalizeCompareText(row?.["代号"]);
    const tagName = String(row?.["元件名称"] || "").trim();
    const tagQuantity = parseCount(row?.["数量"]);
    const matched = recognitionRows.find((item) =>
      item.code && tagCode && (item.code === tagCode || item.code.includes(tagCode) || tagCode.includes(item.code))
    );
    const recognizedCount = matched ? Number(matched.count) || 0 : 0;
    let status = "missing";
    let statusText = "未识别";
    if (!tagCode) {
      status = "empty";
      statusText = "标签缺失";
    } else if (matched && tagQuantity !== null && recognizedCount !== tagQuantity) {
      status = "mismatch";
      statusText = "数量不一致";
    } else if (matched) {
      status = "match";
      statusText = "一致";
    }
    return {
      sequence: String(row?.["序号"] || "").trim(),
      code: String(row?.["代号"] || "").trim(),
      tagName,
      model: String(row?.["规格型号"] || "").trim(),
      tagQuantity,
      recognizedName: matched?.label || "",
      recognizedCode: matched?.rawCode || "",
      recognizedCount,
      status,
      statusText
    };
  });
  const matchedCount = comparisons.filter((item) => item.status === "match").length;
  const mismatchCount = comparisons.filter((item) => item.status === "mismatch").length;
  const missingCount = comparisons.filter((item) => item.status === "missing").length;
  const titleRows = [
    ["工程名称", titleFields["工程名称"]],
    ["图纸名称", titleFields["图纸名称"]],
    ["原理图号", titleFields["原理图号"]],
    ["合同号", titleFields["合同号"]]
  ].filter(([, value]) => String(value || "").trim());

  if (!tableRows.length && !titleRows.length) {
    return `<p class="empty-copy">暂无可比对的图签信息或图纸标签。</p>`;
  }

  const titleSummary = titleRows.length
    ? `<section class="label-compare-section">
        <h4>图签摘要</h4>
        <div class="label-compare-title-grid">${titleRows.map(([label, value]) =>
          `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
        ).join("")}</div>
      </section>`
    : "";

  const comparisonTable = comparisons.length
    ? `<section class="label-compare-section">
        <h4>图纸标签与识别结果</h4>
        <div class="component-table-info-wrap">
          <table class="component-table label-compare-table">
            <thead><tr>
              <th>状态</th><th>序号</th><th>图纸标签代号</th><th>图纸标签名称</th>
              <th>标签数量</th><th>识别代号</th><th>识别名称</th><th>识别数量</th>
            </tr></thead>
            <tbody>${comparisons.map((item) => `<tr>
              <td><span class="compare-badge ${item.status}">${escapeHtml(item.statusText)}</span></td>
              <td>${escapeHtml(item.sequence || "--")}</td>
              <td>${escapeHtml(item.code || "--")}</td>
              <td>${escapeHtml(item.tagName || "--")}</td>
              <td>${escapeHtml(item.tagQuantity ?? "--")}</td>
              <td>${escapeHtml(item.recognizedCode || "--")}</td>
              <td>${escapeHtml(item.recognizedName || "--")}</td>
              <td>${escapeHtml(item.recognizedCount || "--")}</td>
            </tr>`).join("")}</tbody>
          </table>
        </div>
      </section>`
    : `<p class="empty-copy">未提取到图纸标签表格，无法进行标签逐项比对。</p>`;

  return `<div class="label-compare-card">
    <div class="label-compare-summary">
      <article><span>图签字段</span><strong>${titleRows.length}</strong></article>
      <article><span>图纸标签</span><strong>${tableRows.length}</strong></article>
      <article><span>一致</span><strong>${matchedCount}</strong></article>
      <article><span>待核对</span><strong>${mismatchCount + missingCount}</strong></article>
    </div>
    ${titleSummary}
    ${comparisonTable}
  </div>`;
}

function normalizeCompareText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[，,;；、]/g, ",")
    .replace(/^[-_]+|[-_]+$/g, "");
}

function parseCount(value) {
  const match = String(value || "").match(/\d+/);
  return match ? Number(match[0]) : null;
}

function renderIntermediateSteps(steps) {
  const entries = Object.entries(steps || {}).filter(([, payload]) =>
    payload !== undefined
  );
  if (!entries.length) {
    return `<p class="empty-copy">暂无中间结果。</p>`;
  }
  return `<div class="intermediate-grid">
    ${entries.map(([name, payload]) =>
      renderStepJsonBlock(stepTitle(name), payload)
    ).join("")}
  </div>`;
}

function renderStepJsonBlock(title, payload) {
  const count = Array.isArray(payload)
    ? `${payload.length} 项`
    : payload && typeof payload === "object"
      ? `${Object.keys(payload).length} 键`
      : "1 项";
  return `<section class="intermediate-block">
    <header><h4>${escapeHtml(title)}</h4><span>${escapeHtml(count)}</span></header>
    <pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
  </section>`;
}

function renderIntermediateProcess(result, groups) {
  const steps = {
    ...(result.intermediate_steps || {}),
    warnings: result.warnings || result.intermediate_steps?.warnings || []
  };
  return `<div class="intermediate-process-stack">
    ${renderIntermediateDisclosure(
      "标签比对",
      "对照图签信息、图纸标签与元件识别结果。",
      renderLabelComparison(result, groups)
    )}
    ${renderIntermediateDisclosure(
      "中间结果 JSON",
      "展示开放识别与 RAG 修正的中间数据。",
      renderIntermediateSteps(steps)
    )}
    ${renderIntermediateDisclosure(
      "原始 JSON",
      "展示当前识别结果的导出内容。",
      `<pre>${escapeHtml(JSON.stringify(exportableResult(result), null, 2))}</pre>`
    )}
  </div>`;
}

function renderIntermediateDisclosure(title, description, content) {
  return `<details class="intermediate-process-section">
    <summary>
      <span class="intermediate-process-heading">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(description)}</span>
      </span>
      <svg class="intermediate-process-chevron" viewBox="0 0 24 24" aria-hidden="true">
        <path d="m8 10 4 4 4-4" />
      </svg>
    </summary>
    <div class="intermediate-process-content">${content}</div>
  </details>`;
}

function stepTitle(name) {
  const titles = {
    recognition_log: "00 识别日志",
    document: "00 文档解析",
    title_block: "01 图签信息",
    control_signal_configuration: "02 控制与信号配置",
    component_table: "03 图纸标签",
    open_symbols: "04 开放识别",
    open_recognition_tiles: "04A 切片识别状态",
    open_categories: "04B 开放类别汇总",
    rag_corrections: "05 RAG 修正",
    detected_components: "06 元件结果",
    detected_combinations: "06B 组合元件结果",
    preview_pages: "07 页面预览",
    warnings: "08 警告",
    meta: "09 元信息",
    legacy_detected_components: "旧版元件结果"
  };
  return titles[name] || name;
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  $("componentsPanel").classList.toggle("hidden", name !== "components");
  $("combinationsPanel").classList.toggle("hidden", name !== "combinations");
  $("titleBlockPanel").classList.toggle("hidden", name !== "titleBlock");
  $("controlSignalPanel").classList.toggle("hidden", name !== "controlSignal");
  $("componentTableInfoPanel").classList.toggle("hidden", name !== "componentTableInfo");
  $("intermediateProcessPanel").classList.toggle("hidden", name !== "intermediateProcess");
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
