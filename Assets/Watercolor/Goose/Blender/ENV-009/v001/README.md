# ENV-009 远山轮廓组

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 11 页，任务清单第 22 项，P0，适用 S0–S6，直接依赖 MAT-003/v001。

[可编辑母版](ENV-009_far_ridges.blend) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-009_generate.py) · [固定机位运动脚本](ENV-009_motion_preview.py)

独立 GLB　[FarRidge_A](ENV-009_FarRidge_A.glb) · [FarRidge_B](ENV-009_FarRidge_B.glb) · [FarRidge_C](ENV-009_FarRidge_C.glb)

[灰盒横屏](graybox_fixed_rear.png) · [山体轮廓对照](preview_lineup.png) · [固定后上方入口](preview_fixed_rear_1.png) · [向前滑行](preview_fixed_rear_2.png) · [轻转向](preview_fixed_rear_3.png) · [GLB 回导重拼](preview_glb_roundtrip.png) · [固定机位连续预览](preview_motion_fixed_rear.mp4)

## 模块与摆放

| 名称 | X 宽 × Y 深（BU） | 最高点 Z（BU） | 三角面 |
| --- | ---: | ---: | ---: |
| FarRidge_A | 37.00 × 5.16 | 1.565 | 598 |
| FarRidge_B | 53.00 × 6.21 | 2.682 | 598 |
| FarRidge_C | 78.00 × 7.50 | 4.005 | 598 |

三款为有厚度的封闭低模，分别使用低缓双峰、错落连峰与宽阔远脊。对象中心枢轴位于地面原点 `(0,0,0)`，底部埋入 0.16 BU。各变体的源网格有 301 个顶点。Blender 本地 +Z 向上、+Y 朝前，GLB 坐标为 `(x,z,-y)`，宽度沿本地 X。建议以各关卡的最远可飞位置为摆位参考，将近远层的基底保留在可飞区外。母版场景 `ENV-009 | Standalone asset meshes at origin` 可独立追加三个资产，场景 `ENV-009 | Fixed follow backdrop` 演示近层两次错放 A、中层 B、远层 C。

MAT-003 的 MountainRock 源 PNG 已与其清单哈希核对。三张 384 × 384 新贴图保留淡化的原纹理颗粒和手绘色阶，分别着淡蓝灰、雾蓝和薰衣草灰。GLB 内嵌同一批 RGB PNG，使用不透明材质与浅色过渡。

## 取景与回导

先检查封闭体拓扑和灰盒轮廓，再换上三套材质。审阅用源码 `ThirdPersonRig.graybox` 的距离 180 游戏单位、俯仰参数 0.48 rad、垂直视野 50° 和注视点高度 6，`depthLift=0`。领队高度 8，按 CHR-001 喙尾约 0.9900 BU 对齐 27.5 游戏单位。三张横屏和连续运动均为 852 × 393 的固定后上方相对机位；领队平移与水平朝向变化由场景驱动。

三款 GLB 逐个重开并核对节点名、中心枢轴、比例、原始 glTF 轴向、包围盒、封闭性、三角面、法线、UV 和原贴图。回导顶点差 0 BU，UV 最大差 2.98 × 10⁻⁸，法线最大差 0.000011°。回导件按四个样段变换重拼，固定机位的投影数值一致。

样段测量包括三个关键帧和 34 帧连续相机移动。远山限制在画面上沿 11.23% 内，与路线标记最窄相隔 15.23 px，四个远山摆位距示意飞行终点沿 +Y 至少 13.92 BU。画面中央的远脊连续叠于较近 A 的低洼后方，路线转弯后结束，降低将远山误读为入口的风险。当前 iOS 画幅下远山细节在上沿收敛；各关的实际通行提示、碰撞边界、不同画幅的远山与山口关系仍待 RealityKit 验证。

## 复现

Blender 5.2.2 LTS。以下命令在本目录运行，输出到独立空目录。视频需要 ffmpeg。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-009_generate.py -- /absolute/path/to/build
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-009_generate.py -- /absolute/path/to/recheck --verify "$PWD"
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-009_motion_preview.py -- /absolute/path/to/preview
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 补候选母版、三个 GLB、QA、清单和 `needs_review`。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 补原创网格、MAT-003 项目内输入、重新烘焙的纹理与审阅证据。运行时资源在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回 FarRidge_A/B/C 的交付路径和候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补技术实测和待验收项。

已对照设计红线。App 模拟器沿用 iPhone 18 Pro（iOS 27.2）既有构建和 340 项测试记录。待负责人复核轮廓与配色、USDZ / RealityKit 接入、实际关卡可飞边界、iPhone / iPad 真机。
