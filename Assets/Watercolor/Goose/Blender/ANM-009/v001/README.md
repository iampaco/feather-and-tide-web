# ANM-009｜离队呼唤 / 归队反馈

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-009_call_rejoin.blend) · [双动作蒙皮 GLB](ANM-009_call_rejoin.glb) · [复现脚本](ANM-009_call_rejoin_generate.py) · [素材清单](asset_manifest.json) · [QA](qa.json)

| Action | 48 fps 帧范围 | 时长 | 动作 |
| --- | --- | --- | --- |
| `Call_Loop` | 1–57 | 1.167 秒 | 短拍翼并抬头，末帧是循环接缝 |
| `Rejoin` | 1–53 | 1.083 秒 | 呼唤姿态逐渐并入正常振翅 |

审阅先播放两个呼唤周期，在 `Call_Loop` 第 **57** 帧接到 `Rejoin` 首帧，末帧接巡航第 **1** 帧。两处接点网格差为 0 BU，边界速度差分别约 0.00050 和 0.00203 BU/s。若游戏需在呼唤中途立即开始回归，接入时可继续采样当前呼唤相位并在局部姿态层过渡到 `Rejoin`，实际时机待运行时验证。

主场景提供两个可编辑 Action。`Review | Separated companion` 中 11 只雁继续巡航，第 12 只先在右外侧呼唤，再由独立载体移动到队伍右侧并恢复巡航。固定后上方镜头采用 180、0.48 rad、纵向 FOV 50°、注视高度 6，领队高 8、同伴高 6，约 27.77748 游戏单位 / BU。画面摆位与归队轨迹用于审阅。游戏驱动寻路、速度、航向与归队完成条件。Blender 预览另放置 `FX-009 | preview attachment` 空对象，局部高 0.38 BU，供后续定位参考。

- [固定后上方 12 只视频](preview_call_rejoin_flock_12.mp4) · [离队者近景视频](preview_call_rejoin_detail.mp4)
- 顶视 [呼唤](preview_top_flock_call.png) · [归队中](preview_top_flock_rejoining.png) · [恢复巡航](preview_top_flock_rejoined.png)
- 同机位 [1×](preview_fixed_1x_call.png) · [0.5×](preview_fixed_half_call.png) · 顶视 [1×](preview_top_1x_call.png) · [0.5×](preview_top_half_call.png)
- [群体后上方](preview_rear_flock_call.png) · 回导 [呼唤](preview_glb_call_loop.png) · [归队](preview_glb_rejoin.png)

分别检查 113 和 105 个半帧，覆盖 Root、肩翼连接、指定部件穿插、呼唤接缝、归队过渡及平地净空。12 只同屏逐帧检查通过。GLB 含单只蒙皮雁和两个动作，保留 3,940 三角面、15 根骨、原局部轴、UV、蒙皮、四张羽色及变体。枢轴和对象缩放沿用 CHR-001，Root 和对象无动画通道。归队载体和 FX 定位为空间审阅元素。

原尺寸双纹与飞羽暗边可辨，半尺寸前纹偏弱。Paco 待复核呼唤辨识度、归队节奏和 MAT-002。FX-009 正式特效、USDZ / RealityKit 的衔接和运动控制、iPhone / iPad 实际画面与性能均待验收。App 灰盒构建与 340 项测试另有 QA 记录。

在项目根目录运行 Blender 5.2.2 和 ffmpeg，指定空输出目录。脚本复用 ANM-007 的 Blender 验证工具。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 8 \
  --python-exit-code 1 --python Assets/Watercolor/Goose/Blender/ANM-009/v001/ANM-009_call_rejoin_generate.py \
  -- /tmp/feather-tide-anm009-rebuild
```
