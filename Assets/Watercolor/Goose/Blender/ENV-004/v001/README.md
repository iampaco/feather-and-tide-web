# ENV-004 芦苇单株组三型

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 10 页，任务清单第 18 项。直接依赖 MAT-001/v001。

[可编辑 Blender 母版](ENV-004_reeds.blend) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-004_generate.py)

独立 GLB　[Reed_A_Height_M](ENV-004_Reed_A_Height_M.glb) · [Reed_A_Height_S](ENV-004_Reed_A_Height_S.glb) · [Reed_B_Height_M](ENV-004_Reed_B_Height_M.glb) · [Reed_B_Height_S](ENV-004_Reed_B_Height_S.glb) · [Reed_C_Height_M](ENV-004_Reed_C_Height_M.glb) · [Reed_C_Height_S](ENV-004_Reed_C_Height_S.glb)


[灰盒排布](graybox_lineup.png) · [六变体近景](preview_lineup.png) · [成片横屏](preview_fixed_rear.png) · [回导排布](preview_glb_roundtrip.png)

A 是幼株，B 是多叶常规株，C 有暖棕细穗。每型各有 S / M，根轴原点 `(0,0,0)`，叶片用有弧度和折脊的条带双面绘制，穗头为独立体积几何。材质使用 MAT-001 的 PlantOpaque、DryGround 和工程内色调参数。GLB 为双面 OPAQUE，无透明卡片。环境取景按源固定后上方参数复现，含 80 个不同原型、尺寸和方位的芦苇实例。

| 变体 | 高度 S / M（BU） | 每变体三角面 |
| --- | --- | ---: |
| Reed_A | 0.513 / 0.731 | 76 |
| Reed_B | 0.681 / 0.981 | 118 |
| Reed_C | 0.825 / 1.166 | 198 |

GLB 已逐个回导并比较节点名、单位缩放、根点、轴向、网格、法线、UV、双面材质、色调参数和内嵌原图。母版有可选原型、单株近景与成片审阅场景。成片预览使用朝 +X 的低幅根部倾转，方位和倾角有差异。游戏里的风压、摆动幅度与遮挡待 FX-007 和运行时验证。


## 复现

输出到独立空目录。生成脚本只读素材库内的输入。使用 Blender 5.2.2 LTS。

```sh
blender --background --factory-startup -t 6 --python-exit-code 1   --python ENV-004_generate.py -- /absolute/path/to/empty-output
blender --background --factory-startup -t 4 --python-exit-code 1   --python ENV-004_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-004/v001
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补候选母版、GLB、QA、贴图映射、依赖及 `needs_review`。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 增补原创几何及项目内材质来源、处理记录、审阅证据和待验项。运行时导出路径在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回变体、交付路径与候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补 Blender 验证记录与待验项。iPhone 18 Pro（iOS 27.2）模拟器构建和 340 项测试沿用现有记录。

本轮已对照设计红线。待负责人复核观感、USDZ / RealityKit 接入及 iPhone / iPad 真机验证。
