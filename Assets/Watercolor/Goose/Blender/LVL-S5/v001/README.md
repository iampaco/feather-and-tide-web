# LVL-S5｜逆风消耗段

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 18 页，任务清单执行顺序第 47 项，P0 / S5，变体 `S5_Headwind`。

[可编辑母版](LVL-S5_S5_Headwind.blend) · [组装 GLB](LVL-S5_S5_Headwind.glb) · [布局与运行时输入](s5_layout.json) · [资产清单与 SHA-256](asset_manifest.json) · [独立 QA](qa.json) · [可复跑脚本](LVL-S5_generate.py)

- [灰盒横屏](graybox_fixed_rear.png) · [灰盒顶视](graybox_top.png)
- [固定后上方短片](preview_fixed_rear.mp4) · [背风区出现](preview_fixed_rear_shelter.png) · [转入安全支路](preview_fixed_rear_detour.png) · [通往 S6](preview_fixed_rear_exit.png) · [技术顶视](preview_top.png)
- [GLB 独立回导横屏](roundtrip_fixed_rear.png) · [GLB 独立回导顶视](roundtrip_top.png)

## 组装与接缝

`S5_Headwind` 为原点，不带缩放。Blender 的 +Z 向上、+Y 朝前，GLB 坐标为 `(x,z,-y)`。审阅换算 0.9900 BU = 27.5 游戏单位，用 0.036 BU / 游戏单位重现项目固定机位。

两条门位于 `S5_Entry (0,0,0)` 和 `S5_Exit (0,64,0)`，都朝 +Y。地面在两处门位截断，铺满 44 BU 宽，中心 24 BU 按共用接口保持 Z = 0。S4 的实际北缘 `(2,45,0)` 接 S5 入口，S5 出口接 S6 入口 `(0,0,0)`，按门位平移整段即可。实际源水面 Z = −0.18 BU，内收至 Y ≈ 7.91–56.09 BU。两端没有跨门水面。出口芦苇疏开，审阅场景里的 ENV-017 盆地以 +84 BU 摆放，作为继续前进的取景参照。该盆地、入口审阅地毯、远景 C、相机和审阅雁与主段 GLB 分开。

湿地谷底直接复用 ENV-007 的 Straight → OpenBank → OpenBank → Bend。床层与水面分别保留，南北使用相同 R 剖面逐步收浅，相邻陆地复用 ENV-001 Flat 的贴图。左右 ENV-009 A/B 低山收束，5 个内部水床拼接断面按实装测量。少量芦苇为 Blender 原创低模，四张半透明着色图由生成脚本制作，包括背风岸色、支路笔触、淡绿微光和逆向云影。贴图与依赖哈希均见清单。安全岸锚点为 `S5_SafeRest (4.55,33.4,0)`，支持从主航路转入后向前归航，两条走法都连接 S6。约 30% 的低能量标记为玩法样例，由运行时判定。

## 风场和固定机位

48 条短带共用 FX-003 的 72 三角面网格、UV 与贴图，分布在 12 条侧带。在 Blender 绕 +Z 转 π，局部 +Y 的下游 U=1 端朝世界 −Y。审阅位移 2.55 BU/s，约 8.4 BU 局部相位循环，云影也朝 −Y。母版中可改风带参数和关键帧。运行时导出包含带编号的静态实例和输入元数据，场景侧按 FX-003 的方向、速度、时钟、每条相位和透明度输入驱动。GLB 的亮度与运行时相位仍待联验。

短片沿同一架第三人称相机随行，使用 Swift 180 游戏单位、0.48 rad、50° 纵向 FOV、注视点高度 6。领队保持相对机位抬升量以上 8 游戏单位，其余雁 6，ANM-006 替用实际网格姿态，审阅轨迹演示整队通过安全支路。共 50 个 Blender 采样帧，852 × 393。转成 H.264 时补一行兼容 YUV420，时长 8.33 秒，编码 24 fps。约 40 秒是完整关卡规格时长。

## 离线回验

从交付目录重开母版、清空场景并回导 GLB。实测 1,164 个门内取样无高差、无跨门水面及跨线地板，回导锚点位置与朝向按项目尺度一致。725 个补给岸采样均落在干燥平地。低能量样例到安全岸直线相距 6.470 BU。沿前进路线及可归队支路分别采样 483 和 1,083 次，最低净空见 [QA](qa.json)。固定后上方三组关键视点都能看到对应的安静岸和 S6 出口，地形和风带未截断对目标的中心视线。母版 197 帧实测风速从 −2.55002 到 −2.54997 BU/s，关键帧回读及 GLB 的轴向、贴图字节和透明材质都复测。FFmpeg 完整解码 200 帧，视频无音轨。

## 复现与待验

Blender 5.2.2 LTS。PATH 需包含 ffmpeg 和 ffprobe。命令从本目录执行，每次使用新的空输出目录。完整构建目录中的 `build.json` 是源阶段 QA。交付的 `qa.json` 包含源阶段及独立回验。

```sh
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S5_generate.py -- /tmp/ft-s5-build
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python LVL-S5_generate.py -- /tmp/ft-s5-recheck --verify "$PWD"
```

- 待美术复核风纹、补给岸与过渡。碰撞、补给触发与恢复、低能耗反馈、结阵倍率、通往 S6 和约 40 秒流程待运行时联验。USDZ、RealityKit / App、iPhone / iPad 均待验。本轮引用 iOS 27.2 iPhone 18 Pro 模拟器已有构建和 340 项测试基线。本候选已对照项目红线清单。
- `Assets/docs/asset-index.json` 待登记母版、GLB、布局、清单与预览。 `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 待登记原创几何、程序贴图、源 GLB 贴图继承、权限依据和接入状态。 `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待记录 v001 候选及各项离线证据和运行时待验。
