# LVL-S1 顺风带与结阵

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 17 页，任务执行顺序第 43 项，P0 / S1。变体 `S1_Tailwind`。

[可编辑 Blender 母版](LVL-S1_S1_Tailwind.blend) · [组装 GLB](LVL-S1_S1_Tailwind.glb) · [摆位、接缝与运行时接口](s1_layout.json) · [资产清单与依赖映射](asset_manifest.json) · [独立回验](qa.json) · [复跑脚本](LVL-S1_generate.py)

## 审阅

- [固定第三人称短片](preview_fixed_rear.mp4)。10 秒静音，从松散飞行、2 秒结阵，到芦苇洲和岔口。约 40 秒是运行时关卡规格。源画幅 852 × 393，H.264 底部补 1 像素，80 帧。
- 灰盒 [固定后上方](graybox_fixed_rear.png) · [技术顶视](graybox_top.png)。
- 材质 [松散](preview_fixed_rear_loose.png) · [结阵中](preview_fixed_rear_forming.png) · [V 形完成](preview_fixed_rear_formed.png) · [完整 V 形技术顶视](preview_top_full_v.png) · [补给岸](preview_fixed_rear_checkpoint.png) · [岔口](preview_fixed_rear_fork.png)。
- [同帧关闭引导光痕](comparison_without_formation_guide.png) · GLB 回导 [结阵](roundtrip_fixed_rear_formed.png) · [补给岸](roundtrip_fixed_rear_checkpoint.png)。

## 组装与控制

地面由 ENV-001 的 10 BU 模块和其原网格的 5 BU 半块拼接。ENV-014 `CheckpointA_Visual` 以 `(0,50,0)` 组装，其水面、干地和冻结芦苇保留原始材质。ENV-005 Sparse 补外围芦苇，少量原创浅绿金笔触勾出补给面。Blender 的审阅组用 ENV-010 Mouth、ENV-008 LakeWide 和 ENV-009 远脊呈现岔口方向。实际出口后的可走路线和布局见 LVL-S2。

内部坐标采用 +Y 朝前、+Z 朝上。GLB 转为 `(x,z,-y)`。`Entry=(0,0,0)`；`Checkpoint_A=(0,60,0)`，同时作为 S2 入口对接点，两端朝 +Y。接缝在 X ±12 BU 内为 Z=0 干地，入口与出口各向内保留 2 BU。水面 Z=-0.18 BU，位于两道接缝之间。`Rest_Pad_A=(-0.65,49.96,0)` 是补给与重试落点的候选。运行时检查点激活域、补给用量与重试状态由游戏提供。

FX-001 长短流线使用原网格、枢轴、UV 和浅金／乳白贴图，审阅风向 +Y。FX-008 单条柔边光痕按两翼有效、连续的动态队形锚点摆位，切向向近端，中心沿队形的右向轴偏移 0.91 BU，长度为锚点间距的 0.67。提供实际机身位置、航向、离地、配对有效性、结阵完成度和透明度倍率。审阅母版中两条 ANM-006 动作按相同巡航相位混合，12 只雁分别错相。可在 Outliner 的 `Formation Guide | Review Controls` 调风速、风向、两秒渐显、前后段位置和光痕偏移，再用 `--rebuild-controls` 重打关键帧。GLB 含地面、水面、芦苇、补给笔触和锚点。光痕网格、局部动作与风线实例的运行时输入由布局映射到上游候选。

固定机位沿用 Swift `ThirdPersonRig.graybox` 的距离参数 180、俯仰输入 0.48 rad、纵向 FOV 50°、注视点为高度 6 加航行抬高量。喙尾 0.9900 BU 对齐 27.5 游戏单位。短片采用 0.930 BU 领队根高，其中 0.288 BU 是领队基础高度，0.642 BU 是审阅用 `depthLift`，相机只随 `depthLift` 抬升。母版技术顶视为独立审阅机位。

## 离线回验

在另一个 Blender 后台进程，从实际交付路径重开母版，移除全部原场景导出几何后回导 GLB，使用同一动作、轴向和固定机位复测。明细与相同机位帧差见 QA。

- 55 个时间样本、1,281,076 次实际蒙皮顶点向下探针。12 雁最大横宽约 5.759 BU，干地接缝宽 24 BU，宽度比 4.17。沿途抽样的最小竖向净空约 0.712 BU。
- 从第 25 到 73 帧完成 2 秒结阵。队形对 V 槽位置的 RMS 从 0.359 BU 经中途 0.179 BU 收敛到 0。完成帧 12 只雁的载体中心均入画。9 段光痕的锚点重算位置误差为 0。同帧开关对照有 1,031 像素至少一通道变化超过 5/255。335 个非回收风线样本中，沿航向相对机位前移至少 0.0404 BU/帧。
- 40 条入洲补给点探针均入画且穿透到预定观测点，中间无植被或地表交点。两端总计 970 次地表探针均覆盖干地，采样高程误差 0。候选 GLB 中检查点为 `(0,0,-60)`，10 张独立上游 PNG 内嵌字节核对全部一致。结阵帧及补给帧的回导同机位 RGB 平均通道差均低于 0.003/255。
- FFmpeg 严格解码 80 帧 H.264，0 音轨。红线自查记录随 QA。未测真机体验和性能。

## 复现

在本目录使用 Blender 5.2.2 LTS，ffmpeg 和 ffprobe 需可调用。输出使用新的空目录。

```sh
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python LVL-S1_generate.py -- /tmp/ft-s1-build
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python LVL-S1_generate.py -- /tmp/ft-s1-verify --verify "$PWD"
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python LVL-S1_generate.py -- /tmp/ft-s1-edited --rebuild-controls "$PWD/LVL-S1_S1_Tailwind.blend"
```

## 待验与登记

- 待负责人审阅顺风方向、V 形渐显、补给岸和实机关卡的辨识度。待运行时验证真实队形、透明排序、输入触发和取消、转向受限与约三分之一能耗减免、补给与重试、碰撞和玩法交接。USDZ、RealityKit／App 接入与 iPhone／iPad 待真机。引用 active 计划已有 iOS 27.2 模拟器构建及 340 项测试基线。
- [共用素材索引](../../../../../docs/asset-index.json)待登记母版、GLB、布局、预览和 v001 路径。[候选素材台账](../../../../../docs/asset-ledger.md)和[正式素材台账](../../../../../../docs/references/asset-ledger.md)待登记项目内依赖、素材许可沿用和原创笔触。[任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json)与 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md)待登记技术候选和剩余接入验收。
