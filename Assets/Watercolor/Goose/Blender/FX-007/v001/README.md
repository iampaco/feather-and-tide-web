# FX-007 植被受风摆动控制样例

**v001 · needs_review · Blender 5.2.2 LTS · P0 · S0–S6**。按制作规格书第 15 页及任务 JSON 制作 `WindSwayPreset`。

[可编辑 Blender 母版](FX-007_WindSwayPreset.blend) · [清单及文件哈希](asset_manifest.json) · [独立回验](qa.json) · [运行时输入接口](wind_interface.json) · [复跑脚本](FX-007_generate.py)

| 来源 | 含三节点蒙皮、处于中立姿态的独立 GLB |
| --- | --- |
| ENV-004/v001 | [A · S](FX-007_Reed_A_Height_S.glb) · [A · M](FX-007_Reed_A_Height_M.glb) · [B · S](FX-007_Reed_B_Height_S.glb) · [B · M](FX-007_Reed_B_Height_M.glb) · [C · S](FX-007_Reed_C_Height_S.glb) · [C · M](FX-007_Reed_C_Height_M.glb) |
| ENV-012/v001 | [RiverTree_A](FX-007_RiverTree_A.glb) · [RiverTree_B](FX-007_RiverTree_B.glb) · [LeaningTree](FX-007_LeaningTree.glb) |

[灰盒后上方](graybox_fixed_rear.png) · [灰盒顶视](graybox_top.png) · [单株近景](preview_individual.png) · [S1 轻风](preview_s1_fixed.png) · [S3 先兆](preview_s3_fixed.png) · [S3 顶视](preview_s3_top.png) · [S3 降低动态](preview_s3_reduced.png) · [S5 逆风](preview_s5_fixed.png) · [固定机位短片](preview_fixed_rear.mp4)

## 制作与接口

先以灰盒核对根部、冠部和屏占，再渲染材质。六型芦苇保留 ENV-004 的造型、UV 和色调，新增渐变蒙皮 `Root → Stem → Tip`。三型树沿用 ENV-012 的 `Root → Stem → Crown` 蒙皮，用线性蒙皮和本预设的骨骼旋转作为 GLB 与 Blender 的共同基准。实际使用的 MAT-001 植被和干地纹理按源字节嵌入 GLB，并在 `qa.json` 记录逐款纹理哈希。ENV-002 的水岸模块和 CHR-001 主雁只用于镜头审阅。各源母版路径和 SHA-256 见 `wind_interface.json`。

母版默认打开 S3。每个 S1、S3、S5 场景都有 `WindSwayPreset | … shared control` 空物体。可在物体自定义属性中调整 `windAngleRad`、`windStrength`、`motionScale` 和 `periodSeconds`。S3 的 `windStrength` 曲线有关键帧。各植株骨架有 `phaseRad`、`response` 和 `instanceYawRad`；修改实例绕 Z 偏航时，同步最后一项。场景共用世界下风方向，实例用各自相位，Root 保持固定。将 `motionScale` 设为 0 会立即回到中立几何。

GLB 交付原型蒙皮和静态中立姿态。引擎按 `wind_interface.json` 提供世界下风方向、归一化风强、持续时钟、实例相位及动效倍率，将下风向转入实例和关节的局部静止基，并同步驱动 `Stem` 和 `Tip` 或 `Crown`。游戏控制实际风场和触发时刻；审阅场景用三个参数组演示预期差异。坐标以 Blender +Z 向上、+Y 向前，导出到 `(x,z,-y)`。比例为喙尾 0.9900 BU 对齐 27.5 游戏单位。固定后上方复现 Swift 的 `ThirdPersonRig.graybox`，距离 180、俯角参数 0.48 rad、纵向视野 50°、目标高 6，画幅 852 × 393。

## 回验

- 从本交付目录在独立后台 Blender 重开母版。S1、S3、S5 每组 78 株芦苇及 8 株树，逐场采样 49 帧。全量锁定根部最大位移为 0 BU。关闭动效后在 6 个采样时刻均保持静止，和中立网格的最大误差低于 0.000002 BU。
- S1、S3、S5 梢端最大下风位移约 0.118、0.398、0.438 BU。逐株梢端峰值出现在 38、24、35 个不同帧。S3 在审阅标记第 28 帧前已有响应，第 27 帧画内树梢投影位移最大约 8.84 px，芦苇约 26.71 px。实测为素材审阅数据。
- 九份 GLB 回导均通过。核对原点、骨骼层级、网格三角形、UV、法线、权重、材质侧面和内嵌纹理。对回导骨骼施加旋转后，九款均产生可测梢端形变。
- 视频为 S1、S3、S5 各 2 秒，原尺寸 852 × 393。H.264 4:4:4 保留奇数画幅高度；使用 ffprobe 和 ffmpeg 实际确认 48 帧可全部解码、无音轨。

## 复现

使用 Blender 5.2.2 LTS 和 ffmpeg ／ ffprobe。选择两个不同的空临时目录。在素材库原路径运行时可省略 `--source-root`；复制脚本后用该参数指定 `Assets/Watercolor/Goose/Blender`。验证命令仅读当前候选，结果写入临时目录。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-007_generate.py -- /absolute/empty-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python FX-007_generate.py -- /absolute/empty-recheck --verify "$PWD"
```

## 待审阅与登记

- 待 Paco 审阅枝叶弹性、风摆幅度及轻风、阵风先兆、逆风的固定镜头可读性。待 USDZ 与 RealityKit 接入、App 风场和触发与降低动态设置、iPhone ／ iPad 显示与性能验证。App 参考 active 计划记录的 iPhone 18 Pro（iOS 27.2）模拟器基线。
- 待在 `Assets/docs/asset-index.json` 登记母版、九份 GLB、接口、QA 和 `needs_review`。
- 待在 `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 登记项目内模型及 MAT-001 项目纹理、原创权重和控制驱动、审阅证据、待验状态及后续运行导出。制作仅使用项目内依赖。
- 待在 `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 回写变体和候选位置，在 `plans/active/goose-preview-model-cleanup.md` 写回离线实测和接入待办。

已对照设计红线。交付仅展示植被和环境风响应。
