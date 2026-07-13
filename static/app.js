const bySelector = (selector, root = document) => root.querySelector(selector);

function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined && text !== null) item.textContent = String(text);
  return item;
}

function replaceContent(container, items) {
  container.replaceChildren(...items);
}

function emptyState(message) {
  return element("div", "empty-state", message);
}

function stockHref(code, fallback = "/dashboard") {
  const normalized = String(code || "").toUpperCase();
  return /^[A-Z0-9.-]{1,16}$/.test(normalized)
    ? `/stock/${encodeURIComponent(normalized)}`
    : fallback;
}

function card(tag, className, rows, href) {
  const item = element(tag, className);
  if (href) item.setAttribute("href", href);
  rows.forEach(([rowTag, rowClass, value]) => item.append(element(rowTag, rowClass, value)));
  return item;
}

async function loadDashboard() {
  const page = bySelector("[data-dashboard-endpoint]");
  if (!page) return;
  try {
    const response = await fetch(page.dataset.dashboardEndpoint, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("dashboard");
    renderDashboard(await response.json());
  } catch (error) {
    const banner = bySelector("[data-dashboard-error]");
    if (banner) banner.hidden = false;
  }
}

function renderDashboard(data) {
  const marketData = data.market || {};
  const marketRecommendation = marketData.recommendation || {};
  const hero = bySelector("[data-market-hero]");
  if (hero) {
    const label = element("p", `action-label action-${marketRecommendation.level || "insufficient"}`, marketRecommendation.action || "等待資料");
    const headline = element("h1", "market-headline", marketRecommendation.headline || "市場建議資料暫時不足");
    const reasons = element("ul", "hero-reasons");
    (marketRecommendation.supporting_reasons || []).slice(0, 3).forEach((reason) => reasons.append(element("li", "", reason)));
    if (!reasons.children.length) reasons.append(element("li", "", "等待完整市場資料更新"));
    const risk = element("p", "hero-risk");
    risk.append(element("strong", "", "最大風險："));
    risk.append(document.createTextNode((marketRecommendation.risk_reasons || ["資料品質不足"])[0]));
    const meta = element("p", "muted small", `資料日 ${marketData.as_of || "待更新"} · ${marketRecommendation.confidence || "可信度低"}`);
    replaceContent(hero, [label, headline, reasons, risk, meta]);
  }

  const market = bySelector("[data-market-summary]");
  if (market) {
    replaceContent(market, [
      card("article", "pulse-card", [["span", "", "市場行動"], ["strong", "", marketRecommendation.action || "等待資料"], ["small", "muted", marketRecommendation.headline || "市場建議資料不足"]]),
      card("article", "pulse-card", [["span", "", "優先方向"], ["strong", "", (data.sector_cards || [])[0]?.name || "等待資料"], ["small", "muted", "先看產業，再評估個股"]]),
      card("article", "pulse-card", [["span", "", "最大風險"], ["strong", "", (marketRecommendation.risk_reasons || ["資料品質不足"])[0]], ["small", "muted", `加權指數 ${Number(marketData.price || 0).toFixed(2)}`]]),
    ]);
  }
  const status = bySelector(".status-dot");
  if (status) status.textContent = marketData.as_of ? `資料日 ${marketData.as_of}` : "已更新";

  const watchlist = bySelector("[data-watchlist-strip]");
  if (watchlist) {
    const hint = data.watchlist_hint || { title: "", steps: [] };
    replaceContent(watchlist, (hint.steps || []).map((step, index) =>
      card("article", "watch-chip", [["span", "", `Step ${index + 1}`], ["strong", "", step]])
    ));
  }

  const focus = bySelector("[data-daily-focus]");
  if (focus) {
    const items = data.top_picks || [];
    replaceContent(focus, items.length ? items.slice(0, 2).map((item) =>
      card("a", "focus-card", [["span", "", item.recommendation?.action || "等待確認"], ["strong", "", item.name], ["small", "", item.headline], ["small", "", item.summary]], stockHref(item.code))
    ) : [emptyState("今日焦點等待產業快照更新。")]);
  }

  const heatmap = bySelector("[data-market-heatmap]");
  if (heatmap) {
    const cells = data.heatmap || [];
    replaceContent(heatmap, cells.length ? cells.map((item) =>
      card("a", `heatmap-cell ${["hot", "cold", "steady"].includes(item.tone) ? item.tone : "steady"}`, [["span", "", item.name], ["strong", "", `${item.probability}%`], ["small", "", `${item.count} 檔候選`]], item.code ? stockHref(item.code, "#industry-forecast") : "#industry-forecast")
    ) : [emptyState("熱力圖等待產業快照更新。")]);
  }

  const forecasts = bySelector("[data-sector-grid]");
  if (forecasts) {
    const cards = data.sector_cards || [];
    replaceContent(forecasts, cards.length ? cards.map((sector, index) => {
      const recommendation = sector.leader.recommendation || {};
      return card("a", "forecast-card", [
        ["span", "", `第 ${index + 1} 名 · ${sector.name}`],
        ["strong", "", recommendation.action || "等待確認"],
        ["small", "", `五日上漲機率 ${sector.leader.prob}% · ${sector.leader.trend}`],
        ["small", "", recommendation.headline || "等待完整資料"],
        ["small", "", `代表股票 ${sector.leader.name || "待更新"} · ${recommendation.confidence || "可信度低"}`],
      ], stockHref(sector.leader.code));
    }) : [emptyState("產業預測快照尚未準備好，請稍後再試。")]);
  }

  const picks = bySelector("[data-top-picks]");
  if (picks) {
    const items = data.top_picks || [];
    replaceContent(picks, items.length ? items.map((item) => {
      const recommendation = item.recommendation || {};
      return card("a", "pick-card", [
        ["span", "", `${item.name} · ${item.code}`],
        ["strong", "", recommendation.action || "等待確認"],
        ["p", "", item.headline],
        ["p", "", item.summary],
        ["small", "", `主要風險：${(recommendation.risk_reasons || ["資料不足"])[0]}`],
      ], stockHref(item.code));
    }) : [emptyState("目前沒有足夠的精選標的資料。")]);
  }
}

function formatNumber(value) {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("zh-TW") : "—";
}

function initReturnCalculator() {
  const panel = bySelector("[data-return-calculator]");
  if (!panel) return;
  const input = bySelector("[data-investment-amount]", panel);
  const price = Number(panel.dataset.price);
  const strategyReturn = Number(panel.dataset.strategyReturn);
  const buyholdReturn = Number(panel.dataset.buyholdReturn);
  const update = () => {
    const amount = Number(input.value);
    const shares = Math.floor(amount / price);
    const deployed = shares * price;
    const valid = Number.isFinite(amount) && amount > 0 && price > 0 && shares > 0;
    bySelector("[data-shares]", panel).textContent = valid ? shares.toLocaleString("zh-TW") : "—";
    bySelector("[data-deployed]", panel).textContent = valid ? formatNumber(deployed) : "—";
    bySelector("[data-strategy-profit]", panel).textContent = valid ? formatNumber((deployed * strategyReturn) / 100) : "—";
    bySelector("[data-buyhold-profit]", panel).textContent = valid ? formatNumber((deployed * buyholdReturn) / 100) : "—";
  };
  input.addEventListener("input", update);
  update();
}

function measureChartHeight(container) {
  return Math.max(320, Math.min(460, Math.round(container.clientWidth * 0.62)));
}

function setChartRange(days) {
  if (!window.stockChart) return;
  const { chart, length } = window.stockChart;
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, length - days), to: length + 5 });
}

function initStockChart() {
  const container = bySelector("#stock-chart");
  const source = bySelector("#stock-chart-data");
  if (!container || !source || !window.LightweightCharts) return;
  const raw = JSON.parse(source.textContent);
  const candles = JSON.parse(raw.candles);
  const height = measureChartHeight(container);
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height,
    layout: { background: { color: "transparent" }, textColor: "#74685d" },
    grid: { vertLines: { color: "#e7dacd" }, horzLines: { color: "#e7dacd" } },
    timeScale: { borderColor: "#dbcdbd" },
  });
  const candleSeries = chart.addCandlestickSeries({
    upColor: "#d94b63",
    downColor: "#1f9a72",
    borderVisible: false,
    wickUpColor: "#d94b63",
    wickDownColor: "#1f9a72",
  });
  candleSeries.setData(candles);
  chart.addLineSeries({ color: "#7fd7c4", lineWidth: 1, title: "MA20" }).setData(JSON.parse(raw.ma20));
  chart.addLineSeries({ color: "#c98542", lineWidth: 2, lineStyle: 2, title: "五日預測" }).setData(JSON.parse(raw.prediction));
  window.stockChart = { chart, length: candles.length };
  setChartRange(90);
  const resize = () => chart.resize(container.clientWidth, measureChartHeight(container));
  if (window.ResizeObserver) new ResizeObserver(resize).observe(container);
  window.addEventListener("resize", resize);
}

document.addEventListener("click", (event) => {
  const preset = event.target.closest("[data-amount-preset]");
  if (preset) {
    const input = bySelector("[data-investment-amount]", preset.closest("[data-return-calculator]"));
    if (input) {
      input.value = preset.dataset.amountPreset;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  const filter = event.target.closest("[data-news-filter]");
  if (filter) {
    const panel = filter.closest(".news-panel");
    const entries = panel.querySelectorAll("[data-news-direction]");
    if (!entries.length) return;
    const direction = filter.dataset.newsFilter;
    let visible = 0;
    panel.querySelectorAll("[data-news-filter]").forEach((item) => {
      const active = item === filter;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", active);
    });
    entries.forEach((item) => {
      item.hidden = direction !== "all" && item.dataset.newsDirection !== direction;
      if (!item.hidden) visible += 1;
    });
    const empty = bySelector("[data-news-filter-empty]", panel);
    if (empty) empty.hidden = visible > 0;
  }

  const range = event.target.closest("[data-chart-range]");
  if (!range) return;
  document.querySelectorAll("[data-chart-range]").forEach((item) => {
    item.classList.toggle("active", item === range);
    item.setAttribute("aria-pressed", item === range);
  });
  setChartRange(Number(range.dataset.chartRange));
});

loadDashboard();
initStockChart();
initReturnCalculator();
