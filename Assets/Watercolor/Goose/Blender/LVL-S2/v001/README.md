# LVL-S2 山口与长湖双路线

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 17 页，执行顺序第 44 项，P0 / S2。变体 `S2_Fork`。

[可编辑母版](LVL-S2_S2_Fork.blend) · [组装 GLB](LVL-S2_S2_Fork.glb) · [锚点、摆位和运行时接口](s2_layout.json) · [资产清单](asset_manifest.json) · [独立回验](qa.json) · [复跑脚本](LVL-S2_generate.py)

## 审阅素材

- [入口灰盒](graybox_fixed_rear.png) · [同一入口材质](preview_checkpoint_A.png) · [双路线技术顶视](preview_both_routes_top.png)
- [短山口](preview_short_pass.png) · [长湖](preview_long_lake.png) · [补给滩进场](preview_lakeside_rest.png) · [汇合](preview_merge.png)
- [固定后上方短片](preview_fixed_rear.mp4) · [交付 GLB 回导入口](roundtrip_fixed_rear.png)

短片从同一检查点分别展示山口和长湖，两段各四秒。取景按 Swift `ThirdPersonRig.graybox` 的 180 游戏单位距离参数、0.48 rad 俯仰参数、50° 纵向视场及 +6 游戏单位注视高度。领队根部高为 8 游戏单位加审阅升降量，同一升降量用于相机眼位和注视点。首帧升降量为零。原画幅 852 × 393，H.264 底部补一行。顶视交会点和航线仅供技术审阅。实际短片的尾部同伴会随固定机位出画。

## 组装接口

- `S2_Entry` 与 `S2_Checkpoint_A` 在 Blender 本地 `(0,0,0)`，沿上一段 S1 检查点 A 对齐。两条路线在 `S2_JoinBeforeGate` `(0,69,0)` 汇合，再由 `S2_Merge` `(0,76,0)` 交接 S3。入口与出口一致朝 +Y。地面 +Z 向上，GLB 坐标为 `(x,z,-y)`，0.036 BU / 游戏单位。两个接口在 X = −12 至 +12 BU 的接缝各保留朝内 2 BU 的零高程干地。水面 Z = −0.18 BU，于段内收口。
- 环境使用已有候选。ENV-010 的山口草地 UV 加 `(0.35,0.5)` 与 ENV-008 草地相位同源，导入处分离山口、湖床和水面。移除 ENV-008 检查点前方延伸段与原占位补给模块的 512 个三角面，按 `(4,10,0)` 放入 ENV-015 的三层 `LakesideRest`，保留岸形和源贴图。补给滩为淡金细环和芦苇留白。导出的 `S2_Rest` 供游戏绑定实际补给区。
- `S2_WindField` 为空物体控制节点。组装选用 ENV-012 的三种有骨架树、FX-002 的 `CrosswindWarn` 和 `Gust`、ENV-018 的云梢。Blender 审阅关键帧示范同一水平下风向 `(-0.9798,0.2000)`、强度和时钟驱动树冠和风带，再让云带横移。GLB 保留中立树模型、骨架、各特效节点以及控制属性。运行时按同一风场提供 direction、strength、clockSeconds、windSpeedBUPerSecond 和 motionScale，激活山口预警及阵风。湖路线在审阅中使用安静风态。[FX-002 接口](../../FX-002/v001/runtime_mapping.json)
- CHR-001 的 12 只雁、镜头布光、技术路径点和段外审阅底板留在母版。承接碰撞、路径选择、能量、补给和检查点行为由游戏负责。新增几何为项目内原创的段内填地和淡金细环，图像来自依赖交付，15 张内嵌 PNG 均通过逐字节核对。

## 离线回验

独立后台进程从本目录重开母版、清空场景回导 GLB，并分别测量下表。路径样本使用中性雁的 1.6004 BU 翼展，山口和长湖均测中心线及两侧各 2 BU 的通行包络。补给滩按单雁支线测试。

| 项目 | 两次测试结果 |
| --- | --- |
| 同一入口固定取景视线 | 山口 13/13、湖面 9/9、补给滩 25/25 |
| 路线长度与最小净空 | 山口 82.92 BU / 0.1117 BU，长湖 106.94 BU / 0.1115 BU |
| 探针数量 | 山口 3,916、长湖 5,037、补给支线 408 |
| 补给滩接合 | 49 个公共边顶点高度差 0 BU |
| 入口和出口 | 各 388 个地面探针，最大高度误差 0.000002 BU，干地连续 |
| 树梢与风带 | 8 个骨架与 7 个效果实例共享风向，带状实例平移约 1.95 BU/s |
| 视频 | FFmpeg 完整解码 64 帧，8 秒，静音 |

横屏同框可看到左右两处入口与补给滩。固定后上方的地形尽头有原地块的低多边形坡面，技术顶视右侧的远岸拼接可见一条细线。待负责人评审地形观感及约 3 秒内的分岔可读性。

## 复跑

在本目录运行 Blender 5.2.2。使用不同空目录，PATH 需包含 ffmpeg 和 ffprobe。

```sh
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S2_generate.py -- --out /tmp/ft-s2-build --scratch /tmp/ft-s2-frames
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S2_generate.py -- --out /tmp/ft-s2-recheck --verify "$PWD"
```

## 待验与待登记

- 待运行时联验两路分岔、实际队形、碰撞、汇合、满能量过山口、长湖低能量反馈及补给、检查点 A 重试。约 60 秒为规格的玩法目标。USDZ、RealityKit／App、iPhone／iPad 真机待验。本轮引用 [iOS 27.2 模拟器与 340 项测试基线](../../../../../../plans/active/goose-preview-model-cleanup.md)。
- [共用素材索引](../../../../../docs/asset-index.json) 待登记母版、导出、预览、布局、候选状态。
- [候选素材台账](../../../../../docs/asset-ledger.md) 与 [正式素材台账](../../../../../../docs/references/asset-ledger.md) 待登记装配来源、翻用纹理、变换、候选状态及正式接入后记录。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json) 第 44 项和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md) 待登记 Blender 回验、交付链接与运行时待验项。已对照项目红线清单。
