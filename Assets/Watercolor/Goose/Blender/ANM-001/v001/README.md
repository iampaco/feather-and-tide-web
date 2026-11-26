# ANM-001 巡航振翅 · v001

**制作验收通过**。Paco 于 2026-11-14 确认。在已验收的 CHR-001/v001 上制作 `Cruise_Flap_Loop`。保留原网格、蒙皮、15 根骨的命名与局部轴、四种羽色和躯干中心枢轴。

[可编辑 Blender 文件](ANM-001_cruise_flap.blend) · [带动作与蒙皮的 GLB](ANM-001_cruise_flap.glb) · [资源清单与贴图映射](asset_manifest.json) · [QA](qa.json) · [生成脚本](ANM-001_cruise_flap_generate.py)

## 预览

| 视角 | 证据 |
| --- | --- |
| 后上方近看 | [循环 MP4](preview_rear_detail_loop.mp4) · [GLB 回导上举](preview_glb_roundtrip.png) |
| 固定机位原尺寸 | [循环 MP4](preview_gameplay_1x_loop.mp4) · [上举](preview_gameplay_1x_upstroke.png) · [下压](preview_gameplay_1x_downstroke.png) · [复位](preview_gameplay_1x_recovery.png) |
| 固定机位半尺寸 | [上举](preview_gameplay_half_upstroke.png) · [下压](preview_gameplay_half_downstroke.png) · [复位](preview_gameplay_half_recovery.png) |
| 固定机位 1 领队 + 11 同伴 | [错相循环 MP4](preview_gameplay_flock_12_loop.mp4) · [同屏静帧](preview_gameplay_flock_12.png) |
| 顶视 | [上举](preview_top_upstroke.png) · [下压](preview_top_downstroke.png) |

固定机位静帧为 852 × 393，复现 `ThirdPersonRig.graybox` 的 180 距离、0.48 rad 俯仰参数、50° 纵向 FOV，沿用 27.7775 游戏单位 / BU。横屏视频底部补 1 行供 H.264 编码。雁群沿用 CHR-001 审阅摆位与同伴 0.8 倍缩放，每只同伴错开相位并与领队共享同一个网格数据块。

## 编辑与接入

打开源文件按播放键。主场景默认使用后上方近看机位。切换场景 Camera 到 `Gameplay | fixed rear` 可看固定机位。领队选中 `GooseRig` 后，在 Action Editor 或 Graph Editor 编辑 `Cruise_Flap_Loop`。如需看雁群，在 Outliner 重新启用 `Flock review | shared mesh` 集合的视口及渲染。该集合的同伴用同一个 Action 的错相 NLA 条带。

源文件 48 fps，第 1–53 帧定义 **1.0833 秒**循环。第 53 帧是第 1 帧的接缝样本，循环播放范围为 1–52。第 11 帧翼根上举到峰值，第 29 帧下压到最低，第 35 帧腕部展开到峰值，较翼根最低点延迟 0.125 秒。Body 轻微升降并俯仰，Neck 与 Head 抵消俯仰以稳定朝向。Root 锁在原点，动作无 Root 通道，航向与位移交由游戏控制。GLB 只带 `Cruise_Flap_Loop`，播放器按片段时长设置循环。

## 验收

- 105 个半帧采样检查了循环接缝、左右对称、肩翼连接、14 对指定非相邻部件的相交情况及巡航离地。最低点出现在第 29 帧。按灰盒直飞高度，领队与同伴分别留有 **2.91** 和 **1.92 游戏单位**。转向、俯仰和实际地形的余量留待接入验证。
- GLB 复用同一套网格属性、蒙皮、关节静置变换与嵌入贴图。Blender 回导后首末帧网格重合，53 个烘焙帧的最大顶点误差约 0.0000014 BU，半帧误差见 QA。
- iPhone 18 Pro（iOS 27.2）模拟器通过 App 灰盒基线构建和 340 项测试。待 USDZ / RealityKit 循环、动态雁群与 iPhone / iPad 实际显示和性能验证。
- 清单中的下一项为 **ANM-002｜起飞与爬升**，从本循环的恢复姿势衔接。

## 复现

需 Blender 5.2，生成视频时需 PATH 中有 FFmpeg。脚本读取相邻的 CHR-001/v001 源文件、导出与生成脚本，以独立空目录作为输出。只跑检查时在输出目录参数后附加 `--checks-only`。

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python ANM-001_cruise_flap_generate.py -- /absolute/path/to/empty-output
```
