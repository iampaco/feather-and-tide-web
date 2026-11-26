# ENV-008 长湖路湖面与岸线

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 11 页，任务清单第 21 项，适用 S2。依赖 ENV-001/v001、ENV-002/v001、MAT-004/v001。

[可编辑母版](ENV-008_long_lake.blend) · [LakeWide 水面](ENV-008_LakeWide.glb) · [LakeShore 岸线与湖床](ENV-008_LakeShore.glb) · [资产清单与纹理映射](asset_manifest.json) · [QA](qa.json) · [生成与复验脚本](ENV-008_generate.py)

[灰盒检查点 A](graybox_checkpoint_A.png) · [灰盒顶视](graybox_top.png) · [材质顶视](preview_top.png) · [检查点 A 固定横屏](preview_checkpoint_A.png) · [原位朝湖路转向](preview_lake_route_heading.png) · [湖面航段](preview_approach.png) · [GLB 回导重拼](preview_glb_roundtrip.png) · [慢速湖面预览](preview_lake_motion.mp4)

## 拼装

| 对象 | 内容 | 三角面 |
| --- | --- | ---: |
| LakeWide | 一张完整的水平湖面，局部 Z = −0.18 BU，沿 +Y 延展 54 BU，最大宽 24.7 BU | 726 |
| LakeShore | 两岸、连续湖床与一块真实 ENV-002 RestPatch 地形，西侧边起于 X = −1 BU | 2,624 |

两份 GLB 都以检查点 A 为本地原点，比例 1、旋转 0，按相同变换叠放。Blender 坐标映射为 glTF `(x,z,-y)`。RestPatch 中心 `(4, 10, 0)`，保留 289 个点和 10 × 10 BU 的平接边。湖水从 Y = 4 BU 延到 58 BU，湖床最低 −0.65 BU。主航道中段（Y = 10.5–48.5 BU）水宽至少 16.56 BU，入口和出口收窄。湖面投影面积 1,015.81 BU²。

母版场景 **Asset pair** 可直接选择导出对象。**Checkpoint A and lake** 包含主雁尺度参照、画面前景和 ENV-003 小水洼参照。**Review-only slow water** 在同一后上方镜头下展示轻微水面明暗变化。两份 GLB 的湖面颜色为静态。运行时的慢波、云影和水面透明排序留待 FX-006 / RealityKit。

湖面取经哈希核对的 MAT-004 Water_Lake 原始 PNG 的水彩纹理，按实际水深重烘焙一张 1024² 直通 RGBA。岸线边界 Alpha 为 0，0.225 BU 深度达到设定最大值 227/255。GLB 为 BLEND。MAT-004 的母版哈希与其清单记录有差异，实读值及源 PNG 的一致性已分别记录。湖岸复用 MAT-003 四张地表贴图。湖岸、湖床与贴图来源均为项目内素材。

## 已验证

- 灰盒及 GLB 回导重拼各测 88 个共岸顶点，水线高度差 0 BU。2,904 个湖面内采样的湖床射线均有覆盖，未探到湖面伸入干地。
- RestPatch 的 64 个边界顶点高度差 0 BU，289 个源点的位置一致。补给滩朝湖面的 20 个干地采样至少高出水位 0.102 BU。
- 沿湖方向测了 109 个截面。按现行审阅飞行高度取得最小垂直净空 0.468 BU，实际可飞范围、耗能、补给触发与碰撞由关卡和运行时代码验收。
- 852 × 393 检查点画面沿用 `ThirdPersonRig.graybox` 的 180 游戏单位距离、0.48 rad、50° 纵向 FOV，视点高度 6，主雁飞行高度 8。沿用 0.9900 BU 对应 27.5 游戏单位的审阅换算。固定朝 +Y 的检查点画面中，两岸和补给滩有无遮挡探针，湖面靠右且近侧部分出框。原位转向与湖面航段使用同一镜头参数，展示完整方向感和纵深。补给辨识与长短路线的实际比较仍待 S2 合场审阅。
- 两份 GLB 的节点名、中心、轴向、拓扑、面角法线、UV、Alpha 和嵌入式纹理逐一复核。项目红线已自查。

## 复现

使用 Blender 5.2.2 LTS，分别指定空的输出目录和复检目录。视频脚本需要 ffmpeg。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 --python ENV-008_generate.py -- /absolute/empty-out --video-frames 24
python3 ENV-008_video.py /absolute/empty-out
blender -b --factory-startup -t 4 --python-exit-code 1 --python ENV-008_generate.py -- /absolute/empty-recheck --verify /absolute/ENV-008/v001
```

本轮沿用已有 iPhone 18 Pro（iOS 27.2）模拟器构建及 340 项测试记录。待美术审阅、S2 双路线、USDZ / RealityKit 透明排序及 iPhone / iPad 真机验证。

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补两份 GLB、母版、QA、贴图和 `needs_review`。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 增补制作来源、材质依赖、纹理哈希、候选与后续运行时状态。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 回写两份变体、候选路径与状态。
- `plans/active/goose-preview-model-cleanup.md` 增补拼装、水线、检查点视场、基线引用及待验项。
