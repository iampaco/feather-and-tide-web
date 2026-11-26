# ANM-005｜右倾转向

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-005_bank_right.blend) · [蒙皮 GLB](ANM-005_bank_right.glb) · [生成脚本](ANM-005_bank_right_generate.py) · [素材清单与贴图来源](asset_manifest.json) · [QA](qa.json)

## 动作与切换

`Bank_R` 为 48 fps、第 **1–25 帧 / 0.500 秒**的原地姿态片段。逐骨骼读取 `Bank_L` 原始曲线，交换左右骨骼，将旋转沿角色纵向对称面反射并换回 CHR-001 原局部轴。躯干满幅绕 Blender +Y 右倾 **12°**，半幅约 **6°**。内侧右腕额外绕本地 Y 轴变化 0.65°，右翼尖绕本地 X 轴最多多下压 1.1°，翼尖变化在满幅保持前收回。头颈跟随角色前向并抵消躯干侧倾。

把经过死区和响应曲线的右转强度平滑为 `w ∈ [0,1]`，在 Blender 采样 **`1 + 24w` 帧**，或在 GLB 采样 **`0.500w` 秒**。保持时固定采样点。左右切换时，用有符号参数 `s ∈ [-1,1]`，负值采样 `Bank_L`、正值采样 `Bank_R`，两侧都按 `abs(s)` 映射到动作相位。零值回到共同中立姿势。审阅切换每半段用五次平滑权重，左满幅到右满幅 **1.000 秒**，右满幅到左满幅 **1.000 秒**，中间帧为 37 和 93。两侧通过同一个中立姿态衔接。

巡航预览沿用左倾基准，从 `Cruise_Flap_Loop` 第 **49 帧（92.31% 相位）**进入。巡航相位前 6 帧减速至第 52 帧，前 18 帧渐入右倾姿态。满幅入场 **0.500 秒**、保持 **0.583 秒**、退出 **0.583 秒**。退出末 16 帧混回巡航第 52 帧，再用 6 帧恢复相位速度。全幅和半幅都按该方式验证。

主场景默认显示满幅 `Bank_R`，可在 Action Editor / Graph Editor 编辑。场景 `Review | Cruise to right turn` 包含固定后上方镜头与 12 只群体。场景 `Review | Left and right transitions` 含双向切换与中立标记。源文件保留 `Bank_L` 和巡航审阅参考。ANM-004/v001 在任务表仍为 `needs_review`，本次以该版作为镜像基准。

## 审阅证据

- [固定后上方 1+11 视频](preview_rear_flock_12.mp4) · [单只近景](preview_rear_detail.mp4) · [左右双向切换](preview_switch_both_directions.mp4)
- 后上方原尺寸 [巡航](preview_rear_1x_cruise.png) · [进入](preview_rear_1x_entry.png) · [满幅](preview_rear_1x_full_bank.png) · [退出](preview_rear_1x_release.png) · [半尺寸满幅](preview_rear_half_full_bank.png)
- 顶视 [原尺寸](preview_top_full_bank.png) · [半尺寸](preview_top_half_full_bank.png) · [1+11](preview_top_flock_12.png) · [载体右转轨迹](preview_top_world_trajectory.png)
- [1+11 后上方](preview_rear_flock_12.png) · [GLB 回导](preview_glb_full_bank.png) · 切换关键帧 [左](preview_switch_left.png) · [中](preview_switch_neutral.png) · [右](preview_switch_right.png)

固定后上方画面为 852 × 393。取景使用距离 180、俯仰 0.48 rad、纵向 FOV 50°、注视高度 6、领队高度 8、同伴高度 6。喙尾 0.9900106 BU 对应 27.5 游戏单位，约 27.77748 游戏单位 / BU。1× 能分开头部双纹，深飞羽清楚。0.5× 的前纹约 1 像素，偏弱。深飞羽仍呈暗边。审阅队形使用固定相对偏移、0.8× 同伴、A/B/C 三种羽色和 3–22 帧延迟。实际队形由游戏群体模拟计算。

## 接入与验收

沿用 CHR-001 3,940 三角面、15 根骨、原 UV 和蒙皮、四张羽色及同网格变体。Blender +Z 向上、+Y 向前，GLB +Y 向上、−Z 向前。对象缩放为 1，Root 枢轴在躯干中心。生产 GLB 只包含 `Bank_R` 和局部骨骼旋转通道。游戏控制实体航向、俯仰、世界位置、速度与障碍处理。独立审阅载体的示意速度是 30 游戏单位/秒，最大偏航速率 0.60 rad/s。

现有 `PlayfieldPilot` 右推得到负的 `sample.bank`。未来可用 `clamp(-sample.bank / 0.32, 0, 1)` 映射为右倾强度。混合期间将实体层原有 `bank` 渐出，并用同一权重渐入局部姿态，避免重复施加侧倾。游戏俯仰、航向与相机继续由现有载体驱动。左右切换共用有符号的采样权重，实际轴向和运行时混合待 RealityKit 验证。

- **Blender** 独立动作及 GLB 回导各 49 个半帧，巡航过渡全幅与半幅各 351 个，左右双向切换 257 个。检查肩翼连接、蒙皮、指定部件相交、前向、双向中立接点、平地净空及 12 只同屏。
- **App 灰盒** 在 iPhone 18 Pro（iOS 27.2）运行项目构建及测试脚本，340 项通过，0 失败。
- **待验收** Paco 复核右倾与左倾配对、半尺寸辨识和独立 MAT-002 材质。USDZ / RealityKit 待验证采样、实体侧倾交接、切换和实际地形净空。iPhone / iPad 待验证显示、触控、镜头和性能。下一项是 ANM-006 结阵省力姿态。

## 复现

在项目根目录运行 Blender 5.2.2 和 ffmpeg，将结果写到新目录。脚本读取 CHR-001、ANM-004 原文件及 ANM-001 巡航参考，复用同库脚本的检查和渲染工具。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 10 \
  --python-exit-code 1 \
  --python Assets/Watercolor/Goose/Blender/ANM-005/v001/ANM-005_bank_right_generate.py \
  -- /tmp/feather-tide-anm005-rebuild
```

附加 `--mode checks` 跳过渲染。App 结果和视觉复核单独记录。
