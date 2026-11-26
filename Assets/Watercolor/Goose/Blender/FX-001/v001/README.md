# FX-001 顺风流线

**v001 · needs_review · Blender 5.2.2 LTS**。斑头雁制作规格书第 14 页，任务 JSON 的 FX-001 项，P0 / S1。依赖已审阅的 MAT-001/v001；静音审阅样段使用 ANM-001/v001 巡航雁。

[可编辑母版](FX-001_WindTail.blend) · [长流线 GLB](FX-001_WindTail_Long.glb) · [短流线 GLB](FX-001_WindTail_Short.glb) · [资产清单](asset_manifest.json) · [QA](qa.json) · [复跑脚本](FX-001_generate.py)

[固定后上方短片](preview_fixed_rear.mp4) · 灰盒 [固定后上方](graybox_fixed_rear.png) / [顶视](graybox_top.png) · 材质 [松散](preview_fixed_rear_loose.png) / [结阵中](preview_fixed_rear_forming.png) / [对齐](preview_fixed_rear_aligned.png) / [顶视](preview_top.png) · [减弱](preview_fixed_rear_reduced.png) · [关闭](comparison_without_fx.png) · [GLB 回导](roundtrip_fixed_rear.png)

## 模型与可编辑控制

| 变体 | 长 × 最宽 | 三角面 | 直通 RGBA |
| --- | --- | ---: | --- |
| `WindTail_Long` | 2.8 × 0.18 BU | 72 | [512 × 64 浅金](textures/ft_goose_fx_wind_tail_long_rgba.png) |
| `WindTail_Short` | 1.4 × 0.13 BU | 48 | [256 × 64 乳白](textures/ft_goose_fx_wind_tail_short_rgba.png) |

先以灰盒确定长短笔触、稀疏度和主雁通道，再从 MAT-001 `SoftStone` 的贴图抽取纸纹，在双色流线内烘焙。贴图在流向末端形成较亮笔触，四边 Alpha 均为 0。网格原点是上游中心线起点，首尾横截面同宽，中心线两端切向均沿 +Y。单条可按自身长度排布。导出为双面 BLEND。Blender 导出器提示颜色、发光与 Alpha 共用采样器；GLB 和回导均核对了同一张内嵌 PNG，以及一致的钳位采样。

母版含 8 条审阅实例，放在雁群可见轮廓外侧，领队循环复用在先的巡航动作，同伴使用固定巡航姿态。Outliner 选中 `Wind | editable preview controls`，在物体自定义属性调整风向 `windBearingRad`、漂移速度 `windSpeedBUPerSecond`、结阵权重 `formationWeight`、透明倍率 `opacityMultiplier`。调 `reviewFlightBUPerSecond` 可比较跟随速度。每条审阅实例还保留 `phaseOffsetBU`、`looseYawRad`、`looseSwayBU`。默认从第 17 帧至第 41 帧用 2 秒过渡至对齐。

## 接口

- Blender +Y 向前、+Z 向上，GLB 为 −Z 向前、+Y 向上。U=0 为上游，U=1 为下游，V 从左到右。世界坐标按 0.9900 BU / 27.5 游戏单位换算，即乘 0.036。
- 引擎提供世界锚点、局部水平风向、风速、经过秒数、相位偏移和结阵权重。沿风向漂移距离为风速 × 秒数 + 相位偏移。实例朝向逐渐收敛到风向，侧向扰动随结阵权重衰减。减弱与淡出在直通 Alpha 上乘透明倍率。排布与循环回收时沿用端点羽化，并按游戏相机投影给雁群预留间距。
- 侧风和逆风沿用同一枢轴和 U 方向。反向时绕向上轴旋转 180°，用正比例，保留 UV 方向，颜色可按后续资产派生。GLB 为静态单网格，Blender 审阅时间线单独示范移动。

## 回验

从实际交付目录在独立 Blender 进程重开母版，重新导入两份 GLB，复测网格、首尾拼接、UV、坐标、直通 Alpha、反向旋转和静音视频解码。取景沿用距离 180 游戏单位、俯仰参数 0.48 rad、垂直 FOV 50°、注视高度 6，领队高度 8、同伴高度 6。固定相机有效源幅 852 × 393，H.264 底部补一行，12 fps、5 秒。119 次半帧抽样中 12 只雁始终入画；流线与领队投影包围盒最小间隔 52.74 像素，与任一雁最小间隔 9.40 像素。两变体回导重拼的固定机位帧 RGB 差值为 0，60 帧视频均可解码。细项见 [QA](qa.json)。

待负责人确认水彩观感及风向辨识，待 USDZ / RealityKit、App 接入、动态风场与画面排序、iPhone / iPad 真机。沿用当前 iOS 27.2 灰盒构建和测试记录。本轮对照设计红线清单。

## 复现

使用 Blender 5.2.2 LTS。PATH 需包含 ffmpeg 和 ffprobe。以下命令从本目录运行。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-001_generate.py -- /tmp/ft-fx001-rebuild
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-001_generate.py -- /tmp/ft-fx001-recheck --verify "$PWD"
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 登记母版、两种 GLB、贴图、FX-001 依赖及 `needs_review`。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 记录原创几何、MAT-001 纸纹、审阅证据和待验状态。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回 FX-001 交付路径和候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补 Blender 回验及 App、USDZ 与真机待验，FX-002 / FX-003 可复用本文导出和接口。
