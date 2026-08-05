"""Format bot responses for Feishu text messages."""
from __future__ import annotations

from app.models.ai_news import AiNewsDigest
from app.models.learning_note import LearningNote
from app.models.practice import AnswerAttempt
from app.models.todo import TodoItem
from app.services.bot_facade import QuestionPublic, QuestionWithAnswer

_MAX_CHUNK = 3800


def help_text() -> str:
    return (
        "SmartLearning 飞书助手(自然语言理解):\n"
        "直接用口语即可,例如:\n"
        "· 给我 5 道 Redis 场景题\n"
        "· 来 3 道困难八股 / 错题 5 道\n"
        "· 答案 12 / 下一题\n"
        "· 提交作答须带题号: 「15 你的答案…」或「作答 15 …」(会评分并记入练习)\n"
        "· 不带题号的提问走对话,例如解释 CAP 定理\n"
        "· 总结 今天学了…(检验+结构化保存,次日起按间隔复习;前缀可在设置中配置)\n"
        "· 待办 明天3点提醒我交周报(可追问补全时间/事项)\n"
        "· 待办列表 / 我的待办\n"
        "· 新建对话(清空聊天上下文)\n"
        "· 推送设置 / 立即推题(定时推题)\n"
        "抽题不会附带标准答案;需要时说「答案」或「答案+题号」。"
    )


def format_questions_batch(questions: list[QuestionPublic], *, pool_hint: str = "") -> list[str]:
    if not questions:
        return ["题库为空,请先在 Web 端生成并入库题目。"]
    lines = [f"已抽 {len(questions)} 道题{pool_hint}。发送「答案 ID」或「下一题」继续。"]
    for i, q in enumerate(questions, 1):
        tags = ",".join(q.tags) if q.tags else "-"
        lines.append(
            f"\n[{i}] ID={q.id} [{q.difficulty}/{q.qtype}] {tags}\n{q.question_text[:800]}"
        )
    return _chunk("\n".join(lines))


def format_question_one(q: QuestionPublic, *, index: int, total: int) -> str:
    tags = ",".join(q.tags) if q.tags else "-"
    return (
        f"第 {index}/{total} 题 · ID={q.id} [{q.difficulty}/{q.qtype}] {tags}\n"
        f"{q.question_text[:3500]}\n\n"
        f"提交作答请用「{q.id} 你的答案…」或「作答 {q.id} …」(须带题号);"
        f"「答案 {q.id}」看标准答案、「下一题」换题。"
    )


def format_scoring_result(
    q: QuestionPublic,
    attempt: AnswerAttempt,
    *,
    user_answer: str,
) -> list[str]:
    preview = user_answer.strip()
    if len(preview) > 400:
        preview = preview[:400] + "…"
    body = (
        f"【作答已记录】题目 ID={q.id}\n"
        f"等级 {attempt.grade} · 正确 {attempt.score_correctness} · "
        f"完整 {attempt.score_completeness} · 结构 {attempt.score_structure} · "
        f"深度 {attempt.score_depth}\n"
        f"记录编号 attempt_id={attempt.id}\n\n"
        f"你的作答:\n{preview}\n\n"
        f"反馈:\n{attempt.feedback_text[:2800]}"
    )
    body += "\n\n发送「下一题」继续,或「答案」查看标准答案。"
    return _chunk(body)


def format_answer(q: QuestionWithAnswer) -> list[str]:
    body = (
        f"【答案】ID={q.id}\n"
        f"题干: {q.question_text[:500]}\n\n"
        f"标准答案:\n{q.answer_standard}"
    )
    return _chunk(body)


def format_chat_reply(text: str) -> list[str]:
    if not text.strip():
        return ["(模型返回为空)"]
    return _chunk(text)


def next_question_card(question_id: int) -> dict:
    """Minimal interactive card with action buttons (Feishu schema 2.0)."""
    return {
        "config": {"wide_screen_mode": True},
        "elements": [
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "看答案"},
                        "type": "primary",
                        "value": {"cmd": "答案", "qid": str(question_id)},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "下一题"},
                        "type": "default",
                        "value": {"cmd": "下一题"},
                    },
                ],
            }
        ],
    }


def format_note_saved(note: LearningNote) -> list[str]:
    """Reply after a learning summary is validated + structured + saved."""
    tags = "、".join(t.name for t in (note.tags or [])) or "-"
    lines = [
        f"✅ 已保存学习总结 · ID={note.id}",
        f"标题: {note.title}",
    ]
    if note.category:
        lines.append(f"分类: {note.category}")
    lines.append(f"标签: {tags}")
    if note.quality_score is not None:
        lines.append(f"质量评分: {note.quality_score}/100")
    if note.summary:
        lines.append(f"\n概述:\n{note.summary}")
    kp = note.key_points_json or []
    if kp:
        lines.append("\n要点:")
        lines.extend(f"· {p}" for p in kp)
    review = note.review_json or {}
    issues = review.get("issues") or []
    corrections = review.get("corrections") or []
    if issues:
        lines.append("\n⚠️ 检验发现:")
        lines.extend(f"- {x}" for x in issues)
    if corrections:
        lines.append("\n纠正:")
        lines.extend(f"- {x}" for x in corrections)
    suggestions = review.get("suggestions") or []
    if suggestions:
        lines.append("\n建议:")
        lines.extend(f"- {x}" for x in suggestions)
    if note.next_review_at:
        lines.append(
            f"\n📅 已加入复习计划,将在 {note.next_review_at.strftime('%m-%d')} 推送复习。"
        )
    return _chunk("\n".join(lines))


def review_push_intro(count: int, *, manual: bool = False) -> str:
    tag = "（手动触发）" if manual else ""
    return (
        f"🧠 学习复习时间{tag}\n"
        f"今天有 {count} 条待复习的学习总结,先回忆再点「查看要点」对照。"
    )


def note_review_card(note: LearningNote, *, recall_mode: bool = True) -> dict:
    """Active-recall card: title first; reveal key points on demand."""
    head = f"**复习 · {note.title}**"
    if note.category:
        head += f"\n分类: {note.category}"
    elements: list[dict] = []
    if recall_mode:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{head}\n\n先自己回忆一下要点,再点下方「查看要点」对照。",
                },
            }
        )
    else:
        kp = "\n".join(f"· {p}" for p in (note.key_points_json or [])) or "(无要点)"
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{head}\n\n{note.summary}\n\n{kp}"},
            }
        )
    actions: list[dict] = []
    if recall_mode:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看要点"},
                "type": "primary",
                "value": {"cmd": "复习要点", "nid": str(note.id)},
            }
        )
    actions.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "已掌握"},
            "type": "default",
            "value": {"cmd": "复习掌握", "nid": str(note.id)},
        }
    )
    actions.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "需加强"},
            "type": "default",
            "value": {"cmd": "复习加强", "nid": str(note.id)},
        }
    )
    elements.append({"tag": "action", "actions": actions})
    return {"config": {"wide_screen_mode": True}, "elements": elements}


def ai_news_card(digest: AiNewsDigest, *, manual: bool = False) -> dict:
    """Interactive card listing today's top AI news with real source links."""
    tag = "（手动触发）" if manual else ""
    n = len(digest.items)
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"共 {n} 条 · 从 {digest.total_candidates} 条候选中"
                    f"{'由模型精选' if digest.used_llm else '按热度筛选'}"
                ),
            },
        },
        {"tag": "hr"},
    ]
    for it in digest.items:
        heat = f" 🔥{it.heat_score}" if it.heat_score else ""
        why = f"\n💡 {it.why}" if it.why else ""
        summary = f"\n{it.summary}" if it.summary else ""
        content = (
            f"**{it.rank}. {it.title}**{heat}{summary}{why}\n"
            f"来源: {it.source} · [查看原文]({it.url})"
        )
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": content}}
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "SmartLearning · AI 资讯每日精选"}
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": f"🗞️ 今日 AI 热点 Top{n}{tag}"},
        },
        "elements": elements,
    }


def format_note_reveal(note: LearningNote) -> list[str]:
    lines = [f"📖 ID={note.id} · {note.title}"]
    if note.summary:
        lines.append(f"\n{note.summary}")
    kp = note.key_points_json or []
    if kp:
        lines.append("\n要点:")
        lines.extend(f"· {p}" for p in kp)
    review = note.review_json or {}
    corrections = review.get("corrections") or []
    if corrections:
        lines.append("\n纠正:")
        lines.extend(f"- {x}" for x in corrections)
    lines.append("\n回复「已掌握」会大幅拉长该条的复习间隔(仍会偶尔抽查),「需加强」会尽快再次推送。")
    return _chunk("\n".join(lines))


def todo_reminder_card(todo: TodoItem) -> dict:
    when = ""
    if todo.remind_at:
        try:
            from datetime import timezone
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(todo.timezone or "Asia/Shanghai")
            local = todo.remind_at.replace(tzinfo=timezone.utc).astimezone(tz)
            when = local.strftime("%m-%d %H:%M")
        except Exception:
            when = str(todo.remind_at)
    body = f"**{todo.title}**"
    if todo.description:
        body += f"\n{todo.description}"
    if when:
        body += f"\n计划时间: {when}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "⏰ 待办提醒"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": body}},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "已完成"},
                        "type": "primary",
                        "value": {"cmd": "todo_done", "tid": str(todo.id)},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "稍后提醒"},
                        "type": "default",
                        "value": {"cmd": "todo_snooze", "tid": str(todo.id)},
                    },
                ],
            },
        ],
    }


def todo_no_plan_card(today) -> dict:
    """Nudge when the user has no plan for today."""
    day = today.isoformat() if hasattr(today, "isoformat") else str(today)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "turquoise",
            "title": {"tag": "plain_text", "content": "🗓️ 今日暂无计划"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"今天是 {day}，还没有任何安排。\n"
                        "花一分钟为今天定个小目标吧 —— 在飞书发送「待办 …」，"
                        "或在网页「待办」里安排今天的计划。"
                    ),
                },
            },
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "SmartLearning · 每日计划检测"}
                ],
            },
        ],
    }


def todo_today_plan_card(today, tasks: list, motivations: dict | None = None) -> dict:
    """Today's plan list; long-overdue items carry an encouragement line."""
    motivations = motivations or {}
    day = today.isoformat() if hasattr(today, "isoformat") else str(today)
    n = len(tasks)
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"今天是 {day}，共 {n} 项计划:"},
        },
        {"tag": "hr"},
    ]
    for i, t in enumerate(tasks, start=1):
        line = f"**{i}. {t.title}**"
        if t.description:
            line += f"\n{t.description}"
        defer = int(getattr(t, "defer_count", 0) or 0)
        if defer > 0 and t.original_plan_date is not None:
            orig = t.original_plan_date.isoformat()
            line += f"\n⏳ 原计划 {orig} · 已延期 {defer} 天"
        mot = motivations.get(t.id)
        if mot:
            line += f"\n💪 {mot}"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": line}})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 完成"},
                        "type": "primary",
                        "value": {"cmd": "todo_done", "tid": str(t.id)},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "⏸ 挂起3天"},
                        "type": "default",
                        "value": {"cmd": "todo_hold", "tid": str(t.id)},
                    },
                ],
            }
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "SmartLearning · 今日计划"}
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": f"📋 今日计划 · {n} 项"},
        },
        "elements": elements,
    }


def _chunk(text: str) -> list[str]:
    if len(text) <= _MAX_CHUNK:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:_MAX_CHUNK])
        text = text[_MAX_CHUNK:]
    return parts
