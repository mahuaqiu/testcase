---
name: testcase-create
description: "自动化测试用例生成。接收用户输入的测试用例描述，通过四阶段流水线生成测试代码。"
---

# 自动化测试用例生成（入口 Skill）

这是用例生成的统一入口。收到用户请求后，通过 Agent 调用四个子 Skill，每个阶段上下文独立。

## 流水线概览

```
用户输入
    │
    ▼
┌─────────────────────────┐
│  Agent: testcase-refiner  │  独立上下文 → 输出 .cache/refined.md
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Agent: testcase-planner  │  独立上下文 → 输出 .cache/plan.md
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Agent: testcase-reviewer │  独立上下文 → 输出 .cache/review.md
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Agent: testcase-coder    │  独立上下文 → 生成代码 + 更新 INDEX.md
└─────────────────────────┘
```

## 上下文隔离机制

每个阶段通过 **Agent** 在独立子进程中执行，通过中间文件传递信息：

| 阶段 | 输入文件 | 输出文件 |
|------|----------|----------|
| refiner | 用户原始输入 | `.cache/refined.md` |
| planner | `.cache/refined.md` | `.cache/plan.md` |
| reviewer | `.cache/plan.md` | `.cache/review.md` |
| coder | `.cache/review.md` | 生成的代码文件 |

---

## 执行流程

### 阶段 1：需求结构化（testcase-refiner）

```python
Agent(
    subagent_type="general-purpose",
    description="需求结构化",
    prompt="""
执行 testcase-refiner Skill：
1. 读取用户原始输入
2. 与用户交互确认测试细节
3. 输出结构化测试步骤到 .cache/refined.md

用户原始输入：
{用户输入}
"""
)
```

### 阶段 2：代码库分析（testcase-planner）

```python
Agent(
    subagent_type="general-purpose",
    description="代码库分析",
    prompt="""
执行 testcase-planner Skill：
1. 读取 .cache/refined.md
2. 读取 aw/INDEX.md 和 config.yaml
3. 分析 AW 资源，制定代码生成计划
4. 输出计划到 .cache/plan.md
"""
)
```

### 阶段 3：计划审查（testcase-reviewer）

```python
Agent(
    subagent_type="general-purpose",
    description="计划审查",
    prompt="""
执行 testcase-reviewer Skill：
1. 读取 .cache/plan.md
2. 审查 AW 重复、命名规范、步骤逻辑
3. 如有问题，与用户确认后直接修改计划
4. 审查通过后，输出到 .cache/review.md
5. 与用户确认是否执行代码生成
"""
)
```

### 阶段 4：代码生成（testcase-coder）

```python
Agent(
    subagent_type="general-purpose",
    description="代码生成",
    prompt="""
执行 testcase-coder Skill：
1. 读取 .cache/review.md
2. 按计划生成 AW 和测试用例代码
3. 更新 aw/INDEX.md
"""
)
```

---

## 中间文件格式

### .cache/refined.md

```markdown
# 结构化测试步骤

## 基本信息
- 功能模块: {模块名}
- 测试端: {平台}
- 前置条件: {前置条件}

## 角色
- userA: {平台}（{角色}）

## 测试步骤
| 步骤 | 操作 | 期望结果 | 操作类型 |
|------|------|----------|----------|
| 1 | {操作} | {期望} | UI/API |

## 清理步骤
| 步骤 | 操作 | 操作类型 |
|------|------|----------|
| 1 | {操作} | UI/API |

## 用例归属
- 平台: {平台}
- 目录: testcases/{平台}/{模块}
```

### .cache/plan.md

```markdown
# 代码生成计划

## hooks 配置
| 平台 | setup | teardown |
|------|-------|----------|
| {平台} | {操作} | {操作} |

## 可复用的 AW
| 步骤 | AW 类 | 方法 | 文件路径 |
|------|-------|------|----------|

## 需要扩展的 AW
| 步骤 | AW 类 | 需新增方法 | 文件路径 |
|------|-------|-----------|----------|

## 需要新建的 AW
| 步骤 | 建议AW类 | 建议方法 | 建议文件路径 |
|------|----------|----------|--------------|

## 即将生成的文件
| 文件 | 操作 | 说明 |
|------|------|------|

## 用户资源需求
- userA: {平台}（{角色}）
```

### .cache/review.md

```markdown
# 审查通过的计划

## 审查结果
✅ 通过

## 审查检查项
- [x] AW 无重复
- [x] 文件命名规范
- [x] 步骤逻辑完整

## 最终生成计划
{与 plan.md 相同格式}

## 用户确认
用户已确认执行代码生成。
```

---

## 使用示例

用户输入：
```
/testcase-create 帮我生成会议等候室功能的测试用例，Web 端
```

执行流水线：
1. **Agent(refiner)** 独立上下文，与用户交互，输出 `.cache/refined.md`
2. **Agent(planner)** 独立上下文，读取 INDEX.md，输出 `.cache/plan.md`
3. **Agent(reviewer)** 独立上下文，审查计划，与用户确认，输出 `.cache/review.md`
4. **Agent(coder)** 独立上下文，生成代码，更新 INDEX.md

---

## 上下文隔离优势

1. **互不干扰**：每个阶段只看到自己的输入文件
2. **可追溯**：中间文件保留，便于调试
3. **可重试**：某阶段失败可单独重新执行