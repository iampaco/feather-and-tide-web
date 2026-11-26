# FX-002 强侧风预警与阵风

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 14 页，任务清单执行顺序第 31 项，P0，适用 S2、S3。

[可编辑母版](FX-002_Crosswind.blend) · [CrosswindWarn GLB](FX-002_CrosswindWarn.glb) · [Gust GLB](FX-002_Gust.glb) · [共享风场接口](runtime_mapping.json) · [资产清单](asset_manifest.json) · [QA](qa.json) · [复跑脚本](FX-002_generate.py)

- 灰盒：[固定后上方](graybox_fixed_rear.png) · [技术顶视](graybox_top.png)
- 材质：[静风](comparison_before_wind.png) · [预警](preview_fixed_rear_warning.png) · [阵风](preview_fixed_rear_gust.png) · [技术顶视](preview_top.png) · [减弱动态](preview_fixed_rear_reduced.png)
- 同机位对照：[预警树梢](comparison_warning_tree_only.png) · [阵风树梢](comparison_gust_tree_only.png) · [GLB 回导](roundtrip_fixed_rear.png) · [4.5 秒静音短片](preview_fixed_rear_silent.mp4)

## 组装与控制

| 变体 | 独立子节点 | 贴图 |
| --- | --- | --- |
| `CrosswindWarn` | `WarnBand` 远处短风带，`CrownSweep` 从露出的冠缘扫过 | [预警](textures/ft_goose_fx_crosswind_warn_rgba.png) · [树梢](textures/ft_goose_fx_crosswind_crown_rgba.png) |
| `Gust` | `GustBand` 阵风长带，`Leaf` 低面数碎叶 | [阵风](textures/ft_goose_fx_crosswind_gust_rgba.png) · [碎叶](textures/ft_goose_fx_crosswind_leaf_rgba.png) |

FX-001/v001 长、短风带继承拓扑、夹取采样、边缘羽化、上游枢轴和 UV 方向。短带经正比例变换得到两个灰青变体，完整长带用作较强阵风。每个 GLB 可拆分两件独立摆放，也可在同一根下统一旋转。两份导出均为静态网格和双面 BLEND，动画由世界风场驱动。预警和冠缘带透明边界保留清楚的遮挡顺序，缩小设定时原样保留端点羽化。

S3 母版沿用 ENV-012/v001 六棵蒙皮树、真实河谷样段和在地面站立的同伴，导入 FX-009/v001 的实际救援光点作为持续可见的遮挡探针。固定风场与接应锚点只用于本段离线审阅。树根保持静止，独立的树干与冠层共用一组世界下风参数，植株各自将世界方向换算到本地骨骼。Outliner 选中 `FX-002 | Edit shared wind inputs` 可调风向、强度、速度、动态倍率和各段包络的关键帧。关卡用 FX-007 的水平下风 `direction`（默认 S3 为归一化的 `(-0.98, 0.20)`）、`strength`、`motionScale` 和统一时钟。叶片翻滚随动态倍率减至静止，倍率 0 时停用碎叶并减弱风带。

本地 +Y 下风，+Z 向上，GLB 转换为 `(x,z,-y)`。U=0 上游，U=1 下游。按 0.9900 BU = 27.5 游戏单位换算。短片相机复现 Swift 的距离 180、俯仰参数 0.48 rad、垂直 FOV 50°，领队高度为 8 个游戏单位，注视高度为 6。相机的眼点和注视点均接收额外的游戏 `depthLift`；本段设为 0。有效源帧 852 × 393，H.264 底部补一行。规格书要求的掉队事件由关卡触发，时间线事件标记仅用于验证先后，正式接应坐标由 S3 与运行时提供。

## 独立离线回验

| 离线实测 | 母版与 GLB 回导 |
| --- | ---: |
| 每轮半帧样本 | 215 |
| 六树均达到提示阈值早于风带 | 0.229 秒 |
| 风带可见早于示范掉队时刻 | 1.188 秒 |
| 树梢最大顺风位移，树根位移 | 0.467 BU，0 BU |
| 特效距光点或接应雁最小投影间隔 | 34.45 px |
| 树冠距光点最小投影间隔 | 11.90 px |
| 地形视线可达 | 4,515 / 4,515 条 |
| 与同机位树冠对照相比的风效像素变化 | 预警 3,415 px，阵风 3,901 px |
| GLB 重拼与母版固定机位图像平均 RGB8 差 | 0 |
| 完整解码 | 36 帧，无音轨 |

将同一风向输入转 180°，六株树尖沿新下风方向最小位移 0.266 BU，阵风风带最小位移 1.299 BU。减弱模式下叶片透明倍率为 0，树梢无可测偏移。

用第二个 Blender 后台进程重开实际交付母版，再回导两个实际 GLB。逐变体核对上游枢轴、轴向、位置、UV、三角面、双面 Alpha 混合与四张内嵌 PNG 原字节，将回导网格代入原风场重复测试。FFmpeg 完整解码静音短片；实测项及阈值见 [QA](qa.json)。已对照项目设计红线清单。

## 复现

从本目录运行，Blender 5.2.2 LTS 和 FFmpeg/ffprobe 可用，临时输出需为空。

```sh
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python FX-002_generate.py -- /tmp/ft-fx002-build
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python FX-002_generate.py -- /tmp/ft-fx002-verify --verify "$PWD"
```

## 待验与登记

- 负责人复核手持画幅下风向、树冠及灰青笔触可读性。S2/S3 运行时需检查实际风区、事件先后、接应可达性、透明混合排序和效果减弱。USDZ、RealityKit / App 接入、iPhone / iPad 真机待验。本次使用现有 iOS 27.2 模拟器灰盒构建与 340 项测试基线。
- [素材索引](../../../../../docs/asset-index.json) 待登记母版、两份 GLB、接口、贴图和证据。[候选台账](../../../../../docs/asset-ledger.md)和[运行时台账](../../../../../../docs/references/asset-ledger.md)待登记 FX-001 继承、ENV-012 树冠、FX-009 审阅输入、FX-007 共享接口及候选状态。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json)第 31 项和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md)待登记离线回验与接入待验项。
