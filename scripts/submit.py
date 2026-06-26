#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新信息提交接口 —— 把用户输入的新观察（新题目/新雷区/规则变化/新经验/勘误等）
结构化、脱敏后追加到 submissions/_inbox.md（待审区）。**不直接改动 references/**。

复用 clean.py 的 redact() 做脱敏，保证与第一轮清洗同口径。

用法：
  python3 submit.py --category 电话面试常见问题 --content "对方问……" \
                    [--source 待证] [--by 匿名] [--note "…"]

流程：用户输入 → 脱敏 + 来源强度 → 待审区（_inbox.md）→ 由维护者/skill 复核后再并入 references。
"""
import os
import sys
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from clean import redact  # 复用脱敏逻辑（电话/邮箱/wxid/身份证/链接/@昵称）

BASE = os.path.dirname(HERE)
SUB = os.path.join(BASE, "submissions")
INBOX = os.path.join(SUB, "_inbox.md")

CATEGORIES = [
    "问卷常见问题", "电话面试常见问题", "节目组筛选标准", "回答中的高风险表述",
    "成功入选者经验摘要", "落选或被质疑原因摘要", "现场听审注意事项", "如何表达理性普通观众",
    "规则与流程变化", "勘误与纠正", "其他",
]
SOURCES = ["待证", "高", "中", "低", "推测"]

# 守门嫌疑词：命中则标黄待复核（仍写入待审区，透明可追溯；不直接采纳）
SUSPECT = ["编造", "伪造", "假装", "冒充", "骗过", "规避审查", "绕开筛选", "隐藏账号",
           "清理关注", "清理歌单", "装作", "伪装身份", "假身份"]


def ensure_inbox():
    os.makedirs(SUB, exist_ok=True)
    if not os.path.exists(INBOX):
        with open(INBOX, "w", encoding="utf-8") as fh:
            fh.write("# 待审区（_inbox）\n\n> 所有新提交都追加到本文件末尾。"
                     "状态流转：`待审` → `已采纳` / `已驳回`。\n\n---\n")


def main():
    ap = argparse.ArgumentParser(description="提交一条新信息到知识库待审区")
    ap.add_argument("--category", required=True, choices=CATEGORIES)
    ap.add_argument("--content", required=True, help="新信息内容（会自动脱敏）")
    ap.add_argument("--source", default="待证", choices=SOURCES, help="来源强度，默认 待证")
    ap.add_argument("--by", default="匿名", help="提交者署名，默认 匿名")
    ap.add_argument("--note", default="", help="备注（可选）")
    args = ap.parse_args()

    content = redact(args.content.strip())
    if not content:
        print("内容为空（脱敏后无残留），未写入。"); sys.exit(1)

    flagged = [w for w in SUSPECT if w in content] or [w for w in SUSPECT if w in args.content]

    ensure_inbox()
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    block = []
    block.append("\n### [待审%s] · %s · %s" % (
        " · ⚠️疑似守门违规(待复核)" if flagged else "", date, args.category))
    block.append("- 来源强度: %s" % args.source)
    block.append("- 提交者: %s" % args.by)
    block.append("- 内容: %s" % content)
    block.append("- 备注: %s" % (args.note.strip() or "—"))
    if flagged:
        block.append("- 守门提示: 命中嫌疑词 %s —— 按 SKILL.md 第5节禁止事项，"
                     "复核时大概率拒收（不进入 references）。" % flagged)
    block.append("")  # 空行分隔

    with open(INBOX, "a", encoding="utf-8") as fh:
        fh.write("\n".join(block) + "\n")

    print("已写入待审区: submissions/_inbox.md")
    print("类别: %s | 来源强度: %s | 日期: %s" % (args.category, args.source, date))
    print("脱敏后内容: %s" % content)
    if flagged:
        print("⚠️ 命中守门嫌疑词 %s —— 该条已标记，复核时大概率拒收。" % flagged)
    print("提示: 新提交默认'待证'，需交叉印证后方可升至'高'；采纳时请在 CHANGELOG.md 留痕。")


if __name__ == "__main__":
    main()
