# LVL-S6 芦苇落脚

**v001 · needs_review · Blender 5.2.2 LTS**。制作规格书第 18 页，任务清单执行顺序第 48 项，P0，变体 `S6_Landing`。

[可编辑母版](LVL-S6_S6_Landing.blend) · [场景与锚点 GLB](LVL-S6_S6_Landing.glb) · [坐标、资源映射和事件输入](s6_layout.json) · [资产清单](asset_manifest.json) · [独立 QA](qa.json) · [复跑脚本](LVL-S6_generate.py)

## 审阅

- [固定后上方短片](preview_fixed_rear.mp4)
- 灰盒 [固定后上方](graybox_fixed_rear.png) · [技术顶视](graybox_top.png)
- 材质 [进场](preview_fixed_rear_approach.png) · [领队等候](preview_fixed_rear_leader_wait.png) · [11 只接触](preview_fixed_rear_eleven_landed.png) · [两侧浅水涟漪](preview_fixed_rear_water_ripples.png) · [全队落脚](preview_fixed_rear_all_landed.png) · [休整](preview_fixed_rear_rest.png) · [技术顶视](preview_top_landing_basin.png)
- 对照 [涟漪关闭](preview_comparison_water_ripples_disabled.png) · [落羽启用](preview_fixed_rear_feather_motes.png) · [落羽关闭](preview_comparison_feather_disabled.png)
- GLB 回导 [全队落脚](roundtrip_fixed_rear.png) · [浅水着陆](roundtrip_water_contact.png) · [回导涟漪关闭](roundtrip_comparison_water_ripples_disabled.png) · [休整](roundtrip_fixed_rear_rest.png) · [技术顶视](roundtrip_top.png)

## 组装和运行时接口

`S6 | Approach, landing and rest` 场景打开即可查看 12 个独立载体、ANM-007 的 `Land_Mudflat` / `Land_ShallowWater` 和 ANM-008 的 `Rest_Idle`。ENV-017 的原可编辑布局、散布及网格保存在独立场景。组装导出场景平移 ENV-017，保留三层地面、水面与芦苇及其源贴图，在两处水内把床底抬至约 −0.221 BU，并清理 S5 接缝附近芦苇。10 只停在泥滩，第 10、12 只停在浅水。各浅水足底贴在可见水面，水床低约 0.041 BU。FX-006 沿原水域覆盖和世界平面 UV 混合微纹，在两次着水点独立触发 1.8 秒涟漪。FX-013 的 `enabled` 属性可切换落羽，预览在全队均开始落脚后触发。

入口 `S6_Entry` 为 `(0,0,0)`，朝 +Y，X ∈ [−12,+12] BU 为干地通行带，地面 Z = 0，水位基准 Z = −0.18 BU。终点 `S6_Terminal` 为 `(0,21,0)`。GLB 含 3 个静态网格和 15 个锚点。导出轴从 Blender `(x,y,z)` 转为 `(x,z,-y)`。静态可接入场景与雁实例、动作和特效按布局文件分配。引擎负责碰撞、目标区、动态槽位、接触触发、全队落脚结算、锁输入及重试。

按 CHR-001 的 0.9900 BU = 27.5 游戏单位，固定相机复现 Swift 的 180 单位距离、0.48 rad 俯仰、50° 垂直视野及注视高度 6。eye 和 target 随领队载体加同一个抬升量，抬升量为领队根高度减 8 游戏单位。播放全程使用这架相机。技术顶视用于验收槽位。7.5 秒审阅短片使用 852 × 393 源帧，H.264 底部补 1 像素，共 90 帧，无音轨。约 20 秒为规格中的玩法目标。

## 独立回验

后台第二进程重开交付母版，在空场景导入交付 GLB 和四项动作与特效依赖的 GLB。比较母版与回导的锚点、网格、透明混合、贴图哈希、动作包围盒、接合带及落脚波纹。FFmpeg 完整解码短片。

- 接缝地面 1,067 个探针高程误差 0 BU，接缝带无芦苇或水面命中。九张嵌入贴图字节与 ENV-017 一致。
- 第 151、211、221 帧在候选区内分别有 1、11、12 只足底接触。每轮 194 帧，12,804 次同帧鸟对测试。两脚最大接触差小于 0.000001 BU，最小鸟对包围盒间隔 0.220 BU。两处浅水脚下的水深约 0.041 BU。两处涟漪以各自接触点为中心，非微弱透光区域的最大扩散采样均留在水域。
- 全队休整验收中，固定横屏最窄雁宽 30.26 px，离裁边至少 78.56 px，雁体投影相互覆盖最高 4.09%，芦苇相机遮挡 0 命中。母版与同一交付 GLB 和动作 GLB 回导重新组装的包围盒最大差约 0.000002 BU。
- 同机位开关对照以 RGB 通道至少变化 3/255 为阈值，浅水涟漪在母版与回导分别影响 301 和 301 个像素。落羽开关影响 208 个像素，关闭后可见卡片数为 0。
- 对照设计红线，新增交付内容为终场空间、角色动作和水纹/落羽审阅。已有 iPhone 18 Pro（iOS 27.2）灰盒构建和 340 项测试作为基线。

## 复跑

从本目录运行 Blender 5.2.2 LTS，PATH 需有 ffmpeg 和 ffprobe。每条命令使用独立空目录。

```sh
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S6_generate.py -- /tmp/ft-s6-build
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S6_generate.py -- /tmp/ft-s6-verify --verify "$PWD"
```

## 待验及登记

- 待负责人复核暖光、芦苇构图、两种落脚节奏和粒子强度。待 App 联验 S5 流送、碰撞、动态槽位及坡岸水位、连续触地事件、透明层排序。待在 App 验证只有领队或 11/12 时继续等候、12/12 时才结算、结算锁输入及重试重置。USDZ、RealityKit / App 接入和 iPhone / iPad 真机待验。
- [素材索引](../../../../../docs/asset-index.json)待登记母版、GLB、布局、预览及候选状态。
- [候选素材台账](../../../../../docs/asset-ledger.md)与[运行时素材台账](../../../../../../docs/references/asset-ledger.md)待登记 ENV-017 的继承贴图、几何改动、动作与效果版本、离线证据及运行时待验。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json)第 48 项和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md)待登记交付、离线回验及运行时后续。
