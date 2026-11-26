# ANM-003｜滑翔循环 / 进入盘旋

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-003_glide_circle.blend) · [蒙皮 GLB](ANM-003_glide_circle.glb) · [生成脚本](ANM-003_glide_circle_generate.py) · [素材清单与贴图来源](asset_manifest.json) · [检查结果](qa.json)

## 动作与衔接

| Action | 48 fps 帧范围 | 周期 | 姿态 |
| --- | --- | --- | --- |
| `Glide_Loop` | 1–73 | 1.50 秒 | 双翼展开，腕和翅尖错相微动，头颈维持朝前 |
| `Circle_Loop` | 1–97 | 2.00 秒 | 示范左翼下沉。躯干绕角色 +Y 侧倾 −7.5° ±0.75°，内侧左腕略收、外侧右翼维持伸展，颈和头局部反补偿 |

末帧为重复接缝样本。两个动作使用循环 Bézier 曲线。默认场景 `ANM-003 | Editable loops` 选中了 `GooseRig` 和 `Glide_Loop`。在 Dope Sheet 的 Action Editor 下拉菜单可选 `Circle_Loop`，播放范围设为 1–96。审阅场景 `Review | Glide and left circle` 自带时间线标记和延迟播放的 11 只同伴，使用固定后上方镜头。复合审阅动作、巡航参考与 CHR 姿势测试保留在 .blend 中供编辑。

在巡航复位段第 **49 帧**触发过渡，距循环首帧 1.000 秒，相位 `48/52 = 92.31%`。过渡用 `w(u) = 6u⁵ − 15u⁴ + 10u³` 在相同骨架的局部曲线上混合，缺省通道取绑定姿势。滑翔入场用 **16 帧 / 0.333 秒**。从触发起的前 6 帧，巡航相位按 `49 + d × (1 − d/12)` 前进，其中 `d = min(6, 经过的帧数)`，随后停在巡航第 52 帧。目标滑翔相位在混合结束时到达第 1 帧。纯滑翔停留 **48 帧 / 1.000 秒**。滑翔第 49 帧开始混入盘旋，耗时 **24 帧 / 0.500 秒**，结束时进入盘旋第 1 帧。两个目标片段在混合中用循环曲线回采，使到达第 1 帧时延续该动作的速度。具体实现见脚本 `build_review`。规格的约 1 秒是游戏状态时长。

## 预览

- 视频：[固定后上方 1+11](preview_rear_flock_12.mp4) · [单只后方斜角近景](preview_rear_detail.mp4)。两段均从巡航播放到左倾盘旋循环。
- 后上方原尺寸：[巡航复位](preview_rear_1x_recovery.png) · [滑翔](preview_rear_1x_glide.png) · [盘旋](preview_rear_1x_circle.png)。半尺寸：[滑翔](preview_rear_half_glide.png) · [盘旋](preview_rear_half_circle.png)。
- 顶视原尺寸：[滑翔](preview_top_glide.png) · [盘旋](preview_top_circle.png)。半尺寸：[滑翔](preview_top_half_glide.png) · [盘旋](preview_top_half_circle.png)。
- 1 领队 + 11 同伴：[固定后上方](preview_rear_flock_12.png) · [顶视](preview_top_flock_12.png)。Blender 回导：[滑翔](preview_glb_glide.png) · [盘旋](preview_glb_circle.png)。

固定后上方横屏为 852 × 393。复用 `ThirdPersonRig.graybox` 的距离 180、俯仰参数 0.48 rad、纵向 FOV 50°、注视高度 6，领队高 8、同伴高 6。喙尾 0.9900106 BU 对应 27.5 游戏单位，换算为 27.77748 游戏单位 / BU。0.5× 以同机位和领队高度缩放审阅载体。原尺寸双纹分开，深色飞羽边沿可辨。半尺寸可看出两条暗纹，前纹约 1 px，盘旋时偏弱。深飞羽仍形成暗边，单根羽片在半尺寸下较难分开。

12 只审阅队形为固定间距的分排站位，同伴 0.8×，A/B/C 循环分配，并延迟 3–22 帧进入同一复合动作。App 的同伴位置由实际群体模拟决定。审阅使用原地盘旋姿态，世界轨迹由游戏提供。

## 接入与验证

Blender 为 +Z 向上、+Y 向前、+X 向右，GLB 为 +Y 向上、−Z 向前、+X 向右。GLB 含 CHR-001 的 3,940 三角面、15 根骨、原 UV、蒙皮、四张内嵌羽色及同网格 Leader / Follower A/B/C 变体。Root 保持躯干中心，角色对象单位缩放。两个生产片段仅含骨骼旋转通道。游戏控制载体的世界位置、速度、航向、路径和障碍。

`PlayfieldPilot` 当前以巡航速度的 0.35 倍慢飞，松手后沿当前航向飞行，俯仰归平。 `PlayfieldView` 对领队实体应用 `sample.pitch` 和绕模型前轴 −Z 的 `sample.bank`，其中 bank 上限 0.32 rad、缓动时间 0.18 秒。接入时在滑翔至盘旋的混合窗用同一权重将实体层 bank 渐出，让 `Circle_Loop` 的 Body 曲线接管可见侧倾。退出时反向交接。实体层继续持有航向和俯仰。若以后由动态 bank 持续驱动盘旋，需在动画混合层扣除示范 roll，并配套处理头颈反补偿。状态计时、程序化盘旋轨迹和正式转向动作在各自后续任务验收。

- **Blender** 两个循环分别检查 145 和 193 个半帧样本，切换段检查 177 个。肩翼连接、蒙皮边长和指定部件相交检查通过。原始循环及 Blender 回导的首末姿势误差为 0 BU。回导后用相邻帧差估算的最大接缝速度差为 0.00347 BU/s。盘旋入场由 0° 渐至左倾 7.5°，最大采样侧倾速度约 29.3°/s。
- **平地参考** 盘旋下侧翼尖最小余量为领队 6.17、同伴 4.53 游戏单位。包括巡航起段的 12 只全片最低网格净空为 1.92 游戏单位。检查范围为审阅地面与指定部件组合。地形、额外俯仰和运行时姿态留待接入后复测。
- **App 灰盒** 2026-11-14 使用 iPhone 18 Pro（iOS 27.2）运行 `./Scripts/build.sh` 和 `./Scripts/test.sh`，340 项通过，0 失败。
- **待验收** Paco 复核节奏、半尺寸双纹和左倾观感。MAT-002 仍待独立材质复核。USDZ / RealityKit 待验证动画资源、过渡、侧倾交接、平地与地形净空。iPhone / iPad 待验证实际显示、触控、镜头、同屏表现和性能。

## 复现

在仓库根目录使用 Blender 5.2.2 和 ffmpeg，将结果写到新目录。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 10 \
  --python-exit-code 1 \
  --python Assets/Watercolor/Goose/Blender/ANM-003/v001/ANM-003_glide_circle_generate.py \
  -- /tmp/feather-tide-anm003-rebuild
```

`--mode checks` 跳过视频和静帧。脚本依赖同库已验收的 CHR-001/v001 与 ANM-001/v001 和它们的工具脚本。人工看图结论、App 测试记录和 README 独立于 Blender 生成步骤。
