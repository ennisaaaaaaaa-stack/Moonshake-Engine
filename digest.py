"""digest 感官收件箱聚合器（Moonshake phase01 第三件，2026-10-05）。

设计师的原始设计（2026-10-05 口述，契约字段直接翻译）：
  agent session 拉起时收到的器官概览——
    耳朵：听到了 n 条电台；n 条播客；n 条新音乐；权重前三标题为 XX，XX，XX
    Internet reach：n 条互联网信息，权重前三标题
    眼睛：a摄像头 n 次；b摄像头 n 次；地图 n 次
  拉取三级：只拉某细分器官概览 / 全概览（token 帽内取高权）/ 下钻单通道再深挖单条。

四设计钉子（实现侧补，当晚拍板）：
  1. 计数去重后聚合（同一目标反复出现=1条目带count，phase13冷却同思路）
  2. 两级拉取懒加载
  3. 收件箱读 Moonshake 自己的事件日志，不读记忆库——「器官听见了什么」和
     「记忆留下了什么」是两本账；wake packet = 本digest + salience_read背景
  4. 权重初值 = saliency_hint × confidence；二号槽打分器建好后换重排序

零依赖铁律同 contract/consent_gate：不 import 记忆库、零副作用纯聚合。
"""

from collections import defaultdict

from contract import split_organ_id

# 概览层默认参数（拍板③边用边调同款：先钉保守值）
DEFAULT_TOP_K = 3          # 每通道权重前几
DEFAULT_TOKEN_CAP = 1200   # 全概览 token 帽（粗估：1 token ≈ 3 chars，帽按字符预算折算）


def _weight(ev):
    """单事件权重：saliency_hint × confidence（二号槽建成前的初值排序）。"""
    try:
        return float(ev.get("saliency_hint", 0.0)) * float(ev.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _dedup_key(ev):
    """去重键：organ 通道 × 语义目标。同目标反复出现聚成一条，count 累积。"""
    return (ev.get("organ_id", "?"), ev.get("payload_summary", "?"))


def _split_safe(oid):
    """消费侧兜底：缺失/畸形 organ_id（三级、空段）不炸聚合——落进
    ('?', 原串) 桶可追溯。契约照抛 ValueError（脏数据是 bug），
    优雅降级是消费方的选择（审计④：M10 只兜了缺失没兜畸形）。"""
    try:
        return split_organ_id(oid or "?")
    except ValueError:
        return ("?", str(oid))


def digest(events, top_k=DEFAULT_TOP_K, token_cap=DEFAULT_TOKEN_CAP, organ_filter=None):
    """聚合感官收件箱概览。

    events: 未裁决的原始事件流（已过 consent_gate 的降级/全量行也兼容——
            纯读字段聚合，不关心 verdict）。
    organ_filter: None=全部器官；"ear"=只拉耳朵（含 ear.radio/ear.podcast 全通道）；
                 "ear.radio"=只拉该细分通道。
    返回 dict：
      { "organs": { organ: { "channels": { ch: {"count": n,            # 去重后条目数
                                                   "raw_events": n,     # 去重前原始事件数
                                                   "top": [ {"summary","weight","count"} ] } }
                              "total_raw": n } },
        "dropped_by_cap": bool }
    token_cap: 概览渲染的字符预算（粗折算）。聚合先全量算，渲染层负责按帽截断——
    本函数只标 dropped_by_cap，不做静默丢条（调用方决定砍谁，概览砍条必须显式）。
    """
    # ── 器官过滤 ──
    if organ_filter is not None:
        if "." in organ_filter:
            events = [e for e in events if e.get("organ_id", "") == organ_filter]
        else:
            events = [e for e in events
                      if _split_safe(e.get("organ_id"))[0] == organ_filter]

    # ── 聚合：organ → channel → 去重条目 ──
    buckets = defaultdict(lambda: defaultdict(dict))  # organ → channel → key → entry
    raw_counts = defaultdict(lambda: defaultdict(int))
    for ev in events:
        organ, channel = _split_safe(ev.get("organ_id"))
        key = _dedup_key(ev)
        bucket = buckets[organ][channel]
        if key not in bucket:
            bucket[key] = {"summary": ev.get("payload_summary", "?"),
                           "weight": _weight(ev), "count": 1, "_last_ts": ev.get("ts", "")}
        else:
            bucket[key]["count"] += 1
            w = _weight(ev)
            if w > bucket[key]["weight"]:
                bucket[key]["weight"] = w
        raw_counts[organ][channel] += 1

    # ── 渲染概览 ──
    organs_out = {}
    chars = 0
    dropped = False
    for organ, channels in sorted(buckets.items()):
        ch_out = {}
        for channel, entries in sorted(channels.items()):
            ranked = sorted(entries.values(), key=lambda x: (-x["weight"], x["summary"]))
            top = [{"summary": e["summary"], "weight": round(e["weight"], 4), "count": e["count"]}
                   for e in ranked[:top_k]]
            ch_out[channel] = {"count": len(entries), "raw_events": raw_counts[organ][channel], "top": top}
            chars += len(str(top))
            if len(ranked) > top_k:
                chars += 40  # 「…还有N条」占位粗估
        organs_out[organ] = {"channels": ch_out, "total_raw": sum(raw_counts[organ].values())}

    if token_cap is not None and chars > token_cap * 3:  # 1 token ≈ 3 chars 粗折算
        dropped = True

    return {"organs": organs_out, "dropped_by_cap": dropped}
