# CHR-002 斑头雁远景 LOD · v001

候选状态 **needs_review**。从已验收的 [CHR-001/v001](../../CHR-001/v001/README.md) 派生两个带蒙皮的三维模型，使用 [ANM-001/v001](../../ANM-001/v001/README.md) 的原始巡航动作做离线交接审阅。Blender 5.2.2 LTS。

| 文件 | 用途 |
| --- | --- |
| [可编辑母版](CHR-002_goose_lods.blend) | 原始 LOD0 与两级新网格共用 `GooseRig`。固定后上方审阅场景带 11 个错相同伴 |
| [LOD1 GLB](CHR-002_LOD1.glb) | **1,380 三角面**，较 LOD0 少约 65%。保留单根飞羽、双脚和眼部 |
| [LOD2 GLB](CHR-002_LOD2.glb) | **500 三角面**，较 LOD0 少约 87%。每侧翼为一块闭合网格，保留飞羽暗色带与双头纹 |
| [资源清单](asset_manifest.json) · [QA](qa.json) · [逐帧级别证据](generation_evidence.json) | 依赖、贴图映射、切换采样与重新导入结果 |

## 预览

- 固定机位灰盒 [LOD0](graybox_fixed_lod0.png) · [LOD1](graybox_fixed_lod1.png) · [LOD2](graybox_fixed_lod2.png)
- 双纹与羽色顶视 [LOD1](preview_top_lod1.png) · [LOD2](preview_top_lod2.png)
- 固定机位同姿势交接 [LOD0](preview_fixed_switch_01_lod0.png) → [LOD1](preview_fixed_switch_01_lod1.png) · [LOD1](preview_fixed_switch_12_lod1.png) → [LOD2](preview_fixed_switch_12_lod2.png)
- 固定机位 [12 只错相静帧](preview_fixed_flock.png) · [覆盖三级的无声短片](preview_fixed_rear.mp4)

## 编辑与接入

- 母版在 `CHR-002 | Editable tiers` 集合放置 `Goose_LOD1`、`Goose_LOD2`。审阅单鸟时关闭 `Preview | 11 phase-shifted companions` 的视口和渲染，再分别启用目标网格。选中目标网格编辑材质，选中 `GooseRig` 播放或编辑共用 `Cruise_Flap_Loop`。场景播放 1–52 帧，完整循环含第 53 帧接缝样本。
- 两个 GLB 各含一个带蒙皮网格、原 15 根骨及同名 1.0833 秒巡航。沿用 Leader、Follower A/B/C 四种材质变体和内嵌的 4 张 MAT-002 1K PNG。尺寸、骨名、局部轴与枢轴匹配 CHR-001。Blender +Z 向上、+Y 向前，导出采用 `(x,y,z) → (x,z,-y)`，Root 在躯干原点。
- 预览沿用源码 180 游戏单位、0.48 rad、50° 纵向视角、注视基高 6，以及 0.9900 BU 对 27.5 游戏单位。固定画幅 852 × 393，H.264 在底部补一行。短片由同伴移动产生投影视宽变化，机位始终固定。
- 短片以世界坐标静置翼展的屏占宽度演示。小于约 70 px 时进入 LOD1，小于约 32 px 时进入 LOD2。接入时提供同一只雁的朝向、世界变换、材质变体和动作相位，以静置包围盒的屏幕投影做选择，保持跨级的动作相位一致。阈值为审阅初值。LOD1 单根羽尖比 LOD0 更简化，LOD2 双纹在极远投影下随屏占缩小。

## 离线回验

- 在最终交付目录独立重开母版及回导两个 GLB。十个巡航相位的投影轮廓重叠率最低为 LOD0→1 的 91.2%、LOD1→2 的 79.4%，对应最大外框跳动 0.115 和 0.402 像素。前向偏移分别为 150 和 560 游戏单位。
- 两个 GLB 复用了原始纹理字节和巡航 13 条活动通道。坐标、UV、骨架静置矩阵、105 个半帧网格采样及循环接缝通过独立回验。网格最大整帧误差低于 0.000001 BU，最大半帧误差 0.00285 BU 为曲线采样与烘焙插值差。接缝误差为 0 BU。
- 样片全部 54 帧解码通过，24 fps、2.25 秒、无音轨。抽看双纹顶视、固定交接与群飞。已对照项目红线清单。

## 复跑

需要 Blender 5.2，PATH 包含 FFmpeg 与 FFprobe。当前目录是本 README 所在目录。

```sh
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python CHR-002_generate.py -- /tmp/ft-chr002-new
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python CHR-002_recheck.py -- "$PWD" /tmp/ft-chr002-recheck.json
```

## 待验与登记

待负责人美术审阅，USDZ、App 接入、运行时屏占切换与动作同步、iPhone／iPad 视觉和性能待验。本轮引用 active 计划内 iOS 27.2 模拟器基线。

待登记 `Assets/docs/asset-index.json`、`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md`、`完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 中 CHR-002 及 `plans/active/goose-preview-model-cleanup.md`。登记派生来源、两种候选、离线证据和运行时待验。
