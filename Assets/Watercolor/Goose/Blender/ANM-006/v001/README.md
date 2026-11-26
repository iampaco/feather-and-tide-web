# ANM-006｜结阵省力姿态

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-006_formation_blend.blend) · [单只蒙皮 GLB](ANM-006_formation_blend.glb) · [生成脚本](ANM-006_formation_blend_generate.py) · [素材清单与贴图来源](asset_manifest.json) · [QA](qa.json)

## 动作和两秒过渡

`Formation_Blend` 为 48 fps、第 **1–53 帧**的原地振翅循环，周期 **1.08333 秒**。第 53 帧是接缝样本，循环播放使用第 1–52 帧。动作由已验收的 `Cruise_Flap_Loop` 派生，保留展翼、下压、腕部滞后及复位相位。翼根峰峰幅度从 **53° 降到 39.22°**，腕部从 **25° 降到 16.75°**。躯干俯仰和头颈补偿曲线缩至 44%，躯干起伏缩至 42%。Root 始终在躯干中心。

结阵混合用 **2.000 秒**。从当前巡航相位同时采样两个循环，每只雁保留自己的相位偏移。设 `u = clamp(结阵完成度, 0, 1)`，局部姿态混合权重为 `w = 6u⁵ − 15u⁴ + 10u³`。两条循环继续前进，到 `w = 1` 时接上同一相位的省力振翅。审阅时间线从第 53 帧开始混合，领队此时对应巡航第 1 帧，第 149 帧混合完成，对应 `Formation_Blend` 第 45 帧。另在相隔四分之一周期的巡航第 1、14、27、40 帧做半帧验证。

主场景默认选中 `GooseRig` 和 `Formation_Blend`，可在 Action Editor 或 Graph Editor 修改原曲线。`Review | Loose flock to V` 中有错相的 1 领队 + 11 同伴。每只的局部混合与独立 Empty 的 V 槽位插值分别可编辑。原巡航动作也保留在 .blend 中供对照。

## 预览

- [固定后上方 1+11 视频](preview_rear_flock_12.mp4) · [顶视结阵视频](preview_top_formation.mp4) · [单只后方近景](preview_rear_detail.mp4)
- 原尺寸后上方 [巡航](preview_rear_1x_cruise.png) · [结阵后上举](preview_rear_1x_formed.png) · [结阵后下压](preview_rear_1x_formed_downstroke.png) · [结阵后顶视](preview_top_1x_formed.png)
- 半尺寸 [后上方](preview_rear_half_formed.png) · [顶视](preview_top_half_formed.png)
- 群体顶视 [松散](preview_top_flock_loose.png) · [结阵中](preview_top_flock_forming.png) · [V 形](preview_top_flock_formed.png) · [群体后上方](preview_rear_flock_12.png) · [GLB 回导](preview_glb_roundtrip.png)

后上方画面为 852 × 393，距离 180、俯仰 0.48 rad、纵向 FOV 50°、注视高度 6。领队高度 8、同伴高度 6。喙尾 0.9900106 BU 对齐领队占位盒的 27.5 游戏单位，约 27.77748 游戏单位 / BU。领队为 1×，同伴为 0.8× 并轮换 A/B/C 羽色。半尺寸静帧仅缩放领队。

原尺寸双纹可分开，深飞羽清楚。半尺寸前纹约 1 像素、偏弱，深飞羽仍可辨为暗边。V 形槽位为审阅摆位，第一排横向偏移为 26，随后每排横向增加 6、向后增加 13 游戏单位。游戏当前由 `SpeciesAbilityState` 在 2 秒内累计完成度，`formsVisual` 过阈值后由 `FlockSystem` 驱动同伴追踪 V 槽位，配置间距为 36。省力规则、转向、碰撞和队形继续由游戏处理。接入可读取完成度驱动局部动作权重，独立保留每只雁的相位。取消结阵或急转重置完成度时，表现层可从当前权重平滑退出，具体退出与运行时 `bank` / 俯仰叠加待 RealityKit 验证。

## 检查

- **Blender** 105 个循环半帧、四组各 193 个两秒过渡半帧。检查循环接缝、过渡边界、肩翼连接、指定部件相交、头部前向与平地余量。12 只队形逐帧检查取景、净空及相邻网格。
- **GLB** 回导 105 个半帧。保留单网格、3,940 三角面、15 根骨、原蒙皮、UV、四张羽色及 Leader / Follower A/B/C 变体。Blender 为 +Z 向上、+Y 向前，GLB 为 +Y 向上、−Z 向前。对象单位缩放，Root 与对象无动画通道。Body 保留局部微起伏。
- **App 灰盒** iPhone 18 Pro（iOS 27.2）重新执行 `./Scripts/build.sh` 与 `./Scripts/test.sh`，340 项通过，0 失败。
- **待验收** Paco 复核振翅幅度和 V 形观感，MAT-002 仍待独立材质复核。USDZ / RealityKit 待验证相位同步、结阵与解阵混合、实际群体和地形净空。iPhone / iPad 待验证实际显示、触控、镜头与性能。按任务清单下一项为 ANM-007｜落水 / 立足 / 收翼。

## 复现

在仓库根目录用 Blender 5.2.2 和 ffmpeg，将结果写到新目录。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 10 \
  --python-exit-code 1 \
  --python Assets/Watercolor/Goose/Blender/ANM-006/v001/ANM-006_formation_blend_generate.py \
  -- /tmp/feather-tide-anm006-rebuild
```

附加 `--mode checks` 可跳过渲染。脚本读取 CHR-001/v001 和 ANM-001/v001，复用 ANM-001 与 ANM-003 的 Blender 曲线、检查和渲染工具。人工看片与 App 验证单独记录。
