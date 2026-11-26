# ANM-004｜左倾转向

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-004_bank_left.blend) · [蒙皮 GLB](ANM-004_bank_left.glb) · [生成脚本](ANM-004_bank_left_generate.py) · [素材清单与贴图来源](asset_manifest.json) · [QA](qa.json)

## 动作与衔接

`Bank_L` 是单向姿态片段，48 fps，第 **1–25 帧 / 0.500 秒**。第 1 帧为中立，第 13 帧左倾约 6°，第 25 帧左倾约 12°。内侧左翼下沉，左腕轻收；外侧右翼保持展开，颈与头分担反补偿。按 Blender 的 +Y 前轴计算，满幅躯干侧倾为 −12°。两端可停留，松杆时沿同一动作减小采样相位。

把经过死区和响应曲线的左转强度平滑为 `w ∈ [0, 1]`，以 **`1 + 24w` 帧**采样 Blender Action，或以 **`0.500w` 秒**采样 GLB。25%、50%、75%、100% 强度分别约为 1.25°、6°、10.75°、12°。输入可连续变化，保持时固定采样点。片段只有局部骨骼旋转，游戏实体负责世界位置、速度、航向、俯仰、路线和障碍。

审阅以 `Cruise_Flap_Loop` 复位段 **第 49 帧（92.31%，距首帧 1.000 秒）**进入。巡航相位在前 6 帧由 49 减速至 52，随后保持；姿势用五次平滑权重在前 18 帧内混合至 Bank_L。审阅满幅入场 **24 帧 / 0.500 秒**，保持 **28 帧 / 0.583 秒**，释放 **28 帧 / 0.583 秒**。采样相位的前后各 20% 做三次缓入缓出，保证半幅也能平稳停留。退出末 16 帧渐回巡航第 52 帧，再用 6 帧恢复正常巡航相位速度。可复现细节见脚本 `phase_at` 和 `review_pose`。

主场景默认打开满幅姿态，选择 `GooseRig` 后在 Action Editor 或 Graph Editor 编辑。切至 `Review | Cruise to left turn` 场景查看完整衔接。半幅复核动作 `Review | Half left and release` 保留在 .blend 的 Action 下拉菜单。审阅场景的独立 Empty 按示意路线移动并转向，固定相对机位跟随该 Empty。

## 预览

- 视频：[后上方 1 领队 + 11 同伴](preview_rear_flock_12.mp4) · [单只后方近景](preview_rear_detail.mp4)。
- 后上方原尺寸：[巡航复位](preview_rear_1x_cruise.png) · [进入](preview_rear_1x_entry.png) · [满幅](preview_rear_1x_full_bank.png) · [退出](preview_rear_1x_release.png)。
- 满幅姿态：[半尺寸后上方](preview_rear_half_full_bank.png) · [原尺寸顶视](preview_top_full_bank.png) · [半尺寸顶视](preview_top_half_full_bank.png) · [GLB 回导](preview_glb_full_bank.png)。
- 群体与路线：[固定后上方](preview_rear_flock_12.png) · [群体顶视](preview_top_flock_12.png) · [独立载体路线顶视](preview_top_world_trajectory.png)。

固定后上方画面为 852 × 393，距离 180、俯仰参数 0.48 rad、纵向 FOV 50°、注视高度 6，领队高 8、同伴高 6。喙尾 0.9900106 BU 对齐领队占位盒的 27.5 游戏单位，约 27.77748 游戏单位 / BU。半尺寸只缩放审阅领队，镜头和领队参考高度一致。原尺寸双纹和深飞羽清楚。半尺寸前纹约 1 像素，明显偏弱。深飞羽仍呈暗边，单根羽片较难分开。

12 只审阅队形使用固定偏移，共享一个网格。同伴 0.8×，使用 A/B/C 三种羽色，进入延迟 3–22 帧。示意载体速度为 30 游戏单位/秒，最大偏航速率 0.60 rad/s，固定相对镜头随航向转动。实际队形和速度由 App 的群体与输入模拟决定。

## 接入与验证

沿用 CHR-001 的 3,940 三角面、15 根骨、蒙皮、UV、躯干中心 Root 和四张打包羽色。Blender 为 +Z 向上、+Y 向前，GLB 为 +Y 向上、−Z 向前。对象单位缩放。

`PlayfieldPilot` 当前以 `-yaw × 0.32` 作为实体 bank 目标，按 0.18 秒常数缓动。左推的 yaw 为负，当前 bank 参数为正。未来接入可用平滑左转强度，或以 **`clamp(sample.bank / 0.32, 0, 1)`** 把现有参数转成采样权重。用 Blender 已验证的左翼下沉方向校验导入映射。在混合窗把实体层的旧 bank 渐出，同时渐入骨骼姿态，使侧倾只施加一次；保持游戏载体的世界航向和俯仰。由 `Circle_Loop` 切入时，应先用同一混合权重交接其已有局部侧倾。该接入方案仍待 RealityKit 验证。

- **Blender** 独立 Action 检查 49 个半帧，全幅与半幅审阅过渡各检查 351 个。肩翼连接、指定部件相交、蒙皮与平地净空检查通过。入场和退出与巡航的接点位置误差均为 0 BU。单独左倾动作左翼尖最低余量约为领队 4.95、同伴 3.56 游戏单位。1+11 同屏含巡航段的最小网格净空约 1.92 游戏单位。
- **GLB** 回导后重采样 49 个半帧。核对名称、时长、网格、UV、羽色、蒙皮、局部轴、尺度、枢轴、朝向，Root 和骨架对象无动画通道。
- **App 灰盒** 2026-11-14 使用 iPhone 18 Pro（iOS 27.2）运行 `./Scripts/build.sh` 和 `./Scripts/test.sh`，340 项通过，0 失败。
- **待验收** Paco 复核左倾节奏、姿态和半尺寸双纹，MAT-002 仍待独立材质复核。USDZ / RealityKit 待验证动画采样、侧倾交接、地形净空和实际队形。iPhone / iPad 待验证显示、输入、镜头和性能。下一项为 ANM-005 右倾转向。

## 复现

在仓库根目录使用 Blender 5.2.2 和 ffmpeg，将结果写到新目录。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 10 \
  --python-exit-code 1 \
  --python Assets/Watercolor/Goose/Blender/ANM-004/v001/ANM-004_bank_left_generate.py \
  -- /tmp/feather-tide-anm004-rebuild
```

`--mode checks` 生成资产并跳过渲染。生产资产直接依赖 CHR-001/v001。复现脚本读取 ANM-001/v001 作为巡航审阅参考，并复用 CHR-001、ANM-001 与 ANM-003 脚本中的制作工具。人工看片和 App 测试记录在生成流程之外。
