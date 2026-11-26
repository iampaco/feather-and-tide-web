# ENV-012 风向指示树组

**v001 · needs_review · Blender 5.2.2 LTS**。制作规格书第 11–12 页，任务 JSON `execution_order` 第 24 项，P0，适用 S2 山口、S3 河谷接应。直接依赖 MAT-001/v001。

[可编辑母版](ENV-012_wind_trees.blend) · [资产清单与贴图映射](asset_manifest.json) · [QA 实测](qa.json) · [生成与独立复验脚本](ENV-012_generate.py)

| 变体 | 建模轮廓 | 高度（BU） | 三角面 | 带骨骼和动作的导出 |
| --- | --- | ---: | ---: | --- |
| RiverTree_A | 较高的团簇树冠、收束树干 | 1.948 | 984 | [GLB](ENV-012_RiverTree_A.glb) |
| RiverTree_B | 较低的宽冠、分叉轮廓 | 1.722 | 828 | [GLB](ENV-012_RiverTree_B.glb) |
| LeaningTree | 偏左的层叠树冠、斜树干 | 2.176 | 984 | [GLB](ENV-012_LeaningTree.glb) |

资产场景 `ENV-012 | Tree assets at origin` 内每棵树的网格和骨架都在一个集合。按表中变体名找网格，骨架对象以 `_Rig` 结尾。枢轴为地面原点，Blender +Z 向上、+Y 向前，导出轴为 `(x,z,-y)`。树体两张 MAT-001/v001 已哈希核对的项目源 PNG 为 `PlantOpaque` 和 `DryGround`。四个不透明材质共享两张纹理，并用独立灰绿、灰褐色调和粗糙度控制分层。PNG 原字节已内嵌到导出。新增仅为项目原创模型、材质参数与动作。

## 风摆接口和审阅

每棵树的蒙皮层级为 `Root → Stem → Crown`。脚下和低树干锁在 Root，树干与冠层权重逐渐过渡；Crown 独立控制树梢响应。动作名为 `<Variant>_WindCue`，从中立到侧摆再回中立，时长 2 秒。制作参考统一朝本地 −X，适配引擎时可分别给 Stem 和 Crown 传入按实例旋转换算的风向、幅度与相位。审阅组按实际世界风向控制不同朝向的实例，带 0–1.4 帧相位差；实机的风场开始时刻由后续 FX-002 / FX-007 和关卡驱动。

- [灰盒造型](graybox_lineup.png) · [材质造型](preview_lineup.png) · [强风姿势排布](preview_wind.png) · [回导姿势](preview_glb_roundtrip.png)
- S2 已建山口　[灰盒](graybox_pass.png) · [风前](preview_pass_before.png) · [预提示](preview_pass_early.png) · [侧摆峰值](preview_pass_crest.png)
- S3 已建河谷　[灰盒](graybox_river.png) · [风前](preview_river_before.png) · [预提示](preview_river_early.png) · [侧摆峰值](preview_river_crest.png)
- [两处固定机位风摆视频](preview_WindCue.mp4)

场景沿用 ENV-010 山口地形和 ENV-007 河床、水面、接应空地。ANM-007 站姿只用于接应目标，CHR-001 主雁只用于尺度。固定后上方机位 852 × 393，按 `ThirdPersonRig.graybox` 的 180 / 0.48 rad / 50°、目标高 6 复现。预览为材料和摆位审阅，不包含树木运行时碰撞体或风场事件。

## 实测

- 单棵树采样 49 帧，下部顶点位移 0 BU，最高点最大朝左移动 0.419–0.461 BU，帧尾回到中立。以 −X 位移 0.06 BU 为提示起点，三个原型在第 12 帧均已超过它，比审阅风场标记第 22 帧领先约 0.417 秒。此时间为素材审阅阈值。
- 在审阅标记前一帧，同一树梢顶点在两处画面向左移动 5.04–14.76 px。S2、S3 各使用 6 株带不同偏航的树，世界下风方向一致。河谷接应雁投影约 25 × 18 px。49 帧中，3,234 条网格采样视线分别经过地表与全部动态树网格测试，遮挡数均为 0。树顶点距接应框最小余量 0.626 BU。
- GLB 回导后按三角形对应核对几何、绕序、轴向、法线、UV、材质和两张原图，并核对三关节层级和蒙皮权重。三个动画每款逐 49 帧比较，最差顶点变形差约 0.00000051 BU，最大 UV 差约 0.000000030，最大法线差约 0.00000863°。只有 Stem 和 Crown 发生可测的动画变化。实际交付目录独立重开后，三个 GLB 的结果一致。

视频由 34 帧 Blender 画面编码，包含山口与河谷两段，并通过 H.264 解码验证。

## 复现与待办

在空临时目录中使用 Blender 5.2.2 LTS，视频需要 ffmpeg。生成过程读相邻资产；母版、导出和源材质不向原目录回写。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-012_generate.py -- /absolute/empty-output --video
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-012_generate.py -- /absolute/empty-recheck --verify "$PWD"
```

已对照设计红线。App 沿用 iPhone 18 Pro（iOS 27.2）既有构建和 340 项测试记录。后续由负责人复核三款树冠、预提示观感和实际屏占，再验证运行时风向/预提示、实际接应路线、USDZ / RealityKit 与 iPhone / iPad 真机。

- `Assets/docs/asset-index.json` 待补 v001 候选、模型、GLB、清单与 QA。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 待记录模型和动作原创来源、MAT-001 贴图、ENV-007/010 及 ANM-007/CHR-001 审阅输入。正式接入后补运行时路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json`、`plans/active/goose-preview-model-cleanup.md` 待回写三款变体、素材状态、独立回导实测与待验项。
