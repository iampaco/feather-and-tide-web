# ENV-013 河岸灌木和矮树

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 12 页，任务清单第 52 项，P1，适用 S2 / S3 / S5。按本轮指定提前制作。直接依赖 MAT-001/v001。

[可编辑母版](ENV-013_riparian_shrubs.blend) · [资产清单与贴图映射](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-013_generate.py) · [风摆预览脚本](ENV-013_breeze_preview.py)

| 变体 | 轮廓 | 宽 × 深 × 高（BU） | 三角面 | 导出 |
| --- | --- | --- | ---: | --- |
| Shrub_A | 雾绿宽矮灌木，六块低垂叶冠 | 1.432 × 1.004 × 0.757 | 474 | [GLB](ENV-013_Shrub_A.glb) |
| Shrub_B | 黄绿色低树，五块较高不对称叶冠 | 1.388 × 0.951 × 1.294 | 440 | [GLB](ENV-013_Shrub_B.glb) |

各冠层和树干为封闭的三角网格。原点在根部接地处，Blender XYZ 到 glTF 为 `(x,z,-y)`，局部 +Y 朝前。贴图由 MAT-001 的 PlantOpaque、DryGround 提取纸纹颗粒，重新烘焙三套 256 × 256 色带，从较暗的近地色过渡到较浅冠层色。源图和输入母版的哈希已核对。输出为不透明单面材质，内嵌 PNG 与附带文件一致。

## 灰盒、河岸和微风

- [灰盒单株](graybox_lineup.png) · [灰盒固定后上方](graybox_fixed_rear.png) · [两种灌木同尺度近景](preview_lineup.png) · [GLB 回导近景](preview_glb_roundtrip.png)
- [固定机位进入河湾](preview_fixed_rear_entry.png) · [固定机位接近](preview_fixed_rear.png) · [固定机位接应](preview_fixed_rear_rescue.png) · [河岸布设顶视](preview_open_bank_overhead.png) · [微风横屏短片](preview_breeze_fixed_rear.mp4)

母版的源对象场景可单独选取两种变体。审阅场景使用 ENV-007 的实测 OpenBank、CHR-001 主雁尺度与 ANM-007 站姿，沿用 180 / 0.48 rad / 50° 源码镜头和 852 × 393 横屏。河岸暖金示意点与审阅对象留在场景内。

先在灰盒验证留空和视线，再上材质。27 株在两岸交错布置，东岸连续接近带宽 2.47 BU，与 ENV-007 的干地接应区一并留空。12 个种子、4 个风摆相位、3 个固定后上方取景和每景 16 个目标点，共 **2,304 条灌木视线射线**均未被遮挡。数据覆盖掉队雁的头、身与翼侧，以及接应区的 9 个台面采样点。网格距留空矩形的最小余量 **0.1562 BU**，同样的 48 条地形视线通过。目标在最远取景中较小，近景和顶视可复核其位置。样段由固定分区和生长点布设，关卡随机散布应沿用同一留空条件并复测。

两种 GLB 均带 `Wind_sway_X` 权重目标及 3.333 秒微风动作。变形沿高度平方增加，根部测得位移为 0，两个变体的最大摆幅分别为 0.1034 / 0.1415 BU。两份 GLB 检查了节点、枢轴、轴向、拓扑、法线、UV、原图和形变向量，按 81 帧比较权重，循环首尾和形变向量误差为 0。独立重开实际交付目录后回导，重跑河岸布设和遮挡检查，结果一致。短片对植株错相施加轻风供观感复核。

## 复现

指定各自的空临时目录。使用 Blender 5.2.2 LTS，短片编码使用 ffmpeg。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-013_generate.py -- /absolute/path/to/empty-output

blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-013_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-013/v001

blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-013_breeze_preview.py -- /absolute/path/to/empty-video-output
```

## 待验与待登记

待负责人复核轮廓与配色。实际救援视线、随地形散布、风场、形变、碰撞、USDZ / RealityKit 和 iPhone / iPad 真机待验证。App 沿用 iOS 27.2 的 iPhone 18 Pro 模拟器构建及 340 项测试记录。已对照设计红线。

- `Assets/docs/asset-index.json` 补候选条目、母版、两份 GLB、依赖、贴图和 QA。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 补原创网格、MAT-001 衍生纹理及候选记录。正式路径在运行时接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 回写 Shrub_A/B 的交付路径和 `needs_review`。
- `plans/active/goose-preview-model-cleanup.md` 补几何、轻风、救援样段和运行时待验项。
