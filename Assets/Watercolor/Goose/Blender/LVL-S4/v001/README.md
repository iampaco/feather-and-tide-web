# LVL-S4 弧形风电场与保护湿地

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 18 页，任务清单执行顺序第 46 项，P0 / S4。变体 `S4_WindFarm`。

[可编辑 Blender 母版](LVL-S4_S4_WindFarm.blend) · [组装 GLB](LVL-S4_S4_WindFarm.glb) · [坐标、落脚槽和引擎接口](s4_layout.json) · [资产清单与依赖](asset_manifest.json) · [QA](qa.json) · [复跑脚本](LVL-S4_generate.py)

## 审阅文件

- 灰盒：[进场](graybox_fixed_rear.png) · [落脚](graybox_wetland_landing.png) · [航道与完整 V 形顶视](graybox_top.png)
- 材质：[进场](preview_fixed_rear_approach.png) · [航道与完整 V 形顶视](preview_full_v_top.png) · [12 雁落脚](preview_wetland_landing.png) · [出场](preview_fixed_rear_egress.png)
- 效果：[接近暖金边](preview_warning_edge.png) · [同机位未触发对照](comparison_warning_idle.png) · [灰紫接触波](preview_contact_wave.png)
- 短片：[6 秒外侧绕行](preview_fixed_rear_bypass.mp4) · [5 秒静音预警测试](preview_fixed_rear_silent_warning.mp4)
- 独立 GLB 回导：[进场](roundtrip_fixed_rear_approach.png) · [顶视](roundtrip_full_v_top.png) · [落脚](roundtrip_wetland_landing.png) · [暖金边](roundtrip_warning_edge.png) · [灰紫接触波](roundtrip_contact_wave.png)

## 母版与导出接口

四组可独立选择的组装源来自 STR-002 的七台错相风机、ENV-016 的三层保护湿地、FX-010 连续扫掠面和 FX-011 两条形态动画。保留既有水彩纹理和材质。源母版的局部几何及节点编辑路径见各依赖的 README。组装原点为保护湿地基准 `(0, 0, 0)`。以 ENV-001 的 Flat 增补 22 个可复用模块，作为进出场地缝和风机视觉的承托层。导出含场景五个可独立管理的子根，19 张来源 PNG 原样保留，另有 1 张 ENV-001 草滩贴图。审阅雁、相机、方向记号及最外围审阅地面仅随母版。

Blender 地面为 XY，+Y 朝前、+Z 朝上。GLB 为 `(x,z,-y)`。审阅取景按 CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位，折算 0.036 BU / 游戏单位。航道沿 X = 2 BU，南北全程 Y = −28 … 35 BU，经过 Y = −14 和 22 两道湿地通行门。技术顶视可看到整个 V 形。固定后上方机位采用 Swift 原有的 180 游戏单位、0.48 rad 俯仰参数、50° 纵向视场以及抬高量以上 6 游戏单位的注视点。小段进场使用现有航向和飞行高度接口取景，镜头距离和俯仰固定，随行时部分同伴出画。落脚采用 ANM-007 的收翼站姿作为独立落脚检查点。技术顶视不参与随行播放。

GLB 的 `Farm_Rotor_Loop` 与 `RotorPressureLoop` 均为 9 秒，分别驱动七台叶轮和七片风压图层。两个独立的 `ApproachCue` / `BoundaryContact` 分别驱动暖金亮边和灰紫波的形态权重。正片绕行与静音预警使用同一套固定机位。预警短片单独让一只 CHR-001 跟随审阅轨迹跨越 T01 候选边界。以 2.4 BU/s 前进时，第 12 帧接近、第 84 帧首次进入候选扫掠区，间隔 3 秒。暖金边和接触波分别只播放一次。短片用 852 × 393 源帧，H.264 编码在底部补一行；绕行 48 帧，跨界 40 帧，均无音轨。

游戏接入由 Zone 提供最终边界、接近及跨界事件、FX-011 接触位置和重置、保护区补给及离场规则。当前 Swift 灰盒仍对应出生点偏移 `(920,−10)` 的 78 单位单圆，以及中心 `(920,−78)`、尺寸 `200 × 52` 的保护矩形。离线采用同一布局提案计算七圆并集、扫掠视觉接合、航道与预警测试。约 50 秒是关卡规格的玩法目标，短片是审阅切片。

## 测量与回验

| 离线测量 | Blender 母版与 GLB 回导 |
| --- | ---: |
| 含翼尖完整 V 形 / 外侧航道最窄宽度 | 15.856 / 34.092 BU |
| 最窄通行宽度和整队宽度之比 | 2.150 |
| 整队全程到连续扫掠区最近净距 | 6.193 BU |
| 12 雁落脚包围盒到连续扫掠区最近净距 | 15.046 BU |
| 离场时队尾全身越过湿地北接缝 | 1.405 BU |
| 站姿足底最大接点误差 / 容差 | 0.008419 / 0.009 BU |
| 扫掠并集闭合轮廓 / 连接处 | 1 / 6 |
| BVH 边界及网格探针 | 35,988；与解析圆并集判定差异 0 |
| 预警带半帧采样 / 首次解析接触 | 241 次 / 第 84 帧 |

从交付目录用另一个 Blender 后台进程重新打开母版，再清空场景导入 GLB，复核了关键净距、六道实交付地缝、叶轮与风压相位、预警动画与边界、材质的透明混合及源 PNG 字节。两个视频已全帧解码并验证无音轨。源和回导的逐项证据见 QA。已对照项目红线清单。

PATH 需包含 ffmpeg 和 ffprobe。两个输出目录都应为空。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python LVL-S4_generate.py -- /tmp/ft-s4-build
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python LVL-S4_generate.py -- /tmp/ft-s4-verify --verify "$PWD"
```

## 待验与共用登记

- 待负责人复核 S4 美术，待游戏 Zone 联验正式边界内外触发、按实际速度给出预警、重复接近重置、动态队形、触地、补给、离地与约 50 秒流程。USDZ / RealityKit / App 接入及 iPhone、iPad 真机待验。本轮引用计划已有的 iOS 27.2 灰盒构建与 340 项测试基线。
- `Assets/docs/asset-index.json` 待登记母版、GLB、布局与预览。两份台账 `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 待登记组装来源、继承贴图与候选状态。任务 JSON `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 第 46 项和 `plans/active/goose-preview-model-cleanup.md` 待登记离线回验结果及运行时待验项。
