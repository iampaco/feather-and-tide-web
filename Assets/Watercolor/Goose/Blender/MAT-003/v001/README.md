# MAT-003 山岩与湿地地表纹理

Blender 5.2.2 LTS，v001。 [可编辑材质库](MAT-003_wetland_rock.blend)沿用 MAT-001 的 Principled BSDF 节点、低饱和水彩色阶和纸纹强度。五张 1024 × 1024 sRGB Base Color PNG 均为 U/V 可重复贴图，已打包进源文件。通过 Blender 的 File → Append → Material 可以在其他文件中使用。

| 材质 | 表现 |
| --- | --- |
| `GrassFlat` | 雾绿草滩，局部浅黄草色与细簇 |
| `MudBank` | 暖褐泥岸，柔和沉积色带 |
| `MossStone` | 灰石底色与低对比苔绿晕染 |
| `MountainRock` | 灰蓝山岩，断续斜向岩层 |
| `ShallowMargin` | 青绿浅滩底色与泥沙色块，作为浅水下的地表 |

## 预览与导出

[顶视对照](preview_top.png)和[小尺寸顶视](preview_repeat_small.png)对比单张贴图与 4 × 4 平铺。[斜视转角](preview_corner.png)展示独立网格在坡面转折处如何接续 UV。转角的光照明暗来自坡面法线，纹理坐标沿坡长保持连续。

[GLB 样块](MAT-003_wetland_rock.glb)包含五个材质和 17 段测试网格。[回导预览](preview_glb_roundtrip.png)使用相同灯光和机位。应用到正式地块时，共边需要相同的 UV 或相差整数的 UV。浅滩色块是地表材质，湖面与浅水表层由 MAT-004 制作。

[资产清单](asset_manifest.json)记录来源、色板和哈希。[QA](qa.json)记录边缘采样、共边、回导和目视检查。RealityKit 接入与 iPhone、iPad 真机效果留待关卡拼装时验证。

## 复现

[生成脚本](MAT-003_wetland_rock_generate.py)读取相邻的 MAT-001/v001。用 Blender 5.2 在空输出目录生成。

```sh
blender --background --factory-startup --python MAT-003_wetland_rock_generate.py -- /absolute/path/to/empty-output
```
