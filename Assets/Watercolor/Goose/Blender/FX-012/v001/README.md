# FX-012 补给区柔光 / 恢复反馈

**v001 · needs_review · Blender 5.2.2 LTS**。任务规格第 16 页，P1，适用 S1、S2、S4。交付变体为 `RestCue`。

[可编辑 Blender 母版](FX-012_RestCue.blend) · [资产清单](asset_manifest.json) · [独立 QA](qa.json) · [运行时接口](rest_cue_interface.json) · [生成与复验脚本](FX-012_generate.py)

| 已有湿地模块 | 模块局部原点适配 | 固定后上方预览 |
| --- | --- | --- |
| S1 · ENV-014/v001 CheckpointA | [FX-012_RestCue_S1.glb](FX-012_RestCue_S1.glb) | [全队恢复](preview_s1_restoring.png) |
| S2 · ENV-015/v001 LakesideRest | [FX-012_RestCue_S2.glb](FX-012_RestCue_S2.glb) | [全队恢复](preview_s2_restoring.png) |
| S4 · ENV-016/v001 ProtectedMarsh | [FX-012_RestCue_S4.glb](FX-012_RestCue_S4.glb) | [全队恢复](preview_s4_restoring.png) |

[灰盒机位](graybox_s4_fixed.png) · [可用、未停留](preview_s4_available_idle.png) · [离开后收敛](preview_s4_release.png) · [耗尽后再入](preview_s4_exhausted_reentry.png) · [固定机位状态短片](preview_fixed_rear.mp4)

## 制作

先在灰盒检查空间覆盖，随后从三个已交付的可编辑湿地母版中取实际水面、芦苇和落脚雁。浅水柔光从源水面裁切并抬高 0.009 BU。各地有三个贴近现有芦苇的轻薄边缘光罩。浅暖米色和柔边来自两张 192 × 192 RGBA 贴图，GLB 有内嵌字节和独立 [水面图](textures/ft_goose_fx_rest_cue_water.png)／[芦苇图](textures/ft_goose_fx_rest_cue_reeds.png)。

`RestCue_S*` 为模块局部原点。每份 GLB 有 `ShallowLight` 和 `ReedHalo` 两个已命名绘制层，使用 `KHR_materials_unlit` 和 `BLEND`。母版包含源湿地背景和 12 只落脚雁，羽色仅通过 Feather 材质的轻微暖色偏移表现。GLB 的场景仅含柔光层。后上方机位沿用 Swift 参数，距离 180 游戏单位、俯仰参数 0.48 rad、目标高 6、纵向视野 50°。画幅 852 × 393，CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位，BLENDER → GLB／RealityKit 为 `(x,z,-y)`。

## 接入预设

每个材质审阅场景均有 `RestCue | S… review controls` 空物体。时间轴中的 `capacityAvailable` 和 `allSettled` 演示游戏输入。两条可编辑曲线 `displayIntensity` 和 `featherIntensity` 分别驱动两片柔光 Alpha 与参与停歇的雁羽暖色。底层效果不带声效。

引擎按稳定的 `siteID` 传入权威容量标记、全队已落脚、时间步长和可选的休整雁名单。可用且全队停留时，用 0.68 s 时间常数向恢复目标渐强。离开后用 0.39 s 时间常数回到 0.27 的可用柔光倍率。耗尽时容量标记立即将柔光和羽色收为 0，演示再次进入仍为 0。落脚和补给容量的持久化由游戏 Zone 与现有存档控制。GLB 内部为满幅 Alpha，接入方用效果状态乘以源 Alpha。

## 独立回验

- 从实际交付目录重开母版，三份 GLB 回导通过。对照根节点、命名、三角形、坐标、UV、Alpha 混合与内嵌 PNG 字节。S1／S2／S4 分别为 100、171、138 个三角面，每款两层。
- 在三个实际地块上复测 **1,564** 个水面样点，柔光高差相对 0.009 BU 的最大误差约 0.00000042 BU；9 个柔光罩到原有芦苇曲面的最近采样距离均小于 0.36 BU。三个固定机位的 12 只落脚雁中心均入框。
- 每场逐帧复测 148 帧。S4 的可用、恢复、离场和耗尽后再次进入分别取到约 0.27、0.92、0.36、0 的柔光倍率。同一画幅相对于耗尽状态，三个状态分别有 632、3,032、1,297 个像素的最大通道差超过 8／255。
- 固定机位短片 852 × 393、6.17 秒，使用 4:4:4 编码保留奇数高度。37 个 H.264 帧通过实际解码，视频无音轨。短片以固定落脚雁作为对照，由输入曲线切换状态。

## 复现

使用 Blender 5.2.2 LTS、ffmpeg 和 ffprobe。在相邻素材库目录结构下，将生成与复验分别输出到各自空临时目录。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-012_generate.py -- /absolute/empty-build
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-012_generate.py -- /absolute/empty-recheck --verify "$PWD"
```

## 待验与登记

- 待 Paco 复核暖光和状态辨识，待 USDZ、RealityKit 水面与透明排序、App 实际落脚与补给容量绑定、iPhone／iPad 显示和性能。App 构建与测试引用已有 iOS 27.2 模拟器基线。
- 待在 `Assets/docs/asset-index.json` 登记候选及依赖，并在 `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 登记项目内模型、两张原创程序贴图、可编辑曲线和来源哈希。后续接入时记录正式运行时路径。
- 待在 `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 回写候选目录、审阅结果和待验项。

已对照设计红线。效果只使用水色、芦苇和羽色变化。
