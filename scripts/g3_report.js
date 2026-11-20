"use strict";
const byId = id => document.getElementById(id);
const fixtures = JSON.parse(byId("seos-data").textContent);
const editor = byId("parameters");
const mode = byId("mode");
const drafts = {};
let activeMode, formData, timer, engine, lastValid, version = 0, charts = [], chartReady = false;
const telemetry = {state: "LOADING", cycle: 0, timings: [], current: null};
window.seosTelemetry = telemetry;

function element(tag, content, parent) {
  const node = document.createElement(tag);
  if (content !== null) node.textContent = content;
  if (parent) parent.append(node);
  return node;
}
function status(code, message, bad = false) {
  telemetry.state = code;
  const node = byId("status");
  node.dataset.state = code;
  node.textContent = message;
  node.classList.toggle("error", bad);
}
function clearCurrent() {
  // Also remove any instance registered before a constructor threw.
  for (const canvas of byId("current").querySelectorAll("canvas")) {
    const chart = window.Chart?.getChart(canvas);
    if (chart) {
      try { chart.destroy(); } catch (error) { console.error(error); }
    }
  }
  charts = [];
  byId("current").replaceChildren();
  byId("current-result").hidden = true;
  byId("result").textContent = "";
  telemetry.current = null;
}
function errorStatus(code, message) {
  clearCurrent();
  byId("current").style.minBlockSize="";
  status(code, message, true);
}
window.seosDependency = (name, ready) => {
  if (name === "chart") chartReady = ready;
  byId(name === "python" ? "engine-state" : "chart-state").textContent =
    (name === "python" ? "Python" : "Chart.js") + (ready ? " 就绪" : " 加载失败");
  if (!ready) errorStatus("DEPENDENCY_ERROR", "运行依赖加载失败。请检查网络，或打开离线基线快照。");
};

function canonical(text) {
  const match = text.match(/^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/);
  if (!match) return null;
  let digits = (match[2] + (match[3] || "")).replace(/^0+/, "");
  if (!digits) return "0";
  let power = Number(match[4] || 0) - (match[3] || "").length;
  if (!Number.isSafeInteger(power)) return null;
  while (digits.endsWith("0")) { digits = digits.slice(0, -1); power++; }
  return match[1] + digits + "e" + power;
}
function numeric(text) {
  if (!text.trim()) return null;
  const n = Number(text);
  const exact = canonical(text);
  return exact && Number.isFinite(n) && exact === canonical(String(n)) ? n : text;
}
function field(parent, path, title, type = "number", options = []) {
  const owner = path.slice(0, -1).reduce((obj, key) => obj?.[key], formData);
  if (!owner || typeof owner !== "object") return;
  const key = path.at(-1);
  const label = element("label", null, parent);
  label.className = type === "bool" ? "field check" : "field";
  if (type === "text" || type === "choice") label.classList.add("wide");
  element("span", title, label);
  const selectable = type === "choice" || type === "index";
  const control = element(selectable ? "select" : "input", null, label);
  control.dataset.path = path.join(".");
  if (selectable) {
    for (const [value, caption] of options) {
      const option = element("option", caption, control);
      option.value = value;
    }
  } else {
    control.type = type === "bool" ? "checkbox" : "text";
    if (type === "number") control.inputMode = "decimal";
  }
  if (type === "bool") control.checked = owner[key] === true;
  else control.value = owner[key] ?? "";
  control.addEventListener("input", () => {
    owner[key] = type === "bool" ? control.checked : (type === "number" || type === "index") ? numeric(control.value) : control.value;
    editor.value = JSON.stringify(formData, null, 2);
    schedule();
  });
}
function group(parent, title, open = false) {
  const details = element("details", null, parent);
  details.open = open;
  element("summary", title, details);
  const grid = element("div", null, details);
  grid.className = "fields";
  return grid;
}
const routeName = (i, j) => (i + 1) + " → " + (j + 1);
function indexed(grid, path, name, count, type) {
  for (let i = 0; i < count; ++i) field(grid, [...path, i], name + " " + (i + 1), type);
}
function matrix(grid, path, type = "number") {
  for (let i = 0; i < 3; ++i) for (let j = 0; j < 3; ++j) field(grid, [...path, i, j], routeName(i, j), type);
}
function heading(grid, name) { element("h3", name, grid).className = "wide subgroup"; }

function buildFields() {
  const target = byId("fields");
  const opened = new Set([...target.querySelectorAll("details[open] > summary")].map(n => n.textContent));
  const fresh = !target.childElementCount;
  target.replaceChildren();
  if (!formData || formData.dataset?.kind !== "synthetic") return;

  const soil = group(target, "土料与填区适用性");
  (Array.isArray(formData.samples) ? formData.samples.slice(0, 3) : []).forEach((_, i) => {
    heading(soil, "挖方 " + (i + 1));
    const fields = {fine_mass_pct:"细粒 %",oversize_mass_pct:"巨粒 %",organic_mass_pct:"有机质 %",
                    liquid_limit_pct:"液限 %",plastic_limit_pct:"塑限 %"};
    for (const [key, name] of Object.entries(fields)) field(soil, ["samples", i, key], name);
    field(soil, ["samples", i, "liquid_limit_method"], "液限方法", "choice",
          [["disk","碟式仪"],["cone_76g_30deg_17mm","76 g / 30° / 17 mm 液限仪"]]);
  });
  const accepted = formData.material_policy?.accepted_classes;
  if (Array.isArray(accepted)) accepted.slice(0, 3).forEach((classes, j) => {
    if (!Array.isArray(classes)) return;
    heading(soil, "填方 " + (j + 1) + " 允许类码");
    for (const code of ["CL","CH","ML","MH"]) {
      const label = element("label", code, soil);
      label.className = "field check";
      const cb = element("input", null, label);
      cb.type = "checkbox";
      cb.checked = classes.includes(code);
      cb.addEventListener("input", () => {
        if (cb.checked && !classes.includes(code)) classes.push(code);
        if (!cb.checked && classes.includes(code)) classes.splice(classes.indexOf(code), 1);
        editor.value = JSON.stringify(formData, null, 2);
        schedule();
      });
    }
  });

  const references = group(target, "含水率与击实参考");
  element("p","选填。含水率仅比较差值；最大干密度和压实系数作参考记录。运输计算使用方量区的目标压实干密度。",references).className = "wide note";
  const labFields = {natural_water_pct:"天然含水 %",optimum_water_pct:"最优含水 %",
                     lab_max_dry_density_kg_m3:"最大干密度 kg/m³",reported_compaction_ratio:"压实系数"};
  for (let i=0;i<3;i++) {
    heading(references,"挖方 "+(i+1));
    for (const [key,title] of Object.entries(labFields)) field(references,["soil_reference",i,key],title);
  }

  const quantities = group(target, "方量与干密度", fresh && !matchMedia("(max-width:820px)").matches);
  for (const [key, title] of Object.entries({bank_volumes_m3:"天然方供应 · m³",compacted_volumes_m3:"压实方需求 · m³",
      bank_dry_density_kg_m3:"天然干密度 · kg/m³",compacted_dry_density_kg_m3:"目标压实干密度 · kg/m³"})) {
    heading(quantities,title); indexed(quantities,["transport",key],"区",3);
  }
  heading(quantities, "松散干密度 · kg/m³");
  indexed(quantities,["loose_dry_density_kg_m3"],"挖方",3);
  heading(quantities, "可松性比 · 松方 / 天然方（选填）");
  indexed(quantities,["loose_volume_ratio"],"挖方",3);
  element("p","填写时按天然干密度 ÷ 可松性比推导松散干密度。",quantities).className = "wide note";

  const routes = group(target,"路线、运距与费率");
  heading(routes,"费率 · 元/(m³天然方·km)"); matrix(routes,["transport","haul_rate_cny_per_m3_km"]);
  heading(routes,"合成运距 · km"); matrix(routes,["transport","distance_km"]);
  heading(routes,"道路开通"); matrix(routes,["transport","allowed"],"bool");
  heading(routes,"敏感性扫描路线");
  const indices = [["0","区 1"],["1","区 2"],["2","区 3"]];
  // Choice values are converted to integers by the generic field handler.
  field(routes,["sensitivity_route",0],"挖方","index",indices);
  field(routes,["sensitivity_route",1],"填方","index",indices);

  const forecast = group(target,"供需情景与折现");
  for (const [key,title] of Object.entries({years:"年数 · 3–10",supply_growth_pct:"供应增长 %",demand_growth_pct:"需求增长 %",
      discount_pct:"折现率 %",annual_payment_synthetic_cny:"年末付款 · 合成元"})) field(forecast,["prediction",key],title);

  const risk = group(target,"扰动情景、方案与权重");
  field(risk,["risk","horizon_days"],"评估窗 · 天");
  const events = formData.risk?.events;
  if (Array.isArray(events)) events.slice(0,30).forEach((event,i) => {
    heading(risk,event?.id || "情景 " + (i + 1));
    field(risk,["risk","events",i,"duration_days"],"持续 · 天");
    indexed(risk,["risk","events",i,"supply_available"],"可用率 0–1 · 区",3);
    heading(risk,"扰动期间开通");
    matrix(risk,["risk","events",i,"routes_open"],"bool");
  });
  const variants = formData.risk?.alternatives;
  if (Array.isArray(variants)) variants.slice(0,8).forEach((variant,i) => {
    heading(risk,variant?.id || "方案 " + (i + 1));
    matrix(risk,["risk","alternatives",i,"allowed"],"bool");
  });
  heading(risk,"指标权重 · 合计 1");
  for (const [key,title] of Object.entries(metricLabels)) field(risk,["risk","weights",key],title);
  for (const details of target.querySelectorAll("details")) {
    if (opened.has(details.querySelector("summary").textContent)) details.open = true;
  }
}
const metricLabels = {worst_service:"最差服务率",horizon_service:"评价窗服务率",original_plan_service:"原计划送达率",
                      full_service_share:"完整服务占比",cost_retention:"成本保持率"};
const exampleNames = {
  baseline:"基线方案",enable_backup_1_to_2:"启用备用路线 1 → 2",rain:"雨季",machine:"设备故障",route:"道路中断"
};
const labelOf = id => Object.hasOwn(exampleNames,id) ? exampleNames[id] : id;
const palette = getComputedStyle(document.documentElement);
const token = name => palette.getPropertyValue(name).trim();
const colors = ["--supply","--comparison","--demand","--purple","--muted"].map(token);
const gridColor = token("--grid");
const fmt = new Intl.NumberFormat("zh-CN",{maximumSignificantDigits:7});
const format = value => fmt.format(value);
function heatmap(parent, plan) {
  const table = element("table",null,parent);
  table.className = "heat";
  table.setAttribute("aria-label","天然方调运矩阵，单位立方米");
  const head = element("tr",null,element("thead",null,table));
  element("th","挖方 / 填方",head);
  for (let j=0;j<3;j++) element("th","填方 "+(j+1),head).scope = "col";
  const body = element("tbody",null,table);
  const peak = Math.max(...plan.matrix.flat(),0);
  plan.matrix.forEach((row,i) => {
    const tr = element("tr",null,body);
    element("th","挖方 "+(i+1),tr).scope = "row";
    row.forEach((value,j) => {
      const cell = element("td",plan.allowed[i][j] ? format(value) : "禁运",tr);
      cell.dataset.volume = value;
      const description = "挖方 "+(i+1)+" → 填方 "+(j+1)+"，"+(plan.allowed[i][j] ? format(value)+" m³天然方" : "禁运");
      cell.tabIndex = 0;
      cell.title = description;
      cell.setAttribute("aria-label",description);
      if (plan.allowed[i][j]) {
        cell.style.backgroundColor = "rgba(22,160,133,"+(0.06+(peak ? 0.58*value/peak : 0))+")";
      } else cell.dataset.blocked = "";
    });
  });
  const key = element("div",null,parent); key.className="heat-key";
  element("span","0",key);
  element("span",null,key).className="heat-scale";
  element("span",format(peak)+" m³天然方 · 斜纹表示禁运",key);
}
function panel(grid, title, description) {
  const section = element("section",null,grid);
  section.className = "viz";
  element("h3",title,section);
  element("p",description,section);
  return section;
}
function chart(panelNode,id,label,config) {
  const box = element("div",null,panelNode); box.className = "plot";
  const canvas = element("canvas",null,box); canvas.id=id;
  canvas.setAttribute("role","img"); canvas.setAttribute("aria-label",label);
  const custom = config.options || {};
  const hooks = custom.plugins || {};
  config.options = {animation:false,responsive:true,maintainAspectRatio:false,devicePixelRatio:Math.min(window.devicePixelRatio,2),
    color:token("--muted"),font:{family:token("--font"),size:12},...custom,
    plugins:{...hooks,legend:{position:"top",align:"start",labels:{usePointStyle:true,boxWidth:7,boxHeight:7,padding:11},...hooks.legend}}};
  charts.push(new Chart(canvas,config));
}
function line(label,values,color) {
  return {label,data:values,borderColor:color,backgroundColor:color,pointRadius:2.5,borderWidth:2,tension:0};
}
function verify(result, input) {
  const finite = value => typeof value === "number" ? Number.isFinite(value) :
    value && typeof value === "object" ? Object.values(value).every(finite) : true;
  if (!finite(result) || result.dataset_kind !== "synthetic" || result.currency_result !== null ||
      input.dataset.kind !== "synthetic") throw Error("教学结果口径或数值范围异常");
  const plan = result.modules.M3, t = input.transport;
  if (!plan.feasibility_verified || plan.matrix.length !== 3 || !plan.matrix.every(row =>
    row.length === 3 && row.every(v => typeof v === "number" && v >= 0))) throw Error("非法调运矩阵");
  const close = (x,y) => Number.isFinite(x) && Math.abs(x-y) <= 1e-12 + 1e-12*Math.abs(y);
  let cost = 0;
  for (let i=0;i<3;i++) {
    if (!close(plan.matrix[i].reduce((a,b)=>a+b,0),t.bank_volumes_m3[i])) throw Error("挖方供应校核失败");
    if (!close(plan.matrix.reduce((a,row,k)=>a+row[i]*t.bank_dry_density_kg_m3[k],0),
               t.compacted_volumes_m3[i]*t.compacted_dry_density_kg_m3[i])) throw Error("填方干质量校核失败");
    for (let j=0;j<3;j++) {
      if (!plan.allowed[i][j] && plan.matrix[i][j] !== 0) throw Error("禁运路线出现运量");
      cost += plan.matrix[i][j]*t.distance_km[i][j]*t.haul_rate_cny_per_m3_km[i][j];
    }
  }
  if (!close(cost,plan.synthetic_cost_cny)) throw Error("天然方计费校核失败");
}

function axes(yTitle,xTitle) {
  return {
    x:{title:{display:!!xTitle,text:xTitle},grid:{display:false},ticks:{maxRotation:0}},
    y:{title:{display:true,text:yTitle},grid:{color:gridColor},ticks:{maxTicksLimit:5}}
  };
}
function kpi(panel,label,value,detail) {
  const block = element("div",null,panel); block.className = "kpi";
  element("dt",label,block);
  const reading = element("dd",value,block);
  element("small",detail,reading);
}
const barLabels = {
  id:"seosBarLabels",
  afterDatasetsDraw(chart) {
    if (chart.width < 360 || chart.data.labels.length > 5 || chart.data.datasets.length > 2) return;
    const context = chart.ctx;
    context.save();
    context.font = "600 11px "+token("--font");
    context.fillStyle = token("--ink"); context.textAlign="center"; context.textBaseline="bottom";
    chart.data.datasets.forEach((dataset,i)=>chart.getDatasetMeta(i).data.forEach((bar,j)=>{
      if (chart.isDatasetVisible(i) && dataset.data[j] !== null) context.fillText(format(dataset.data[j]),bar.x,bar.y-3);
    }));
    context.restore();
  }
};
function show(result) {
  const {M1,M2,M3,M4,M5}=result.modules;
  const output = byId("current");
  output.classList.add("pending");
  try {
    const summary = element("section",null,output);
    summary.className = "summary";
    const metrics = element("dl",null,summary); metrics.className="kpis";
    const demandMass = M2.states.compacted.reduce((sum,row)=>sum+row.dry_mass_kg,0);
    kpi(metrics,"最优运输费",format(M3.synthetic_cost_cny),"合成元 · 天然方计费");
    kpi(metrics,"已匹配需求",format(demandMass),"kg 干土");
    kpi(metrics,"约束状态","已校核","供需守恒和禁运路线");
    kpi(metrics,"首次年度缺口",M4.first_shortfall_year === null ? "未出现" : "第 "+M4.first_shortfall_year+" 年","教学情景");
    const worst = M5.alternatives[0].metrics.worst_service;
    kpi(metrics,"最差服务率",format(100*worst)+"%","基线方案 · 合成扰动");
    element("p","土类 "+M1.samples.map(x=>x.soil_class).join(" / ")+" · 松方 "+
      M2.states.bank.map(x=>format(x.target_volume_m3)).join(" / ")+" m³",summary);
    element("p","现金流现值 "+format(M4.present_value_synthetic_cny)+" 合成元",summary);
    for (const test of result.soil_reference) {
      const values = [];
      if (test.water_difference_pp !== null) values.push("含水偏差 "+format(test.water_difference_pp)+" 个百分点");
      if (test.lab_max_dry_density_kg_m3 !== null) values.push("最大干密度 "+format(test.lab_max_dry_density_kg_m3)+" kg/m³");
      if (test.reported_compaction_ratio !== null) values.push("录入压实系数 "+format(test.reported_compaction_ratio));
      if (values.length) element("p","挖方 "+test.source_zone+" 试验参考 · "+values.join(" · "),summary);
    }
    const grid = element("div",null,output); grid.className="viz-grid";
    heatmap(panel(grid,"调运矩阵","行是挖方区，列是填方区 · m³天然方"),M3);
    const scenarios = M5.alternatives.filter(a=>a.status==="EVALUATED");
    const withheld = M5.alternatives.filter(a=>a.status!=="EVALUATED");
    if (withheld.length) element("p","未进入对比："+withheld.map(a=>labelOf(a.id)+"（"+a.status+"）").join("、"),summary);
    const baseline = scenarios[0];
    const events = baseline.events;
    chart(panel(grid,"成本对比","合成元 · 扰动时无法完全服务则留空"),"cost","基线及扰动成本柱状图",{
      type:"bar", data:{labels:["无扰动",...events.map(e=>labelOf(e.id))],datasets:scenarios.map((a,i)=>({
        label:labelOf(a.id),data:[a.base_synthetic_cny,...a.events.map(e=>e.full_service_cost_synthetic_cny)],backgroundColor:colors[i%colors.length]
      }))},plugins:[barLabels],options:{layout:{padding:{top:10}},scales:{
        ...axes("合成元"),y:{...axes("合成元").y,beginAtZero:true,grace:"14%"}
      },plugins:{tooltip:{callbacks:{label:item=>{
        const base = item.chart.data.datasets[0].data[item.dataIndex];
        const diff = item.raw-base;
        const suffix = base !== null && item.datasetIndex > 0 ? "（较基线 "+(diff >= 0 ? "+" : "")+format(diff)+"）" : "";
        return item.dataset.label+"："+format(item.raw)+" 合成元"+suffix;
      }}}}}
    });
    const s = result.sensitivity;
    const rejectedPoints = s.points.filter(p=>p.status!=="OPTIMAL");
    if (rejectedPoints.length) {
      element("p","敏感性部分取值超出模型范围："+rejectedPoints.map(p=>p.ratio+"× "+p.status).join("、"),summary);
    }
    chart(panel(grid,"费率敏感性","路线 "+routeName(...s.route)+" · 横轴为该路线费率倍数"+
      (s.route_allowed ? "" : " · 当前禁运")),"sensitivity","费率敏感性折线图",{
      type:"line",data:{labels:s.points.map(p=>p.ratio+"×"),datasets:[{
        ...line("合成运费",s.points.map(p=>p.synthetic_cny),colors[0]),
        pointRadius:s.points.map(p=>p.ratio===1?6:3),
        pointBackgroundColor:s.points.map(p=>p.ratio===1?colors[2]:colors[0])
      }]},options:{scales:axes("合成元","费率倍率"),plugins:{legend:{display:false},tooltip:{callbacks:{
        title:items=>"费率 "+format(s.points[items[0].dataIndex].rate)+" 元/(m³天然方·km)"
      }}}}
    });
    chart(panel(grid,"供需情景推演","教学情景 · 当年需求超过供给即触发缺口预警"),"forecast","供需及年度缺口时序图",{
      type:"line",data:{labels:M4.series.map(p=>"第 "+p.year+" 年"),datasets:[
        line("供给",M4.series.map(p=>p.supply_kg),colors[0]),line("需求",M4.series.map(p=>p.demand_kg),colors[2]),
        {...line("年度缺口",M4.series.map(p=>p.shortfall_kg),colors[1]),
          pointRadius:M4.series.map(p=>p.year===M4.first_shortfall_year?6:2)},
        {...line("累计净缺口",M4.series.map(p=>p.cumulative_net_deficit_kg),colors[3]),borderDash:[5,4]}
      ]},options:{scales:axes("干土质量 · kg")}
    });
    chart(panel(grid,"方案韧性","五项指标 0–1 · 比较相同合成扰动"),"resilience","五指标方案韧性雷达图",{
      type:"radar",data:{labels:Object.values(metricLabels),datasets:scenarios.map((a,i)=>({
        ...line(labelOf(a.id),Object.keys(metricLabels).map(key=>a.metrics[key]),colors[i%colors.length]),fill:false
      }))},options:{scales:{r:{min:0,max:1,grid:{color:gridColor},pointLabels:{font:{size:12}},ticks:{stepSize:.25}}}}
    });
  } finally {
    output.classList.remove("pending");
  }
}

const statusText = {MISSING_DATA:"缺少必要参数",UNSUPPORTED_MODEL:"超出当前教学模型范围",
  REVIEW_REQUIRED:"土类限值需要人工判读",UNBALANCED:"供需干质量不平衡",INFEASIBLE:"现有材料与道路约束下无可行解",
  INVALID_INPUT:"输入无效",SOURCE_REVIEW_REQUIRED:"真实工程资料待审，未执行工程计算",NUMERIC_ERROR:"数值校核失败"};
function markDirty() {
  if (telemetry.state !== "INPUT_CHANGED") {
    const area = byId("current");
    if (telemetry.current) area.style.minBlockSize = area.offsetHeight+"px";
    clearCurrent();
  }
  status("INPUT_CHANGED","输入已更新，正在等待重算…");
}
function schedule(immediate = false) {
  const token = ++version;
  const start = performance.now();
  window.clearTimeout(timer);
  markDirty();
  if (engine) timer = window.setTimeout(() => recalculate(token,start),immediate ? 0 : 140);
}
function recalculate(token,start) {
  if (token !== version) return;
  if (!chartReady || typeof Chart !== "function") {
    errorStatus("DEPENDENCY_ERROR","Chart.js 未就绪。请检查网络后重新载入，或打开离线基线快照。");
    return;
  }
  status("CALCULATING","正在计算五模块与敏感性…");
  let input, output;
  try {
    input = JSON.parse(editor.value);
    if (input?.dataset?.kind && input.dataset.kind !== mode.value) {
      throw Error("JSON 数据轨道与当前模式不一致，请切换模式后再录入。");
    }
  } catch (error) {
    telemetry.cycle++;
    errorStatus("INVALID_INPUT",String(error));
    return;
  }
  const computeStart = performance.now();
  try { output = JSON.parse(engine(editor.value)); }
  catch (error) {
    telemetry.cycle++;
    errorStatus("SERIALIZATION_ERROR","Python 计算或 JSON 返回失败。"+String(error));
    return;
  }
  const computeEnd = performance.now();
  telemetry.cycle++;
  if (output.status !== "CALCULATED") {
    const note = output.message || output.modules?.M1?.samples?.find(s=>s.status!=="CLASSIFIED")?.reason || "";
    errorStatus(output.status,statusText[output.status] || output.status);
    if (note) byId("status").textContent += "。"+note;
    return;
  }
  try { verify(output,input); } catch (error) { errorStatus("NUMERIC_ERROR",String(error)); return; }
  try { show(output); } catch (error) { errorStatus("RENDER_ERROR","图表绘制失败。"+String(error)); return; }
  byId("current").style.minBlockSize="";
  telemetry.current = output;
  lastValid = {input,output};
  byId("result").textContent = JSON.stringify(output,null,2);
  byId("current-result").hidden = false;
  byId("last-valid").textContent = JSON.stringify(lastValid,null,2);
  status("CALCULATED","计算完成 · 五图已更新");
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (version !== token || telemetry.state !== "CALCULATED") return;
    telemetry.timings.push({cycle:telemetry.cycle,total_ms:performance.now()-start,
      python_ms:computeEnd-computeStart,chart_count:charts.length+1});
    if (telemetry.timings.length > 100) telemetry.timings.shift();
  }));
}

window.seosAttach = callback => {
  engine = callback;
  byId("recalculate").disabled = false;
  seosDependency("python",true);
  schedule(true);
};
function changeMode(reset = false) {
  if (!reset && activeMode) drafts[activeMode] = editor.value;
  activeMode = mode.value;
  byId("scope-chip").textContent = mode.value === "synthetic" ? "教学工程 · 合成数据" : "真实工程 · 资料待审";
  byId("case-note").textContent = mode.value === "synthetic" ? "预置案例 "+fixtures.synthetic.dataset.id : "请提供真实工程数据与来源记录。";
  byId("fields").inert = false;
  formData = structuredClone(fixtures[mode.value]);
  byId("mode-note").textContent = mode.value === "synthetic" ?
    "预置试验与运输参数均为合成。更改字段后自动重算。" :
    "该轨道需要实测密度、实际运距、有效费率及材料适用性证据。可在 JSON 录入资料。";
  editor.value = (!reset && drafts[mode.value]) || JSON.stringify(formData,null,2);
  // Preserve edited lexemes. The structured form reopens after a validated calculation.
  formData = parseFormData();
  buildFields();
  schedule(true);
}
editor.addEventListener("input", () => {
  byId("fields").inert = true;
  schedule();
});
function parseFormData() {
  try {
    const data = JSON.parse(editor.value);
    // Preserve unsupported-precision numbers until corrected in the original text.
    const tokens = editor.value.match(/"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?/g) || [];
    const safe = tokens.filter(x=>x[0]!=='"').every(x=>typeof numeric(x)==="number");
    return safe && data?.dataset?.kind===mode.value ? data : null;
  } catch (_) { return null; }
}
byId("sync-form").addEventListener("click", () => {
  byId("fields").inert = false;
  formData = parseFormData();
  buildFields();
  schedule(true);
});
mode.addEventListener("change",()=>changeMode());
byId("reset").addEventListener("click",()=>changeMode(true));
byId("recalculate").addEventListener("click",()=>schedule(true));
changeMode(true);
setTimeout(() => {
  if (!engine) {
    byId("engine-state").textContent="Python 初始化超时";
    errorStatus("DEPENDENCY_ERROR","Python 未在 60 秒内初始化。可重试或打开离线基线快照。");
  }
},60000);
