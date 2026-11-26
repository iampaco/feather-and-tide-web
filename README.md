# 羽与潮 · Feather & Tide

从标题页点「进入游戏」，即可自由选择斑头雁 S0–S6、鲸 W0–W4 或驯鹿 R0–R4 的旅程。斑头雁篇带领 12 只雁经过晨雾湿地、岔路、侧风河谷和风电外围，最后在芦苇湿地落脚。飞行实验场用于练习操控。规则试飞提供使用旅程规则的短航线。

首次打开游戏默认显示英文。标题页右上角的语言菜单可即时切换 English 或中文，浏览器会记住选择。

## 启动

使用 Node.js 24 和 npm 11。在仓库根目录运行以下命令。

```sh
npm ci
npm run dev
```

选择页展现斑头雁、鲸与驯鹿的水彩栖息地。三种生物在开发和生产构建中均可直接开始旅程。标题页的「原声试听」可播放主题曲、斑头雁与鲸的配乐。

在标题页选择「练习飞行 → 顺风转弯试飞」，可以单独练习顺风洲 S1 的两条航线。宽水面需沿航标缓转绕过芦苇浅滩。顺风短线可解阵斜切、转正结阵并短暂加速，留意收速等队尾。带 12 只雁落脚后可以比较剩余体力。暂停、失败或落脚后都可从起点重飞。每次试飞独立使用自己的初始状态。

飞行时仅播放配乐。斑头雁配乐在起飞后淡入，随飞行阶段调整音量，全员落脚时进入主题曲尾奏。可在设置中关闭配乐。

桌面可在标题页按 Enter 打开生物选择。用 WASD 或方向键飞行，任一 Shift 加速，C 或左 Alt 缓行，Space 结阵。按住鼠标左键或右键拖动空白场景，左右可 360° 环视，上下可调整俯视角。开启「设置 → 镜头 → 宽幅鼠标环绕」可把鼠标俯视范围扩大到 20°–80°，接近地形或设施时镜头会抬高。R 复位镜头，Esc 暂停或继续。可在「设置 → 键鼠操作」更改主要键位。

横屏触控用左侧浮动摇杆、右侧拖镜环视和右下结阵键。设置里可以镜像、放大按钮、切换结阵方式与镜头映射，或关闭声音与减弱动态。

## 鲸篇原型

在生物选择页选择「鲸」即可开始旅程。带六只鲸穿过船道与渔网，选择经过疏浚水域的近航道或安静航道，再过防波堤横流。鲸群可以在观鲸船减速区换气，再游向外海。桌面长按 Space 下潜，松开上浮；横屏触控用右下「下潜」。设置可改为点按切换。镜头、缓行、加速与暂停沿用飞行操作。

预览链接附加 `?whaleGraybox=1` 可载入灰盒鲸进行对照；`?diagnostics` 可查看当前路线、鲸群、检查点和渲染数据。路线图、回放及设备验收状态见[鲸篇执行记录](docs/plans/whale/04-execution-record.md)。

## 驯鹿篇原型

点「进入游戏 → 驯鹿 · 开始旅程」，带领 9 只鹿从冬林经涵洞、围栏和矿业廊道到春季苔原。

桌面用 WASD 或方向键步行，Shift 奔跑，C 或左 Alt 缓行，Space 等候。触屏用左侧摇杆、右侧拖镜和右下「等候」。在路肩收拢队伍，沿公路找到标有动物通道的涵洞。可用 `?diagnostics` 查看状态和渲染采样，用 `?reindeerGraybox=1` 对照灰盒角色。详见[驯鹿篇执行记录](docs/plans/reindeer/execution.md)。

## 验证生产构建

```sh
npm run check
npx playwright install chromium webkit
npm run test:e2e
npm run preview -- --host 0.0.0.0
```

在同一局域网的 iPhone 或 iPad Safari 打开终端中的 Network 地址。用横屏完成旅程。原旅程检查点仍写入浏览器 IndexedDB，刷新后可继续。旧漫游档保留但不读取或转换。落脚后可查看上次结果或开始新航程。

`npm run check` 包括 lint、格式、关卡与资源校验、Vitest、类型检查和生产构建。浏览器测试通过 Vite 预览访问 `dist/`。真实设备与首次玩家验收按执行记录推进。

## 项目资料

仓库包含 `public/assets/` 下的运行资源、校验所需的源素材和自动化测试使用的回放。其余美术原稿、开发过程截图和演示导出由项目负责人在本地归档，相关记录中的素材路径可用于查找原档。

- [玩法设计 GDD v2.0](Feather_Tide_Gameplay_Design_v2.0.md) · [技术设计 TDD v1.0](Feather_Tide_Threejs_TDD_v1.0.md)
- [执行记录](docs/plans/goose/execution/record.md) · [实机与首次玩家执行单](docs/plans/goose/execution/playtest-handoff.md)
- [驯鹿篇「苔原过路」开发计划与验收标准](docs/plans/reindeer/README.md)
- [双手操作 ADR-009](docs/adr/009-dual-hand-camera-controls.md)
- [原始素材库](Assets/README.md) · [Web 资产清单](public/assets/manifest.json)

入口与模式变更依据 [ADR-010](docs/adr/010-journey-only-entry.md)，验证与截图见[入口执行记录](docs/plans/goose/execution/journey-only-entry.md)。
