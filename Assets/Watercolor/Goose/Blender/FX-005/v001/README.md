# FX-005 云影与光照软遮罩 · v001

**needs_review**。`CloudShadow` 以两张水平低对比遮罩表现云影漂移。同一根节点下可以单独调整冷灰 `CoolShadow` 和暖金 `DiffuseLight`。使用 ENV-018/v001 的 CloudPatch Alpha 拓宽明暗范围，借 MAT-001/v001 的 SoftStone 纸纹轻调色。审阅以 CHR-001 的雁形和源码尺寸的路径标记作参照。

[可编辑 Blender 母版](FX-005_CloudShadow.blend) · [两层遮罩 GLB](FX-005_CloudShadow.glb) · [清单](asset_manifest.json) · [QA](qa.json)

## 固定机位预览

- [灰盒载体](graybox_fixed_planes.png)
- [默认](preview_fixed_default.png) · [减弱](preview_fixed_reduced.png) · [关闭](preview_fixed_off.png)
- [冷灰影单独预览](preview_fixed_coolshadow.png) · [暖柔光单独预览](preview_fixed_diffuselight.png)
- [4 秒无声 H.264](preview_fixed_rear.mp4) · [GLB 回导复渲](roundtrip_fixed_rear.png)

固定镜头复现 `ThirdPersonRig.graybox` 的距离 180 游戏单位、俯仰 0.48 rad、纵向视角 50°、注视高 6，使用 0.9900 BU 对齐 27.5 游戏单位。所有画面为 852 × 393，H.264 为 852 × 394，底部补一行。

## 结构与控制

| 子对象 | 审阅载体宽深 | 局部位置 XYZ（BU） | 贴图 |
| --- | --- | --- | --- |
| `CoolShadow` | 32 × 24 BU | (−8, 9.5, 0.012) | [512 × 512 RGBA](textures/ft_goose_vfx_cloud_shadow_alpha.png) |
| `DiffuseLight` | 37 × 27.5 BU | (10, 11.5, 0.024) | [512 × 512 RGBA](textures/ft_goose_vfx_cloud_light_alpha.png) |

- 两层总计 4 三角面，从上方可见，Alpha Blend、Unlit、Clamp To Edge。Blender 地面为 XY，枢轴 `CloudShadow` 在 (0,0,0)，导出转换为 `(x,y,z) → (x,z,-y)`。两张 PNG 在母版和 GLB 内打包。
- 在 Blender 中修改 `CloudShadow` 的 `CloudShadow_Drift_Review` 动作与每个材质的 `Review strength` 倍率。时间线 1–97 帧、24 fps，对应横向匀速漂 0.78 BU/s 的 4 秒样段。默认、减弱和关闭倍率分别为 1、0.35、0。山口 1.28 BU/s 为建议参数，样片使用默认速度。
- GLB 提供静态地面载体。接入时输入接收地面/水面的变换、水平风方向及速度、经过时间、遮罩强度和设置倍率。坡面接入可以把同一贴图投射到接收表面。按地形调整偏移，遮罩在地表上方并留在路径层下方。场景代码负责深度排序和跨地块过渡。材质数值可按白昼色板做平缓调整。
- 资产和预览数据使用关卡装饰为用途。碰撞、触发和路线逻辑继续由游戏负责。可视化验收依据为固定镜头的低对比渐变与无遮挡记录。实际试玩中是否会与危险区或路线边界混淆仍待验证。

## 独立回验

- 从实际交付目录重开 .blend、回导 GLB，验证 3 个节点、两层几何、局部变换、UV、法线与两张 PNG 的字节。GLB 回导复渲与默认画面平均通道误差 0.288/255，99 分位为 2/255。
- 冷、暖贴图峰值 Alpha 分别为 37/255、29/255，四周为 0，贴图相邻像素 Alpha 最多变化 1/255。默认相对关闭画面明度范围变化约 −7.71 至 +7.99/255，变化量的相邻像素差 99 分位为 1/255。减弱后绝对明度变化 99 分位从 6.77/255 降至 2.35/255。
- 九个漂移相位中，33 个标记和六只审阅雁的 111,042 个在画投影视线均位于遮罩之上。97 个时间线样本机位矩阵一致。短片全部 48 帧通过解码，确认无音轨。本轮对照项目红线清单审查。

## 复跑

需 Blender 5.2，PATH 中包含 ffmpeg 和 ffprobe。两条命令分别使用独立空输出目录。

```sh
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python FX-005_generate.py -- /tmp/ft-fx005-output
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python FX-005_recheck.py -- "$PWD" /tmp/ft-fx005-recheck
```

## 待验与登记

待负责人审阅色调与动效。USDZ、App 接入、RealityKit 透明排序、运行时地形贴合与山口速度、辅助设置、实际玩法辨识及 iPhone／iPad 真机待验。本轮引用 active 计划内 iOS 27.2 模拟器基线。

待登记 `Assets/docs/asset-index.json`、`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md`、`完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 的 FX-005 及 `plans/active/goose-preview-model-cleanup.md`，补录派生贴图、候选路径、离线证据和后续接入项。
