const state = {
  config: null,
  activeKind: "component",
  components: [],
  rules: [],
  selectedId: "",
  editorMode: "closed",
  draft: null,
};

const elements = {
  status: document.getElementById("dataStatus"),
  componentTotal: document.getElementById("componentTotal"),
  ruleTotal: document.getElementById("ruleTotal"),
  enabledRuleTotal: document.getElementById("enabledRuleTotal"),
  updatedAt: document.getElementById("updatedAt"),
  listPanel: document.getElementById("listPanel"),
  editorBody: document.getElementById("editorBody"),
  editorTitle: document.getElementById("editorTitle"),
  editorEyebrow: document.getElementById("editorEyebrow"),
  feedback: document.getElementById("feedbackMessage"),
  search: document.getElementById("searchInput"),
  secondaryFilter: document.getElementById("secondaryFilter"),
  refresh: document.getElementById("refreshButton"),
  create: document.getElementById("createButton"),
  save: document.getElementById("saveButton"),
  remove: document.getElementById("deleteButton"),
  validate: document.getElementById("validateButton"),
  test: document.getElementById("testButton"),
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindEvents();
  await loadAll();
}

function bindEvents() {
  document.querySelectorAll(".kind-tab").forEach((button) => {
    button.addEventListener("click", async () => {
      state.activeKind = button.dataset.kind || "component";
      document.querySelectorAll(".kind-tab").forEach((tab) =>
        tab.classList.toggle("active", tab === button)
      );
      state.selectedId = "";
      state.editorMode = "closed";
      renderFilters();
      renderList();
      renderEditor();
    });
  });
  elements.search.addEventListener("input", renderList);
  elements.secondaryFilter.addEventListener("change", renderList);
  elements.refresh.addEventListener("click", loadAll);
  elements.create.addEventListener("click", handleCreate);
  elements.save.addEventListener("click", handleSave);
  elements.remove.addEventListener("click", handleDelete);
  elements.validate.addEventListener("click", handleValidate);
  elements.test.addEventListener("click", handleTest);
}

async function loadAll() {
  setDataStatus("数据读取中", "");
  setFeedback("数据刷新中...", "success");
  try {
    const [config, components, rules] = await Promise.all([
      fetchJson("/api/config"),
      fetchJson("/api/knowledge"),
      fetchJson("/api/custom-rules"),
    ]);
    state.config = config;
    state.components = components.items || [];
    state.rules = rules.items || [];
    renderStats();
    renderFilters();
    renderList();
    renderEditor();
    setDataStatus("数据已加载", "online");
    setFeedback("数据已同步。", "success");
  } catch (error) {
    setDataStatus("读取失败", "error");
    setFeedback(error.message, "error");
  }
}

function renderStats() {
  elements.componentTotal.textContent = String(state.components.length);
  elements.ruleTotal.textContent = String(state.rules.length);
  elements.enabledRuleTotal.textContent = String(
    state.rules.filter((item) => item.enabled).length
  );
  elements.updatedAt.textContent = new Date().toLocaleString("zh-CN");
}

function setDataStatus(message, stateName) {
  elements.status.classList.remove("online", "error");
  if (stateName) elements.status.classList.add(stateName);
  elements.status.querySelector("b").textContent = message;
}

function renderFilters() {
  const options = state.activeKind === "component"
    ? uniqueValues(state.components.map((item) => item.component_type || "未分类"))
    : uniqueValues(state.rules.map((item) => item.scope || "same_page"));
  elements.secondaryFilter.innerHTML = `<option value="">全部</option>${options.map(
    (value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
  ).join("")}`;
}

function renderList() {
  const items = getFilteredItems();
  if (!items.length) {
    elements.listPanel.innerHTML = `<div class="empty-editor"><h3>暂无数据</h3><p>可以点击右上角“新建”开始录入。</p></div>`;
    return;
  }
  elements.listPanel.innerHTML = items.map((item) => `<button
      class="list-item${item.id === state.selectedId ? " active" : ""}"
      type="button"
      data-id="${escapeHtml(item.id)}"
    >
      <strong>${escapeHtml(item.name || item.label || item.id)}</strong>
      <span>${escapeHtml(item.id)}</span>
      <span>${escapeHtml(state.activeKind === "component" ? (item.component_type || "未分类") : `${item.scope || "same_page"} · ${item.enabled ? "启用" : "停用"}`)}</span>
    </button>`).join("");
  elements.listPanel.querySelectorAll("[data-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id || "";
      state.editorMode = "edit";
      state.draft = await loadDetail(state.activeKind, state.selectedId);
      renderList();
      renderEditor();
    });
  });
}

function renderEditor() {
  if (!state.draft) {
    elements.editorTitle.textContent = "选择左侧记录查看详情";
    elements.editorEyebrow.textContent = "MANAGEMENT";
    elements.editorBody.innerHTML = `<div class="empty-editor"><h3>从左侧选择记录</h3><p>单元件支持图片维护，组合元件支持成员编排和精确组件选择。</p></div>`;
    return;
  }
  elements.remove.disabled = false;
  if (state.activeKind === "component") {
    renderComponentEditor();
  } else {
    renderRuleEditor();
  }
}

function renderComponentEditor() {
  const template = document.getElementById("componentEditorTemplate");
  const node = template.content.firstElementChild.cloneNode(true);
  elements.editorTitle.textContent = state.editorMode === "create" ? "新建单元件" : `编辑单元件 · ${state.draft.label || state.draft.id}`;
  elements.editorEyebrow.textContent = "COMPONENT";
  fillValue(node, "id", state.draft.id || "");
  fillValue(node, "label", state.draft.label || "");
  fillValue(node, "component_type", state.draft.component_type || "");
  fillValue(node, "model", state.draft.model || "");
  fillValue(node, "definition", state.draft.definition || "");
  fillValue(node, "standards", (state.draft.standards || []).join(", "));
  fillValue(node, "aliases", (state.draft.aliases || []).join(", "));
  fillValue(node, "source", state.draft.source || "");
  fillValue(node, "notes", state.draft.notes || "");
  node.querySelector('[name="enabled"]').checked = state.draft.enabled !== false;
  const preview = node.querySelector("[data-image-preview]");
  const images = [];
  if (state.draft.image_url) {
    images.push({
      label: "主图",
      url: state.draft.image_url,
      path: state.draft.image_path || "",
    });
  }
  (state.draft.variant_image_urls || []).forEach((url, index) => {
    images.push({
      label: `变体 ${index + 1}`,
      url,
      path: (state.draft.variant_images || [])[index] || "",
    });
  });
  preview.innerHTML = images.length
    ? images.map((item) => `<figure class="image-preview-card">
        <div class="image-preview-canvas">
          <img
            src="${escapeHtml(item.url)}"
            alt="${escapeHtml(state.draft.label || state.draft.id)} ${escapeHtml(item.label)}"
          />
        </div>
        <figcaption>
          <strong>${escapeHtml(item.label)}</strong>
          <span title="${escapeHtml(item.path)}">${escapeHtml(item.path || item.url)}</span>
        </figcaption>
      </figure>`).join("")
    : `<div class="image-chip">暂无图片</div>`;
  elements.editorBody.innerHTML = "";
  elements.editorBody.appendChild(node);
}

function renderRuleEditor() {
  const template = document.getElementById("ruleEditorTemplate");
  const node = template.content.firstElementChild.cloneNode(true);
  elements.editorTitle.textContent = state.editorMode === "create" ? "新建组合元件" : `编辑组合元件 · ${state.draft.name || state.draft.id}`;
  elements.editorEyebrow.textContent = "RULE";
  fillValue(node, "id", state.draft.id || "");
  fillValue(node, "name", state.draft.name || "");
  fillValue(node, "scope", state.draft.scope || "same_page");
  fillValue(node, "confidence", String(state.draft.confidence ?? 0.95));
  fillValue(node, "source", state.draft.source || "");
  fillValue(node, "description", state.draft.description || "");
  fillValue(node, "aliases", (state.draft.aliases || []).join(", "));
  fillValue(node, "notes", state.draft.notes || "");
  node.querySelector('[name="enabled"]').checked = state.draft.enabled !== false;
  const imagePreview = node.querySelector("[data-rule-image-preview]");
  imagePreview.innerHTML = state.draft.image_url
    ? `<figure class="image-preview-card">
        <div class="image-preview-canvas">
          <img
            src="${escapeHtml(state.draft.image_url)}"
            alt="${escapeHtml(state.draft.name || state.draft.id)} 预览图"
          />
        </div>
        <figcaption>
          <strong>组合元件预览图</strong>
          <span title="${escapeHtml(state.draft.image_path || "")}">${escapeHtml(state.draft.image_path || state.draft.image_url)}</span>
        </figcaption>
      </figure>`
    : `<div class="image-chip">暂无图片</div>`;
  const builtinReadonly = state.draft.engine === "builtin";
  const memberList = node.querySelector("[data-member-list]");
  (state.draft.members || []).forEach((member) => {
    memberList.appendChild(renderMemberRow(member));
  });
  if (!(state.draft.members || []).length) {
    memberList.appendChild(renderMemberRow({ role: "", min_quantity: 1, component_ids: [], code_patterns: [], label_keywords: [] }));
  }
  node.querySelector('[data-action="add-member"]').addEventListener("click", () => {
    memberList.appendChild(renderMemberRow({ role: "", min_quantity: 1, component_ids: [], code_patterns: [], label_keywords: [] }));
  });
  if (builtinReadonly) {
    node.querySelectorAll('input:not([name="enabled"]), textarea, select').forEach((field) => {
      field.disabled = true;
    });
    node.querySelector('[data-action="add-member"]').disabled = true;
    setFeedback("内置组合元件为只读，只允许调整启用状态。", "success");
  }
  elements.remove.disabled = builtinReadonly;
  elements.editorBody.innerHTML = "";
  elements.editorBody.appendChild(node);
}

function renderMemberRow(member) {
  const template = document.getElementById("memberRowTemplate");
  const node = template.content.firstElementChild.cloneNode(true);
  fillValue(node, "role", member.role || "");
  fillValue(node, "min_quantity", String(member.min_quantity || 1));
  fillValue(node, "code_patterns", (member.code_patterns || []).join(", "));
  fillValue(node, "label_keywords", (member.label_keywords || []).join(", "));
  const select = node.querySelector('[name="component_ids"]');
  select.innerHTML = state.components.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${escapeHtml(item.id)}</option>`).join("");
  Array.from(select.options).forEach((option) => {
    option.selected = (member.component_ids || []).includes(option.value);
  });
  node.querySelector('[data-action="remove-member"]').addEventListener("click", () => {
    node.remove();
  });
  return node;
}

async function handleCreate() {
  state.selectedId = "";
  state.editorMode = "create";
  state.draft = state.activeKind === "component"
    ? { enabled: true, standards: [], aliases: [], variant_images: [] }
    : { enabled: true, scope: "same_page", confidence: 0.95, members: [] };
  renderList();
  renderEditor();
}

async function handleSave() {
  if (!state.draft) return;
  try {
    if (state.activeKind === "component") {
      await saveComponent();
    } else {
      await saveRule();
    }
    await loadAll();
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function saveComponent() {
  const form = elements.editorBody.querySelector('[data-form="component"]');
  const payload = {
    id: fieldValue(form, "id"),
    label: fieldValue(form, "label"),
    component_type: fieldValue(form, "component_type"),
    model: fieldValue(form, "model"),
    definition: fieldValue(form, "definition"),
    standards: splitCsv(fieldValue(form, "standards")),
    aliases: splitCsv(fieldValue(form, "aliases")),
    source: fieldValue(form, "source"),
    notes: fieldValue(form, "notes"),
    enabled: form.querySelector('[name="enabled"]').checked,
    image_path: state.draft.image_path || "",
    variant_images: state.draft.variant_images || [],
  };
  const url = state.editorMode === "create"
    ? "/api/knowledge"
    : `/api/knowledge/${encodeURIComponent(state.draft.id)}`;
  const method = state.editorMode === "create" ? "POST" : "PUT";
  const saved = await fetchJson(url, {
    method,
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
  });
  state.draft = saved;
  await uploadSelectedImage(form, "primaryImage", `/api/knowledge/${encodeURIComponent(saved.id)}/images`, "primary");
  await uploadSelectedImage(form, "variantImage", `/api/knowledge/${encodeURIComponent(saved.id)}/images`, "variant");
  setFeedback("单元件已保存。", "success");
}

async function saveRule() {
  const form = elements.editorBody.querySelector('[data-form="rule"]');
  if (state.draft.engine === "builtin") {
    const saved = await fetchJson(`/api/custom-rules/${encodeURIComponent(state.draft.id)}/enabled`, {
      method: "PATCH",
      body: JSON.stringify({
        enabled: form.querySelector('[name="enabled"]').checked,
      }),
      headers: { "Content-Type": "application/json" },
    });
    state.draft = saved;
    setFeedback("内置组合元件启用状态已更新。", "success");
    return;
  }
  const payload = {
    id: fieldValue(form, "id"),
    name: fieldValue(form, "name"),
    scope: fieldValue(form, "scope"),
    confidence: Number(fieldValue(form, "confidence") || "0.95"),
    source: fieldValue(form, "source"),
    description: fieldValue(form, "description"),
    aliases: splitCsv(fieldValue(form, "aliases")),
    notes: fieldValue(form, "notes"),
    enabled: form.querySelector('[name="enabled"]').checked,
    members: collectMembers(form),
  };
  const url = state.editorMode === "create"
    ? "/api/custom-rules"
    : `/api/custom-rules/${encodeURIComponent(state.draft.id)}`;
  const method = state.editorMode === "create" ? "POST" : "PUT";
  const saved = await fetchJson(url, {
    method,
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
  });
  state.draft = saved;
  await uploadSelectedImage(form, "ruleImage", `/api/custom-rules/${encodeURIComponent(saved.id)}/image`);
  setFeedback("组合元件已保存。", "success");
}

async function handleDelete() {
  if (!state.draft || !confirm("确认删除当前记录吗？")) return;
  if (state.activeKind === "rule" && state.draft.engine === "builtin") {
    setFeedback("内置组合元件不允许删除。", "error");
    return;
  }
  try {
    const url = state.activeKind === "component"
      ? `/api/knowledge/${encodeURIComponent(state.draft.id)}`
      : `/api/custom-rules/${encodeURIComponent(state.draft.id)}`;
    await fetchJson(url, { method: "DELETE" });
    state.draft = null;
    state.selectedId = "";
    await loadAll();
    setFeedback("记录已删除。", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function handleValidate() {
  if (state.activeKind !== "rule") return;
  const form = elements.editorBody.querySelector('[data-form="rule"]');
  if (!form) return;
  try {
    const result = await fetchJson("/api/custom-rules/validate", {
      method: "POST",
      body: JSON.stringify({
        id: fieldValue(form, "id") || "draft-rule",
        name: fieldValue(form, "name") || "草稿组合",
        scope: fieldValue(form, "scope"),
        confidence: Number(fieldValue(form, "confidence") || "0.95"),
        members: collectMembers(form),
      }),
      headers: { "Content-Type": "application/json" },
    });
    setFeedback(`规则校验通过，成员 ${result.summary.member_count} 个。`, "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function handleTest() {
  if (state.activeKind !== "rule") return;
  const form = elements.editorBody.querySelector('[data-form="rule"]');
  if (!form) return;
  let input = {};
  const raw = fieldValue(form, "test_payload");
  if (raw.trim()) {
    try {
      input = JSON.parse(raw);
    } catch (error) {
      setFeedback("试运行 JSON 解析失败。", "error");
      return;
    }
  }
  try {
    const result = await fetchJson("/api/custom-rules/test", {
      method: "POST",
      body: JSON.stringify({
        rule: {
          id: fieldValue(form, "id") || "draft-rule",
          name: fieldValue(form, "name") || "草稿组合",
          scope: fieldValue(form, "scope"),
          confidence: Number(fieldValue(form, "confidence") || "0.95"),
          members: collectMembers(form),
        },
        detected_components: input.detected_components || [],
        open_symbols: input.open_symbols || [],
      }),
      headers: { "Content-Type": "application/json" },
    });
    setFeedback(`试运行完成，命中 ${result.matches.length} 条组合。`, "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

function collectMembers(form) {
  return Array.from(form.querySelectorAll(".member-card")).map((card) => ({
    role: fieldValue(card, "role"),
    min_quantity: Number(fieldValue(card, "min_quantity") || "1"),
    component_ids: Array.from(card.querySelector('[name="component_ids"]').selectedOptions).map((option) => option.value),
    code_patterns: splitCsv(fieldValue(card, "code_patterns")),
    label_keywords: splitCsv(fieldValue(card, "label_keywords")),
  })).filter((item) => item.role);
}

async function loadDetail(kind, id) {
  const url = kind === "component"
    ? `/api/knowledge/${encodeURIComponent(id)}`
    : `/api/custom-rules/${encodeURIComponent(id)}`;
  return fetchJson(url);
}

function getFilteredItems() {
  const source = state.activeKind === "component" ? state.components : state.rules;
  const keyword = elements.search.value.trim().toLowerCase();
  const filter = elements.secondaryFilter.value;
  return source.filter((item) => {
    const searchable = JSON.stringify(item).toLowerCase();
    const matchesKeyword = !keyword || searchable.includes(keyword);
    const facet = state.activeKind === "component" ? (item.component_type || "未分类") : (item.scope || "same_page");
    const matchesFilter = !filter || facet === filter;
    return matchesKeyword && matchesFilter;
  });
}

async function uploadSelectedImage(form, fieldName, url, kind = "") {
  const input = form.querySelector(`[name="${fieldName}"]`);
  if (!input || !input.files || !input.files[0]) return;
  const data = new FormData();
  data.append("file", input.files[0]);
  if (kind) data.append("kind", kind);
  await fetchJson(url, { method: "POST", body: data });
}

function setFeedback(message, type) {
  elements.feedback.textContent = message;
  elements.feedback.classList.remove("hidden", "success", "error");
  elements.feedback.classList.add(type);
}

function fieldValue(root, name) {
  return root.querySelector(`[name="${name}"]`)?.value ?? "";
}

function fillValue(root, name, value) {
  const field = root.querySelector(`[name="${name}"]`);
  if (field) field.value = value;
}

function splitCsv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh-CN"));
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : {};
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message || "请求失败";
    throw new Error(message);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[character]));
}
