# Pode-Agent E2E Test Prompts

基于当前仓库里的设计文档和代码结构整理，目标是从真实用户视角覆盖 CLI、REPL、工具调用、权限、Plan Mode、Skills、Plugins、MCP、Hooks、SubAgent、会话恢复等关键链路。

这些内容不是测试代码，而是可直接拿来做人测、录制回归脚本、或转成自动化 E2E 用例的输入文本。

## 使用建议

1. 先按依赖把测试分组执行：无需 API Key、需要 API Key、需要插件/Mock MCP、需要多轮交互。
2. 建议准备一个固定测试仓库，至少包含 Python 文件、Markdown、JSON、ipynb、`.pode/commands/`、`.pode/skills/`、测试插件目录、Mock MCP server。
3. 对需要确认权限的场景，分别测一遍“允许一次”“永久允许”“拒绝”。
4. 对多轮测试，尽量保留完整 Session，方便验证 JSONL 日志、上下文压缩、恢复和子代理 transcript。

## A. CLI 基础能力

1. `pode --version`
2. `pode --help`
3. `pode`
4. `pode "只回复：print mode ok"`
5. `pode --output-format text "只回复：text format ok"`
6. `pode --output-format json "返回一个最简单的 JSON 结果"`
7. `pode --verbose "请读取 ./not-found-file.txt，并明确展示失败原因"`
8. `pode --safe "请在当前目录新建 SAFE_MODE_TEST.md，内容为 hello"`

## B. 配置与模型路由

1. `pode config list`
2. `pode config get theme`
3. `pode config set theme light`
4. `pode config get theme`
5. `pode config set verbose true`
6. `pode config get verbose`
7. `pode --model claude-sonnet-4-5-20251101 "只回复：anthropic route ok"`
8. `pode --model gpt-5 "只回复：openai route ok"`
9. `pode config set model_pointers.quick claude-haiku-4-5-20251001`
10. `pode config get model_pointers.quick`

## C. REPL 与终端 UI 手工输入

1. 打开 `uv run pode`，确认 Logo、欢迎区、输入框正常显示。
2. 在输入框中键入 `hello world`，再连续按 Backspace，确认删除行为正常。
3. 输入一长串文本后按左/右方向键，确认光标移动正常。
4. 输入 `abcdef` 后使用 `Ctrl+A`、`Ctrl+E`，确认能跳到行首/行尾。
5. 连续发送 3 条消息后，使用历史导航确认可以取回上一条和更早的输入。
6. 在长回复流式输出过程中，确认界面不会卡死，文本会持续刷新。
7. 在有权限请求时，确认权限对话框能正确显示工具类型、输入摘要和确认选项。
8. 在空输入框下连续按两次 `Ctrl+C`，确认按预期退出。

## D. 项目感知、上下文与 @mention

1. `请先告诉我这个仓库是做什么的，只根据你自动收集到的项目上下文回答。`
2. `请阅读 @README.md，用 5 句话总结这个项目的目标、技术栈和当前进度。`
3. `请同时阅读 @README.md 和 @docs/architecture.md，说明这两个文档在系统分层上的一致点和差异点。`
4. `请阅读 @docs/plan-mode.md，总结 Plan Mode 的目标、进入方式、退出方式和持久化方式。`
5. `请阅读 @docs/subagent-system.md，说明子代理和主代理的上下文隔离是如何设计的。`
6. `请阅读 @docs/skill-system.md 和 @docs/tools-system.md，对比 Skill、Tool、Slash Command 三者的定位。`
7. `请阅读 @docs/not-exist.md，如果文件不存在请明确报错，不要编造内容。`
8. `请基于当前项目上下文，告诉我最值得优先测试的 5 个高风险功能点。`

## E. 文件系统、搜索与代码理解

1. `请列出当前仓库顶层目录，并说明每个目录的大致职责。`
2. `请在当前仓库中找出所有定义了 Tool 子类的文件，并按功能域分组。`
3. `请搜索 enter_plan_mode 的定义、调用链路和相关文档引用。`
4. `请搜索 TaskTool、TaskOutputTool 和 background task 的实现位置，并总结它们如何协作。`
5. `请搜索所有 plugin marketplace 相关 CLI 命令，并列出命令名和用途。`
6. `请找出所有处理 @mention 的实现和文档说明，并总结支持的语法。`
7. `请对比 docs/testing-strategy.md 和当前代码目录，指出哪些 E2E 场景已经有明显实现基础。`
8. `请定位 REPL 输入处理相关文件，并说明当前输入事件是如何集中处理的。`

## F. Bash、编辑与写入链路

1. `请运行一个只读命令，告诉我当前仓库的 git 状态摘要。`
2. `请运行一个只读命令，列出 docs 目录下所有 Markdown 文件。`
3. `请在当前目录创建一个文件 E2E_WRITE_TEST.txt，内容为 first line。`
4. `请把 E2E_WRITE_TEST.txt 的内容改成 second line，并说明你改了什么。`
5. `请在当前目录再创建一个 E2E_MULTI_EDIT.txt，然后一次完成 3 处文本替换。`
6. `请尝试读取一个不存在的文件 ./missing/none.py，并只返回真实错误。`
7. `请执行一个会失败的命令，并把 stdout、stderr 和 exit code 分开总结给我。`
8. `请执行一个需要权限确认的命令：创建目录 ./tmp-e2e-output，然后列出该目录内容。`
9. `请删除 ./tmp-e2e-output 目录。执行前必须先确认权限。`
10. `请在 safe mode 下再次尝试创建一个文件，并解释为什么当前模式下不能直接执行。`

## G. 代码修改类任务

1. `请在一个临时测试文件里新增一个 hello_world 函数，只做最小改动。`
2. `请把临时测试文件中的 main 重命名为 run_main，并同步更新所有引用。`
3. `请在不改逻辑的前提下，重排一个临时 Python 文件里的 import 顺序。`
4. `请把一个长函数拆成两个小函数，并解释拆分依据。`
5. `请只修复一个明确的语法错误，不要顺手做风格清理。`
6. `请对一个 JSON 文件做结构化修改，新增字段 e2e=true。`
7. `请编辑一个 Markdown 文件，在末尾追加一节 “E2E Notes”。`
8. `请在修改前先告诉我会改哪些文件，然后再执行。`

## H. Web Fetch、Web Search 与 Notebook

1. `请抓取 https://example.com，并用中文总结页面主旨。`
2. `请搜索 “Python 3.13 release notes official”，只总结最重要的 3 点。`
3. `请搜索 “Anthropic prompt caching documentation”，并告诉我是否适合这个项目。`
4. `请读取 @tests/fixtures/demo.ipynb（或任意测试 notebook），列出每个代码单元的大致作用。`
5. `请在测试 notebook 的最后新增一个代码单元，打印字符串 notebook e2e ok。`
6. `请尝试读取一个损坏的 notebook 文件，并明确说明解析失败。`

## I. Ask User 与 TodoWrite 交互

1. `请帮我生成一个发布说明，但在开始前你必须先问我版本号和目标受众。`
2. `版本号是 1.2.3，目标受众是内部开发者。现在继续。`
3. `请先把这项任务拆成 todo list，再逐项完成：阅读 README、阅读 architecture、输出架构摘要。`
4. `请把当前待办重新排序，优先级最高的放在最前面。`
5. `请把已经完成的 todo 标记出来，并告诉我还剩什么。`
6. `请为“补齐 MCP 回归测试”生成一份可执行待办列表，每项不超过一行。`

## J. Plan Mode

1. `先不要修改任何文件。请先为“给 pode plugin install 增加 dry-run 参数”制定一个完整计划，包含步骤、风险、验收标准。`
2. `在我批准前，不要做任何写操作。请继续补充刚才计划里的回滚方案和测试矩阵。`
3. `我批准这个计划。请按步骤执行，并在每完成一步后汇报进度。`
4. `我不批准这个计划，请取消执行，并说明你认为最大的风险是什么。`
5. `请先进入计划模式，分析如何为 TaskTool 增加更清晰的用户可见状态提示。`
6. `请在计划模式中尝试修改文件；如果当前模式不允许，请明确告诉我为什么不允许。`
7. `请先做只读探索，再给我一版“最小可行改动”的计划，不要给大而全方案。`
8. `如果会话恢复成功，请继续上一个未完成计划，并告诉我已经完成到第几步。`

## K. Skill、Slash Command 与自定义命令

1. `请列出当前项目里可发现的自定义命令和技能，并区分哪些是用户可见命令，哪些是隐藏技能。`
2. `如果当前项目里有适合“代码审查”的 skill，请自动使用它来审查最近修改过的文件。`
3. `如果当前项目里有适合“生成 commit message”的 command，请调用它，但不要真的执行 git commit。`
4. `/commit 只生成一条 Conventional Commit 风格的提交信息`
5. `/review-pr 请从风险、回归、缺失测试三个角度审查当前改动`
6. `请验证一个带 $ARGUMENTS 的 slash command 是否正确拿到了参数：release-notes 版本 1.2.3`
7. `请调用一个 frontmatter 中限制了 allowed-tools 的 skill，并说明后续工具范围是否被收窄。`
8. `请调用一个 frontmatter 中指定 model=haiku 的 skill，并说明是否切换到了对应模型指针。`
9. `请尝试调用一个不存在的 slash command /not-found-command，并明确报错。`
10. `请在执行完一个 skill 后，告诉我它有没有向上下文追加新的消息或约束。`

## L. Plugin 与 Marketplace CLI

1. `pode plugin list`
2. `pode plugin refresh`
3. `pode plugin marketplace list`
4. `pode plugin marketplace add file:./tests/fixtures/marketplace.json`
5. `pode plugin marketplace list`
6. `pode plugin marketplace update test-marketplace`
7. `pode plugin install file:./tests/fixtures/test-plugin --scope project`
8. `pode plugin list --scope project`
9. `pode plugin disable <plugin-id>`
10. `pode plugin enable <plugin-id>`
11. `pode plugin uninstall <plugin-id>`
12. `pode plugin install file:./tests/fixtures/broken-plugin --scope project`

## M. Hook 系统

前提建议：准备一个测试插件或项目级 hook 配置，至少包含 `user_prompt_submit`、`pre_tool_use`、`post_tool_use`、`stop` 四类 hook，并让每类 hook 都产生可观察行为。

1. `这条消息如果经过 user_prompt_submit hook 处理，请把附加上下文也体现在最终回答里。`
2. `请尝试执行一个被 pre_tool_use hook 明确禁止的命令，并告诉我为什么被拦截。`
3. `请执行 echo hook-test，确认 post_tool_use hook 是否会在结果里追加审计信息。`
4. `请只用一句话回答：done。`
5. `如果 stop hook 认为答案不完整，请继续补充直到满足格式要求。`
6. `请尝试读取一个敏感路径；如果 hook 会重写路径或阻止访问，请明确展示最终行为。`
7. `请说明当前回答是否受到了 hook 注入的额外 system prompt 影响。`
8. `请重复执行同一类操作两次，确认 hook 的行为是否稳定且不会无限重入。`

## N. MCP 客户端与动态工具

前提建议：准备一个 Mock MCP server 矩阵，至少覆盖以下组合：1 个正常工作的 stdio server、1 个正常工作的 SSE/HTTP server（如果当前版本声称支持）、1 个“能连上但不会完成 JSON-RPC roundtrip”的异常 SSE/HTTP endpoint、1 个明确返回 404/非 JSON/非法响应的异常 endpoint。每个 server 最好都提供 1 个只读工具、1 个有副作用工具，以及至少 1 个 resource。

1. `请告诉我当前可用的 MCP 工具有哪些，并按服务器名分组。`
2. `请调用测试 MCP 服务器上的只读工具，查询 demo 数据并原样总结返回结果。`
3. `请调用测试 MCP 服务器上的写操作工具；如果需要权限，请先征求我同意。`
4. `请尝试调用一个不存在的 MCP 工具，并明确给出真实错误。`
5. `请在我拒绝权限后，不要再次执行那个 MCP 写操作。`
6. `请在我允许一次权限后，仅执行一次 MCP 写操作，然后停止。`
7. `请在 MCP server 临时不可达的情况下重试一次，并说明最终失败原因。`
8. `请比较原生工具和 MCP 工具在权限策略上的差异。`
9. `请分别列出 stdio、SSE、HTTP 三类 MCP server 的 transport、连接状态、可发现工具数；如果某类 transport 当前未实现，请明确标注“未实现/不支持”，不要把它伪装成已连接但 0 工具。`
10. `请只使用 SSE MCP server 上的只读工具读取 demo 数据；如果 SSE transport 尚未真实支持，请明确报错，不要返回空结果、空对象或假成功。`
11. `请只使用 HTTP MCP server 上的只读工具读取 demo 数据；如果 HTTP transport 尚未真实支持，请明确报错，不要返回空结果、空对象或假成功。`
12. `请先列出某个 SSE/HTTP MCP server 暴露的工具，再立刻调用其中一个工具；如果工具发现阶段显示可用，调用阶段就必须完成真实 roundtrip，否则要明确指出是“发现成功但调用失败”，并给出真实原因。`
13. `请列出测试 MCP server 的 resources，再读取其中一个 resource；如果 transport 不支持 resources/list 或 resources/read，请给出真实错误，不要把空列表或空对象当成正常结果。`
14. `请接入一个会返回 404、HTML、非法 JSON 或非法 SSE 帧的 MCP endpoint，确认系统会把它标记为连接失败或请求失败，而不是“连接成功但没有工具”。`
15. `请同时接入一个正常 stdio server 和一个异常 SSE/HTTP server，确认异常 server 不会导致正常 server 的工具发现、调用结果或权限提示被吞掉、串线或混淆。`
16. `请让一个 SSE/HTTP server 在 initialize 阶段失败，然后再次查询当前 MCP 工具列表；确认失败服务器不会继续以“可用”状态出现在结果里。`
17. `请比较 CLI、会话日志和最终回答里展示的 MCP server 状态是否一致；“已连接”“未实现”“请求失败”“0 个工具”四种状态不要混淆。`

## O. SubAgent、后台任务与恢复

1. `请启动一个 Explore 子代理，找出所有与 permissions 相关的实现文件，并只返回汇总。`
2. `请启动一个 Plan 子代理，分析如何为 plugin marketplace update 增加缓存失效测试。`
3. `请启动一个 general-purpose 子代理，在后台扫描 docs 目录并生成架构摘要；先只告诉我 task id。`
4. `请查询刚才后台任务的状态；如果还没完成，就等待 5 秒后再查一次。`
5. `请读取刚才后台任务的最终输出，并总结它实际用了多少工具、耗时多久。`
6. `请尝试读取一个不存在的后台 task id，并明确报错。`
7. `请恢复 agent_id=<填写真实 id> 对应的子代理继续执行刚才未完成的任务。`
8. `请比较前台子代理和后台子代理的用户体验差异，并结合这次测试给建议。`

## P. 会话持久化、恢复与上下文压缩

1. `请记住这次测试标签：E2E-SESSION-001。后面我会问你。`
2. `请再记住第二个标签：E2E-SESSION-ALPHA。`
3. `现在请总结到目前为止，这个会话中你已经完成了哪些动作。`
4. `请告诉我我在前两轮让你记住的两个标签分别是什么。`
5. `如果当前会话支持恢复，请在重新打开后回答：我们上次测试记住的第一个标签是什么。`
6. `请在多轮长对话后，仍然保持最初目标：最后只告诉我第一次和最后一次提到的关键词。`

## Q. Print Mode 多轮替代与单轮精确输出

1. `pode "只输出 OK，不要解释"`
2. `pode "请用一句话总结当前项目，不要调用任何写工具"`
3. `pode --safe "请运行测试并自动修复失败"`
4. `pode --verbose "请搜索当前仓库中的 TaskTool，并说明如果查找失败应怎样展示错误"`
5. `pode --output-format json "返回字段 status=ok, mode=print"`

## R. 错误处理与边界条件

1. `请读取一个不存在的文件 ./does/not/exist.py，并明确报错，不要猜测文件内容。`
2. `请编辑一个不存在的文件，并说明是新建还是报错。`
3. `请在一个只读文件上执行写操作，并如实说明失败原因。`
4. `请执行一个超时命令，并在超时后停止等待。`
5. `请抓取一个不可达的 URL，并说明这是 DNS、连接失败还是超时。`
6. `请搜索一个完全不存在的符号名 __THIS_SYMBOL_SHOULD_NOT_EXIST__，并说明没有结果。`
7. `请让一个子代理在不存在的 agent type 上启动，并展示真实错误。`
8. `请安装一个非法 plugin 清单，观察是否能给出清晰验证错误。`
9. `请添加一个损坏的 marketplace.json 来源，观察 CLI 是否能正确拒绝。`
10. `请在没有 Bun 的环境下启动 REPL，确认错误信息能明确指出缺少 Bun。`
11. `请在 UI 入口文件缺失时启动 REPL，确认错误信息能明确指出缺少前端入口。`
12. `请在权限被拒绝后重试同一操作，确认不会绕过拒绝策略。`
13. `请配置一个 type=sse 或 type=http 但缺少 url 的 MCP server，确认系统会直接报配置错误，而不是进入“已连接”状态。`
14. `请连接一个能建立 TCP/HTTP 连接、但不会返回合法 JSON-RPC 响应的 MCP endpoint，确认 list_tools、call_tool、read_resource 都会暴露真实错误，而不是默默返回空结构。`
15. `请连接一个会在 initialize 成功后、后续 tools/list 或 tools/call 才失败的 MCP endpoint，确认系统不会把“初始化成功”错误外推成“整体可用”。`

## S. 综合链路回归场景

1. `请先阅读 @README.md 和 @docs/testing-strategy.md，然后给我一份“当前仓库最需要补的 E2E 用例清单”，先只规划不要改文件。`
2. `我批准你的计划。请在当前仓库里新增一份测试文档草稿，只覆盖 CLI、权限、Plan Mode 三部分。`
3. `请把这份测试文档再扩展到 Skill、MCP、SubAgent，并保证结构清晰。`
4. `请启动一个 Explore 子代理去核对 docs 和代码目录是否一致，主代理继续整理最终总结。`
5. `请把最终结果总结成：已验证、待验证、高风险未覆盖 三部分。`
6. `请同时验证一个正常 stdio MCP server、一个真实可用的 SSE/HTTP MCP server（若当前版本支持），以及一个故障 SSE/HTTP endpoint，最后总结哪些 transport 是真实可用，哪些只是配置层可见但运行层不可用。`

## T. 适合转成自动化断言的短文本

1. `只回复：ok`
2. `只回复 JSON：{"status":"ok"}`
3. `只回复当前仓库名`
4. `只回复当前工作目录的最后一级目录名`
5. `只回复 docs 目录下 Markdown 文件数量`
6. `只回复 theme 当前配置值`
7. `只回复当前是否处于 safe mode`
8. `只回复当前是否检测到可用 plugin`
9. `只回复当前是否检测到可用 MCP 工具`
10. `只回复当前是否存在活跃后台任务`
11. `只回复当前每个 MCP server 的 transport 和状态`
12. `只回复当前是否存在“显示已连接但无法完成 roundtrip”的 MCP server`
