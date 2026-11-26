# ENV-017｜终点芦苇落脚盆地

**v001 · needs_review · Blender 5.2.2 LTS**。S6，P0，任务清单执行顺序第 27 项，建模规格书第 13 页。直接依赖 ENV-002、ENV-003、ENV-005、ANM-007。取景继续使用项目现有 27.5 游戏单位 / 0.9900 BU 的审阅换算。

[可编辑母版](ENV-017_landing_basin.blend) · [LandingBasin GLB](ENV-017_LandingBasin.glb) · [材质与文件清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与回导脚本](ENV-017_generate.py)

## 布局与导出

- 地面占地 **40 × 40 BU**，中心弯形盆地 **20 × 20 BU**，外圈复用 ENV-002 的 Flat、StartMudflat 和 RestPatch。沿用 10 BU 陆接格、0.625 BU 共边间距、陆边 Z = 0 BU、水平水位 Z = −0.18 BU；主盆地中心位于 `(0,5,0)`。模块枢轴在场景 `(0,0,0)`，Blender 前向 +Y，GLB 为 `(x,z,-y)`。浅水两侧围合干泥舌，中央进场和等待区留空。边缘芦苇的自然悬叶可超出地面占地框约 0.20 BU。
- `Editable layout and live reeds` 保留独立地形、池面、岸线权重、ENV-005 Geometry Nodes 和芦苇原型。换种子或调密度后重新生成冻结层。灰盒场景、冻结导出场景以及带动画的审阅场景可在场景切换器单独打开。
- `LandingBasin` GLB 带 `LandingBasin_Ground`（8,192 三角面）、`LandingBasin_Water`（824）和 `LandingBasin_Reeds`（33,686）。水岸用 ENV-003 的贴合池，中心另烘焙一张 512 × 512 的床深 RGBA，引用 MAT-004 的浅水贴图。地表、芦苇与透明水的色彩源逐项列于清单，导出自带嵌入图像。暖金斜光、弱风芦苇、微波节点和 12 只雁位于 Blender 审阅场景。游戏侧水纹与补给、触发、碰撞另由运行时实现和验证。

## 审阅证据

[灰盒路面与落点](graybox_fixed_rear_final.png) · [灰盒顶视](graybox_top_final.png) · [进场](preview_fixed_rear_approach.png) · [领队等候](preview_leader_wait.png) · [12 只落脚](preview_fixed_rear_final.png) · [材质顶视](preview_top_final.png) · [休整关键帧](preview_rest_idle.png) · [GLB 回导后上方](roundtrip_fixed_rear_final.png)

[降落与休整视频](preview_landing_motion.mp4) · [视频复现脚本](ENV-017_motion_preview.py)

现行 `ThirdPersonRig.swift` 提供固定后上方相机的距离参数 180、俯仰 0.48 rad、纵向 FOV 50°、注视高度 6。沿 +Y 取景，固定参数、跟随领队 XY。动画段按审阅载体的高度变化调节相机。原始横屏 852 × 393，视频用 52 个 Blender 渲染帧编码为 5 秒 H.264，编码下边补 1 像素，已解码 120 帧。

- **陆边** 27 道拼缝逐顶点对照，最大位置和高度差 **0 BU**、周期 UV 差 **0**、法线差 **0.00484°**。位置与 UV 容差 0.00001，法线容差 0.03°。
- **水岸与进场** 合计水面 **103.11 BU²**，水线 Z = −0.18 BU，源件与回导件水面越入干地最大 **0.00000065 BU**（容差 0.000001 BU）。255 个芦苇实例通过种子复现，冻结网格到受保护矩形的最短坐标轴间隔 **0.650 BU**。三条航线各测躯干轴与两侧翼尖位置，共 909 条竖向探针；芦苇零命中，CHR-001 审阅模型的最低静态净空 **0.183 BU**。
- **动态落脚** 使用 ANM-007 `Land_Mudflat` 和 ANM-008 `Rest_Idle`。原尺寸 12 只错开 5 帧，相继进入干燥目标框 `X [−3.35,3.35] × Y [−3.65,4.97] BU`。审阅源按 48 fps 检查前 136 帧的落脚与后 72 帧的衔接，13,728 个同帧鸟对包围盒均分离。最近轴向间距 **0.327 BU**。落脚后逐只逐脚最近接触差最大 **0.00000003 BU**（容差 0.009 BU）。最低网格探针没有穿地（容差 0.003 BU）；着陆段抽测点无芦苇命中。领队定稳后等待 **1.146 s**；第 136 帧 12/12 入框。横屏原尺寸下最近裁边裕量 **79.16 px**，最窄雁宽 **30.32 px**，由逐雁网格投影得到的同伴遮挡上界 **9.85%**。
- **回导** Blender 独立进程重开交付母版并回导交付 GLB。复查根与子层、轴向及边界（容差 0.00001 BU）、枢轴、缩放、三角形、逐角 UV、角点法线（最大 **0.02471°**，容差 0.12°）、材质、透明模式、嵌入图像哈希、岸线底板与进场净空。回导重拼横屏带本地审阅雁作尺度对照。

## 复现

从本目录用 Blender 5.2.2 LTS 与 ffmpeg 执行。每行使用独立空目录，脚本读取相邻候选素材和已有复用脚本。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-017_generate.py -- /tmp/ft-env017-rebuild
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-017_generate.py -- /tmp/ft-env017-recheck --verify "$PWD"
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-017_motion_preview.py -- /tmp/ft-env017-motion
```

## 待验与待登记

- 负责人复核暖光、芦苇密度和小屏阅读。S6 全员进目标区才完成、领队等候的实际状态、路径与碰撞、重试及 `Rest_Idle` 接续、正式微波 FX 和水面排序、USDZ / RealityKit 接入及 iPhone / iPad 真机待验。App 基线沿用已有 iOS 27.2 构建及 340 项测试记录。
- `Assets/docs/asset-index.json` 待登记相对路径、母版、GLB、材质清单、预览与 QA。
- `Assets/docs/asset-ledger.md` 和 `docs/references/asset-ledger.md` 待登记项目内来源、MAT-003 和 MAT-004 复用、床深贴图生成方式、内嵌映射及候选状态。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 和 `plans/active/goose-preview-model-cleanup.md` 待记录候选、审阅证据和后续运行时验收。

本轮已对照设计红线。按清单后续为 ENV-018｜云层与远景雾带卡片。
