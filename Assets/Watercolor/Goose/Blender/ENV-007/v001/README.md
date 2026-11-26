# ENV-007 河谷河道与河岸

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。制作规格书第 10 页，任务清单第 20 项，P0，适用 S2、S3、S5。直接依赖 ENV-001/v001、MAT-004/v001。

[可编辑母版](ENV-007_river_valley.blend) · [资产清单](asset_manifest.json) · [QA](qa.json) · [生成与复验脚本](ENV-007_generate.py)

| 模块 | 用途 | GLB |
| --- | --- | --- |
| Straight | 平直主河槽，两岸缓坡 | [Straight](ENV-007_Straight.glb) |
| Bend | 河槽向东侧转弯后回到共用剖面 | [Bend](ENV-007_Bend.glb) |
| OpenBank | 河槽往西侧收出连续的东岸接应平台 | [OpenBank](ENV-007_OpenBank.glb) |

[灰盒顶视](graybox_top.png) · [灰盒固定后上方](graybox_fixed_rear.png) · [材质顶视](preview_top.png) · [弯道横屏](preview_bend_approach.png) · [接应岸横屏](preview_fixed_rear.png) · [接应岸近景](preview_open_bank.png) · [独立 GLB 回导重拼](preview_glb_roundtrip.png)

## 尺度和拼接

模块边长 10 × 10 BU。XZ 剖面朝 Blender +Y 连续，地面零点和枢轴为 (0, 0, 0)，按 10 BU 整格平移。验证方向为 0°，Blender XYZ 到 glTF 为 `(x,z,-y)`。每个 GLB 含一张河床和一张独立水面，可按名称选取。单块 512 河床三角面与 128 水面三角面。

- 西、东为 ENV-001 的 **L** 陆接边。17 个等距点、Z = 0，外伸陆地可继续铺 ENV-001 平地。
- 南、北为河道 **R**，河床 17 点、水面 5 点。河口段保留一格恒定剖面，第一个内圈开始变形。剖面与相邻水面按模块南北对接。完整剖面见清单。
- 水面为 **−0.18 BU**，横向 U 0–1 从西岸到东岸，沿流向 +Y 布置 V 0–1，周期 10 BU。水面端点与河床对应的真实水位线逐点共线。
- 采用 MAT-004 的 Water_River 已登记原图并重建导出可移植的 Alpha 连线，水面 GLB 使用 BLEND。陆坡使用同一 ENV-001 底材及 MAT-003 原图。原图嵌在母版和导出中，清单列出路径和 SHA-256。主雁、站姿雁、地表散布及暖金路径留在审阅场景。

## S3 接应区域

OpenBank 的可审阅接应区位于东岸，本地 X = 1.72–4.55、Y = −2.72–2.72 BU。面积 **15.3952 BU²**，最近水线相距 **1.2476 BU**。880 个台面样本以及向南、北、东出界的 123 个路径样本复验通过。三段各 65 条横剖面均只有一个连续水区，干地连接模块侧边。河槽没有截断干地接应区。

沿用源码机位 180 / 0.48 rad / 50° 纵向视场，注视点 6 游戏单位，领队高 8 游戏单位，横屏 852 × 393。CHR-001 只用于 0.9900 BU 对应 27.5 游戏单位的审阅尺度。ANM-007 站姿双脚接地点、地形光线遮挡及四角入镜都作了离线复验。示意路径用来辨认接应方向。关卡脚本的掉队、导航、落脚、归队及动态遮挡接入待验。

## 复验与范围

先完成灰盒的面积、水位、拼缝、连续水区和接应站姿检查，再上材质。回导逐节点核对枢轴、轴向、三角拓扑、法线、UV、采样及内嵌原图，重新拼组 Straight → Bend → OpenBank。九个有向 R 配对与六个 ENV-001 陆接配对都重测了法线、位置与 UV。回导共边最大位置和 UV 误差均为 0，河床共边最大法线差 0.00374°。从交付目录独立重开母版并再次回导，定量结果一致。回导重拼使用源母版同一相机，平均通道绝对差 0.0684 RGB8，P99 为 1。

MAT-004、MAT-003 保留候选审阅状态。运行时的 FX-006 波纹、透明排序、接应判定、碰撞和 USDZ / RealityKit 接入待验证。iPhone / iPad 真机待验。App 构建保留 iOS 27.2 iPhone 18 Pro 模拟器既有的 340 项测试基线记录。本轮限于离线资产，已对照设计红线。

## 复现

使用 Blender 5.2.2 LTS。生成与独立复验各写到自己的空临时目录。

```sh
blender --background --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-007_generate.py -- /absolute/path/to/empty-output

blender --background --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-007_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-007/v001
```

用 `--geometry-only` 可复现第一轮灰盒定量检查。母版的源对象场景按变体分集合，可单独切换。

## 共用文件待登记

- `Assets/docs/asset-index.json` 补候选母版、三个 GLB、QA、清单和依赖路径。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 补原创河床与水面建模、源材质和审阅依赖、验证记录。正式运行时导出在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回变体及 `needs_review` 状态。
- `plans/active/goose-preview-model-cleanup.md` 补灰盒、回导和接应区域度量。记录关卡、App 与真机待验项。
