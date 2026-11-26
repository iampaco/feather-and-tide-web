# 仅旅程与生物选择入口 · 2026-11-18

依据：[ADR-010](../../../adr/010-journey-only-entry.md)。项目负责人要求取消漫游，首屏先选生物，再进入引导旅程。

## 实现

- 首屏展示斑头雁、鲸、驯鹿，斑头雁直接进入 S0 起飞教学。鲸按已有开发/预览开关开放 W0–W4 原型；驯鹿尚未开放。
- 首次无模式、年份或二次开始确认。已有有效旅程档仍允许继续或重新出发。
- 初版曾将片头改为主动播放，后续按项目负责人决定移除影片与播放入口。练习与规则试飞使用旅程规则。
- `GameMode` 仅接受 `journey`，四份关卡数据仅声明旅程。删除漫游规则和自动接应参数，救援需主动接近并缓行。
- 保留存档版本和旅程槽键；旧漫游槽保留但不读取、不覆盖、不转换。模式校验拒绝旧漫游快照及运行记录；旅程离队成员必须带有有效救援计时。
- 修正鲸资源失败后改选斑头雁时的加载提示清理。

主要涉及 `index.html`、`src/app/main.ts`、样式及片头生命周期、模式类型与规则、雁/鲸救援、关卡 Schema、存档校验、四份关卡数据及相应测试。没有升级依赖或更改模拟时钟、相机映射和全员到达谓词。

## 验证

- `npm run check`：lint、格式、关卡数据、资源清单、113 项单元/集成测试、严格类型和生产构建通过。
- 默认生产构建完整回归：141 项通过、58 项按平台/鲸开关跳过；2 项旧漫游自动归队的落脚用例失败。已改为有效的旅程救援快照与接应前提，定向复测结果见下方最终构建复核项。
- 鲸开关构建的入口/存档专项：18 项通过，覆盖 Chromium 与模拟 iPhone 横屏 WebKit。包括三生物入口、旧漫游槽隔离、鲸损坏存档、跨标签页保护、物种独立存档、全员汇合、加载重试和 WebGL 恢复。
- 最终生产构建定向复核：18 项通过、2 项按平台跳过。覆盖生物选择、旧漫游槽隔离、旧旅程档继续、接应条件提示、11/12 等待、旅程接应后 12/12 落脚与 WebGL 暂停恢复；前述两项落脚用例在 Chromium 与横屏 WebKit 均已通过。

浏览器回归使用独立输出目录。首轮暴露的旧菜单选择器残留和同时运行时的输出目录冲突已修正，再重新运行。原先依赖漫游自动归队的落脚测试改用带有效计时、满足缓行接应条件的旅程快照。未降低危险损耗、救援、快照或全员胜利的原有正确断言；原漫游专用验收按 ADR-010 显式替换。

鲸专项使用 `VITE_FEATHER_WHALE=1` 构建到临时目录，独立本地预览端口 4184。命令为：

```sh
VITE_FEATHER_WHALE=1 FEATHER_E2E_PORT=4184 npm run test:e2e -- tests/e2e/whale.spec.ts tests/e2e/species-entry.spec.ts --grep 'T17|T23|WH-A11|independent saves|W4 only settles' --project=chromium --project=mobile-webkit --workers=1 --output=/tmp/ft-whale-journey-e2e
```

## 视觉证据与未验证项

截图来自 Playwright 的模拟 iPhone 横屏 WebKit，尺寸 852 × 393，并已人工查看。不是实体设备或帧率测量。

![生物选择](evidence/journey-only/species-selection-mobile-webkit.png)

![选择后直接进入起飞引导](evidence/journey-only/guided-journey-mobile-webkit.png)

真实 iPhone/iPad Safari 的触感、系统手势和长时间性能未验证。构建仍提示主包超过 500 kB；本次未做无关拆包优化。未新增资产，原有资源清单与授权校验通过。

最终定向复核命令：

```sh
npm run test:e2e -- tests/e2e/species-entry.spec.ts tests/e2e/recovery.spec.ts tests/e2e/flight.spec.ts --grep 'T17|T23|real landing area|continue a valid|S3 rescue circle|losing the WebGL' --project=chromium --project=mobile-webkit --workers=2 --output=/tmp/ft-journey-final-e2e
```
