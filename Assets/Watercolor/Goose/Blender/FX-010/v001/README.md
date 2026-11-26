# FX-010 风机扫掠区可视化轮廓

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 16 页，制作清单第 38 项，P0 / S4。变体 `RotorFootprint`。几何使用已通过美术审阅的 STR-002/v001 布局，动态与 STR-001/v001 的叶轮周期对齐。

[可编辑 Blender 母版](FX-010_RotorFootprint.blend) · [最终 GLB](FX-010_RotorFootprint.glb) · [资产清单及贴图来源](asset_manifest.json) · [QA](qa.json) · [可复跑脚本](FX-010_generate.py)

[灰盒固定后上方](graybox_fixed_rear.png) · [灰盒顶视](graybox_top.png) · [材质顶视](preview_top.png) · [连续边界细节](preview_boundary_detail.png) · 雾层 [默认](preview_fog_default.png) / [减弱](preview_fog_reduced.png) / [关闭](preview_fog_off.png) · [固定后上方短片](preview_fixed_rear.mp4) · [回导重拼](roundtrip_fixed_rear.png) · [回导顶视](roundtrip_top.png)

## 模型与接口

- 生成器直接读取 STR-002 的 `farm_layout.json`，以七个风机基座中心的 2.808 BU 圆做解析并集。外边为一圈闭合轮廓，内部为单张连续三角面，灰紫暗边和半透明纸纹共用贴图。表面高于平地 0.021 BU。六个相邻接合处没有重复圆面叠加，最小轴向重叠 1.322 BU。最终 GLB 仅含扫掠表面和内部风压纹理节点，母版另含对照的阵列、湿地、雁群、雾层、镜头与审阅航向标记。
- `SweepSurface` 是固定表面。七个 `Pressure_T01` 至 `Pressure_T07` 在 Z = 0.034 BU 复用同一组羽化纹理网格。初相读取 STR-002，跟随 STR-001 的 9 秒周期缓移。GLB `RotorPressureLoop` 只动画化七路风压节点的平移，播放时与阵列在同一时刻起播并各自循环。
- 场景原点与 STR-002 和 ENV-016 对齐，Blender `(x,y,z)` 到 GLB `(x,z,-y)`。现行灰盒为出生点加 `(920,-10)` 的单个领队地面圆，距离 ≤ 78 游戏单位时在圈内，跨入的首帧产生提示。T04 对齐该圆。候选半径使用每游戏单位 0.036 BU 换算，七个圆及其大小由上游布局给出。正式 Collider / Zone 是运行时几何和触发的依据。
- 两张直通 Alpha PNG 内嵌在 GLB，并另交原图。地面色阶使用 MAT-001 SoftStone 纸纹派生，风压纹理由生成脚本绘制。GLB 两种材质均为 BLEND。导出器提示颜色与 Alpha 共用采样器，回导内嵌贴图和同机位画面均已核对。

## 验证与复跑

独立 Blender 进程从交付目录重开母版与 GLB，核对 9 个节点、2 个网格、两张内嵌 PNG 的 SHA-256、UV、材质、局部变换和法线。静态扫掠面为 2,029 三角面，边界有 2,031 点，边界弦中点最大误差 0.000061 BU。共 35,988 个边界及内部／外部探针，在 0.005 BU 容差下均符合解析并集。每路风压采样 433 个半帧，首尾差 0 BU。任意相位下距本台扫掠边至少 1.271 BU。

使用真实 STR-002 和 ENV-016 GLB 重拼。最窄净宽 34.092 BU，含翼尖的 12 只 V 形宽 15.856 BU，比值 2.150。整队轨迹距扫掠至少 6.193 BU，12 只落脚包围盒距扫掠至少 15.046 BU。回导复核的四项距离与源样段一致。

三档各检测 11887, 11887, 11887 条可见目标视线，雾 Alpha 最大值分别为 0.0, 0.0, 0.0。默认档与关闭本效果的同机位对照，339 个在画面内的边界采样点局部 RGB 差值中位数为 33.0/255。六处接合中心可见 6 处，可见接合中心最小差值为 5.0/255。源画幅 852 × 393，H.264 编码底部补一行，48 帧、6 秒，已全帧解码。

固定后上方镜头使用现行距离 180 游戏单位、俯仰 0.48 rad、垂直视角 50°、注视基高 6。审阅比例由 CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位得出。远景静帧沿用 +48 游戏单位合法飞行高度和朝向阵列的 0.28 rad 偏航。短片沿 ENV-016 的 +Y 航路，后排雁与风机随跟随镜头移出画幅，完整队形和边界见技术顶视。

从本目录使用不同的空输出目录，PATH 需包含 ffmpeg 和 ffprobe。

```sh
blender -b --factory-startup -t 7 --python-exit-code 1 \
  --python FX-010_generate.py -- /tmp/ft-fx010-build
blender -b --factory-startup -t 6 --python-exit-code 1 \
  --python FX-010_generate.py -- /tmp/ft-fx010-verify --verify "$PWD"
```

## 待验与登记

- 待负责人美术审阅。正式 Zone 形状、轮廓外无触发、跨界触发、与 FX-011 联验约 3 秒预警、运行时透明排序、USDZ / RealityKit / App 接入、iPhone / iPad 真机仍待验证。本轮复用 iOS 27.2 灰盒基线。
- 共用登记待回写 `Assets/docs/asset-index.json`、`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md`、`完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 的第 38 项和 `plans/active/goose-preview-model-cleanup.md`。一并登记负责人已审阅的 STR-001、STR-002 v001 及三者的运行时待验项。
