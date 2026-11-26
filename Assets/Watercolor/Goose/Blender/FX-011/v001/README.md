# FX-011 风机接近边缘预警

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 16 页，任务清单第 41 项，P0 / S4。变体 `TurbineWarn`，依赖 FX-010/v001。

[可编辑母版](FX-011_TurbineWarn.blend) · [最终 GLB](FX-011_TurbineWarn.glb) · [审阅摆位和时间线](warning_review.json) · [资产清单与贴图映射](asset_manifest.json) · [QA](qa.json) · [复跑脚本](FX-011_generate.py)

[灰盒固定机位](graybox_fixed_rear.png) · [灰盒顶视](graybox_top.png) · [亮边细节](preview_warning_detail.png) · [灰紫接触波](preview_contact.png) · [湿地与绕行顶视](preview_route_top.png) · [5 秒无声短片](preview_fixed_rear_silent.mp4) · [GLB 回导亮边](roundtrip_fixed_rear.png) · [GLB 回导接触波](roundtrip_contact.png)

三档雾层固定机位对照 [默认](preview_fog_default.png) / [减弱](preview_fog_reduced.png) / [关闭](preview_fog_off.png)。[同机位无预警对照](comparison_idle_default.png)。

## 模型和播放约定

- 两条带从 FX-010 同源的 STR-002 圆并集外轮廓取样。导出的样件定位在 T01 南侧接触点附近，锚点约为 `(19.200, −5.235)` BU。暖金边沿轮廓占 5.25 BU 弧长，最多向内展开 0.48 BU。灰紫波占 3.60 BU 弧长，随接触最多向内移动 0.50 BU。两个根下子节点可独立编辑。Blender 地面为 XY，导出到 GLB 为 `(x,z,−y)`。
- `ApproachCue` 由接近事件一次性播放，暖金边柔和展开后收束，时长 3.000 秒。轮廓本身仍由 FX-010 常驻显示。`BoundaryContact` 由边界接触事件一次性播放，灰紫风压波向内扩散并收束，时长 1.083 秒。两条 GLB 动画只改形态权重。首尾均收束到零面积。
- 本次采用 2.4 BU/s 的脚本审阅速度。时间线第 12 帧安排接近事件，第 84 帧解析轨迹首次进入候选扫掠区。两事件间隔正好 3.000 秒。游戏接入时，应由实际 Zone 触发、定位与控制复位，并按实际速度验证预警窗口。GLB 作为 T01 样件，`warning_review.json` 和生成器记录了从真实边界生成局部弧段的规则。
- 两张 512 × 128 RGBA 使用项目 MAT-001 的 SoftStone 纸纹派生。Blender 已打包，GLB 两材质均为 BLEND。最终 GLB 仅含提示视觉节点。运行时以游戏 Zone 为碰撞依据。

## 独立回验

- 在交付目录重开母版、回导 GLB，核对 3 个节点、2 个网格、UV、法线、枢轴、透明材质、内嵌 PNG 字节和两条动画的时长与目标。每段时间线采样 241 个半帧，两个动画各出现一个有效区间。亮边最大边界误差约 0.000061 BU，最大越界为 0 BU。
- 将 FX-011、FX-010、STR-002 与 ENV-016 的 GLB 重拼。完整 12 只雁的最窄航道仍为 34.092 BU，整队轨迹到扫掠边最近 6.193 BU，落脚包围盒最近 15.046 BU。脚本跨界短片使用单只领队展示提示，真实绕行全队见顶视。
- 固定镜头采用 180 游戏单位、俯仰 0.48 rad、纵向视角 50°、注视基高 6。采用 CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位和源码允许的 +48 飞行高度。ENV-018 默认／减弱／关闭三档各有 59 个预警顶点投影抽样，雾 Alpha 峰值均为 0。默认档与同机位无预警相比，546 像素的 RGB 最大通道差至少为 12/255。
- 无声 H.264 样片通过全部 40 帧解码，确认无音轨。Blender 源帧 852 × 393，编码底部补一行。已按红线清单审查。

从本目录使用 Blender 和不同的空输出目录。PATH 需包含 ffmpeg 与 ffprobe。

```sh
blender -b --factory-startup -t 8 --python-exit-code 1 \
  --python FX-011_generate.py -- /tmp/ft-fx011-build
blender -b --factory-startup -t 8 --python-exit-code 1 \
  --python FX-011_generate.py -- /tmp/ft-fx011-verify --verify "$PWD"
```

## 待验与登记

- 待负责人美术复核，待 LVL-S4 在真实 Zone 中联验触发一次、跨界反馈、离开与再次接近、扫掠外无碰撞及约 3 秒反应时间。USDZ、RealityKit 透明排序与形态动画、App 接入、小屏辨识与 iPhone／iPad 真机待验证。本轮引用计划已有 iOS 27.2 验证基线。
- 待回写 `Assets/docs/asset-index.json`、`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md`、`完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 第 41 项和 `plans/active/goose-preview-model-cleanup.md`。待登记候选、派生贴图、离线证据和运行时联验项。
