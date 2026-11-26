# ENV-001 通用地形与岸线基座

**v001 · needs_review · 2026-11-14**。按制作规格书第 9 页与任务 JSON 制作。ENV-001 是 `execution_order` 第 15 项，P0、S0–S6，直接依赖 `MAT-003/v001`。`CHR-001/v001` 用于取景尺度。几何先通过灰盒检查，再换入 MAT-003 的候选地表材质。

## 文件与预览

| 文件 | 用途 |
| --- | --- |
| [ENV-001_terrain.blend](ENV-001_terrain.blend) | 可编辑母版。场景 `ENV-001 \| Module library` 的四个资产对象各自位于原点，可单独 Append、选择或导出。场景 `ENV-001 \| Review sample` 用同一批网格实例拼装，可独立关闭水位、路线、主雁与取景背景 |
| [Flat](ENV-001_Flat.glb) · [GentleSlope](ENV-001_GentleSlope.glb) · [Shore](ENV-001_Shore.glb) · [Ridge](ENV-001_Ridge.glb) | 每个 GLB 内一个同名网格节点，材质和使用的 PNG 内嵌 |
| [灰盒顶视](graybox_top.png) · [灰盒岸缝](graybox_seam.png) · [灰盒横屏](graybox_fixed_rear.png) | 贴入候选材质前的样段 |
| [顶视与拼装坐标](preview_assembly.png) · [无网格顶视](preview_top.png) · [岸缝近景](preview_seam.png) · [缓坡与陆脊接合](preview_slope_join.png) | MAT-003 审阅帧，网格和标注仅在拼装图中出现 |
| [横屏视频](preview_fixed_rear.mp4) · [入口](preview_fixed_rear_entry.png) · [沿岸](preview_fixed_rear_shore.png) · [转弯](preview_fixed_rear_bend.png) | 源码机位。雁用 CHR-001 的静态姿势，镜头随审阅轨迹移动 |
| [回导拼缝](preview_roundtrip_seam.png) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) | GLB 重拼、材料映射、哈希和可复核读数 |
| [Blender 生成与复验](ENV-001_generate.py) · [视频与拼装图生成](ENV-001_preview.py) | 复现模型、预览和回导检查 |

## 模块接口

四块均为 **10 × 10 BU**，本地 XY 为 `[-5, 5] × [-5, 5]`，中心枢轴为 `(0, 0, 0)`，对象缩放 1。中心按 10 BU 整格平移，v001 验证方向为 **0°**。每边 17 点，间距 0.625 BU。统一方格可在同一段内重复摆放，四边和转角都能用同一采样规则。单块审阅宽度约等于 10.1 个领队喙尾长度，约 277.78 游戏单位。该换算用于 Blender 审阅，App 导入比例待验证。

| 模块 | Z 范围（BU） | 最大三角面倾角 | 西 / 东 / 南 / 北 | 材质 |
| --- | ---: | ---: | --- | --- |
| Flat | 0 | 0° | L / L / L / L | GrassFlat |
| GentleSlope | 0 到 +0.1898 | 6.09° | L / L / L / L | GrassFlat |
| Shore | −0.6500 到 0 | 10.82° | L / W / C / C | GrassFlat、MudBank、ShallowMargin |
| Ridge | 0 到 +0.2350 | 10.40° | L / L / L / L | GrassFlat、MossStone、MountainRock |

每块 289 个源顶点、512 三角面。GLB 在材质交界处分顶点，Shore 和 Ridge 回导分别有 328 和 351 个顶点，位置网格仍各有 289 点。

- **L** 为 Z = 0 的陆接边，边法线 +Z。坡与陆脊在内部起伏，靠边回到同一基准并留出至少一格缓冲。
- **C** 为沿岸接边，Shore 北对南，岸剖面从西向东沉入水下。17 个采样高度见清单 `shore_edge_z_BU_in_increasing_local_x`。本版提供沿岸串接，带弯折的新岸块可用同样的进出边剖面。
- **W** 为 Shore 东端的开放水下边，Z = −0.65 BU。当前库里无配对模块。独立参考水位 Z = −0.18 BU，东端底床低于水位 0.47 BU。这里的水体覆盖结论限定在审阅样段的 10 × 40 BU 水位矩形。
- 只将同类型的相对边对接。Blender 为 +Z 向上、+Y 向前，GLB 为 `(x,y,z) → (x,z,-y)`，与 `GroundAxes.point` 的地面方向对应。UV 沿平面投影，`U=(x+5)/10`、`V=(y+5)/10`，周期 10 BU，拼边相差整数时以 Repeat 采样。
- `WorldTileManager` 按段入口对齐上一段出口，并整体平移段内坐标。其湿地段是 1280 × 560 游戏单位，地块接口服务段内摆放。旧米制试看为历史记录。现实游戏的射线交于 RealityKit Y=0，路径存世界坐标，样段用 Flat 串出路线，让 5 × 5 × 1.2 游戏单位、中心高度 1 的路径标记与地面分离。

**ENV-002** 沿用中心栅格、陆接边、地面零点和 UV 周期，在模块内部塑造泥滩、浅滩岛与落脚面。后续检验 12 只的落脚间距与接地。**ENV-003** 沿用同一坐标和岸剖面，以 Z = −0.18 BU 为审阅水位，按实际岸线裁水面轮廓。在透明边外继续铺底床或收口，并验证 RealityKit 水岸透明排序。

## 验证与限制

- 灰盒和最终 GLB 各验证了 22 种有向兼容接法，逐一比较共边 17 点的坐标、高度、法线和 UV 模 1 相位。源样段及 GLB 回导重拼均使用同一个 4 × 4 布局，各验证 24 条邻边和 9 个四块转角。逐格检查三角形共用对角线、覆盖面积和正向绕序，结合相邻网格有符号间隙排查重叠与缺口。
- 位置、接边高差和 UV 相位实测均为 0。容差为 `1e-5 BU`、`0.03°`、`1e-6 UV`。源共边最大法线差约 `0.0000013°`，回导共边约 `0.00242°`。单块回导逐三角角点的最大法线差约 `0.02615°`，位置与 UV 差为 0。回导同时检查模块名、枢轴、单位缩放、边界、三角面数、GLB 原始轴向、材质和内嵌贴图。
- 独立半透明水位面覆盖四块 Shore 的完整网格。实测 400 BU² 底床覆盖，三条沿岸接缝的水线交点差均为 0，东端 68 个采样点最小水深约 0.47 BU。开放样段外缘可在俯视诊断中看到，连续水体由后续组装提供。
- CHR-001 的 0.9900 BU 喙尾对齐 27.5 游戏单位。取景复现 `ThirdPersonRig.graybox` 的 180 距离参数、0.48 rad 俯仰参数、50° 纵向 FOV、注视点高 6、领队高 8，`depthLift=0`。852 × 393 横屏关键帧中，近中景路径、陆地、泥岸与水位轮廓可分。远景标记的投影最低约 0.27 px 高，远处细节会合并。草滩贴图与 Shore 轮廓在长视距下有重复，岸上色带边缘保留低模分面，留待美术审阅。
- MAT-003 仍为 `needs_review`。当前源 `.blend` 哈希与它的 manifest 不同，旁边的 `.blend1` 与清单吻合。本版读取当前 `.blend`，记录实际哈希及清单所列哈希，并核对其五张内嵌 PNG 与 MAT-003 磁盘 PNG、清单哈希和最终 GLB 内嵌 PNG 逐字节相同。节点的粗糙度、贴图色彩空间和 Repeat 也已核对。素材为项目内原创几何与既有项目贴图，来源及映射见清单。
- App 基线引用 active 计划中的 iPhone 18 Pro（iOS 27.2）模拟器构建及 340 项测试通过记录。本轮素材检查使用独立 Blender 后台进程和临时目录，App 脚本沿用已有记录，避免与动画会话争用模拟器。已对照设计红线，审阅内容限于地形、示意路线和尺度证据。
- 待负责人复核地形观感、重复感和路线对比。待 USDZ / App 接入核对实际可通行范围、碰撞、路径拾取、标记与地表遮挡，以及 iPhone / iPad 的触控、可读性与性能。

## 复现

用 Blender 5.2.2 LTS，在空临时目录生成。素材脚本从相邻 `MAT-003/v001`、`CHR-001/v001` 读取输入。合成脚本使用 Python Pillow、ffmpeg 和 ffprobe。

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python ENV-001_generate.py -- /absolute/path/to/empty-output --video-frames 60
python3 ENV-001_preview.py /absolute/path/to/empty-output
blender --background --factory-startup --python-exit-code 1 \
  --python ENV-001_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-001/v001
```

复验会重开母版，逐一回导 GLB，再将四种模块按相同布局拼回 4 × 4 样段并检查岸缝与水位。岸缝近景原始渲染与回导渲染的平均 RGB8 通道绝对差为 0.00012，P99 为 0。生成的序列帧留在临时输出。视频为 H.264，源画幅 852 × 393，编码在底部补 1 像素以兼容 YUV420。

## ANM 交付后待统一登记

| 共用文件 | 待补内容 |
| --- | --- |
| `Assets/docs/asset-index.json` | ENV-001/v001 的项目根相对路径、母版、四个 GLB、manifest、QA、依赖及 `needs_review` |
| `Assets/docs/asset-ledger.md` | Blender 5.2.2 原创几何，规格书第 9 页，MAT-003 五张内嵌贴图映射与哈希差异，CHR-001 仅作审阅参照，样段证据与候选状态 |
| `docs/references/asset-ledger.md` | 依项目台账口径补候选来源 / 审阅记录，正式导出路径与验收信息在 App 接入后填写 |
| `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` | 将 ENV-001 的交付和 `needs_review` 状态写回任务 |
| `plans/active/goose-preview-model-cleanup.md` | 补本候选的 Blender 验证、基线引用、待验项和链接 |

下一项为 **ENV-002｜湿地泥滩 / 浅滩岛**。
