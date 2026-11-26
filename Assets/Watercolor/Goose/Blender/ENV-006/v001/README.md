# ENV-006 低矮草丛与苔草

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 10 页，任务清单第 50 项，本轮按用户指定提前制作。直接依赖 MAT-001/v001。

[可编辑 Blender 母版](ENV-006_grass.blend) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-006_generate.py)

独立 GLB　[Grass_A](ENV-006_Grass_A.glb) · [Grass_B](ENV-006_Grass_B.glb) · [Grass_C](ENV-006_Grass_C.glb)


[灰盒排布](graybox_lineup.png) · [近景排布](preview_lineup.png) · [固定后上方与边界标记](preview_fixed_rear.png) · [回导排布](preview_glb_roundtrip.png)

Grass_A 为灰绿草簇，Grass_B 为浅黄绿叶丛，Grass_C 为暖灰干草夹绿。每簇分别使用 7、9、8 片有折脊和渐尖的弧形叶，色带来自 MAT-001 的 PlantOpaque 和 DryGround。各根点在 `(0,0,0)`。GLB 使用双面不透明材质，可绕根点接风场。

| 变体 | 高度（BU） | 三角面 |
| --- | ---: | ---: |
| Grass_A | 0.205 | 98 |
| Grass_B | 0.282 | 126 |
| Grass_C | 0.245 | 112 |

150 簇散布在固定后上方审阅样段，原型半径乘预览缩放后，距风机边界示意线至少 1.147 BU。禁摆区和示意线的可读性仅在此 Blender 样段评估，风机真实危险边缘、引擎遮挡和运动待集成验证。远排成细色点，近景仍见简化叶形。三份 GLB 的节点名、根点、轴向、三角面、法线、UV、原图和色调参数已回导核对。脚本复用 ENV-004 的条带建模和回导工具，生产材质依赖仍是 MAT-001。


## 复现

输出到独立空目录。生成脚本只读素材库内的输入。使用 Blender 5.2.2 LTS。

```sh
blender --background --factory-startup -t 6 --python-exit-code 1   --python ENV-006_generate.py -- /absolute/path/to/empty-output
blender --background --factory-startup -t 4 --python-exit-code 1   --python ENV-006_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-006/v001
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补候选母版、GLB、QA、贴图映射、依赖及 `needs_review`。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 增补原创几何及项目内材质来源、处理记录、审阅证据和待验项。运行时导出路径在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回变体、交付路径与候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补 Blender 验证记录与待验项。iPhone 18 Pro（iOS 27.2）模拟器构建和 340 项测试沿用现有记录。

本轮已对照设计红线。待负责人复核观感、USDZ / RealityKit 接入及 iPhone / iPad 真机验证。
