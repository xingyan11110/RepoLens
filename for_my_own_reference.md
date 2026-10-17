# 一、几千行的代码，正常人到底怎么看？
先说结论：一般不会从第一行读到最后一行。 这不仅效率低，还很容易读完就忘。
无论是几千行的 .py、.sh，还是其他语言的文件，都可以用类似的方法。

1. 第一步：先看目录结构
先知道项目分成哪些模块，不要马上钻进某个大文件。

2. 第二步：看函数名和入口
先了解程序有哪些功能、从哪里启动，再决定读哪个函数。

3. 第三步：沿调用关系追踪
找到一个函数后，弄清楚谁调用它、它又调用谁。

4. 第四步：遇到问题再深入
只精读当前任务需要理解的部分，不要求一口气弄懂整个项目。

# 二、项目架构（Architecture）

| 部分  | 文件或目录                               | 作用                               |
| --- | ----------------------------------- | -------------------------------- |
| 入口  | `repolens.sh`                       | 命令行入口，负责协调整个流程                   |
| 程序库 | `lib/`                              | 存放模块化的 Bash 代码，例如核心逻辑、日志、模板、并行执行 |
| 配置  | `config/domains.json`               | 登记有哪些 lenses，以及它们属于什么领域          |
| 配置  | `config/label-colors.json`          | 配置 GitHub 标签的颜色                  |
| 提示词 | `prompts/_base/`                    | 不同模式共用的基础提示词模板                   |
| 提示词 | `prompts/lenses/<domain>/<lens>.md` | 各个具体分析任务的提示词                     |
| 日志  | `logs/<run-id>/`                    | 保存每次运行产生的日志；该目录被 Git 忽略          |

例如，你希望 RepoLens 检查 Python 项目的安全问题：

1. `prompts/` 告诉 AI 应重点检查什么。

2. `config/` 登记有哪些检查任务，以及任务属于哪个领域。

3. `repolens.sh` 负责组织运行流程。

4. `lib/` 中的函数负责具体的调度、模板处理、日志等工作。

5. `logs/` 保存运行结果。

注意：`lib/` 是程序代码库，不是存放 AI 模型的地方。

# 三、如何添加新的 Lens（Adding a New Lens）

原文认为，新增一个分析任务通常不需要修改程序代码，只需要完成以下三步：

1. 在 `prompts/lenses/<domain>/<lens-id>.md` 创建新的提示词文件。

2. 在文件中添加 YAML 前置元数据（frontmatter），包含 `id`、`domain`、`name`、`role` 等字段，并在正文中编写 `## Your Expert Focus`，说明这个专家需要重点检查什么。

3. 在 `config/domains.json` 对应的领域下，添加新 lens 的 ID。

# 这里最值得注意的是：新增一种检查能力，主要通过新增提示词和配置来完成，而不一定要改动核心程序。

这是一种偏配置驱动的设计。

# 四、关键设计决策（Key Design Decisions）

## 1. DONE 连续命中三次

普通模式下，每个 lens 会循环调用 Agent，直到 Agent 连续三次输出 `DONE`，并且 `DONE` 是输出的第一个或最后一个单词。

`discover` 和 `deploy` 模式不同：只需要一次 `DONE`，也就是单次检查。

这是项目用于判断某个分析任务是否结束的机制。之后读代码时，我们需要弄清楚它如何识别 `DONE`，以及如何记录连续命中次数。

## 2. 模式隔离（Mode isolation）

`discover` 和 `deploy` 等模式有各自专属的领域。

原文列举了：

* `discovery`：14 个 lenses

* `deployment`：26 个 lenses

* `android`：17 个 lenses

`config/domains.json` 中的 `mode` 字段控制 lens 是否可见。每种模式只使用符合自身模式要求的领域，排除其他模式专属的领域。

## 3. 部署模式（Deploy mode）

这个模式针对正在运行的服务器进行检查。

Agent 会使用 `systemctl`、`ss`、`df`、`journalctl` 等 Bash 命令了解服务器状态。提示词要求它们执行只读操作，也就是只查看、不修改服务器。

部署模式下，`--project` 指定的路径不必是 Git 仓库。

安全提醒：“提示词要求只读”不等于系统层面绝对禁止修改。后续如果接触这部分，不能只依赖提示词来保证安全。

## 4. 不绑定特定 Agent（Agent-agnostic）

RepoLens 支持通过 `--agent` 参数指定不同的 Agent 工具，包括 Claude、Codex、Spark/Sparc、Cursor CLI、Cursor IDE/Composer handoff、OpenCode 和 Antigravity。

也就是说，它尽量把“审计流程”与“实际执行审计的 AI 工具”分开。

## 5. 提示词组合（Prompt composition）

* 基础模板提供通用规则。

* Lens 模板提供某个专家任务的具体要求。

* `lib/template.sh` 将两者拼接起来，并替换 `{{VARIABLES}}` 这样的变量占位符。

最终，Agent 收到的是组合后的完整提示词。

## 6. 并行执行（Parallel execution）

项目使用文件信号量（file-based semaphore）控制并发任务，相关文件放在：

`logs/<run-id>/.semaphore/`

同时使用信号处理器，在程序收到中断等信号时尽可能完成清理工作。

## 7. 恢复运行（Resume support）

通过 `--resume <run-id>`，程序可以跳过已经完成的 lenses，继续尚未完成的任务。

# 五、代码规范（Conventions）

* 所有 Shell 脚本使用 `set -uo pipefail`，而不是 `set -e`；调用者负责处理错误。

* 尽可能让函数保持纯函数式特征，也就是减少副作用；如果函数有副作用，应在注释中说明。

* 配置文件使用 JSON，并通过 `jq` 解析。

* 日志采用结构化格式：

  [LEVEL] [timestamp] message

例如：

```
[INFO] [2026-10-12 19:00:00] Starting audit
```

几个术语：

* `set -u`：使用未定义的 Shell 变量时，通常会触发错误。

* `pipefail`：管道中的某个命令失败时，尽可能让整个管道反映失败状态。

* `set -e`：在很多命令失败的情况下让脚本退出；但它在复杂 Shell 脚本中的行为有一些容易踩坑的地方。

* 副作用：函数除了返回结果，还会修改文件、打印日志、启动进程等。

# 六、测试规范（Tests）

## 1. 测试不能调用真实 AI 模型

测试绝不能真正调用 Claude、Codex、OpenCode 等 AI 模型，没有例外。

因为这样的测试可能会：

* 消耗 API 额度；

* 每次调用等待数分钟；

* 留下未清理的后台进程；

* 导致 AutoDev 的质量检查流程卡死。

如果测试需要验证 `repolens.sh` 的行为，必须使用：

* `--dry-run`：模拟运行；

* Mock（模拟对象）：用假 Agent 调用替代真实调用。

## 2. 如何运行测试

可以通过以下任一命令运行测试：

Bash

```
bash tests/run-all.sh
```

或者：

Bash

```
make check
```

两者共享一个名为 `REPOLENS_MAKE_CHECK` 的环境变量作为递归保护机制，避免测试在检查 Makefile 目标时无限嵌套执行。

每个测试文件应该在几秒内完成。如果新增测试耗时超过 10 秒，原文认为这通常意味着存在问题。

原文还记录了截至 2026 年 9 月 25 日的测试文件数量，以及过去某次环境中运行测试所花费的时间。这些数字是文档记录，不代表我们已经在你的电脑上实际运行过测试。

# 七、禁止事项（Do NOT）

1. 不要在评分或评估逻辑中添加 LLM/AI 推理逻辑。RepoLens 的目标是创建问题单，而不是给代码打分。

2. 不要硬编码只适用于某一个仓库的逻辑。RepoLens 应当适用于任意 Git 仓库或服务器。

3. 不要在没有理解 DONE 连续命中机制的情况下修改它。

4. 不要移除调用 Claude 时的 `--dangerously-skip-permissions` 参数。原文认为它是自主运行所需要的。

5. 不要编写会调用真实 AI 模型的测试，应该使用 `--dry-run` 或模拟调用。

最后一条是我们现在最需要遵守的：先读代码、理解结构，不要贸然执行完整审计。 项目可能会启动具有实际权限的 Agent，而且真实调用可能产生费用或副作用。
