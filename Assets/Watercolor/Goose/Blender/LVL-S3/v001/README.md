# LVL-S3 河谷掉队救援

**v001 · needs_review · Blender 5.2.2 LTS**。建模规格书第 17–18 页，S3，P0。场景变体 `S3_Rescue`。

[可编辑母版](LVL-S3_S3_Rescue.blend) · [组装 GLB](LVL-S3_S3_Rescue.glb) · [摆位与运行时映射](s3_layout.json) · [清单](asset_manifest.json) · [独立回验](qa.json) · [复跑脚本](LVL-S3_generate.py)

## 固定后上方审阅

- [固定机位静音短片](preview_fixed_rear.mp4) · [驶入](preview_fixed_rear_approach.png) · [树梢先兆](preview_fixed_rear_tree_cue.png) · [同帧无风对照](comparison_tree_still.png) · [侧风先兆](preview_fixed_rear_crosswind.png)
- [阵风与救援光点](preview_fixed_rear_rescue.png) · [回头接应](preview_fixed_rear_return.png) · [归队](preview_fixed_rear_rejoined.png)
- [灰盒横屏](graybox_fixed_rear.png) · [灰盒技术顶视](graybox_top.png) · [材质技术顶视](preview_top.png)
- [GLB 回导阵风与光点](roundtrip_fixed_rear_rescue.png) · [GLB 回导回头接应](roundtrip_fixed_rear_return.png)

保留 Blender 的 +Z 向上、+Y 向前，GLB 轴映射 `(x,z,-y)`。0.9900 BU 对应 27.5 游戏单位。横屏源帧 852 × 393，H.264 在底部补一行。机位使用 Swift 的 180 游戏单位距离参数、0.48 rad 俯角参数、50° 纵向 FOV、6 游戏单位目标高，以及随首领共用的高度抬升。审阅抬升为 0.40 BU，领队根还包含 8 游戏单位的模型基准。机位距离、角度和 FOV 固定，沿世界轨迹跟随领队。

## 组装和控制

- 五段 ENV-007 河道保持原尺寸和原岸剖面，沿 X = −3、+Y 拼接。起止河床向干地收平。X = −12 … 12 的干燥门宽 24 BU，门内 2 BU 保持 Z = 0。参考水位 Z = −0.18。出口 `S3_Exit` 位于 `(0,64,0)`，对接 S4 的实际干地入口 `(2,−45,0)`。入口 `S3_Entry` 位于 `(0,0,0)`，接 S2 汇合。两锚点均朝 +Y。
- 河湾前沿置 ENV-012 的八棵带蒙皮风向树。ENV-005 芦苇主要分布在对岸，救援空地和接应带经过视线与地面验证。领队从东岸折回。第 12 只雁使用 ANM-009 的 `Call_Loop` 和 `Rejoin`，其他雁使用 ANM-001 的巡航。FX-009 的内嵌柔光和浅环放在东岸 OpenBank 延伸平地。
- 在审阅母版选择 `S3_WindControl` 可编辑 `windBearingRad`、`strength`、`motionScale` 和 `windSpeedBUPerSecond`。树梢和 FX-002 的预警带、阵风带、碎叶共用同一风向、强度和动效输入。曲线在时间轴 `Event envelopes` 组中。风场下风方向为 `(−.980,.200)`，树干和树梢用相同世界向量转换到各自关节空间。
- GLB 包含地面、水面、植被蒙皮和带空间摆位的视觉实例。兼容 glTF 的预警带、阵风带及柔光使用双面透明混合。效果显隐、粒子位移和树梢驱动通过 [摆位与运行时映射](s3_layout.json) 接入。角色所需的蒙皮和动作继续取自 ANM-009 / ANM-001。审阅动画、相机和远景静态背板保存在母版。

## 离线实测

- 独立 Blender 后台进程从实际交付目录重开母版，再在全新场景读入 GLB，按相同接口重新建立审阅输入。GLB 原始坐标、效件材质和锚点均由独立脚本读取。
- 两端门内采样 970 次，24 BU 范围内干燥平整。OpenBank 原平台做 880 次采样，东侧光点支撑区做 81 次采样。1.30 BU 宽的接应带做 305 次采样，均落在连续干地。审阅从离队到回接约 12.08 秒，轨迹约 21.35 BU，随后用 2.00 秒回到队形。短片覆盖上述离队、回头和归队片段。
- 半帧检查中，树梢首次达到审阅中可辨位移阈值为 0.50 秒，预警带首次进入画幅为 0.75 秒，阵风约 1.42 秒，离队示例约 1.92 秒。对进入画幅的光点，树木、芦苇和地形的射线检查及风带投影留白读数见 [QA](qa.json)。
- 完整解码 H.264 共 137 帧，静音。候选素材 QA 引用已有 iPhone 18 Pro / iOS 27.2 模拟器灰盒与 340 项测试记录。

## 复跑

从项目根目录运行 Blender，PATH 需包含 ffmpeg、ffprobe。生成和独立回验各用新的空目录。

```sh
lib="$PWD/Assets/Watercolor/Goose/Blender"
asset="$lib/LVL-S3/v001"
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python "$asset/LVL-S3_generate.py" -- --library "$lib" --out /tmp/ft-s3-rebuild
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python "$asset/LVL-S3_generate.py" -- --library "$lib" --out /tmp/ft-s3-recheck --verify "$asset"
```

## 待验和共用登记

- 待负责人复核侧风及引导点的移动端视觉。碰撞、实际掉队事件及接应路径、缓行归队、失败时回检查点 A 的行为及阶段时长由 App 接入后验收。USDZ、RealityKit／App 接入和 iPhone／iPad 真机待验。已对照项目设计红线。
- [共用素材索引](../../../../../docs/asset-index.json) 待登记母版、GLB、布局、短片和 QA。[候选资产台账](../../../../../docs/asset-ledger.md) 和 [运行时资产台账](../../../../../../docs/references/asset-ledger.md) 待登记组装来源、继承贴图、候选状态和最终接入记录。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json) 和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md) 待登记候选和离线验收结果。资产源文件和所用贴图 SHA-256 见 [清单](asset_manifest.json)。
