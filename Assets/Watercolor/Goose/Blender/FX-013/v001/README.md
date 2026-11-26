# FX-013 落羽与终点粒子

**v001 · needs_review · Blender 5.2.2 LTS**。S6 / P2，斑头雁制作规格书第 16–17 页，任务 JSON 的 FX-013 项。候选使用 ENV-017/v001 的落脚盆地和审阅载体，以及已装入该母版的 ANM-007/v001 `Land_Mudflat`。

[可编辑母版](FX-013_FeatherMotes.blend) · [FeatherMotes GLB](FX-013_FeatherMotes.glb) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [复跑脚本](FX-013_generate.py)

[固定后上方短片](preview_fixed_rear.mp4) · 灰盒 [后上方](graybox_fixed_rear.png) / [顶视](graybox_top.png) · 材质 [出现前](preview_fixed_rear_pre.png) / [落羽](preview_fixed_rear_peak.png) / [减退](preview_fixed_rear_settling.png) / [清空](preview_fixed_rear_clear.png) / [顶视](preview_top.png) · [完全关闭](preview_disabled.png) · [回导重拼](roundtrip_fixed_rear.png)

## 可编辑资产

`FeatherMotes` GLB 内有同枢轴的 `FeatherMotes_Feather`（0.125 × 0.40 BU）和 `FeatherMotes_Mote`（0.135 × 0.135 BU）。各为 2 三角面的双面卡片。原创[象牙白羽片](textures/ft_goose_fx_feather_motes_feather_rgba.png)和[浅金光点](textures/ft_goose_fx_feather_motes_mote_rgba.png)使用 sRGB 直通 RGBA；四边 Alpha 为 0。独立技术场景留有可编辑网格。GLB 仅含根节点、卡片和打包材质。Blender 局部 +Z 为法线，+Y 为卡片向上，GLB 分别为 +Y 和 −Z。导出器报告共用采样器，回导核对了同一 PNG、钳位采样及 BLEND。

审阅场景使用 4 片落羽和 8 个微粒，沿盆地两侧轻摆缓降。选中 `FeatherMotes | review controls` 可在物体属性调整 `enabled`、`intensity`、`sideDriftBUPerSecond`、`fallSpeedMultiplier`、`allLandingStartFrame`。每条卡片保留可检查的延迟与基速，驱动关系可在 Drivers 编辑器查看。灰盒先检查疏密和占位，材质阶段再固定透明软边、暖白与浅金。

## 游戏输入

- 传入单次落脚会话 ID、固定的参与雁 ID 集合、已收到 ANM-007 落脚入场事件的雁 ID 集合和盆地世界锚点。参与集合全部开始落脚后产生一次视觉事件，忽略同一会话的重复回调。会话重试时清空视觉事件状态。
- 风漂和下落只移动卡片；初值下落 0.21–0.37 BU/s。沿各自的相位淡入、淡出，乘 `intensity` 后取直通 Alpha。可用相机朝向旋转卡面。尺度沿用喙尾 0.9900 BU 对齐 27.5 游戏单位。
- 关闭时不生成卡片，并立即隐藏现有卡片。引擎的土地／水面判定、落脚规则、胜利判定和存档独立运行。参与集合、重试与偏好开关由实际 App 接入验证。

## 回验

以实际 ENV-017 审阅载体的 48 fps 时间线取样。第 1 至第 56 帧间，各只雁依次开始落脚。固定相机继续跟随领队，沿用距离 180 游戏单位、俯仰 0.48 rad、垂直 FOV 50°、注视高度 6；横屏有效画幅 852 × 393。短片 5.083 秒，静音 H.264 底部补一行，61 帧已全部解码。

独立 Blender 进程从交付目录重开母版、回导 GLB，核对枢轴、三角面、UV、轴向、双面 BLEND 与两张内嵌 PNG。回导重拼与原画面像素一致。244 帧抽样中，落羽与雁体投影包围盒最近间隔 1.27 像素，距画边最少 1.50 像素。第 56 帧全员入场，第 67 帧第一张卡片越过 QA 可见阈值，第 213 帧后全部淡出。关闭开关时的画面与隐藏所有粒子的对照图像素相同，四个抽样时刻的雁群位置也一致。详见 [QA](qa.json)。

待负责人审阅水彩观感，待 USDZ、RealityKit / App 接入、正式 Zone 与落脚事件、iPhone / iPad 真机。引用已有 iOS 27.2 灰盒基线。本轮已对照设计红线清单。

## 复现

从本目录运行。需要 Blender 5.2.2 LTS、ffmpeg 和 ffprobe。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-013_generate.py -- /tmp/ft-fx013-rebuild
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-013_generate.py -- /tmp/ft-fx013-recheck --verify "$PWD"
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补母版、GLB、纹理、依赖与 `needs_review`。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 增补制作来源、项目原有依赖、自制纹理、离线证据及待验项。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回 FX-013 候选状态与路径。
- `plans/active/goose-preview-model-cleanup.md` 补交付与后续运行时、真机验证。
