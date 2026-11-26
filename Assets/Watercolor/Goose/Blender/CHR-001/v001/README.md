# CHR-001 斑头雁主体 · v001

**制作验收通过**。Paco 于 2026-11-14 确认 CHR-001/v001 可用于后续制作。Blender 5.2.2 LTS。展翼 **1.6004 BU**，喙尖到尾羽 **0.9900 BU**，中立姿势高 **0.4640 BU**。LOD0 为 **3,940 三角面**、2,036 个源顶点、15 根骨。网格含连续的躯干与弯颈、短喙、分层翼与尾羽、收拢双脚。

- [可编辑 Blender 源文件](CHR-001_goose_rig.blend) · [蒙皮 GLB](CHR-001_goose_rig.glb)
- [资源清单、骨骼坐标和贴图映射](asset_manifest.json) · [验收记录](qa.json) · [生成脚本](CHR-001_goose_rig_generate.py)

## 查看与编辑

- **灰盒**：[固定后上方](preview_graybox_gameplay.png) · [后上方近看](preview_graybox_rear.png) · [顶视](preview_graybox_top.png)
- **羽色与轮廓**：[顶视](preview_top.png) · [后上方近看](preview_rear_detail.png) · [侧面](preview_side.png) · [GLB 回导](preview_glb_roundtrip.png)
- **固定机位，852 × 393**：[原尺寸](preview_gameplay_1x.png) · [原尺寸冷光](preview_gameplay_1x_cool.png) · [半尺寸](preview_gameplay_half.png) · [半尺寸冷光](preview_gameplay_half_cool.png) · [1 领队 + 11 同伴](preview_gameplay_flock_12.png)
- **姿势样张**：[上举](preview_pose_upstroke.png) · [下压](preview_pose_downstroke.png) · [腕弯](preview_pose_wrist_flex.png) · [转颈](preview_pose_neck_turn.png)

源文件以中立展翼打开。选择 `GooseRig` 并打开视图叠加层可查看骨架。在 Pose Mode 的 Asset Browser（Current File）可应用五个 `QA · …` 单帧姿势，也可在 Action Editor 选择相应动作和骨架槽，跳至第 1 帧。蒙皮网格为 `Goose_LOD0`。在材质槽 0 切换 `Body_Leader` 或 `Body_Follower_A/B/C`。GLB 的默认材质是 Leader，四个选项通过 `KHR_materials_variants` 映射到同一网格。正式巡航动作由 ANM-001 制作。

四张 MAT-002/v001 的 1K 羽色 PNG 已打包进两个交付文件。头纹沿正式头部 UV 重新投射，冠面 U 接缝留在中线。头冠加厚，前纹移入固定机位的可见面，双纹加宽并保留纹间暖白区。三种同伴变体通过同一躯干贴图的轻微乘色区分。原始贴图、材质节点与来源哈希见清单。素材由项目内原创程序化建模与既有羽色组成。

## 骨骼和尺度

| 父级 | 子级 |
| --- | --- |
| Root | Body |
| Body | Neck、Tail、Foot.L / .R、WingRoot.L / .R |
| Neck | Head |
| WingRoot.L / .R | 同侧 Elbow |
| Elbow.L / .R | 同侧 Wrist |
| Wrist.L / .R | 同侧 Tip |

Blender 本地坐标为 +X 向右、+Y 朝前、+Z 向上。网格与骨架对象缩放均为 1，Root 在躯干中心 `(0,0,0)`，飞行位移由游戏控制。骨骼局部 +Y 指向骨尾，局部 +Z 向模型上方向对齐，局部 +X 由右手系确定。清单记录每根骨的三个基向量、父级和关节坐标。翼骨用局部 X 上下挥动，两侧局部 X 同号可对称抬翼。

GLB 坐标变换为 `(x,y,z) → (x,z,-y)`，+Y 向上、−Z 朝前，枢轴仍在原点。按 `ThirdPersonRig.graybox` 和 `PlayfieldView`，用 180 距离参数、0.48 rad 俯仰参数、50° 纵向 FOV、注视高度 6 和领队高度 8 复现取景。喙尾 0.9900 BU 对齐领队占位盒的 27.5 游戏单位，预览比例 **27.7775 游戏单位 / BU**。同伴用 0.8 倍、Root 高度 6 和审阅摆位。该摆位用于验证同屏覆盖，实际队形由游戏控制。比例只用于 Blender 取景，App 接入时需复核。

## 验收与后续

- Blender 中原尺寸的暖白头、双纹与深飞羽可辨。半尺寸在中性光和冷光均留有两条独立暗带和亮间隔，前纹约一像素，显示与运动中的辨识度待复核。12 只共享网格的静帧同屏可读。
- 五个静态姿势均通过权重归一、肩翼保持连接和指定部件间的相交检查，目检无明显撕裂。当前试验下压翼尖约低于高度 8 的等效地面 0.21 游戏单位。下压预览的底板为检查蒙皮而降低，ANM-001 需按运行高度复测翼尖离地。
- GLB 回导通过。对照源网格核对了网格位置、UV、蒙皮权重、骨骼层级与局部轴、枢轴、尺度和 4 张嵌入 PNG。iPhone 18 Pro（iOS 27.2）模拟器的 App 基线构建和 340 项测试通过。
- MAT-002 独立材质审阅待复核。RealityKit 资产导入、USDZ 接入、动态 12 只、iPhone / iPad 显示与性能均待验证。
- 按任务顺序，下一项是 **ANM-001 巡航振翅**。**CHR-002** 后续从验收后的主网格派生。

## 复现

在 Blender 5.2 中运行，生成脚本按相对路径读取相邻 MAT-001/v001 与 MAT-002/v001。输出用独立空目录。只需灰盒证据时可在输出目录参数后附加 `--graybox`。

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python CHR-001_goose_rig_generate.py -- /absolute/path/to/empty-output
```
