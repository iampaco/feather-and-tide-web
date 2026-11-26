# ENV-010 短山口 / 峡谷主结构

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 11 页，清单第 23 项，S2。依赖 ENV-001/v001 的陆边和 ENV-009/v001 的远山。灰盒通过后使用 MAT-003 的草滩、苔藓石与山岩。远山候选、树线与雾丝留在审阅场景中。树线为离线占位，正式风向树交给 ENV-012，风速与视觉效果由 FX-002 和游戏数据控制。

[母版](ENV-010_short_pass.blend) · [资产清单与贴图映射](asset_manifest.json) · [QA 实测](qa.json) · [生成和回导脚本](ENV-010_generate.py)

| 组件 | 本地范围（BU） | 三角面 | 导出 |
| --- | --- | ---: | --- |
| Pass_Left | X −21.5 到 −11.5，Y 20 到 50 | 1536 | [GLB](ENV-010_Pass_Left.glb) |
| Pass_Right | X −11.5 到 −1.5，Y 20 到 50 | 1536 | [GLB](ENV-010_Pass_Right.glb) |
| Mouth | X −21.5 到 −1.5，Y 10 到 20 | 1024 | [GLB](ENV-010_Mouth.glb) |

三份模块共用检查点 A 原点 `(0,0,0)`。组装时保持三个对象的单位缩放和零位移。Blender +Y 朝前、+Z 向上，GLB 转为 `(x,z,-y)`。陆边步长 **0.625 BU**，外侧与入口、出口可接 ENV-001 Flat，纹理保持 10 BU 周期。山壁和槽底由连续的低模三角网格构成。大地形平面、参考主雁、雾丝、路径标记和树线占位是审阅元素。

## 审阅与验证

[山口与长湖同框](preview_checkpoint_a_fork.png) · [固定跟随飞越视频](preview_pass_motion.mp4) · [分岔预览脚本](ENV-010_fork_preview.py) · [飞越视频脚本](ENV-010_motion_preview.py)

使用实际 ENV-008 与 ENV-010 候选母版，在同一检查点 A 拼装样段。左侧通道 13/13，右侧湖面和岸边补给各 9/9 条视线采样入镜且未被地形遮挡。图中哑金方块为山口审阅路线。双线选择和汇合由后续关卡实现。飞越短片有 30 个 Blender 源帧并通过 H.264 解码，雾丝横移仅用于看画面。

- [灰盒顶视](graybox_top.png) · [灰盒检查点 A](graybox_checkpoint_a.png) · [材质顶视](preview_top.png) · [回导重拼顶视](preview_glb_roundtrip_top.png)
- 固定后上方 852 × 393　[检查点 A](preview_checkpoint_a.png) · [接近](preview_approach.png) · [豁口](preview_mouth.png) · [谷中](preview_throat.png) · [出谷](preview_exit.png) · [回导检查点 A](preview_glb_roundtrip_checkpoint_a.png)

每个三角形与分段走廊精确裁切，确认 **5.2 × 40 BU** 的走廊覆盖 208 BU²、地面高差为 0。左右坡脚以高度 0.05 BU 定义，最窄相距 **6.388 BU**。用 CHR-001 中立姿态宽 1.6004 BU 的雁，在 3 条横向偏移审阅航道对中心与两翼做 1,449 条探针，最小净空 **0.183 BU**。动态翼尖和满能量可飞性留待运行时验证。

按现行 `ThirdPersonRig.graybox` 的 180、0.48 rad、50°，注视高度 6，领队高 8，模拟五个位置的同一架机位。检查点 A 面向 +Y，山口在左。五处共 65 条直接视线探针均通过，检查点 A 的 5.2 BU 通道投影宽约 **85 px**。画面展示可见的入口及贯通山脊的走廊；过远的山峰和近侧山顶会出画，路标用于对照地面。

灰盒和回导均验证 **15 条拼接边**。重新组装后位置差为 0，UV 差在容差内，最大拼边法线差 0.01238°。GLB 源角点及回导角点法线分别按 0.03° 与 0.12° 检查，最差为 0.00450° 和 0.08264°。三个独立 GLB 还核对原点、缩放、轴向、几何、UV、材质、内嵌贴图、纹理来源。回导后重跑走廊与镜头测量，另外从实际交付目录独立重开母版复验。

## 复现

在空临时目录运行。脚本读取相邻候选母版，图像与网格存进指定输出。材质沿用已在 ENV-001 记录过的 MAT-003 当前输入，源 PNG 按清单哈希核对。

```sh
blender -b --factory-startup -t 5 --python-exit-code 1 \
  --python ENV-010_generate.py -- /absolute/path/to/empty-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-010_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-010/v001
```

补充预览可用同样的后台参数运行两个预览脚本，各指定不同的空输出目录。飞越短片使用 ffmpeg。

## 待验与待登记

- 阴影下的岩层、回看入口与短路径的观感待负责人复核。待 FX-002、ENV-012、实际关卡、输入、能量、侧风与碰撞；待 USDZ / RealityKit 及 iPhone / iPad 真机。App 引用已有 iOS 27.2 构建与 340 项测试记录。
- `Assets/docs/asset-index.json` 登记候选条目、相对路径、母版、三份 GLB、依赖及 QA。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 登记项目原创几何、MAT-003 贴图来源、ENV-009 和 CHR-001 审阅输入。App 正式导出后补正式路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 和 `plans/active/goose-preview-model-cleanup.md` 补候选状态、实测证据与后续。
