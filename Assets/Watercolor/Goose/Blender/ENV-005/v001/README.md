# ENV-005 芦苇滩分布预设

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 10 页，任务清单第 19 项。直接依赖 ENV-004/v001、ENV-002/v001，ENV-003/v001 用于水岸取景。

[可编辑 Blender 母版](ENV-005_reed_distribution.blend) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-005_generate.py)

独立 GLB　[Dense](ENV-005_Dense.glb) · [ShoreEdge](ENV-005_ShoreEdge.glb) · [Sparse](ENV-005_Sparse.glb)


[灰盒顶视](graybox_top.png) · [Sparse 顶视](preview_top_Sparse.png) · [Dense 顶视](preview_top_Dense.png) · [ShoreEdge 顶视](preview_top_ShoreEdge.png) · [GLB 回导](preview_glb_roundtrip.png)

[实时风摆循环](preview_wind_fixed_rear.mp4) · [风摆视频脚本](ENV-005_wind_preview.py)

固定后上方　[Sparse](preview_fixed_rear_Sparse.png) · [Dense](preview_fixed_rear_Dense.png) · [ShoreEdge](preview_fixed_rear_ShoreEdge.png)

`ENV-005 | Reusable distribution` 中的三个对象共用一个 Geometry Nodes 节点组，按名称切换可见性。源地表的 `reed_shore_weight` 是浮点顶点属性，随距水线增加而衰减，可按地块绘制。预设面板公开 Seed、密度、内陆比例、风向、倾角和相位。每株从 6 个 ENV-004 原型择一，方位、尺寸和风摆相位分别取样。导出用 `Realize for export`，实际交付的三个冻结网格位于 `ENV-005 | Frozen GLB exports`，可直接选择和导出。

| 预设 | 实例 | 冻结三角面 | 距水线 1 BU 以内 |
| --- | ---: | ---: | ---: |
| Sparse | 75 | 9,632 | 20.0% |
| Dense | 323 | 41,394 | 20.4% |
| ShoreEdge | 196 | 25,460 | 38.3% |

排除框由 ENV-002 三组 12 只原尺寸落脚位置推得，另设一处救援审阅空地。这个救援框留给关卡组装定位。根点筛去低于参考水位 + 0.021 BU 的地形，并给避让框加 0.66 BU 缓冲（覆盖默认最大缩放和风摆）。已检查冻结叶片顶点与保留区间距，最小余量为 0.4514 BU。同一 Seed 两次输出逐值相同，改 Seed 会改变摆位。改变相位时随机摆位、原型和尺寸均保持一致，倾角随株变化。冻结、三份 GLB 回导、基准预设的回导取景，以及重开母版重算均纳入 QA。

风摆视频从已交付母版直接读取实时节点。相位改变 π 时最大顶点移动 0.1147 BU，整周期回位误差 9.5e-07 BU。视频复现可在同一目录运行 `blender -b --python-exit-code 1 --python ENV-005_wind_preview.py -- /absolute/path/to/empty-wind-output --frames 30`，需 ffmpeg。

冻结网格保留审阅时的倾角和贴图，后续在 RealityKit 以实例化、风场和 LOD 复验。冻结三角面与实例数是资产数据，App 性能待真机验证。


## 复现

输出到独立空目录。生成脚本只读素材库内的输入。使用 Blender 5.2.2 LTS。

```sh
blender --background --factory-startup -t 6 --python-exit-code 1   --python ENV-005_generate.py -- /absolute/path/to/empty-output
blender --background --factory-startup -t 4 --python-exit-code 1   --python ENV-005_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-005/v001
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补候选母版、GLB、QA、贴图映射、依赖及 `needs_review`。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 增补原创几何及项目内材质来源、处理记录、审阅证据和待验项。运行时导出路径在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回变体、交付路径与候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补 Blender 验证记录与待验项。iPhone 18 Pro（iOS 27.2）模拟器构建和 340 项测试沿用现有记录。

本轮已对照设计红线。待负责人复核观感、USDZ / RealityKit 接入及 iPhone / iPad 真机验证。
