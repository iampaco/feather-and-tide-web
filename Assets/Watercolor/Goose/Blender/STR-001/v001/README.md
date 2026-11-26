# STR-001 风力发电机单体

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 13 页，制作清单第 29 项，P0 / S4，直接依赖 MAT-001。

[可编辑母版](STR-001_Main_Turbine.blend) · [GLB](STR-001_Main_Turbine.glb) · [清单及贴图映射](asset_manifest.json) · [QA](qa.json) · [生成与回验脚本](STR-001_generate.py)

[灰盒](graybox_fixed_rear.png) · [材质](preview_fixed_rear.png) · [另一相位](preview_fixed_rear_phase.png) · [模型细节](preview_detail.png) · [旋转短片](preview_rotor_loop.mp4) · [独立 GLB 回导](roundtrip_fixed_rear.png)

## 几何、材质与动画

- 根节点 `Main_Turbine` 的基座原点为 Blender `(0,0,0)`，基座直径 1.020 BU。塔杆、机舱、基础、舱门、轮毂和三片叶片均可单独编辑。塔身顶 2.410 BU，叶轮最高 4.330 BU，叶尖最低离地 0.570 BU。叶轮在面内扫过直径 3.760 BU。
- 叶轮枢轴 `(0,-0.46,2.45)` BU 位于轮毂轴心，正面朝 Blender −Y。Blender 局部 +Y 正转，从正面朝 +Y 看为顺时针，映射到 GLB 局部 −Z。可选绕垂直轴调整朝向、等比缩放和初相。STR-002 使用 −12° 至 +13°、0.96–1.00 倍和 14° 至 238° 初相。改尺度后须重测叶尖包络。
- `Rotor_Constant_Loop` 名义 40°/s，9 秒一周。母版有 Cycles 曲线重复，GLB 含 0–9 秒 LINEAR 旋转轨，播放端可循环。单片叶端有低饱和苔金索引条。12 fps 样片每帧前进约 3.33°，相邻等形叶片的反转混叠阈值为 60°/帧。全周期实测画面顺时针步进 3.00–3.70°。
- 沿用 MAT-001 `SoftStone` 节点和纸纹，以五组低饱和色阶生成并内嵌 512 × 512 PNG。来源、色板和 SHA-256 见清单。全相位叶尖在地面的最大投影半径约 1.925 BU，距 2.808 BU 审阅圆边 0.883 BU。该圆采用旧灰盒 78 游戏单位的半径，按基座中心绘制。正式边界由 Zone 决定。

## 回验与复跑

独立 Blender 后台从本目录重开母版、回导 GLB，核对 10 个节点、2,656 三角面、局部变换、UV、材质绑定和 5 张内嵌 PNG。另采样 361 个几何相位和 433 个半帧动画点，复核周期、转向、首尾、枢轴与地面包络。固定后上方取景距离为 180 游戏单位、俯仰 0.48 rad、纵向视角 50°、注视基高 6，按游戏允许的 +48 单位飞行高度取景，保住全周期叶尖至少 8.82 px 画幅余量。CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位。视频 H.264 解码通过，源帧 852 × 393，编码底部补一行，108 帧、9 秒。斜视图用于查造型。

从本目录运行，使用两个不同的空输出目录和 PATH 中的 ffmpeg / ffprobe。

```sh
blender -b --factory-startup -t 6 --python-exit-code 1 \
  --python STR-001_generate.py -- /tmp/ft-str001-build
blender -b --factory-startup -t 5 --python-exit-code 1 \
  --python STR-001_generate.py -- /tmp/ft-str001-verify --verify "$PWD"
```

## 待验与待登记

- 待负责人复核造型、暖灰色阶和运动辨识。待正式 FX-010 与 Zone 做边界、触发和预警联验，待 USDZ、RealityKit / App 接入与 iPhone / iPad 真机验证。本轮引用 active 计划已有 iOS 27.2 构建和 340 项测试基线。已对照设计红线。
- `Assets/docs/asset-index.json` 待登记项目相对路径、版本、母版、GLB、贴图与 QA。
- `Assets/docs/asset-ledger.md` 和 `docs/references/asset-ledger.md` 待登记程序建模、本项目 MAT-001 派生纸纹、候选状态和接入路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 第 29 项与 `plans/active/goose-preview-model-cleanup.md` 待回写候选和联验信息。
