# Pattern: History Growth Timeline

## When To Use

- 企业发展历程
- 战略演进路径
- 能力升级路线
- 年度里程碑复盘
- 从单一业务到平台化/生态化的升级叙事

## Information Structure

- 标题区：一句大标题 + 一句使命/价值观/核心结论。
- 主体区：3 个阶段节点，沿一条上升路径排列。
- 阶段信息：每个节点包含年份区间、阶段名称、阶段定位。
- 当前阶段区：右侧或右下方使用白色卡片承载 3-5 条关键动作。
- 底部说明区：可选，用于写页面用途、结论补充或页脚标签。

## Visual Grammar

- 主视觉：一条酒红色上升路径，表达增长与升级。
- 节点：酒红圆形节点 + 白色简化图标；节点可随内容重新定位，不要求固定坐标。
- 结构线：使用蓝灰色细线或边框，避免过度装饰。
- 信息密度：三阶段最稳；四阶段可用，但要降低文字密度；五阶段以上建议改横向路线图或表格。
- 可变参数：阶段数量、节点图标、右侧卡片位置、底部说明区都可由 Executor 根据内容重排。

## SIE Adaptation

- 颜色：主强调 `#AD053D`，次强调 `#932341`，结构线 `#7C969D` / `#B4C6CA`。
- 背景：内容页优先 `#F9FCFC` 或 `#F2F6F6`。
- 字体：统一 `Microsoft YaHei`。
- 卡片：右侧行动卡优先白底，标题条可用 `#4A5558`。
- 不要做：不要让增长线穿过正文，不要使用低对比黑底正文区，不要把参考图像素级复刻。

## Executor Prompt Recipe

```text
请基于 SIE 咨询风格绘制一页“发展历程 / 能力升级路径”SVG。

你需要保留的信息结构：
- 上方：页面标题 + 一句使命/价值观/核心结论
- 中部：3 个阶段节点，沿一条上升路径组织
- 每个阶段：年份区间、阶段名称、阶段定位
- 右侧或右下：当前阶段关键动作卡片，承载 3-5 条要点

视觉要求：
- 使用 SIE 酒红 #AD053D 作为增长线和阶段节点主色
- 使用蓝灰 #7C969D / #B4C6CA 做结构线、边框和弱分隔
- 内容页使用浅底 + 白卡，保证正文可读
- 字体统一 Microsoft YaHei
- 可以根据实际文案自由调整节点位置、路径曲线和卡片位置
- 不要像素复刻参考图，不要把线条穿过正文

SVG 兼容要求：
- viewBox="0 0 1280 720"
- 只用原生 rect/circle/line/path/polygon/text/tspan
- 禁止 foreignObject、script、远程图片、clipPath、mask、textPath
- 长文本拆成 tspan，保留换字余量
```

## Optional SVG Example

- 可选 SVG 示例：`my-ppt-skill/ppt-ai-core/templates/layouts/consulting_classic/03_content_history_growth_timeline.svg`
- 使用原则：它是参考资产，不是强制母版，也不是填空题。Executor 应优先按本模式卡和当前内容重新构图。
