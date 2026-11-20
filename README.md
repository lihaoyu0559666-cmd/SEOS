# SEOS · 施工土方挖填调配

教学用土方调配工作台。采用 Python 线性规划按天然方计算合成运费，并提供土料分类、方量换算、年度供需情景和韧性评价。

## 打开报告

下载并解压仓库，在联网情况下用 Chrome 或 Edge 双击 `report/index.html`。页面通过 PyScript 在浏览器中运行同一 Python 模型，无需系统安装 Python 或启动服务。断网可打开 `report/static.html` 查看固定结果。独立离线三维教学原型入口为 `prototypes/three/index.html`。

## 从源码运行

```sh
python -B main.py --input data/g2_teaching.json
python -B -m seos.report_analysis --input data/g2_teaching.json
python -B -m scripts.build_g3
```

自动回归需安装开发依赖，执行 `python -m pip install -r requirements-dev.txt`，然后运行 `python -m pytest -q`。三维原型可在 `prototypes/three` 运行 `npm ci` 与 `npm run build` 重建。

## 适用范围

内置数据为教学合成数据，金额为合成运费。真实工程模式要求经过核验的资料，当前没有可用的真实工程数据集。三维图是非实测剖面示意。交互页首次加载依赖 PyScript 和 Chart.js CDN。

项目代码采用 MIT 许可证。三维原型包含 Three.js，其许可证声明内嵌于原型 HTML。
