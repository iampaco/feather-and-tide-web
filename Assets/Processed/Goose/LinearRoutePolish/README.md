# 斑头雁单线地景精修配方

私有模拟器 Debug 预览。输入是项目内已登记原稿及上一版已校验的全航线预览。着色参考 V07 的暖浅水和蓝灰远山。航线、扫掠、起飞休整与落脚点由既有 Swift 布局给出。[V07 参考](../../../../docs/references/m5-style/dusk-wetland-v07-reference-only.png) · [正式素材台账](../../../../docs/references/asset-ledger.md)

| 输入 | 输出与处理 |
| --- | --- |
| MAT-003 湿泥、草边；MAT-004 河水、浅水；ENV-016 保护湿地和原芦苇 | `ft_goose_linear_landscape.usdz` 和同名 JPG。连续地表承接保护湿地和出口补给岸，以局部河岸起伏、疏密分组植被和浅水纹区分通行水道与停歇侧湾。运行时的 ENV-016 保留原芦苇，使用新连续地表覆盖原地块。 |
| LVL-S0 / S1 上版适配件，MAT-003 / MAT-004，FX-004 | `ft_goose_scene_s0.usdz` 中的一张连续地面和 `ft_goose_opening_terrain_s0.jpg` 从起飞泥滩铺到第一浅岸。`ft_goose_scene_s1.usdz` 保留浅岸锚点、岸石及重新安放的芦苇。FX-004 的低雾向两侧压低，暖色碎水光沿浅湾穿过雾口。首岸使用河道图集对色，下沉到重叠区。 |
| LVL-S6 的 M10a 导出及源布局，MAT-003 / MAT-004 | `ft_goose_linear_basin.usdz` 与从其解出的 `ft_goose_linear_basin_paint.png`。深水沿西侧浅湾向内，东池水线分开。出口对色、干地及水线以终点原始锚点锁高。 |
| ENV-006 A/B/C、ENV-011 三款岩石、MAT-003 三张原贴图 | `ft_goose_linear_ground_details.usdz`。Blender 导入六份源 GLB，按三段地表高程贴地组装，以区段合并网格并保留原材质。`ground_detail.py` 按同一世界坐标烘焙接触阴影、干岸色阶和碎湿边。模型位置避开起落位和扫掠区。 |
| ENV-009 A / B / C，STR-001 | 复用已校验的三款远山与风机导出。远山层级与色调在 RealityKit 固定场景中计算。带 `ShallowWaterGlints` 的地表已移除旧底座印记。16 处湿痕与水线在运行时随风机和扫掠共用圆心。 |

## 重建

需要 Python 3 的 NumPy / Pillow，以及 Blender 5.2.2 和其带 OpenUSD 的 Python。默认使用 Mac 上的 `/Applications/Blender.app`，可通过 `FT_BLENDER_PATH`、`FT_USD_PYTHON` 指定本机安装。由项目根目录运行。

```bash
Assets/Processed/Goose/LinearRoutePolish/prepare.sh /tmp/feather-tide-polish-export
```

配方先核验基线 ZIP，然后在指定目录生成 `GooseLinearPreview/`。远山 B/C 逐文件核对上轮清单后从场景细化 ZIP 复用。开场、河道、盆地与新地表模型的主要导出登记配方和布局散列，全部导出记录 SHA-256 并执行几何读回。USDZ 的封装时间戳会改变整包散列，交付清单标识本轮实际交付的字节。安装只加载该目录下的私有预览内容。

[本轮交付文件及来源 SHA-256](preview-manifest-ground-detail.json) · [本轮 ZIP 接触点读回](../../../../docs/playtests/goose-linear-ground-detail/terrain-probes.txt) · [前版地景清单](preview-manifest-art-pass.json) · [场景细化版清单](preview-manifest-detail.json)
