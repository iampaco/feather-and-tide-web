# ENV-002 湿地泥滩 / 浅滩岛

**v001 · needs_review · 2026-11-14**。任务 JSON 第 16 项，P0，适用 S0、S1、S4、S6。按规格书第 9 页制作，直接依赖 ENV-001/v001、MAT-003/v001。ANM-007/v001 的主雁站姿用于审阅测量。

## 文件与预览

| 文件 | 用途 |
| --- | --- |
| [ENV-002_wetland.blend](ENV-002_wetland.blend) | 可编辑母版。`ENV-002 \| Module library` 里的三个资产对象位于原点，按名称选择或 Append。切到 `ENV-002 \| Review assembly` 可查看 3 × 3 拼装、独立水位和落脚姿势 |
| [StartMudflat.glb](ENV-002_StartMudflat.glb) · [ReedIslet.glb](ENV-002_ReedIslet.glb) · [RestPatch.glb](ENV-002_RestPatch.glb) | 三个独立地形文件，各含一个同名节点及所用的内嵌 MAT-003 PNG |
| [灰盒顶视](graybox_top.png) · [灰盒足部](graybox_foot_detail.png) · [MAT-003 顶视](preview_top.png) · [GLB 回导拼装](preview_glb_roundtrip.png) | 从灰盒到材质、回导的同一布局 |
| [StartMudflat 横屏](preview_fixed_rear_StartMudflat.png) · [ReedIslet 横屏](preview_fixed_rear_ReedIslet.png) · [RestPatch 横屏](preview_fixed_rear_RestPatch.png) | 三组各 12 只，852 × 393 固定后上方 |
| [StartMudflat 边缘](preview_foot_StartMudflat.png) · [ReedIslet 边缘](preview_foot_ReedIslet.png) · [RestPatch 边缘](preview_foot_RestPatch.png) | 各模块的单只岸边静态足部证据 |
| [生成与复验脚本](ENV-002_generate.py) · [资产及依赖清单](asset_manifest.json) · [自动 QA](qa.json) | 含接边、足底、间距、回导、画幅及文件哈希 |

## 接口与用途

每块 **10 × 10 BU**，中心枢轴 `(0,0,0)`、单位缩放，0° 方向按 10 BU 整格平移。每边 17 点、步长 0.625 BU，每块 289 源顶点与 512 三角面。陆接边 L 在 Z=0，法线 +Z。UV 与 ENV-001 同为 `(x+5)/10,(y+5)/10`，Repeat 寻址。Blender +Z 向上、+Y 向前，GLB 坐标为 `(x,z,-y)`。

| 模块 | 西 / 东 / 南 / 北 | 地形 |
| --- | --- | --- |
| StartMudflat | L / L / L / L | 宽泥滩平台，东北与西北有独立浅洼 |
| ReedIslet | L / W / C / C | 纵向滩脊，西侧弯曲浅沟，东侧沉入底床。C 边沿用 ENV-001 Shore 的 17 点剖面；W 是开放的水下末端 |
| RestPatch | L / L / L / L | 中央草滩休整面，边缘 3 处浅洼与苔石色块 |

三块均为连续地形网格。三角面陡处集中在湿洼或滩脊边，实际落脚面按足底探针验收。参考水位 **Z=−0.18 BU**，ReedIslet 东侧边 Z=−0.65 BU。水面和雁群分组留在审阅场景。QA 给出逐三角面水线的模块本地 XY 线段和水位下投影面积，可供 ENV-003 裁水面。岸线浅水暖色反光、实际水材质与透明排序留给 ENV-003。

审阅采用当前 `ThirdPersonRig.graybox` 的 180 距离参数、0.48 rad 俯仰参数、50° 纵向视角、注视点高度 6，`depthLift=0`。领队水平位置跟随 1× 站姿雁，身体高度由测得的泥地接触决定。沿用 0.9900 BU 喙尾对齐 27.5 游戏单位的审阅比例。同伴预览为 0.8×，验证另跑全部 1×。当前游戏路径与落脚状态仍由应用控制。

## 落脚与回导验证

先在灰盒测量与渲染，再贴入 MAT-003 重看轮廓与足部。每个模块使用 ANM-007 的 `Land_Mudflat` 第 81 帧，按实际骨骼权重定位两脚下表面。向下射线逐点读取地形高度，只调整整只雁的高度，不单独移动脚。对整只雁网格顶点检查穿地，对 12 个完整网格在 XY 上的凸包检查 66 对分离。每块另测 8 个临水位置及 8 个朝向，岸边检查采用足底探针距真实水位交线的距离。QA 保存全部审阅站位、两脚探针和安全余量，供接入时重新分配与核对。

回导检查包括节点名、枢轴和单位缩放、原始 GLB 轴向、包围盒、绕序、三角面、法线、UV、材质及 PNG 字节。回导地形重拼 3 × 3，并用同一批群体位置和岸边测试点复验。开发工具的法线写入与回读分别计量，共边独立按 ENV-001 的 0.03° 容差检查。

| 模块 | 12 只全尺寸最小分离 | 8 个临水站姿最大单脚接触差 | 参考水位下投影面积 |
| --- | ---: | ---: | ---: |
| StartMudflat | 0.10815 BU | 0.00692 BU | 2.47 BU² |
| ReedIslet | 0.05405 BU | 0.00596 BU | 38.57 BU² |
| RestPatch | 0.10815 BU | 0.00881 BU | 5.99 BU² |

每脚 65 个探针，单脚接触差容差 0.009 BU。24 个临水站姿最近的足底探针距水线 0.06394–0.23516 BU，脚下地形最少高出水位 0.04082 BU。最大顶点穿入约 0.00125 BU，低于 0.003 BU 容差。量测覆盖所列站位与朝向，岸线其余位置仍由游戏挑选和验证。固定后上方画幅里，三组 12 只全入镜，最小投影约 30 × 22 px，远排足部细节主要看近景。

灰盒和 GLB 各通过 42 种含 ENV-002 的兼容接法，重拼通过 12 条邻边与 4 个四块转角。位置、高度与 UV 相位差均为 0，回导共边最大法线差 0.00291°。独立重开交付文件复检一致，GLB 原始法线与 Blender 回导角点法线最大偏差分别为 0.00418°、0.02471°。原始与回导顶视渲染的平均 RGB8 通道绝对差为 0.00022，P99 为 0。

MAT-003 仍标 `needs_review`，当前源 .blend 与其 manifest 中的哈希差异沿用 ENV-001 的记录。脚本验证当前母版的内嵌 PNG、磁盘 PNG、源清单和输出 GLB 的所用纹理相符。素材为项目内原创地形及既有贴图，主雁与场景参考水位用于审阅。

## 复现

Blender 5.2.2 LTS，输出指定独立空目录。脚本只读相邻的 ENV-001、MAT-003 和 ANM-007。定量复验会打开实际候选母版、回导三个独立 GLB 并重跑拼装与落脚检查。

```sh
blender --background --factory-startup -t 6 --python-exit-code 1 \
  --python ENV-002_generate.py -- /absolute/path/to/empty-output
blender --background --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-002_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-002/v001
```

待负责人复核泥滩、水线、远处小雁与地表配色。已对照设计红线。App 基线引用 iPhone 18 Pro（iOS 27.2）模拟器 340 项测试通过记录，本轮沿用既有记录。待 USDZ / RealityKit 接入、分配落脚点、实际飞入和收翼过程、碰撞、浅水高度，以及 iPhone / iPad 真机验证。

## 共用文件待登记

| 文件 | 内容 |
| --- | --- |
| `Assets/docs/asset-index.json` | ENV-002/v001 的项目根相对路径、母版、三个 GLB、QA、清单和候选状态 |
| `Assets/docs/asset-ledger.md` | 原创地形、MAT-003 映射、ANM-007 审阅站姿、静态足部和群体验证、许可与待审阅项 |
| `docs/references/asset-ledger.md` | 候选来源与审阅证据，正式运行时导出和验收路径在接入后登记 |
| `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` | ENV-002 的三个变体、交付路径及 `needs_review` |
| `plans/active/goose-preview-model-cleanup.md` | 落脚测量、回导拼装、基线引用及运行时待验 |

按任务顺序，下一项为 **ENV-003｜湿地浅水面**。
