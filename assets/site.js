const CATALOG_URL = "data/catalog.json";
const CACHE_TOKEN = Date.now().toString(36);
const LANGUAGES = [
  ["zh", "中文"],
  ["en", "EN"],
  ["ja", "日语"],
  ["ko", "韩语"],
];

const state = {
  catalog: null,
  expandedGames: new Set(),
  query: "",
  game: "all",
  report: "all",
};

const elements = {
  latestGrid: document.querySelector("#latestGrid"),
  archiveGrid: document.querySelector("#archiveGrid"),
  updateBadge: document.querySelector("#updateBadge"),
  footerUpdated: document.querySelector("#footerUpdated"),
  searchInput: document.querySelector("#searchInput"),
  gameFilter: document.querySelector("#gameFilter"),
  reportFilter: document.querySelector("#reportFilter"),
  resetFilters: document.querySelector("#resetFilters"),
  resultSummary: document.querySelector("#resultSummary"),
  downloadToast: document.querySelector("#downloadToast"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function freshDataUrl(value) {
  if (!value) return value;
  return `${value}${value.includes("?") ? "&" : "?"}_=${CACHE_TOKEN}`;
}

function beijingToday() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function phaseStatus(phase, today = beijingToday()) {
  if (today < phase.start) return "upcoming";
  if (today > phase.end) return "ended";
  return "active";
}

function chooseLatestPhase(game) {
  const today = beijingToday();
  const phases = [...game.phases].sort((a, b) => a.start.localeCompare(b.start));
  const active = phases.filter((phase) => phase.start <= today && today <= phase.end);
  if (active.length) return active.at(-1);
  const future = phases.filter((phase) => phase.start > today);
  return future[0] || phases.at(-1);
}

function displayDate(value) {
  return value ? value.slice(5).replace("-", "/") : "—";
}

function reportCount(phase) {
  return Object.values(phase.reports || {}).filter((report) => report?.status === "ready").length;
}

function hasReport(phase) {
  return reportCount(phase) > 0;
}

function characterTags(characters = []) {
  if (!characters.length) return '<span class="character-tag unknown">角色待确认</span>';
  return characters
    .map((character) => `<span class="character-tag ${escapeHtml(character.type)}">${escapeHtml(character.name)}</span>`)
    .join("");
}

function statusLabel(status) {
  return { active: "进行中", upcoming: "即将开始", ended: "已结束" }[status];
}

function latestCard(game) {
  const phase = chooseLatestPhase(game);
  const status = phaseStatus(phase);
  const count = reportCount(phase);
  const endClass = phase.end_estimated ? "estimated" : "";
  const switchText = phase.end_estimated
    ? `预计 ${displayDate(phase.end)} 更新`
    : `${displayDate(phase.end)} 结束`;

  return `
    <article class="latest-card" data-scroll-game="${escapeHtml(game.id)}" tabindex="0" role="button" aria-label="查看${escapeHtml(game.name)}版本档案">
      <div class="latest-card-head">
        <img class="game-icon" src="${escapeHtml(game.icon)}" alt="">
        <div class="game-copy">
          <strong>${escapeHtml(game.name)}</strong>
          <span>${escapeHtml(game.name_en)}</span>
        </div>
        <span class="status-pill ${status}">${statusLabel(status)}</span>
      </div>
      <div class="latest-main">
        <div class="version-line">${escapeHtml(phase.version)}<span class="phase-pill">${escapeHtml(phase.phase)}</span></div>
        <div class="date-range ${endClass}">${displayDate(phase.start)} — ${phase.end_estimated ? "预估" : ""}${displayDate(phase.end)}</div>
      </div>
      <div class="character-list">${characterTags(phase.characters)}</div>
      <div class="latest-footer">
        <span class="switch-copy ${endClass}">${switchText}</span>
        <span class="report-count">${count ? `${count} 种语言报告` : "报告待补充"}</span>
      </div>
    </article>`;
}

function renderLatest() {
  elements.latestGrid.innerHTML = state.catalog.games.map(latestCard).join("");
}

function reportButtons(phase) {
  return LANGUAGES.map(([code, label]) => {
    const report = phase.reports?.[code];
    if (!report || report.status !== "ready") {
      return `<span class="language-missing">${label}待补</span>`;
    }
    const dataSource = report.data_source || "";
    const freshSource = freshDataUrl(dataSource);
    const rawHref = dataSource
      ? `report-viewer.html?data=${encodeURIComponent(freshSource)}`
      : report.href;
    const href = escapeHtml(rawHref);
    const filename = escapeHtml(report.download_name || `${phase.version}-${phase.phase}-${label}-舆情报告.html`);
    const sourceAttribute = dataSource ? ` data-source="${escapeHtml(dataSource)}"` : "";
    return `
      <span class="report-set">
        <span class="language-label">${label}</span>
        <a class="report-action" href="${href}" target="_blank" rel="noopener">查看</a>
        <button class="report-action download-report" type="button" data-href="${href}" data-filename="${filename}"${sourceAttribute}>下载</button>
      </span>`;
  }).join("");
}

function phaseMatches(phase) {
  const reportReady = hasReport(phase);
  if (state.report === "ready" && !reportReady) return false;
  if (state.report === "missing" && reportReady) return false;
  if (!state.query) return true;
  const searchable = [
    phase.version,
    phase.phase,
    phase.start,
    phase.end,
    ...phase.characters.map((character) => character.name),
  ].join(" ").toLowerCase();
  return searchable.includes(state.query);
}

function formatMetric(value) {
  const number = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(number)) return null;
  if (number >= 100000000) return `${Number((number / 100000000).toFixed(number >= 1000000000 ? 1 : 2))}亿`;
  if (number >= 10000) return `${Number((number / 10000).toFixed(number >= 100000 ? 1 : 2))}万`;
  return number.toLocaleString("zh-CN");
}

function metricCell(value) {
  const formatted = formatMetric(value);
  if (formatted === null) return '<div class="phase-metric"><span class="metric-value pending">待统计</span></div>';
  return `<div class="phase-metric"><span class="metric-value" title="${escapeHtml(Number(value).toLocaleString("zh-CN"))}">${escapeHtml(formatted)}</span></div>`;
}

function phaseRow(phase) {
  const status = phaseStatus(phase);
  const activeClass = status === "active" ? " active-row" : "";
  const metrics = phase.video_metrics || {};
  return `
    <div class="phase-row${activeClass}">
      <div class="phase-version">${escapeHtml(phase.version)}</div>
      <div class="phase-name">${escapeHtml(phase.phase)}</div>
      <div class="phase-time ${phase.end_estimated ? "estimated" : ""}">${escapeHtml(phase.start)} — ${phase.end_estimated ? "预估" : ""}${escapeHtml(phase.end)}</div>
      <div class="phase-characters">${characterTags(phase.characters)}</div>
      ${metricCell(metrics.video_count)}
      ${metricCell(metrics.total_views)}
      ${metricCell(metrics.total_comments)}
      <div class="report-cell">${reportButtons(phase)}</div>
    </div>`;
}

function visiblePhases(game, matched) {
  const filtersActive = Boolean(state.query) || state.report !== "all";
  if (filtersActive || state.expandedGames.has(game.id)) return matched;

  const latestIds = new Set([...game.phases]
    .sort((a, b) => b.start.localeCompare(a.start))
    .slice(0, 4)
    .map((phase) => phase.id));
  return matched.filter((phase) => hasReport(phase) || latestIds.has(phase.id) || phaseStatus(phase) === "active");
}

function gamePanel(game, matched) {
  const sorted = [...matched].sort((a, b) => b.start.localeCompare(a.start));
  const visible = visiblePhases(game, sorted);
  const hiddenCount = sorted.length - visible.length;
  const expanded = state.expandedGames.has(game.id);
  return `
    <article class="game-panel" id="game-${escapeHtml(game.id)}">
      <div class="game-panel-head">
        <img class="game-icon" src="${escapeHtml(game.icon)}" alt="">
        <div class="panel-title">
          <h3>${escapeHtml(game.name)}</h3>
          <p>${escapeHtml(game.name_en)}</p>
        </div>
        <span class="phase-count">${matched.length} 个版本阶段</span>
      </div>
      <div class="phase-table-head" aria-hidden="true">
        <span>版本</span><span>阶段</span><span>卡池区间</span><span>卡池角色</span><span class="metric-head">视频总数</span><span class="metric-head">视频总播放量</span><span class="metric-head">视频总评论数</span><span class="report-head-label">舆情报告</span>
      </div>
      <div>${visible.map(phaseRow).join("")}</div>
      ${hiddenCount > 0 || expanded ? `<button class="expand-panel" type="button" data-expand-game="${escapeHtml(game.id)}">${expanded ? "收起历史版本" : `展开其余 ${hiddenCount} 个历史阶段`}</button>` : ""}
    </article>`;
}

function renderArchive() {
  const selectedGames = state.catalog.games.filter((game) => state.game === "all" || game.id === state.game);
  const panels = [];
  let resultCount = 0;
  let readyCount = 0;

  selectedGames.forEach((game) => {
    const matched = game.phases.filter(phaseMatches);
    if (!matched.length) return;
    resultCount += matched.length;
    readyCount += matched.filter(hasReport).length;
    panels.push(gamePanel(game, matched));
  });

  elements.resultSummary.textContent = `找到 ${resultCount} 个版本阶段，其中 ${readyCount} 个已有舆情报告`;
  elements.archiveGrid.innerHTML = panels.length
    ? panels.join("")
    : '<div class="empty-results">没有找到符合条件的版本。请尝试清除筛选条件。</div>';
}

function populateFilters() {
  elements.gameFilter.insertAdjacentHTML(
    "beforeend",
    state.catalog.games.map((game) => `<option value="${escapeHtml(game.id)}">${escapeHtml(game.name)}</option>`).join(""),
  );
}

let toastTimer;
function showToast(message) {
  elements.downloadToast.textContent = message;
  elements.downloadToast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elements.downloadToast.classList.remove("show"), 2600);
}

async function downloadReport(button) {
  const href = button.dataset.href;
  const dataSource = button.dataset.source;
  const filename = button.dataset.filename || "舆情报告.html";
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "准备中";
  showToast("正在准备报告文件，请稍候…");

  try {
    let blob;
    if (dataSource) {
      const [templateResponse, dataResponse] = await Promise.all([
        fetch(freshDataUrl("report-viewer.html"), { cache: "no-store" }),
        fetch(freshDataUrl(dataSource), { cache: "no-store" }),
      ]);
      if (!templateResponse.ok || !dataResponse.ok) {
        throw new Error(`HTTP ${templateResponse.status}/${dataResponse.status}`);
      }
      const template = await templateResponse.text();
      const reportData = await dataResponse.json();
      const serialized = JSON.stringify(reportData, null, 2).replace(/<\/script/gi, "<\\/script");
      const standaloneHtml = template.replace(
        /(<script id="reportData" type="application\/json">)[\s\S]*?(<\/script>)/,
        `$1\n${serialized}\n$2`,
      );
      blob = new Blob([standaloneHtml], { type: "text/html;charset=utf-8" });
    } else {
      const response = await fetch(href);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      blob = new Blob([await response.blob()], { type: "text/html;charset=utf-8" });
    }
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    showToast(`已开始下载：${filename}`);
  } catch (error) {
    const fallback = document.createElement("a");
    fallback.href = href;
    fallback.download = filename;
    document.body.append(fallback);
    fallback.click();
    fallback.remove();
    showToast("已切换为浏览器直接下载方式");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function bindEvents() {
  elements.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderArchive();
  });
  elements.gameFilter.addEventListener("change", (event) => {
    state.game = event.target.value;
    renderArchive();
  });
  elements.reportFilter.addEventListener("change", (event) => {
    state.report = event.target.value;
    renderArchive();
  });
  elements.resetFilters.addEventListener("click", () => {
    state.query = "";
    state.game = "all";
    state.report = "all";
    elements.searchInput.value = "";
    elements.gameFilter.value = "all";
    elements.reportFilter.value = "all";
    renderArchive();
  });

  document.addEventListener("click", (event) => {
    const downloadButton = event.target.closest(".download-report");
    if (downloadButton) {
      downloadReport(downloadButton);
      return;
    }
    const expandButton = event.target.closest("[data-expand-game]");
    if (expandButton) {
      const gameId = expandButton.dataset.expandGame;
      state.expandedGames.has(gameId) ? state.expandedGames.delete(gameId) : state.expandedGames.add(gameId);
      renderArchive();
      document.querySelector(`#game-${CSS.escape(gameId)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const card = event.target.closest("[data-scroll-game]");
    if (card) {
      document.querySelector(`#game-${CSS.escape(card.dataset.scrollGame)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  document.addEventListener("keydown", (event) => {
    const card = event.target.closest?.("[data-scroll-game]");
    if (card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      card.click();
    }
  });
}

async function init() {
  try {
    const response = await fetch(CATALOG_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`目录读取失败：HTTP ${response.status}`);
    state.catalog = await response.json();
    if (state.catalog.schema_version !== 1 || !Array.isArray(state.catalog.games)) {
      throw new Error("目录格式不受支持");
    }
    elements.updateBadge.textContent = `数据更新：${state.catalog.updated_at}`;
    elements.footerUpdated.textContent = `目录更新时间：${state.catalog.updated_at}`;
    populateFilters();
    renderLatest();
    renderArchive();
    bindEvents();
  } catch (error) {
    elements.latestGrid.innerHTML = `<div class="error-card">${escapeHtml(error.message)}，请稍后刷新页面。</div>`;
    elements.archiveGrid.innerHTML = '<div class="empty-results">报告目录暂时无法读取。</div>';
    elements.updateBadge.textContent = "数据读取失败";
  }
}

init();
