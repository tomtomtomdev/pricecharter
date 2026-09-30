// Shared Plotly helpers. Colors come from CSS custom properties so light/dark stay in app.css.
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const CONDITION_LABEL = { loose: "Loose", cib: "CIB", new: "New" };

function baseLayout(extra = {}) {
  const grid = css("--grid"), muted = css("--muted");
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: css("--text"), family: css("--font"), size: 12 },
    margin: { l: 56, r: 64, t: 8, b: 32 },
    hovermode: "x unified",
    hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--border"), font: { color: css("--text") } },
    legend: { orientation: "h", y: 1.08, x: 0 },
    xaxis: { gridcolor: grid, linecolor: css("--border"), tickfont: { color: muted },
             showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: muted, spikedash: "solid" },
    yaxis: { gridcolor: grid, zeroline: false, tickfont: { color: muted } },
    ...extra,
  };
}

const plotConfig = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d"] };

// Direct label at each line's last point so identity never relies on color alone.
// Labels closer than MIN_GAP px are pushed apart (estimated from the plot height, linear or log y).
const MIN_GAP = 15;
function endLabels(traces, el, log) {
  const pts = traces.map((t) => ({ t, x: t.x[t.x.length - 1], y: t.y[t.y.length - 1] }));
  const f = (v) => (log ? Math.log10(Math.max(v, 1e-9)) : v);
  const all = traces.flatMap((t) => t.y).map(f);
  const lo = Math.min(...all), hi = Math.max(...all), h = Math.max(el.clientHeight - 90, 100);
  pts.forEach((p) => { p.px = ((f(p.y) - lo) / (hi - lo || 1)) * h; p.at = p.px; });
  pts.sort((a, b) => b.px - a.px);
  for (let i = 1; i < pts.length; i++) pts[i].at = Math.min(pts[i].at, pts[i - 1].at - MIN_GAP);
  return pts.map((p) => ({
    x: p.x, y: log ? Math.log10(p.y) : p.y, yshift: p.at - p.px,
    text: p.t.name.replace(/^Console index.*/, "Index"), showarrow: false,
    xanchor: "left", xshift: 6, font: { color: css("--text-2"), size: 12 },
  }));
}

function conditionTraces(data, unit) {
  const fmt = unit === "%" ? "%{y:+.1f}%" : "$%{y:,.2f}";
  return data.map((s) => ({
    type: "scatter", mode: "lines", name: CONDITION_LABEL[s.cond] || s.cond, x: s.x, y: s.y,
    line: { color: css(`--series-${s.cond}`), width: 2 },
    hovertemplate: `${fmt}<extra>%{fullData.name}</extra>`,
  }));
}

function drawSeriesChart(el, data, { unit = "$", log = false, extraTraces = [] } = {}) {
  const traces = [...conditionTraces(data, unit), ...extraTraces];
  const layout = baseLayout({ annotations: endLabels(traces, el, log && unit !== "%") });
  const xs = traces.flatMap((t) => [t.x[0], t.x[t.x.length - 1]]).sort();
  layout.xaxis = { ...layout.xaxis, range: [xs[0], xs[xs.length - 1]] };
  layout.yaxis = unit === "%"
    ? { ...layout.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: css("--border") }
    : { ...layout.yaxis, type: log ? "log" : "linear", tickprefix: "$", tickformat: log ? "" : ",.0f" };
  Plotly.react(el, traces, layout, plotConfig);
}

const readJSON = (id) => { const el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; };

// Game page: prices, log toggle, optional console-index overlay.
function initPriceChart(el) {
  const data = readJSON(el.dataset.src);
  const index = readJSON("index-data") || [];
  const log = document.getElementById("log-scale");
  const idxCond = document.getElementById("index-cond");
  const indexTraces = () => index.filter((s) => idxCond && s.cond === idxCond.value).map((s) => ({
    type: "scatter", mode: "lines", name: `Console index (${CONDITION_LABEL[s.cond]})`, x: s.x, y: s.y,
    line: { color: css("--series-index"), width: 2, dash: "dash" },
    hovertemplate: "$%{y:,.2f}<extra>index</extra>",
  }));
  const draw = () => drawSeriesChart(el, data, { log: log && log.checked, extraTraces: indexTraces() });
  for (const c of [log, idxCond]) if (c) c.addEventListener("change", draw);
  return draw;
}

const CHARTS = {
  price: initPriceChart,
  index: (el) => { const data = readJSON(el.dataset.src); return () => drawSeriesChart(el, data, { unit: "%" }); },
};

document.addEventListener("DOMContentLoaded", () => {
  const draws = [...document.querySelectorAll("[data-chart]")].map((el) => CHARTS[el.dataset.chart](el));
  const redraw = () => draws.forEach((d) => d());
  redraw();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
});
