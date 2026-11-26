# ANM-002 起飞与爬升 · v001

**待复核**。在已验收的 CHR-001/v001 网格、蒙皮与 15 根骨上制作 `Takeoff_Climb`。保留四种羽色、嵌入贴图、骨骼局部轴和躯干中心枢轴。

[可编辑 Blender 文件](ANM-002_takeoff_climb.blend) · [带动作和蒙皮的 GLB](ANM-002_takeoff_climb.glb) · [资源清单](asset_manifest.json) · [QA](qa.json) · [生成脚本](ANM-002_takeoff_climb_generate.py)

## 预览

| 视角 | 证据 |
| --- | --- |
| 后上方近看 | [起飞至巡航 MP4](preview_rear_detail.mp4) |
| 固定后上方机位 | [起飞至巡航 MP4](preview_gameplay.mp4) · [接触](preview_gameplay_contact.png) · [蹬离](preview_gameplay_push.png) · [爬升](preview_gameplay_climb.png) · [切入巡航](preview_gameplay_handoff.png) |
| 半尺寸与近看 | [半尺寸爬升](preview_gameplay_half_climb.png) · [侧面脚掌接触](preview_foot_contact.png) · [顶视爬升](preview_top_climb.png) · [GLB 回导](preview_glb_roundtrip.png) |
| 雁群 | [1 领队 + 11 同伴 MP4](preview_gameplay_flock_12.mp4) · [同屏静帧](preview_gameplay_flock_12_still.png) |

固定机位沿用距离 180、俯仰参数 0.48 rad、50° 纵向 FOV 与 27.7775 游戏单位 / BU。静帧为 852 × 393。横屏视频底部补 1 行供 H.264 编码。灰绿岸面与蓝灰水面是审阅参考。三段视频附一小段巡航供检查过渡。

## 编辑与接入

打开源文件，选 `GooseRig` 并在 Action Editor 或 Graph Editor 编辑 `Takeoff_Climb`。时间轴标出了接触、抬头、蓄力、蹬离、两次振翅及巡航衔接。源文件保留 ANM-001 的 `Cruise_Flap_Loop`，可在 Action Editor 手动切换核对。

| 帧 | 动作 |
| --- | --- |
| 1–18 | 脚掌接触，抬头、压低重心并抬翼 |
| 25 | 蹬离平岸，双脚开始向后收 |
| 32–54 | 两次大幅振翅，收腿后进入爬升 |
| 81 | 匹配 `Cruise_Flap_Loop` 第 1 帧 |

动作 48 fps，跨度 80 帧，**1.6667 秒，单次播放**。GLB 含一个动作，无 Root 通道。Root 全程固定在躯干中心，游戏负责位置、朝向、速度与高度。清单的 `preview_carrier` 记录了 Blender 平岸审阅摆位，方便复核脚掌接触与离地。接触段的位置由脚底轨迹计算，蹬离后由单独的高度和前进曲线控制。该位移用于渲染预览，未写入角色动作。实际接入时需与运行时地面、触发时点和起飞速度对齐。

## 验收

- 对 161 个半帧采样检查肩翼连接、14 对指定非相邻部件和 Root。检查通过。平岸预览中脚掌接触保持在岸面约 0.003 游戏单位上方，蹬离后所有顶点的最小余量约 0.34 游戏单位。
- 源动作末帧与巡航首帧的蒙皮网格重合。两侧速度的有限差分约 0.0019 BU/s。GLB 的接缝通道差异小于 0.000001，回导整数帧最大网格误差约 0.000002 BU。
- iPhone 18 Pro（iOS 27.2）模拟器的 App 灰盒基线构建和 340 项测试通过。待 Paco 复核起飞节奏，待 RealityKit 验证实际接地、轨迹与巡航切换，待 iPhone / iPad 验证屏幕观感和性能。
- 清单中下一项是 **ANM-003｜滑翔循环 / 进入盘旋**。

## 复现

需 Blender 5.2。生成视频时需 PATH 中有 FFmpeg。脚本读取相邻的 ANM-001/v001 和 CHR-001/v001，在独立空目录生成交付。只跑检查时可在目录参数后加 `--checks-only`。

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python ANM-002_takeoff_climb_generate.py -- /absolute/path/to/empty-output
```
