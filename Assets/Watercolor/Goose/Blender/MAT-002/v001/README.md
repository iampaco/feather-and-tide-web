# MAT-002 斑头雁羽色材质

Blender 5.2.2 LTS，v001。 [羽色源文件](MAT-002_goose_plumage.blend)从已确认的 MAT-001/v001 复制材质节点，沿用相同的水彩色阶算法和细纸纹强度。简化雁形用于检视材质。

| 材质 | 作用 |
| --- | --- |
| `Head` | 暖灰白底色与两道炭褐横纹。UV 的 U 沿头围，接缝在头顶，V=0 为后脑、V=1 为喙侧。套用到正式头部时需匹配这套 UV，或重新投射头纹。 |
| `Body_Leader` / `Body_Follower` | 共用灰褐贴图。领队用乘色节点微调暖度，同伴使用贴图原色。 |
| `FlightFeather` | 翼端和尾部的深灰褐羽色。 |
| `BillFeet` | 喙和脚的低饱和暖橘。 |

四张 1024 × 1024 sRGB PNG 已打包进 Blender 源文件和 [GLB 样块](MAT-002_goose_plumage.glb)。Blender 的领队乘色在 GLB 内保存为 `baseColorFactor`。五个材质可在后续 .blend 文件中通过 File → Append → Material 追加。

## 预览与验收

[后上方近看](preview_rear_detail.png) · [顶视](preview_top.png) · [GLB 回导](preview_glb_roundtrip.png)

[原尺寸](preview_gameplay_1x.png) · [原尺寸冷光](preview_gameplay_cool.png) · [半尺寸](preview_gameplay_half.png)

玩法预览使用 852 × 393 横屏画布。按 `ThirdPersonRig.graybox` 复现后上方机位、50° 纵向视野和注视高度，样块体长对齐现有领队占位盒的 27.5 游戏单位。原尺寸在两种光下都能区分双纹，半尺寸下靠前的横纹容易变淡。屏占是 Blender 的预览估算。正式头部拓扑、飞行姿态和移动端显示留待接入复测。[QA](qa.json) · [材质与文件清单](asset_manifest.json)

## 复现

[生成脚本](MAT-002_goose_plumage_generate.py)从相邻的 MAT-001/v001 目录读取母版和脚本。在 Blender 5.2 的命令行使用空输出目录生成。

```sh
blender --background --factory-startup --python MAT-002_goose_plumage_generate.py -- /absolute/path/to/empty-output
```
