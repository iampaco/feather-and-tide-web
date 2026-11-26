# FX-006 水面浅波与降落涟漪

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 15 页，资源任务清单第 41 项，P0，适用 S0、S2、S3、S4、S6。

[Blender 母版](FX-006_ripples.blend) · [GLB](FX-006_ripples.glb) · [运行时控制映射](ripple_controls.json) · [资产清单](asset_manifest.json) · [回验](qa.json) · [生成与回验脚本](FX-006_generate.py)

[灰盒后上方](graybox_fixed_rear.png) · [灰盒顶视](graybox_top.png) · [常驻水纹](preview_idle_fixed_rear.png) · [12 只雁同时落水](preview_landing_fixed_rear.png) · [材质顶视](preview_landing_top.png) · [涟漪近景](preview_landing_detail.png) · [固定机位无声短片](preview_fixed_rear.mp4)

[GLB 回导对照](roundtrip_landing_fixed_rear.png) · [同机位无落水波纹](comparison_without_landing.png) · [便于核对的常驻水纹](roundtrip_idle_drift.png) · [同机位无常驻水纹](comparison_without_idle.png)

## 母版与引擎接口

- `Ripple_Idle` 的 512 × 512 RGBA 贴图双轴平铺，样件每格 3.2 × 2.4 BU，U 轴 16 秒漂移一格。共用世界坐标原点以跨越相邻水面。混色强度默认 2.4，可在母版调节。审阅材质在 MAT-004 同一水面着色通道混合水纹颜色，沿用岸线不透明度。
- `Ripple_Landing` 的 512 × 512 RGBA 贴图有两道柔边水纹，单张网格宽 2.20 BU。用实际落水接触点定位，以雁 ID 单独触发，读取事件年龄和入水强度。关键曲线由缩放与不透明度组成，持续 1.8 秒，到时回收实例。引擎应将水体覆盖遮罩乘入最终不透明度。
- 母版的 **Water landing review** 场景可编辑水面节点 **Continuous UV drift**、每只雁的着水点和落水网格的 Graph Editor 曲线。**Portable cards** 场景对应两个 GLB 节点。每个节点为 2 三角面、单位缩放、原点在本地水面中心，材质为 glTF BLEND。GLB 保存静态网格和 RGBA，漂移与落水触发由引擎按映射实现。
- Blender XY 为水面，+Z 朝上，GLB 轴向为 `(x,z,-y)`。复现 `ThirdPersonRig` 的 180 游戏单位、0.48 rad、纵向视角 50°，注视基高 6，领队载体平移时相机保持相对位姿。沿用 CHR-001 实际比例，喙尾约 0.9900 BU 对应 27.5 游戏单位。审阅源帧为 852 × 393，H.264 底部填充一行。

## 依赖与回验

使用 MAT-004/v001 的实际母版。母版 SHA-256 与其旧清单不一致，清单记录两者。三种水材质均在后台 Blender 成功追加，内嵌 PNG 与原 PNG 及已发布 GLB 逐字节一致。审阅使用 `Water_Shallow`，同时追加 ANM-007/v001 浅水落脚审阅载体用于制作 12 雁同时接触的极端样本。

在交付目录重开母版、回导 GLB，复查几何、法线、UV、两种贴图和透明材质。12 个接触点和波心均在固定画幅内，独立实例共享同一网格。逐半帧检查落脚触发、同步扩散及消散。固定机位 5 秒样片通过全部 80 帧解码。177 个半帧中，12 个波心与足部接触点的最大横向偏差低于 0.000001 BU。同机位对照中，常驻水纹有 1,604 个像素至少变化 3/255，落水波纹有 1,523 个像素至少变化 4/255。离线审阅证据、具体计数和哈希见 [QA](qa.json) 和 [清单](asset_manifest.json)。

## 复跑

从本目录运行，输出到两个独立空目录。要求 Blender 5.2.2 LTS、ffmpeg 和 ffprobe。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-006_generate.py -- /tmp/ft-fx006-build
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-006_generate.py -- /tmp/ft-fx006-verify --verify "$PWD"
```

## 待验与登记

候选待负责人美术复核。USDZ、App 接入、运行时 Land 事件、真实岸线覆盖、透明排序和 12 实例并发性能、iPhone／iPad 真机均待验证。工程状态引用 active 计划记录的 iPhone 18 Pro／iOS 27.2 灰盒构建与 340 项测试基线。

对照红线清单，交付为水面视觉效果与离线审阅，无新增 UI、文案或音效。共用文件待登记：`Assets/docs/asset-index.json`、`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md`、`完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 第 41 项、`plans/active/goose-preview-model-cleanup.md`。登记状态为 `needs_review`，附依赖哈希差异、候选文件与验证证据。
