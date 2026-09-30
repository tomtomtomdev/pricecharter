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
function endLabels(traces) {
  return traces.map((t) => ({
    x: t.x[t.x.length - 1], y: t.y[t.y.length - 1], text: t.name.replace(/^Console index.*/, "Index"), showarrow: false,
    xanchor: "left", xshift: 6, font: { color: css("--text-2"), size: 12 },
  }));
}

function priceTraces(data) {
  return data.map((s) => ({
    type: "scatter", mode: "lines", name: CONDITION_LABEL[s.cond] || s.cond, x: s.x, y: s.y,
    line: { color: css(`--series-${s.cond}`), width: 2 },
    hovertemplate: "$%{y:,.2f}<extra>%{fullData.name}</extra>",
  }));
}

function drawPriceChart(el, data, { log = false, extraTraces = [] } = {}) {
  const traces = [...priceTraces(data), ...extraTraces];
  const layout = baseLayout({ annotations: endLabels(traces.filter((t) => !t.noLabel)) });
  const xs = traces.flatMap((t) => [t.x[0], t.x[t.x.length - 1]]).sort();
  layout.xaxis = { ...layout.xaxis, range: [xs[0], xs[xs.length - 1]] };
  layout.yaxis = { ...layout.yaxis, type: log ? "log" : "linear", tickprefix: "$", tickformat: log ? "" : ",.0f" };
  Plotly.react(el, traces, layout, plotConfig);
}

document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("price-chart");
  if (!el) return;
  const data = JSON.parse(document.getElementById("price-data").textContent);
  const log = document.getElementById("log-scale");
  const idxEl = document.getElementById("index-data");
  const index = idxEl ? JSON.parse(idxEl.textContent) : [];
  const idxCond = document.getElementById("index-cond");
  const indexTraces = () => index.filter((s) => idxCond && s.cond === idxCond.value).map((s) => ({
    type: "scatter", mode: "lines", name: `Console index (${CONDITION_LABEL[s.cond]})`, x: s.x, y: s.y,
    line: { color: css("--series-index"), width: 2, dash: "dash" },
    hovertemplate: "$%{y:,.2f}<extra>index</extra>",
  }));
  const draw = () => drawPriceChart(el, data, { log: log && log.checked, extraTraces: indexTraces() });
  draw();
  for (const c of [log, idxCond]) if (c) c.addEventListener("change", draw);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
});
