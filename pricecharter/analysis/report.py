"""Static HTML report (Jinja2 + Plotly.js from cdnjs)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape

from .run import AnalysisResult

TOP_FACTORS = 15
TOP_PATTERNS = 20

_env = Environment(loader=PackageLoader("pricecharter.analysis", "templates"), autoescape=select_autoescape())


def _index_traces(idx: pd.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for cond, grp in idx.groupby("condition"):
        traces = []
        for console, g in grp.groupby("console"):
            g = g.sort_values("month")
            traces.append({
                "name": console,
                "x": g["month"].dt.strftime("%Y-%m-%d").tolist(),
                "y": ((np.exp(g["level"]) - 1) * 100).round(1).tolist(),
            })
        out[cond] = traces
    return out


def _factor_bars(lift: pd.DataFrame) -> dict[str, dict]:
    out = {}
    for cond, grp in lift.groupby("condition"):
        top = grp[grp["lift_lo"] > 1].head(TOP_FACTORS).iloc[::-1]
        out[cond] = {
            "labels": (top["factor"] + "=" + top["value"]).tolist(),
            "lift": top["lift"].round(3).tolist(),
            "lo": top["lift_lo"].round(3).tolist(),
            "hi": top["lift_hi"].round(3).tolist(),
            "n": top["n"].tolist(),
        }
    return out


def _names(ids: str, games: pd.DataFrame) -> list[str]:
    out = []
    for gid in filter(None, (ids or "").split(",")):
        gid = int(gid)
        if gid in games.index:
            g = games.loc[gid]
            out.append(f"{g['name']} ({g['console']})")
    return out


def _json_for_script(data) -> str:
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def context(res: AnalysisResult) -> dict:
    patterns = {}
    for cond, grp in res.patterns.groupby("condition"):
        patterns[cond] = [
            {**r, "examples": _names(r["example_ids"], res.games)} for r in grp.head(TOP_PATTERNS).to_dict("records")
        ]
    factors = {
        cond: grp[grp["lift_lo"] > 1].head(TOP_FACTORS).to_dict("records")
        for cond, grp in res.factor_lift.groupby("condition")
    }
    return {
        "p": res.params,
        "conditions": sorted(res.series_metrics["condition"].unique()),
        "consoles": json.loads(res.params["consoles"]),
        "factors": factors,
        "patterns": patterns,
        "chart_json": _json_for_script({"index": _index_traces(res.console_index),
                                        "factors": _factor_bars(res.factor_lift)}),
        "extra": getattr(res, "extra", {}),
    }


def render_report(res: AnalysisResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_env.get_template("report.html.j2").render(**context(res)))
    return path
