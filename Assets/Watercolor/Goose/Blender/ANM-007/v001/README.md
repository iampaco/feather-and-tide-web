# ANM-007｜落水 / 立足 / 收翼

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-007_landing.blend) · [双动作蒙皮 GLB](ANM-007_landing.glb) · [复现脚本](ANM-007_landing_generate.py) · [素材清单](asset_manifest.json) · [QA](qa.json)

两个 Action 均为 48 fps、第 1–81 帧、**1.667 秒**的单次动作。第 1 帧承接巡航复位第 **49 帧（92.31%）**，前 6 帧减速经过巡航第 52 帧并逐渐转入抬翼制动。双脚随后下伸。泥滩在第 **47** 帧接触，浅水在第 **51** 帧接触并略多保留展翼。两者最后都收拢到同一站立姿势，供 `Rest_Idle` 从第 1 帧接续。审阅测得横向翼展由 1.601 BU 减至 0.880 BU。

主场景可选 `Land_Mudflat` 或 `Land_ShallowWater` 编辑。两个 Review 场景以独立载体演示平参考面上的减速、下降和足底接触。12 只泥滩审阅共用网格并按 0–57 帧延迟逐只落脚。横屏机位按 `ThirdPersonRig` 的 180、0.48 rad、50°、注视高度 6 设置，接触阶段随领队载体高度移动。领队入场高度 8，同伴高度按审阅比例进入并过渡至各自的足底接触。喙尾 0.99001 BU 对应 27.5 游戏单位。同伴 0.8×，A/B/C 轮换。队形为审阅摆位，实际停靠点由游戏分配。

- [12 只错时落脚](preview_landing_flock_12.mp4) · [浅水近景](preview_water_landing_detail.mp4)
- 泥滩 [后上方 1×](preview_mud_rear_1x.png) · [后上方 0.5×](preview_mud_rear_half.png) · [足底侧视](preview_mud_contact_side.png) · [收翼顶视](preview_mud_folded_top.png) · [半尺寸顶视](preview_mud_folded_top_half.png)
- 群体 [后上方](preview_mud_flock_12.png) · [顶视](preview_mud_flock_12_top.png)
- 浅水 [后上方](preview_water_rear_1x.png) · [足底侧视](preview_water_contact_side.png) · [收翼顶视](preview_water_folded_top.png)
- 回导 [泥滩](preview_glb_land_mudflat.png) · [浅水](preview_glb_land_shallowwater.png)

两个片段各检查 161 个半帧。巡航入口和两个站立末姿的网格差均为 0 BU。半帧足底在平参考面接触后保持贴地，群体逐帧检查通过。全尺寸后上方可辨深飞羽和双纹，半尺寸前纹偏弱。生产 GLB 含一只 3,940 三角面的雁、15 根骨、UV、蒙皮、四张嵌入羽色及 CHR-001 变体。Blender +Z 向上、+Y 向前，GLB +Y 向上、−Z 向前。单位缩放与躯干中心 Root 固定。

未来由游戏状态锁定飞行输入并驱动世界位置、地面接触、浅水高度、速度和朝向。平面仅用于 Blender 审阅。真实泥滩与浅水、落脚输入锁定、USDZ / RealityKit 和 iPhone / iPad 待验收。Paco 待复核落脚节奏，MAT-002 待独立材质复核。App 灰盒构建与 340 项测试另有 QA 记录。

在项目根目录用 Blender 5.2.2 和 ffmpeg 运行，指定空输出目录。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 8 \
  --python-exit-code 1 --python Assets/Watercolor/Goose/Blender/ANM-007/v001/ANM-007_landing_generate.py \
  -- /tmp/feather-tide-anm007-rebuild
```
