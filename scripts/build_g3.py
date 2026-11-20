"""Build the self-contained local HTML report; only pinned runtime CDNs are external."""
from html import escape
import json
from pathlib import Path

from seos.report_analysis import analyze

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "seos/__init__.py", "seos/validation.py", "seos/main.py", "seos/g2.py",
    "seos/report_analysis.py", "seos/engineering.py", "seos/engineering_optimizer.py",
    "seos/modules/__init__.py", "seos/modules/earthwork_calculator.py",
    "seos/modules/optimizer.py", "seos/modules/soil_classifier.py",
    "seos/modules/predictor.py", "seos/modules/resilience_evaluator.py",
)
BRIDGE = """
import json
from tempfile import TemporaryDirectory
from pathlib import Path
import platform
import sys
from pyodide.ffi import create_proxy
from js import seosAttach

package_dir = TemporaryDirectory(prefix="seos-")
root = Path(package_dir.name)
for name, source in sources.items():
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source, encoding="utf8")
sys.path.insert(0, str(root))

from seos.report_analysis import analyze_json as run_browser

def compute(data):
    result = run_browser(data)
    return json.dumps(result, ensure_ascii=True, allow_nan=False)

callback = create_proxy(compute)
seosAttach(callback)
"""


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf8"))


def json_data(data):
    # Escaping '<' prevents embedded text from ending its parent script tag.
    return json.dumps(data, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")


def cell(value):
    if value is None:
        return "—"
    return escape(format(value, ".8g") if isinstance(value, (int, float)) else str(value))


def table(caption, headings, rows):
    return (f"<table><caption>{escape(caption)}</caption><thead><tr>"
            + "".join(f'<th scope="col">{cell(title)}</th>' for title in headings)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{cell(value)}</td>" for value in row) + "</tr>" for row in rows)
            + "</tbody></table>")


def static_html(result):
    modules = result["modules"]
    m3, m4 = modules["M3"], modules["M4"]
    alternatives = [a for a in modules["M5"]["alternatives"] if a["status"] == "EVALUATED"]
    labels = ["方案", "无扰动", *[e["id"] for e in alternatives[0]["events"]]]
    metrics = ["最差服务率", "评价窗服务率", "原计划送达率", "完整服务占比", "成本保持率"]
    tables = [
        table("调运矩阵 · m³天然方", ["挖方 / 填方", "1", "2", "3"],
              [[i+1, *row] for i, row in enumerate(m3["matrix"])]),
        table("方案与扰动成本 · 合成元", labels,
              [[a["id"], a["base_synthetic_cny"], *[e["full_service_cost_synthetic_cny"] for e in a["events"]]]
               for a in alternatives]),
        table("费率敏感性 · 调整倍率与合成运费", ["倍率", "费率", "合成运费", "状态"],
              [[p["ratio"], p["rate"], p["synthetic_cny"], p["status"]] for p in result["sensitivity"]["points"]]),
        table("年度情景 · kg 干土", ["年", "供给", "需求", "缺口"],
              [[p["year"], p["supply_kg"], p["demand_kg"], p["shortfall_kg"]] for p in m4["series"]]),
        table("韧性 · 五项归一化指标", ["方案", *metrics],
              [[a["id"], *a["metrics"].values()] for a in alternatives]),
    ]
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>SEOS 离线基线快照</title><style>""" + stylesheet() + """</style>
<header class="masthead"><div class="viewport"><div><h1>SEOS 离线教学基线</h1>
<p>合成数据 · 固定参数</p></div><div class="header-actions"><a href="index.html">返回交互报告（需联网）</a></div></div></header>
<main class="static-shell"><p class="note">结果由同一 Python 教学模型生成。运费以合成元计，以下结果随快照固定。</p>
<section aria-label="五类分析数据">""" + "".join(tables) + (
        '</section><details class="details-pane"><summary>五模块计算明细</summary><pre>'
        + escape(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        + "</pre></details></main></html>\n")


def stylesheet():
    return (ROOT / "scripts/g3_design.css").read_text(encoding="utf8")


def build():
    sample = load("data/g2_teaching.json")
    reference_fields = ("natural_water_pct", "optimum_water_pct", "lab_max_dry_density_kg_m3",
                        "reported_compaction_ratio")
    sample.update(sensitivity_route=[2, 2], loose_volume_ratio=[None, None, None],
                  soil_reference=[dict.fromkeys(reference_fields) for _ in range(3)])
    real = {"schema_version": "g2.1", "dataset": {"kind": "real", "id": "", "source": ""}}
    result = analyze(sample)
    if result["status"] != "CALCULATED":
        raise RuntimeError(f"baseline report calculation failed: {result}")
    sources = {name: (ROOT / name).read_text(encoding="utf8") for name in MODULES}
    # Encode content as a JSON string literal that is also a valid Python literal.
    python = "sources = __import__('json').loads(" + json_data(json_data(sources)) + ")\n" + BRIDGE
    replacements = {"__DATA__": json_data({"synthetic": sample, "real": real}),
                    "__JS__": (ROOT / "scripts/g3_report.js").read_text(encoding="utf8"),
                    "__PYTHON__": python, "__CSS__": stylesheet()}
    html = (ROOT / "scripts/g3_template.html").read_text(encoding="utf8")
    for key, value in replacements.items():
        html = html.replace(key, value)
    (ROOT / "report/index.html").write_text(html, encoding="utf8")
    (ROOT / "report/static.html").write_text(static_html(result), encoding="utf8")


if __name__ == "__main__":
    build()
