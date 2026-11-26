# MAT-001 通用水彩材质母版

Blender 5.2.2 LTS，v001。五种材质已标记为 Blender 资产，可从 [源文件](MAT-001_watercolor_master.blend) 追加到其他制作文件。选用材质后将它赋给已有 UV 的网格。示范几何、布光和相机留在母版中供比较。

| 材质 | 用途 | 通道 |
| --- | --- | --- |
| `DryGround` | 暖褐干地样块 | sRGB Base Color |
| `PlantOpaque` | 双面芦苇几何 | sRGB Base Color |
| `PlantAlpha` | 双面植物卡片 | sRGB Base Color + 直通 Alpha，同一张 RGBA |
| `SoftStone` | 冷灰矿物色阶 | sRGB Base Color |
| `WaterFallback` | 用横向色带表现浅水的哑光底材 | sRGB Base Color |

五张 512 × 512 PNG 已打包进源文件。调整颜色时可替换节点中的 PNG，也可编辑生成脚本开头的色板后重新生成。各材质使用 Principled BSDF，金属度为 0，粗糙度按材质给定。

- [GLB 样块](MAT-001_watercolor_master.glb)包含 7 个示范网格与 5 张内嵌纹理。glTF 朝向为 Y 向上、−Z 向前。样块尺寸用于展示。
- [斜视预览](preview_iso.png)、[顶视预览](preview_top.png)和 [GLB 回导预览](preview_glb_roundtrip.png)使用同一套中性灯光。
- [清单](asset_manifest.json)记录色板、贴图、网格与文件哈希。[QA](qa.json)记录回导检查与待验项。

## 复现

在 Blender 新建 General 文件，在 Python Console 加载 [生成脚本](MAT-001_watercolor_master_generate.py) 并指定新的空输出目录。

```python
from pathlib import Path
import runpy

script = Path("/absolute/path/to/MAT-001_watercolor_master_generate.py")
generator = runpy.run_path(str(script))
generator["main"](Path("/absolute/path/to/empty-output"))
```

脚本在 Blender 内生成并打包贴图、导出 GLB、回导渲染并写入初步 QA。美术预览复核与游戏接入验收各自记录。
