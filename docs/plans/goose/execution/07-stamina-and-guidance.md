# 07 · 常驻体力与游玩指引

2026-11-18。范围为 P0-D 斑头雁 HUD，依据负责人本次体验优化要求、GDD v2.0 §15.1 与 ADR-009/010。

## 玩家可见变化

- 可操作期间，顶部独立显示体力条与整数百分比；略过教学、观察、结阵、救援和等待同伴时仍保留。暂停后数值冻结，短暂落脚演出沿用全员到达信息。
- 偏低、危急、恢复中使用文字及颜色共同提示。数值直接读取模拟 `energy`，继续沿用原阈值、补给、检查点与胜负规则。
- 主提示使用 18–22px、说明使用 15–16px；地点标题单独呈现。纸色底、深色字用于普通提示，救援与危险使用深色底、浅色字。
- 起飞、滑翔、观察、复位、结阵、分岔、补给与落脚提示说明当前动作及其影响。触控、键位重设、镜像与能力点按设置继续影响对应文案。
- 体力移出临时提示卡，继续位于现有信息区内；原有 `ResizeObserver` 同时计入体力与提示高度，为边缘方向标记提供避让高度。HUD 不接管场景指针。

## 修改范围

`index.html`、`src/app/main.ts`、`src/app/style.css`、`tests/e2e/flight.spec.ts`、`tests/e2e/recovery.spec.ts` 与根目录 GDD。没有新增依赖或更改模拟、输入、相机、关卡、存档契约。共享能量控件在鲸篇仍称「能量」；未扩展鲸篇玩法。

## 验证记录

- `npm run check`：lint、格式、关卡/资产校验、113 项逻辑测试、严格类型检查和生产构建通过。构建仍报告主包超过 500 kB 的体积提示。
- Chromium 与 iPhone landscape WebKit 模拟：568×320、852×393、1024×768、1440×900 的镜像加大按钮布局均通过。验证主提示/说明字号、内容无横向溢出、与工具按钮无重叠、略过教学仍显示体力、数值与模拟同步。
- 在 S2 检查点验证正常、偏低、危急体力状态，以及实际消耗时进度条和百分比同步。教学初始湿地是安全区，不以其中体力下降作为断言。
- 截图复核修正了救援卡底色被普通卡片覆盖的问题，并保留背景色回归断言。
- 相关浏览器回归：67 项通过，7 项按平台适用性跳过。覆盖完整 `flight.spec.ts`，以及体力反馈、风机提示/路线可读性、救援、耗尽补给后的恢复、生物入口和 S6 的 11/12 等待与 12/12 落脚保存。命令为：

```sh
npx playwright test tests/e2e/flight.spec.ts tests/e2e/recovery.spec.ts tests/e2e/landscape.spec.ts tests/e2e/species-entry.spec.ts --project=chromium --project=mobile-webkit --workers=3 --grep 'flight.spec.ts|U03|S3 rescue circle|S4.*(warning|readable)|S08 V2-13|exhausted supply|T17 T23'
```

最终救援标题采用「接应同伴」，具体靠近、减速和接应进度由说明表达，避免已经接近时仍要求转身。最终构建再运行 `npx playwright test tests/e2e/recovery.spec.ts --project=chromium --project=mobile-webkit --workers=2 --grep 'S3 rescue circle'`：7 项通过、1 项按平台跳过，救援截图同步更新。

真实 iPhone/iPad 的拇指遮挡、阅读舒适度与连续触控尚未验证；浏览器模拟不能替代实机。此次不作实机帧率、内存或玩家研究结论。

## 截图

- [横屏 WebKit（镜像、放大按钮）](evidence/stamina-guidance/mobile-webkit.png)
- [桌面（镜像、放大按钮）](evidence/stamina-guidance/desktop.png)
- [体力危急](evidence/stamina-guidance/critical.png)
- [救援与常驻体力](evidence/stamina-guidance/rescue.png)
