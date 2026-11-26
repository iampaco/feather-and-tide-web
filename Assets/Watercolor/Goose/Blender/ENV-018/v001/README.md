# ENV-018 云层与远景雾带卡片

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 13 页，清单第 28 项，P0，覆盖 S0–S6，直接依赖 MAT-001。

[可编辑母版](ENV-018_atmosphere_cards.blend) · [资产清单和贴图映射](asset_manifest.json) · [QA 实测](qa.json) · [生成、回导和帧渲染脚本](ENV-018_generate.py) · [视频与证据封装脚本](ENV-018_finish_review.py)

| GLB | 宽 × 高（BU） | 三角面 | 审阅用途 |
| --- | ---: | ---: | --- |
| [MistLow](ENV-018_MistLow.glb) | 18 × 1.45 | 16 | 贴地低雾，灰白底色与微暖亮边 |
| [CloudPatch](ENV-018_CloudPatch.glb) | 13.5 × 3.85 | 16 | 岸外或远景的云片，低频漂移 |
| [CloudStreak](ENV-018_CloudStreak.glb) | 20 × 1.55 | 16 | 冷灰细云带，山口可用较快横移 |

三款卡片均使用独立名称、15 个源顶点、独立 UV 和中心枢轴 `(0,0,0)`。Blender 为 XZ 卡片，正面朝 −Y，导出后按 `(x,z,-y)` 转为 GLB +Y 向上。卡片边缘的 Alpha 归零，三张 512 × 512 RGBA 贴图以本项目 MAT-001/v001 的 DryGround 纸纹为来源，记录源图与成图 SHA-256。GLB 采用双面、BLEND、CLAMP_TO_EDGE，元数据注明纯视觉用途与碰撞关闭，App 接入时由场景代码读取并保持无碰撞。Blender 的 S2/S3/S4 取景场景保留漂移关键帧，S3/S4 一周期 12 秒，S2 一周期 4 秒。交付 GLB 是静态卡片，风向、漂移和强度在接入时控制。

## 预览

- [三款造型](preview_lineup.png) · [GLB 回导造型](preview_glb_roundtrip.png) · [固定镜头漂移短片](preview_atmosphere_motion.mp4)
- S2 山口 · [灰盒](graybox_s2.png) · [薄云材质](preview_s2_default.png)
- S3 救援岸 · [灰盒](graybox_s3.png) · [默认](preview_s3_default.png) · [减弱](preview_s3_reduced.png) · [关闭](preview_s3_off.png)
- S4 风机扫掠 · [灰盒](graybox_s4.png) · [默认](preview_s4_default.png) · [减弱](preview_s4_reduced.png) · [关闭](preview_s4_off.png)

固定后上方取景沿用 `ThirdPersonRig.graybox` 的距离 180、俯仰 0.48 rad、纵向视角 50° 和注视高度 6 游戏单位。领头雁巡航根高 8 游戏单位。审阅采用 CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位的比例。帧源为 852 × 393，H.264 增补一行以满足编码尺寸。S3 使用 ENV-007 的 OpenBank 和带 ANM-007 姿态的救援目标，S2 使用 ENV-010 和 ENV-009 山口地形。S4 采用现行 `PlayfieldView.swift` 塔身和叶片尺寸及 `GrayboxPlaces.swift` 的 78 游戏单位扫掠半径，在候选审阅场景布置一台几何代理。

## 已实测

- 先制作灰盒再套用材质。S3 的 16 个救援与岸边点、S4 的 25 个塔身、叶片、灯点及扫掠边点，均在各自三个固定机位取景内。每种设置、每个机位采样八个漂移相位，S3 与 S4 分别为 384 和 600 条视线。光线穿过前景卡片时以双线性采样计算透明度，并乘积合成透射率。默认、减弱、关闭的被测目标最大 Alpha 都为 0，容差分别为 0.075、0.028、0。用双层云片覆盖探针验证算法能检出遮挡，默认合成 Alpha 为 0.77484，减弱为 0.33402。
- 候选画面提供默认 100%、减弱 35% 及关闭三档；减弱同时缩放漂移幅度。对比关闭画面，通道变化至少 5/255 的像素，S3 从 5,457 降至 454，S4 从 4,931 降至 547。视线结果适用于此处的卡片排布与抽样位置。
- GLB 回导逐件核对三角面、轴向、名称、单位缩放、中心枢轴、边界、UV、角点法线、材质与逐字节一致的内嵌 PNG。三款卡片重排后，源与回导渲染最大通道差 3/255，平均约 0.076/255。独立后台进程重开母版、回导 GLB，并验证 S2、S3、S4 保存的关键帧只沿 X 轴漂移，相机保持固定。视频合计 48 个 Blender 源帧，S3 与 S2 各 2 秒，通过 H.264 解码。

## 复现

用 Blender 5.2.2 LTS 的独立后台进程和独立空输出目录运行。最后一条需要 Pillow 12.2.0 与 ffmpeg/ffprobe。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-018_generate.py -- /tmp/ft-env018-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-018_generate.py -- /tmp/ft-env018-recheck --verify "$PWD"
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-018_generate.py -- /tmp/ft-env018-s3 --motion s3 --delivery "$PWD"
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-018_generate.py -- /tmp/ft-env018-s2 --motion s2 --delivery "$PWD"
python3 ENV-018_finish_review.py /tmp/ft-env018-output /tmp/ft-env018-s3 /tmp/ft-env018-s2 \
  --recheck /tmp/ft-env018-recheck/recheck.json
```

首次复现时，`--motion` 可将 `--delivery` 指向刚生成的空目录产物 `/tmp/ft-env018-output`。照片和外部贴图未用于制作。

## 待验与待登记

- 待负责人复核水彩、对比度与动效。待 S4 正式 STR-002 风机组、FX-004、S0–S6 运行时透明排序和可见性、减弱选项、关闭后行为、USDZ / RealityKit 与 iPhone / iPad 真机。App 沿用已有 iOS 27.2 构建与 340 项测试记录。本轮使用 Blender 后台进行资产验证。已对照设计红线。
- `Assets/docs/asset-index.json` 待补版本、根路径、母版、三个 GLB、贴图和 QA。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 待登记本项目 MAT-001 纸纹来源、生成 Alpha 和候选证据。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待回写版本、证据和运行时待验。

制作清单第 29 项为 **STR-001**。
