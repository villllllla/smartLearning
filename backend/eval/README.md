# Agent 工具路由评测

给飞书 Agent 的**工具选择（tool routing）**建立一个可复现的评测基线：给定一句用户输入，Agent 应该选中哪个工具。

评测直接驱动**真实**路由管线（`app.integrations.feishu.agent.handle_incoming_text`），通过 monkeypatch 把 `execute_tool` 换成一个"只记录、不执行"的探针，因此测的是线上真实决策，而不是另写一份逻辑。整个过程不会真的抽题/评分，也不写库。

## 数据集

`routing_cases.py`，按解析层分类：

| 类别 | 含义 | 何时计分 |
|---|---|---|
| `rule_exact` / `rule_prefix` / `rule_structural` / `rule_answer` | 规则快路径确定性命中，不经过 LLM | **每次都计分**（无需 API Key） |
| `llm_intent` | 无触发前缀，需 LLM 意图路由选工具 | 仅在配置了 Provider 时计分 |
| `adversarial` | 已知难例，探测某个具体失败模式（如数字开头的提问"解释第15题怎么做"不该被读成交答案） | 单独报告，不混入总分 |

## 运行

```bash
cd backend
# 1) 仅规则层（无需模型/Key，CI 可跑）
python -m eval.run_eval

# 2) 连 LLM 一起测：指向一个已配置 chat_general 模型的库
SL_EVAL_DATABASE_URL=sqlite:///./data/app.sqlite3 python -m eval.run_eval

# 看每条明细
python -m eval.run_eval --show-all
```

Windows 终端若中文乱码：`PYTHONIOENCODING=utf-8 python -m eval.run_eval`。

## 当前结果（规则层，rule-only 模式）

```
rule_exact       18/18 = 100.0%
rule_prefix        4/4 = 100.0%
rule_structural    3/3 = 100.0%
rule_answer        2/2 = 100.0%
overall          27/27 = 100.0%   (12 条需 Provider，skip)
```

## 评测发现并已修复的缺陷：前缀误吞提问

评测最初暴露：`resolve_trigger` 的前缀匹配会把"总结一下 Redis 有哪些数据结构"
误路由到 `submit_learning_note`、把"提醒我 CAP 定理是什么"误路由到 `submit_todo`
——以触发词开头的**提问**被当成存笔记/建待办，用户的问题变成了一条噪声笔记。

修复分两步，第二步是第一版修复自己踩的坑：

1. **加问句判别**：前缀命中后，若 body 含疑问词则弃权（返回 `None`），落到 LLM
   意图路由按 `chat` 处理。
2. **判别过宽的回退修正**：无条件扫疑问词会误伤正常笔记——"总结 今天搞清楚了
   MVCC 怎么做可见性判断"是陈述句，却因含"怎么"被整条丢弃，而学习笔记正文里
   "怎么/为什么/如何/哪些"极常见。现在改为看**触发词是否以独立 token 出现**：

   | 输入形态 | 判定 |
   |---|---|
   | 触发词后有分隔符（`总结 今天…`）＝命令式 | 信任，仅显式 `？` 才弃权 |
   | 触发词粘连进句子（`总结一下 Redis 有哪些…`） | 用疑问词判别，命中则弃权 |

   代价是 O(1) 的字符串检查，不额外调用 LLM。

## 回归保护

- `tests/test_agent_routing_eval.py`：把规则层准确率固化进 CI（改动触发词/答案
  解析若误路由已知输入即失败）；对抗样本一旦被规则层修对，测试会提示把它移出
  数据集。
- `tests/test_feishu_triggers.py`：把上面的问句判别单独钉死（该弃权的弃权、
  正常笔记不被误伤）。这层必须留在单测里——那两条修复后的样本在数据集里已归入
  `llm_intent`，**只有配了 Provider 才计分**，光靠评测无法防回归。

## 下一步

- 配好一个便宜的国产 Provider（DeepSeek/Qwen 等）后跑 real-LLM 模式，得到
  `llm_intent` 的工具选择准确率，填进简历。
- 扩充 `llm_intent`/`adversarial` 到 50+ 条，覆盖多参数（难度/类型/标签/题量）
  的**参数抽取**正确率，而不只是工具名。
