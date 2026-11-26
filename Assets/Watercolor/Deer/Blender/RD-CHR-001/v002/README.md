# RD-CHR-001 · 驯鹿 v002

原创驯鹿网格、顶点色和动画。可使用 [生成脚本](generate.py) 重建 [Blender 源](reindeer-v002.blend) 及 Web GLB。运行时文件、权属和哈希见项目资产清单。

- glTF 坐标为 +Y 向上、+Z 向前，原点位于蹄下地面。世界位置由模拟提供。
- 成年鹿使用中性形态。领鹿使用 `Leader`，幼鹿使用 `Calf`。三个体型共享同一个骨架、索引网格和顶点色材质。
- `Idle`、`Walk`、`Run`、`Call`、`Settle` 只驱动骨架。`HoofContact_FL`、`HoofContact_FR`、`HoofContact_HL`、`HoofContact_HR` 随蹄移动，供接地阴影采样。
- 以 Blender 5.2.2 执行 `--background --factory-startup --python` 加本目录的 `generate.py`。重新导出后同步清单中的文件长度和 SHA-256。
