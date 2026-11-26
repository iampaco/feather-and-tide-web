# MAT-004 湖面与浅水基础材质

Blender 5.2.2 LTS，v001。[水面材质库](MAT-004_water_surfaces.blend)沿用 MAT-001/v001 的 Principled BSDF 节点和纸纹强度。三张 1024 × 1024 PNG 将 sRGB Base Color 与直通 Alpha 打包在同一张贴图。使用 Blender 的 File → Append → Material 可追加三种材质。

| 材质 | 颜色与透明度 | UV |
| --- | --- | --- |
| `Water_Shallow` | 灰绿水面，泥沙和小石可透出，岸缘渐隐 | 每块使用一张 0–1 UV，边缘夹紧 |
| `Water_Lake` | 灰蓝水面，湖心更实，低对比横向色带与少量暖金 | 每块使用一张 0–1 UV，边缘夹紧 |
| `Water_River` | 灰青水面，色带顺河道，向两岸渐隐 | U 横跨河宽且保持 0–1，V 沿河道连续重复 |

浅水和湖面的 Alpha 描述样板岸线形状。实际岸线可重新烘焙 Alpha 或映射对应 UV。湖面和河流使用哑光静态色带，后续波纹由 `FX-006` 提供。贴图 Alpha 是美术参数。

## 预览与导出

[顶视](preview_top.png) · [斜视](preview_oblique.png) · [GLB 回导](preview_glb_roundtrip.png)

[GLB](MAT-004_water_surfaces.glb)包含三个可分别使用的水面网格与内嵌 RGBA 贴图，采用 glTF `BLEND`。预览中的泥岸取自 MAT-003，泥岸、小石、相机和灯光仅用于对照岸缘。

[资产清单](asset_manifest.json)记录依赖、贴图、UV 与文件哈希。[QA](qa.json)记录 Alpha、河段重复和回导检查。RealityKit 的透明排序、正式岸线与 iPhone / iPad 真机效果留待接入复测。

## 复现

[生成脚本](MAT-004_water_surfaces_generate.py)读取相邻的 MAT-001/v001 和 MAT-003/v001。在 Blender 5.2 中指定空输出目录。

```sh
blender --background --factory-startup --python MAT-004_water_surfaces_generate.py -- /absolute/path/to/empty-output
```
