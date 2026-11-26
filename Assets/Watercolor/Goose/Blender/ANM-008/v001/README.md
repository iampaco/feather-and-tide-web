# ANM-008｜湿地休整 / 站立轻动作

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑 Blender](ANM-008_rest_idle.blend) · [蒙皮 GLB](ANM-008_rest_idle.glb) · [复现脚本](ANM-008_rest_idle_generate.py) · [素材清单](asset_manifest.json) · [QA](qa.json)

`Rest_Idle` 为 48 fps、第 1–145 帧、**3.000 秒**的站立循环。第 145 帧是接缝样本，循环播放使用第 1–144 帧。第 1 帧与 ANM-007 的两种落脚第 81 帧精确匹配。折翼站立时肩颈轻动，随后回首朝肩羽低头，恢复向前站姿。脚和 Root 固定。单只交接使用第 1 帧，稳定站立后的错相播放可从各自相位开始。

主场景可编辑原 Action，`Review | Wetland rest` 用 1 领队 + 11 同伴演示错相站立。固定后上方取景使用 180、0.48 rad、纵向 FOV 50°，按约 27.77748 游戏单位 / BU 与同一领队占位盒比例。落脚平面沿用 ANM-007，单只半尺寸保持足底接触，队形和相位用于审阅。实际停靠点、高度与补给由游戏决定。

- [单只休整近景](preview_rest_detail.mp4) · [12 只错相休整](preview_rest_flock_12.mp4)
- [站姿后上方](preview_rear_1x_stand.png) · [回首后上方](preview_rear_1x_tend.png) · [1× 顶视](preview_top_1x_tend.png) · [0.5× 后上方](preview_rear_half_tend.png) · [0.5× 顶视](preview_top_half_tend.png)
- [足底接触侧视](preview_feet_contact_side.png) · [群体后上方](preview_rear_flock_12.png) · [群体顶视](preview_top_flock_12.png) · [GLB 回导](preview_glb_rest_idle.png)

289 个半帧检查覆盖肩翼连接、指定部件相交、蒙皮、循环接缝及平参考面接触。双脚顶点位移为 0 BU，两种落脚交接网格差均小于 0.000001 BU。GLB 含 CHR-001 的单只 3,940 三角面网格、15 根骨、四张嵌入贴图、蒙皮、UV 和羽色变体，Root 与骨架对象无动画通道。单位缩放和轴向沿用 CHR-001。

理羽回首会改变头纹可见角度，半尺寸前纹较弱。Paco 待复核理羽姿态、节奏及 MAT-002 独立材质。USDZ / RealityKit 的入场相位、地形足底、实际停靠与 iPhone / iPad 待验证。App 灰盒构建与 340 项测试另有 QA 记录。

在项目根目录运行 Blender 5.2.2 和 ffmpeg，指定空输出目录。复现读取 ANM-007/v001 最终源文件与清单。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 8 \
  --python-exit-code 1 --python Assets/Watercolor/Goose/Blender/ANM-008/v001/ANM-008_rest_idle_generate.py \
  -- /tmp/feather-tide-anm008-rebuild
```
