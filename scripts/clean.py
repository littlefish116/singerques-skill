#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《歌手2026》大众听审报名与电话面试 — 第一轮清洗脚本
仅处理 local_type=1 的明文文本消息；其余媒体类型(图/语音/视频/表情/appmsg/系统)为 zstd
压缩数据，当前环境无法解码，统计后丢弃。

流程: 流式解析 -> 取文本 -> 去噪 -> PII 脱敏 -> 发送者伪化 -> 多标签分类 -> 去重聚合
      -> 来源强度信号 -> 写入 cleaned_records/
"""
import json
import re
import os
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "cleaned_records")
BYCAT = os.path.join(OUT, "by_category")

FILES = [
    ("58498190984@chatroom.jsonl", 1),
    ("57227098604@chatroom.jsonl", 2),
    ("49388501689@chatroom.jsonl", 3),
]

# ---------- 8 个目标类别 (多标签) ----------
CATEGORIES = {
    "问卷常见问题": ["问卷", "填表", "报名表", "问卷星", "填问卷", "题目", "答题"],
    "电话面试常见问题": ["电话", "面试", "面谈", "来电", "接到", "回访", "三通电话", "两通电话",
                     "通话", "客服", "审核", "确认电话", "问我对", "他问我", "问我", "问到",
                     "会问", "问到过", "被问", "问你", "打电话", "来电确认"],
    "节目组筛选标准": ["筛选", "入选", "录取", "入选率", "通过率", "抽中", "被选", "选中", "落选",
                   "没选上", "没过", "刷掉", "淘汰", "排名", "打分", "评分", "标准", "要求",
                   "门槛", "抽签", "随机", "概率", "运气", "名额", "审核", "资质"],
    "回答中的高风险表述": ["粉籍", "超话", "打榜", "微博", "抖音", "小红书", "主页", "追星", "偶像",
                     "粉头", "做数据", "数据", "控评", "一定会投", "只投", "偏袒", "拉踩",
                     "贬低", "吹捧", "黑粉", "脱粉", "唯粉", "私生", "应援", "后援会", "关注"],
    "成功入选者经验摘要": ["入选了", "录取了", "抽中了", "被选", "选上", "我进了", "我去现场",
                     "我去了", "接到电话", "经验", "我报", "我填", "我当时", "标准答案",
                     "我答", "我回答", "我入选", "通过审核", "打电话来"],
    "落选或被质疑原因摘要": ["落选", "没选上", "没过", "刷掉", "被刷", "被拒", "拒了", "没抽中",
                     "没中", "质疑", "怀疑", "被怀疑", "粉籍嫌疑", "被问是不是", "取消资格",
                     "被取消", "拉黑", "黑名单", "没通过"],
    "现场听审注意事项": ["现场", "录制", "入场", "规则", "流程", "不能带", "禁止", "保密",
                   "签协议", "入场须知", "安检", "寄存", "迟到", "候场", "彩排", "直播",
                   "录播", "看台", "座位", "投票", "打分器", "评分器", "马甲", "导演",
                   "现场不能", "进场", "门票"],
    "如何表达理性普通观众": ["看现场", "现场表现", "综合", "唱功", "编曲", "舞美", "氛围",
                     "不偏袒", "看每场", "每场发挥", "客观", "理性", "普通观众", "音乐爱好",
                     "听众", "不追星", "中立", "凭感觉", "听感", "我个人", "根据自己的"],
}
CAT_ORDER = list(CATEGORIES.keys())

# ---------- 推测性语言标记 ----------
SPEC_MARKERS = ["应该", "可能", "我觉得", "估计", "猜测", "好像", "据说", "怀疑", "大概",
                "也许", "感觉", "我猜", "不一定", "未必", "说不定", "据我了解", "疑似"]

# ---------- 纯噪声短词 (无目标关键词时丢弃) ----------
NOISE_EXACT = {
    "哈哈", "哈哈哈", "哈哈哈哈", "哈哈哈哈哈", "笑死", "啊啊", "啊啊啊", "救命", "蹲",
    "dd", "滴滴", "顶", "111", "1111", "11111", "+1", "好", "好的", "嗯", "嗯嗯", "哦",
    "是的", "对的", "666", "牛", "牛啊", "抱抱", "收到", "收到啦", "扣1", "1", "2", "3",
    "哈哈哈好", "哈哈哈哈哈哈", "确实", "对", "啊", "哎", "呜呜", "555", "哭", "裂开",
    "草", "我去", "牛批", "厉害", "加油", "冲", "期待", "期待了", "坐等", "等", "等一个",
}

# ---------- PII 脱敏规则 (顺序敏感) ----------
RE_IDCARD = re.compile(r'\d{17}[\dXx]')
RE_PHONE = re.compile(r'1[3-9]\d{9}')
RE_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
RE_WXID = re.compile(r'wxid_[0-9a-zA-Z_]+')
RE_URL = re.compile(r'https?://\S+|www\.[^\s，。！？]+|(?:weibo|douyin|iesdouyin|xiaohongshu|xhslink|t\.cn|v\.qq\.com|b23\.tv|bilibili)\.[^\s，。！？]*', re.I)
RE_QQ = re.compile(r'(?:qq|企鹅|加我)\s*[:：]?\s*\d{6,12}', re.I)
# 群内 @昵称 (微信 @某人) -> [@群友]; 注意保留歌手名(公众人物, 在正文里是讨论对象而非隐私)
RE_AT = re.compile(r'@[^\s@，。！？：；、）》\[\]【】]+')

# WeChat 表情 token (括号内无数字, 1-8 字符) — 仅用于清洗/归一化, 不含数字以保留 [歌手2026]
RE_EMOJI = re.compile(r'\[[^\[\]0-9]{1,8}\]')
RE_HEX = re.compile(r'^[0-9a-fA-F]{16,}$')  # 未解码的压缩 hex (无 \n 的 type=1)


def redact(text):
    """按顺序脱敏 PII。"""
    text = RE_IDCARD.sub('[身份证]', text)
    text = RE_PHONE.sub('[电话]', text)
    text = RE_EMAIL.sub('[邮箱]', text)
    text = RE_WXID.sub('[微信号]', text)
    text = RE_URL.sub('[社交链接]', text)
    text = RE_QQ.sub('[QQ]', text)
    text = RE_AT.sub('[@群友]', text)
    return text


def strip_emoji(text):
    return RE_EMOJI.sub('', text)


def cjk_len(text):
    return sum(1 for ch in text if '一' <= ch <= '鿿')


def is_noise(body, has_topical):
    """是否应作为噪声丢弃。本轮聚焦知识库: 未命中任何目标类别的消息一律丢弃。"""
    if not body or not body.strip():
        return True
    if cjk_len(body) == 0 and len(body.strip()) < 3:
        return True
    cleaned = re.sub(r'[\s\W_]+', '', strip_emoji(body))
    if len(cleaned) < 2:
        return True
    compact = re.sub(r'\s+', '', body).lower()
    if compact in NOISE_EXACT:
        return True
    if not has_topical:
        return True  # 非相关闲聊/上下文, 不进知识库
    return False


def classify(body):
    cats = []
    for cat in CAT_ORDER:
        for kw in CATEGORIES[cat]:
            if kw in body:
                cats.append(cat)
                break
    return cats


def is_speculative(body):
    return any(m in body for m in SPEC_MARKERS)


def norm_key(body):
    """归一化去重键: 去空白/标点/大小写。"""
    k = re.sub(r'[\s，。！？、,.!?；;：:~…\-—()（）【】\[\]"\'`]+', '', body)
    return k.lower()


def stream_records(path):
    """流式解析单行 JSON 数组。"""
    with open(path, encoding='utf-8') as fh:
        s = fh.read().strip()
    if s[:1] == '[':
        s = s[1:]
    if s[-1:] == ']':
        s = s[:-1]
    dec = json.JSONDecoder()
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i] in ' ,\n\r\t':
            i += 1
        if i >= n:
            break
        try:
            obj, end = dec.raw_decode(s, i)
        except Exception:
            nxt = s.find('{', i + 1)
            if nxt < 0:
                break
            i = nxt
            continue
        yield obj
        i = end


def main():
    os.makedirs(BYCAT, exist_ok=True)
    items = {}            # key -> 聚合记录
    type_counter = Counter()
    dropped = Counter()   # 各阶段丢弃计数
    sender_alias = {fid: {} for _, fid in FILES}  # file_id -> {raw_sender: alias}
    file_seen_order = {}  # file_id -> seq counter

    for fname, fid in FILES:
        path = os.path.join(BASE, fname)
        n_text = 0
        for idx, rec in enumerate(stream_records(path)):
            lt = str(rec.get('local_type', ''))
            type_counter[lt] += 1
            if lt != '1':
                continue
            n_text += 1
            mc = str(rec.get('message_content', ''))
            # 拆分发送者前缀
            if '\n' in mc:
                raw_sender, body = mc.split('\n', 1)
            else:
                raw_sender, body = '', mc
                if RE_HEX.match(body.strip()):
                    dropped['hex_compressed'] += 1
                    continue
            body = strip_emoji(body).strip()
            body = redact(body)                  # 先脱敏, 使分类/去噪都基于最终正文
            cats = classify(body)
            has_topical = len(cats) > 0
            if is_noise(body, has_topical):
                dropped['noise' if has_topical else 'non_topical'] += 1
                continue
            ts = int(rec.get('create_time') or 0)
            spec = is_speculative(body)
            # 发送者伪化
            fm = sender_alias[fid]
            if raw_sender not in fm:
                seq = len(fm) + 1
                fm[raw_sender] = '用户F%d_%04d' % (fid, seq)
            alias = fm[raw_sender]
            # 分类 (脱敏后再判一次, 防脱敏把关键词改掉; 此处以原 body 分类已够)
            key = norm_key(body)
            if not key:
                dropped['empty_key'] += 1
                continue
            it = items.get(key)
            if it is None:
                it = {
                    'text': body,
                    'categories': set(),
                    'senders': set(),
                    'files': set(),
                    'occ': 0,
                    'spec': 0,
                    'first_ts': ts,
                    'last_ts': ts,
                }
                items[key] = it
            it['categories'].update(cats)
            it['senders'].add(alias)
            it['files'].add(fid)
            it['occ'] += 1
            if spec:
                it['spec'] += 1
            if ts:
                if not it['first_ts'] or ts < it['first_ts']:
                    it['first_ts'] = ts
                if ts > it['last_ts']:
                    it['last_ts'] = ts
            if len(body) > len(it['text']):
                it['text'] = body
            if idx and idx % 200000 == 0:
                print('  ...%s scanned %d records' % (fname, idx))
        print('[%s] type=1 text = %d' % (fname, n_text))

    # 计算来源强度 + 组装输出记录
    rows = []
    for it in items.values():
        occ = it['occ']
        ds = len(it['senders'])
        fs = len(it['files'])
        spec_ratio = it['spec'] / occ if occ else 0
        # 来源强度: 程序级"信号", 非最终裁定 (蒸馏阶段会跨条目归并近义表述再定稿)
        if ds >= 4 and occ >= 3 and fs >= 2:
            ss = '多人反复提到'
        elif spec_ratio > 0.5:
            ss = '推测'
        elif occ == 1 and ds == 1 and spec_ratio > 0:
            ss = '证据不足'   # 孤立且带推测/含糊
        else:
            ss = '个别经验'   # 单人/少数人的具体一手陈述
        rows.append({
            'text': it['text'],
            'categories': [c for c in CAT_ORDER if c in it['categories']],
            'occurrences': occ,
            'distinct_senders': ds,
            'files': sorted(it['files']),
            'first_ts': it['first_ts'],
            'last_ts': it['last_ts'],
            'source_strength': ss,
            'speculation_ratio': round(spec_ratio, 2),
            'is_speculative': it['spec'] > 0,
            '_signal': occ * ds,
        })

    rows.sort(key=lambda r: r['_signal'], reverse=True)

    # cleaned_messages.jsonl (全量)
    with open(os.path.join(OUT, 'cleaned_messages.jsonl'), 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps({k: v for k, v in r.items() if k != '_signal'},
                                ensure_ascii=False) + '\n')

    # by_category/*.jsonl (多归属)
    cat_files = {}
    for c in CAT_ORDER:
        fp = os.path.join(BYCAT, '%02d_%s.jsonl' % (CAT_ORDER.index(c) + 1, c))
        cat_files[c] = open(fp, 'w', encoding='utf-8')
    for r in rows:
        for c in r['categories']:
            cat_files[c].write(json.dumps({k: v for k, v in r.items() if k != '_signal'},
                                          ensure_ascii=False) + '\n')
    for fh in cat_files.values():
        fh.close()

    # category_summaries.jsonl (每类 top 80, 蒸馏输入)
    with open(os.path.join(OUT, 'category_summaries.jsonl'), 'w', encoding='utf-8') as fh:
        for c in CAT_ORDER:
            sub = [r for r in rows if c in r['categories']]
            top = sub[:80]
            fh.write(json.dumps({
                'category': c,
                'total_items': len(sub),
                'total_occurrences': sum(r['occurrences'] for r in sub),
                'top': [{k: v for k, v in r.items() if k != '_signal'} for r in top],
            }, ensure_ascii=False) + '\n')

    # 统计输出
    print('\n===== 统计 =====')
    print('local_type 分布:', type_counter.most_common(12))
    print('丢弃:', dict(dropped))
    print('去重后唯一条目: %d' % len(rows))
    print('保留(有类别)条目: %d' % sum(1 for r in rows if r['categories']))
    print('无类别条目(仅信息量保留): %d' % sum(1 for r in rows if not r['categories']))
    sc = Counter(r['source_strength'] for r in rows)
    print('来源强度分布:', dict(sc))
    print('各类条目数:')
    for c in CAT_ORDER:
        n = sum(1 for r in rows if c in r['categories'])
        print('  %02d %s: %d' % (CAT_ORDER.index(c) + 1, c, n))


if __name__ == '__main__':
    main()
