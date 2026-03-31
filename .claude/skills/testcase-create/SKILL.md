---
name: testcase-create
description: "自动化测试用例生成。单Skill直接执行全流程，生成前用户评审，生成后复查验证。"
---

# 自动化测试用例生成

直接执行测试用例生成全流程，无需Agent调用。需要AW操作时调用 testcase-aw Skill。

---

## 执行流程

```
步骤1: 读取项目规范
    ↓
步骤2: 分析用户输入（步骤完整性校验）
    ↓
步骤3: 查找相似用例（优先复用）
    ↓
步骤4: AW匹配分析
    ↓
步骤5: 输出计划 → 用户评审确认
    ↓
步骤6: 生成测试代码
    ↓
步骤7: 复查验证
```

---

### 步骤 1：读取项目规范

**必须**先读取以下文件：

| 文件 | 读取目的 |
|------|----------|
| `AGENTS.md` | 架构、命名规范、编码约定、并行执行模式 |
| `aw/INDEX.md` | 已有AW资源索引 |
| `config.yaml` | hooks配置（setup/teardown自动处理） |

---

### 步骤 2：分析用户输入

解析用户的测试描述，提取关键信息：

#### 2.1 信息提取

| 检查项 | 必要性 | 示例 |
|--------|--------|------|
| 测试端 | 必要 | web / windows / mac / ios / android |
| 测试步骤 | 必要 | STEP 1, STEP 2, STEP 3... |
| 期望结果 | 必要 | 每步的验证点 |
| 前置条件 | 可选 | 如 "已登录"、"api预约会议" |
| 角色 | 可选 | 主持人、与会者 → 自动转换为 userA, userB |
| 清理步骤 | 可选 | 如 "关闭浏览器" |

#### 2.2 步骤完整性校验（强制执行）

**必须**输出校验表格，确保所有STEP都被解析：

```
步骤完整性校验:

用户输入步骤数: {N}
解析步骤数: {M}

| 用户STEP | 解析内容 | 覆盖状态 |
|----------|----------|----------|
| STEP 1 | 登录操作 + 断言成功 | ✅ |
| STEP 2 | 创建会议 + 断言成功 | ✅ |
| STEP 3 | ❌ 遗漏 | ❌ |

校验结论: ✅ 全部覆盖 / ❌ 有遗漏需补充
```

**常见遗漏场景**：

| 用户描述 | 易遗漏内容 | 正确拆分 |
|----------|------------|----------|
| "离会后重新入会" | 离会、断言离会成功、重新入会、断言入会 | 4个独立操作 |
| "设置关闭等候室" | API设置操作 | 单独一行 |
| "A做某事，B做某事" | 可能只解析一半 | 拆分为A操作、B操作两行 |

#### 2.3 角色命名自动转换

遵循AGENTS.md规范：

| 用户输入角色 | 标准命名 |
|-------------|----------|
| 主持人、主持人A、A | userA |
| 与会者、与会者A、B | userB |
| 与会者B、C | userC |

**不询问角色命名，自动转换**。

#### 2.4 操作类型自动识别

| 操作描述 | 自动识别 | 原因 |
|----------|----------|------|
| "api预约会议" | API | 明确写api |
| "api取消会议" | API | 明确写api |
| 其他UI描述 | UI | 默认UI操作 |

**不明确时才询问**（如"portal设置"可能是API或UI）。

---

### 步骤 3：查找相似用例（优先复用）

**在查INDEX.md之前**，先在目标目录查找相似用例。

#### 3.1 查找范围

```bash
目标目录: testcases/{平台}/{模块}/test_*.py
```

使用 Glob 查找目录下所有测试文件。

#### 3.2 匹配逻辑

读取前3个最相似的用例，对比：
- 操作类型（UI/API）
- 操作对象（登录/入会/离会...）
- 角色（单用户/多用户）
- 并行标识

#### 3.3 输出相似度分析

```markdown
| 相似用例 | 相似度 | 可复用步骤 | 可复用AW方法 |
|----------|--------|------------|--------------|
| test_login_001.py | 80% | 登录流程 | LoginAW.do_login |
| test_meeting_001.py | 50% | 入会流程 | MeetingJoinAW.do_join |
```

#### 3.4 复用决策

| 相似度 | 处理方式 |
|--------|----------|
| >= 70% | 优先复用已有AW引用模式，减少新增 |
| < 70% | 正常AW匹配流程 |

---

### 步骤 4：AW匹配分析

结合相似用例复用 + INDEX.md匹配：

#### 4.1 匹配优先级

| 优先级 | 匹配类型 | 处理方式 |
|--------|----------|----------|
| 1 | 完全匹配 | 直接使用已有AW方法 |
| 2 | 部分匹配 | 扩展已有AW（调用 testcase-aw） |
| 3 | 无匹配 | 新建AW（调用 testcase-aw） |

#### 4.2 输出匹配表格

```markdown
| 用户STEP | AW类 | 方法 | 匹配状态 |
|----------|------|------|----------|
| STEP 1: 登录 | LoginAW | do_login | ✅ 已有 |
| STEP 2: 创建会议 | MeetingManageAW | do_create_meeting | ✅ 已有 |
| STEP 3: 新操作 | - | - | ⚠️ 需新建 |
```

#### 4.3 需要AW操作时

发现需要新增/扩展AW时，调用 testcase-aw Skill：

```
Skill(skill="testcase-aw", args="需要新建 {业务}AW，{平台}端")
```

---

### 步骤 5：输出计划，用户评审

**生成完整计划后，必须让用户确认**。

#### 5.1 计划输出格式

```markdown
# 测试用例生成计划

## 基本信息
- 测试文件: testcases/{平台}/{模块}/test_{功能}_{场景}_{编号}.py
- 测试端: {平台}
- 用户资源: {"userA": "{平台}", "userB": "{平台}"}

## 步骤与AW映射
| 用户STEP | AW方法 | 操作类型 | 并行标识 | 状态 |
|----------|--------|----------|----------|------|
| STEP 1 | LoginAW.do_login | UI | - | ✅ 已有 |
| STEP 2 | MeetingManageAW.do_create_meeting | API | - | ✅ 已有 |
| STEP 3 | XxxAW.do_xxx | UI | parallel | ⚠️ 需新建 |

## 需要新增/扩展的AW
| AW类 | 方法 | 平台 | 文件路径 |
|------|------|------|----------|
| XxxAW | do_xxx | web | aw/web/xxx_aw.py |

## hooks自动处理
- setup: start_app（自动执行，无需编写）
- teardown: stop_app（自动执行，无需编写）

## 相似用例复用
- 复用 test_login_001.py 的登录流程引用模式
```

#### 5.2 用户确认

使用 AskUserQuestion：

```
问题: "请评审以上生成计划，确认是否执行？"
选项:
1. 确认执行
2. 需要修改（请在Other说明修改内容）
3. 取消
```

**用户选择"确认执行"后才进入步骤6**。

---

### 步骤 6：生成测试代码

用户确认后执行代码生成。

#### 6.1 测试用例模板

```python
"""
{用例标题}测试用例。

测试场景: {场景描述}
"""

import pytest


@pytest.mark.users({"userA": "{平台}", "userB": "{平台}"})
class TestClass:
    """{用例标题}测试。"""

    def test_{文件名}(self, users):
        """执行测试：{操作}，应{结果}。"""
        userA = users["userA"]
        userB = users["userB"]

        # 测试步骤
        userA.do_xxx()
        userA.should_xxx_success()

        # 多用户并行
        from common.parallel import parallel
        with parallel():
            userA.do_yyy()
            userB.do_yyy()
```

#### 6.2 多用户并行模板

当多用户同时执行相同操作时：

```python
from common.parallel import parallel

with parallel():
    userA.do_join()
    userB.do_join()

# 验证步骤不在并行块内
userA.should_join_success()
userB.should_join_success()
```

#### 6.3 生成AW代码（需要时）

如果计划中标注需新建/扩展AW：
1. 先调用 testcase-aw Skill 完成AW生成
2. 再生成测试用例引用

#### 6.4 更新INDEX.md

新增/扩展AW后，更新 `aw/INDEX.md`：

```markdown
### XxxAW

> 文件路径：`aw/{平台}/xxx_aw.py`
> 功能概述：{业务概述}

| 方法 | 说明 |
|------|------|
| `do_xxx()` | 执行xxx操作 |
| `should_xxx_success()` | 断言xxx成功 |
```

---

### 步骤 7：复查验证

**生成完成后必须执行复查**。

#### 7.1 步骤覆盖验证

对比用户输入STEP与代码实现：

```markdown
| 用户STEP | 代码实现 | 覆盖状态 |
|----------|----------|----------|
| STEP 1 | userA.do_login() + should_login_success() | ✅ |
| STEP 2 | userA_api.do_create_meeting() | ✅ |
```

**遗漏时自动补充**。

#### 7.2 编码规范验证

| 检查项 | 规范要求 | 处理方式 |
|--------|----------|----------|
| 文件命名 | test_{功能}_{场景}_{编号}.py | 不符合则修正 |
| 类命名 | TestClass | 不符合则修正 |
| 方法命名 | test_{文件名} | 不符合则修正 |
| AW引用 | from aw.{平台}.{业务}_aw import XxxAW | 检查路径正确 |
| Docstring | 中文注释 | 缺失则补充 |

#### 7.3 INDEX.md同步验证

检查：
- 新增AW是否已添加到INDEX.md
- 方法列表是否完整

#### 7.4 复查结果输出

**通过**：
```
✅ 复查通过
- 步骤覆盖：{N}/{N} 用户STEP全部覆盖
- 编码规范：命名、格式符合AGENTS.md
- INDEX.md：已同步更新
```

**发现问题**：
```
⚠️ 发现问题，已修正：
- 遗漏STEP 3断言 → 已补充 should_xxx_success()
- 文件命名不规范 → 已修正为 test_xxx_001.py
- INDEX.md未更新 → 已补充XxxAW记录
```

---

## 核心原则

1. **单Skill直接执行**：不调用Agent，降低复杂度
2. **优先复用相似用例**：查INDEX.md前先查同目录用例
3. **用户评审前置**：生成代码前必须让用户确认计划
4. **生成后复查**：步骤覆盖、编码规范、INDEX.md同步
5. **需要AW时调用 testcase-aw**：AW操作专用Skill
6. **遵循命名规范**：详见AGENTS.md

---

## 命名规范速查

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW文件 | {业务名}_aw.py | login_aw.py |
| AW类 | {业务名}AW | LoginAW |
| AW方法 | do_{动作} / should_{期望} | do_login() |
| 测试文件 | test_{功能}_{场景}_{编号}.py | test_login_success_001.py |
| 测试类 | TestClass | 固定名称 |
| 测试方法 | test_{文件名} | test_login_success_001 |