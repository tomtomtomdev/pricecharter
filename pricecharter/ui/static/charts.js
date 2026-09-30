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

// Horizontal lift bars with the 95% range; 1× reference line = baseline rise rate.
function drawFactorBars(el, f) {
  const n = f.labels.length;
  const trace = {
    type: "bar", orientation: "h", y: f.labels, x: f.lift, marker: { color: css("--cat-1") },
    error_x: { type: "data", symmetric: false, array: f.hi.map((h, i) => h - f.lift[i]),
               arrayminus: f.lift.map((l, i) => l - f.lo[i]), color: css("--muted"), thickness: 1.5, width: 3 },
    customdata: f.labels.map((_, i) => [f.lo[i], f.hi[i], f.n[i]]),
    hovertemplate: "<b>%{x:.2f}×</b> (95%: %{customdata[0]:.2f}–%{customdata[1]:.2f}), n=%{customdata[2]}<extra>%{y}</extra>",
  };
  const layout = baseLayout({ hovermode: "closest", margin: { l: 8, r: 24, t: 8, b: 36 }, bargap: 0.35, showlegend: false,
    shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: css("--muted"), dash: "dot", width: 1 } }] });
  layout.xaxis = { ...layout.xaxis, title: { text: "lift vs baseline (×)", font: { size: 12 } }, showspikes: false, rangemode: "tozero" };
  layout.yaxis = { ...layout.yaxis, automargin: true, tickfont: { color: css("--text"), family: "ui-monospace, monospace", size: 12 } };
  Plotly.react(el, [trace], layout, plotConfig);
  el.style.height = `${80 + 26 * n}px`;
}

// One line per curve-shape cluster, excess vs index as %, categorical slots in fixed order.
function drawClusterLines(el, clusters) {
  const traces = clusters.map((c, i) => ({
    type: "scatter", mode: "lines", name: c.name, x: c.y.map((_, m) => m), y: c.y.map((v) => (Math.exp(v) - 1) * 100),
    line: { color: css(`--cat-${i + 1}`), width: 2 }, hovertemplate: "%{y:+.0f}%<extra>%{fullData.name}</extra>",
  }));
  const layout = baseLayout({ annotations: endLabels(traces, el, false).map((a) => ({ ...a, text: a.text.replace(/ \(\d+\)$/, "") })),
    margin: { l: 56, r: 170, t: 8, b: 40 } });
  layout.xaxis = { ...layout.xaxis, title: { text: "months into window", font: { size: 12 } } };
  layout.yaxis = { ...layout.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: css("--border") };
  Plotly.react(el, traces, layout, plotConfig);
}

const CHARTS = {
  factors: (el) => { const d = readJSON(el.dataset.src); return () => drawFactorBars(el, d); },
  clusters: (el) => { const d = readJSON(el.dataset.src); return () => drawClusterLines(el, d); },
  price: initPriceChart,
  index: (el) => { const data = readJSON(el.dataset.src); return () => drawSeriesChart(el, data, { unit: "%" }); },
};

document.addEventListener("DOMContentLoaded", () => {
  const draws = [...document.querySelectorAll("[data-chart]")].map((el) => CHARTS[el.dataset.chart](el));
  const redraw = () => draws.forEach((d) => d());
  redraw();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
});
