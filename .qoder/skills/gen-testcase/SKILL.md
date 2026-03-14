---
name: gen-testcase
description: "自动化测试用例生成入口。将用户的测试需求通过三阶段流水线（需求结构化 → 代码库分析 → 代码生成）转化为落地的自动化测试代码。调用 testcase-leader agent 编排执行。"
---

# 自动化测试用例生成（入口 Skill）

这是用例生成的统一入口。收到用户请求后，启动 `testcase-leader` agent 来编排完整的生成流水线。

## 流水线概览

```
用户输入（零散描述/手工用例/接口文档）
    │
    ▼
┌─────────────────────────┐
│  Skill 1: testcase-refiner  │  需求结构化 → 输出标准测试步骤
└────────────┬────────────┘
             │ 结构化测试步骤
             ▼
┌─────────────────────────┐
│  Skill 2: testcase-planner  │  扫描代码库 → 输出代码生成计划
└────────────┬────────────┘
             │ 代码生成计划
             ▼
┌─────────────────────────┐
│  Skill 3: testcase-coder    │  按计划执行 → 生成代码文件
└─────────────────────────┘
```

## 架构说明

本工程采用 **AW 层 + testcase 层** 两层架构：

| 层级 | 职责 |
|------|------|
| AW 层 | 封装多步骤业务流程，通过 HTTP 调用 testagent 服务 |
| testcase 层 | 测试用例业务代码，调用 AW 层方法 |

支持的测试端：**Windows / Web / Mac / iOS / Android**

## 执行指令

收到用户的测试需求后，使用 Task 工具启动 `testcase-leader` agent，并将用户的原始输入完整传递过去：

```
Task(
    subagent_type="testcase-leader",
    description="生成自动化测试用例",
    prompt="用户需求: <完整的用户输入>"
)
```

## 使用示例

用户输入：
```
/gen-testcase 帮我生成登录功能的测试用例，Web 端，包括正常登录和各种异常场景
```

触发流水线：
1. **testcase-refiner** 与用户交互，确认具体场景，输出结构化测试步骤
2. **testcase-planner** 扫描 web/aw、web/testcase 等目录，发现已有 LoginAW，输出生成计划
3. **testcase-coder** 按计划生成/扩展 AW 文件和测试用例文件

## 直接使用单个 Skill

如果用户只想执行流水线的某个阶段，也可以直接调用对应 Skill：

- `/testcase-refiner` — 只做需求结构化，不生成代码
- `/testcase-planner` — 只做代码库分析和计划，不生成代码
- `/testcase-coder` — 给定计划后直接生成代码