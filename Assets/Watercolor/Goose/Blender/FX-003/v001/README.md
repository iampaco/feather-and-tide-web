# FX-003 逆风阻力流线

**v001 · needs_review · Blender 5.2.2 LTS**。斑头雁制作规格书第 14 页，任务清单执行顺序第 32 项，P0 / S5。变体 `Headwind`。

[可编辑母版](FX-003_Headwind.blend) · [Headwind GLB](FX-003_Headwind.glb) · [直通 RGBA 贴图](textures/ft_goose_fx_headwind_rgba.png) · [风场接口](wind_interface.json) · [资产清单](asset_manifest.json) · [QA](qa.json) · [复跑脚本](FX-003_generate.py)

- [固定后上方静音对照短片](preview_fixed_rear_comparison.mp4)，0–3 秒为 S1 原顺风源，3–6 秒为 S5 逆风候选。两段从相同的雁群轨迹相位起播。
- 灰盒 [固定机位](graybox_fixed_rear.png) / [技术顶视](graybox_top.png)。
- 材质 [逆风](preview_fixed_rear_headwind.png) / [S1 顺风对照](comparison_s1_tailwind.png) / [减弱](preview_fixed_rear_reduced.png) / [关闭流线](comparison_without_fx.png) / [技术顶视](preview_top.png) / [GLB 回导](roundtrip_fixed_rear.png)。

## 资产与接口

派生自 [FX-001/v001](../../FX-001/v001/README.md) 的 `WindTail_Long`。72 三角面，长 2.8 BU，名义宽 0.18 BU。逐三角顶点与 UV 签名同源完全一致。贴图沿用顺风笔触的纸纹、末端聚色与四边羽化，改为冷灰金并用 0.93 倍的直通 Alpha。Blender 和导出均用双面混合及钳位采样。GLB 只有一条流线，可独立实例化。母版的雁群、浅水和终点开口是对照样场，接入摆位见 LVL-S5。

枢轴在笔触上游中心，Blender 本地 +Y 向前、+Z 向上，GLB 映射 `(x,z,-y)`，导出本地 −Z 向前、+Y 向上。U=0 是上游，U=1 是下游。引擎把上游锚点放在世界坐标，绕上轴旋转正比例实例，让本地前向对齐水平风向；沿该向量按 `风速 × 时间 + 相位距离` 推进。S5 航向 +Y 时，将实例绕上轴转 π，风沿 Blender −Y（GLB +Z）移动。保持中央开口和雁群投影净区，沿风向每 2.8 BU 平铺，在实例回收时淡出。

打开母版，在 Outliner 的 `Wind | editable preview controls` 修改 `windBearingRad`、`windSpeedBUPerSecond`、`opacityMultiplier`。灰盒候选航行速度用 `reviewFlightBUPerSecond` 调整，`formationWeight` 影响审阅雁群的队形，单条笔触有 `phaseOffsetBU`。要复现 S1 对照，打开集合 `Review | S1 tailwind control lanes` 的渲染，隐藏 `Review | headwind instance lanes` 的渲染，并把方向设 0、速度设 1.32 BU/s。默认样片逆风设 π、2.55 BU/s，走 12 条带；正向对照走 8 条带。风实例从侧翼通行，飞行与能耗由游戏控制。

## 离线回验

| 固定相机 3 秒对照 | 顺风 | 逆风 |
| --- | ---: | ---: |
| 半帧抽查数 | 71 | 71 |
| 实例速度，沿 Blender Y（BU/s） | +1.32 | −2.55 |
| 下游点纵向屏幕位移中位数（px / 半帧，屏幕向上为正） | +0.240 | −1.552 |
| 风线到领队投影包围盒最小间距（px） | 72.66 | 73.41 |
| 风线到终点开口投影包围盒最小间距（px） | 58.91 | 60.02 |

固定后上方机位按现有 Swift 的距离 180 游戏单位、俯仰参数 0.48 rad、纵向 FOV 50°、领队高度加 6 游戏单位注视。生成依据为 `0.9900 BU = 27.5 游戏单位`。回验逐半帧核对相机位姿、领队投影与湿地开口，确认两个样段的屏幕流向相反。色阶减弱后的像素差低于默认，终点开口在两段可见。静音抽帧观察中逆风从远处向画面下方掠过，结阵领队保持可见；限时辨识还需负责人盲看。

另一 Blender 后台进程从本交付目录重开母版并回导 GLB，复测正反方向、枢轴、UV、坐标、净空和贴图。母版重开与 GLB 回导的同机位关键帧平均 RGB8 差均为 0。内嵌 PNG 与独立文件逐字节匹配，Alpha 峰值 0.341。FFmpeg 完整解码 72 帧，确认无音轨，源分辨率 852 × 393，H.264 底部补一行。

PATH 需含 ffmpeg 和 ffprobe。在本目录运行，下列临时输出目录应为空。

```sh
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python FX-003_generate.py -- /tmp/ft-fx003-rebuild
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python FX-003_generate.py -- /tmp/ft-fx003-recheck --verify "$PWD"
```

## 待验与共用登记

- 待负责人静音盲看约 3 秒风向辨识、冷灰金、水彩及终点引导；待 USDZ、RealityKit／App 接入、实际风场、队形、透明排序、减弱选项和 S5 终点复测。能耗、安全补救、补给、通关交给运行时。iPhone／iPad 待真机验证。引用 active 计划的 iOS 27.2 灰盒基线和 340 项测试。已对照项目红线清单。
- [素材索引](../../../../../docs/asset-index.json) 待登记母版、GLB、贴图和对照预览。
- [候选台账](../../../../../docs/asset-ledger.md) 和 [运行时来源台账](../../../../../../docs/references/asset-ledger.md) 待登记 FX-001 几何、授权纸纹、派生色彩及候选状态。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json) 和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md) 待登记本项离线证据、S5 复用及运行时待验。
