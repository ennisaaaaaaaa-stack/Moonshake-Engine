"""分诊台（Moonshake phase02 第三件，2026-10-05）。

设计师提案原点（2026-10-05）：「信息进器官之前先过一轮机械审核」——
落在契约事件层（方言层没有标准点，contract 事件是第一个标准点）：
validate 之后、gate 之前。

两条轴（设计稿钉死）：
  consent gate 保隐私——什么可以离开器官（主人：用户）；
  triage 保注意力——什么配成为一个事件。垃圾根本不该走到门卫面前。

四条设计钉子：
  1. 全机械零模型：规则确定性、无 LLM 调用。带语义模型的检测是
     另一层的事，永不混进「机械」的定义里（prompt-guard 模式层挂
     候选位，等第一个真实器官上线看到真实攻击面再决定装不装）。
  2. 永不读 saliency_hint——入境用规则、注意用权重，两个旋钮不许
     塌成一个（README 设计规则 5：入境 ≠ 注意）。
  3. 拒 = 静默零行（同 gate 的 survivors-only 语义）。观测走 sidecar
     （triage_stats.jsonl，工具层的事），本模块纯函数不管。
  4. 限流与去重需要状态：state 由调用方持有、逐事件传回（结果里的
     "state" 原样传给下一次调用），本模块不藏可变全局。

注入黑名单第一版自写，专抓 dumb injection（「忽略之前所有指令」
级别的明文攻击）；这层是纵深防御的第三层，不是承重墙——承重的
是结构：默认降级（原始样本不进门）+ adapter 端数据包裹（摘要永不
裸奔进 prompt）。军备竞赛不追求完美检测，只追求层数够多。
"""

import re
from datetime import datetime

DEFAULT_RULES = {
    "rate_per_hour": 60,        # 单器官每小时放行上限（计数的是放行者）
    "dedup_window_min": 30,     # 同 (organ_id, payload_summary) 窗口内折叠
    "confidence_floor": 0.2,    # collector 自己都不信的别进门
    "blocklist": [],            # 关键词黑名单（payload_summary 子串匹配，不区分大小写）
    "injection_patterns": [     # dumb injection 句式（正则，不区分大小写）
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?)",
        r"disregard\s+(all\s+)?(previous|prior|above|earlier)",
        r"forget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?)",
        r"(reveal|show|print|output|repeat|leak)\s+[^.?!]{0,60}?(api[\s_-]?key|secret|password|token|credentials?)",
        r"you\s+are\s+now\s+a\b",
        r"new\s+instructions?\s*[:：]",
        r"^\s*system\s*[:：]",
        r"<\|im_start\|>",
        r"(jailbreak|developer\s+mode|do\s+anything\s+now)",
        r"system\s+prompt\s*[:：]",
    ],
}

_CACHE = [re.compile(p, re.IGNORECASE) for p in DEFAULT_RULES["injection_patterns"]]


def _patterns_for(rules):
    """默认规则用预编译缓存；自定义规则按次编译（机械规则都很短，够快）。"""
    pats = rules.get("injection_patterns")
    if pats is DEFAULT_RULES["injection_patterns"]:
        return _CACHE
    return [re.compile(p, re.IGNORECASE) for p in (pats or [])]


def triage(event, rules=None, state=None):
    """机械分诊。返回 {"keep": bool, "reason": str, "state": 新状态}。

    reason：放行时 "ok"；否则为首个命中的规则名（归因顺序）：
      confidence_floor → injection_pattern → blocklist → dedup → rate_cap
    state：不透明（近期窗口），调用方原样传回下一次调用。
    ts 无法解析时：内容检查照跑，窗口检查（dedup/rate）跳过——
    契约只要求 ts 非空字符串，格式由调用方保证（v1 口径）。
    """
    r = dict(DEFAULT_RULES)
    if rules:
        r.update(rules)
    st = state or {"recent": {}, "hour": {}}

    summary = str(event.get("payload_summary", ""))
    oid = str(event.get("organ_id", "?"))
    conf = event.get("confidence")

    # 1. 置信度地板
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) \
            or conf < r["confidence_floor"]:
        return {"keep": False, "reason": "confidence_floor", "state": st}

    # 2. 注入句式（dumb injection 黑名单）
    if any(p.search(summary) for p in _patterns_for(r)):
        return {"keep": False, "reason": "injection_pattern", "state": st}

    # 3. 关键词黑名单
    low = summary.lower()
    for kw in r.get("blocklist") or []:
        if str(kw).lower() in low:
            return {"keep": False, "reason": "blocklist", "state": st}

    # 4/5. 窗口检查需要 ts
    try:
        t = datetime.fromisoformat(str(event.get("ts", "")))
    except ValueError:
        t = None
    if t is None:
        return {"keep": True, "reason": "ok", "state": st}

    window_s = r["dedup_window_min"] * 60
    recent = [(ot, s) for (ot, s) in st["recent"].get(oid, [])
              if (t - ot).total_seconds() <= window_s]

    # 4. 去重窗：同目标窗口内折叠（digest 的去重在入境之后，这层先挡洪水）
    if any(s == summary for (_, s) in recent):
        st2 = {"recent": {**st["recent"], oid: recent}, "hour": st["hour"]}
        return {"keep": False, "reason": "dedup", "state": st2}

    # 5. 限流：计数的是放行者——卡死的 collector 不许淹日志
    hour_now = t.strftime("%Y%m%d%H")
    hour = {k: v for k, v in st["hour"].items() if k.split("|", 1)[1] >= hour_now}
    hkey = f"{oid}|{hour_now}"
    if hour.get(hkey, 0) >= r["rate_per_hour"]:
        st2 = {"recent": {**st["recent"], oid: recent}, "hour": hour}
        return {"keep": False, "reason": "rate_cap", "state": st2}

    st2 = {"recent": {**st["recent"], oid: recent + [(t, summary)]},
           "hour": {**hour, hkey: hour.get(hkey, 0) + 1}}
    return {"keep": True, "reason": "ok", "state": st2}
