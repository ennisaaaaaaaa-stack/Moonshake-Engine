"""triage 旁听记录（sidecar，Moonshake v1.2，2026-10-05）。

为什么存在：triage 的拒和 consent 的拒一样静默零行——噪音门的裁决
不可见（mingming初审侧车提醒）。「门在干活，但没人看得见它干活」就是
Ready 灯老坑原样复发：severities 会漂、规则会被好心松牙，没人看见
=没人知道门死了。这条升格成硬约束：第一个真器官上线前 sidecar 必接。

定性（zhaozhao 21:19 拍板口径）：诊断面，不是消费面——
  · 本文件给人和审计工具看（wc -l / grep reason / 画趋势），不给
    任何运行时决策供料。任何模块 import 本模块做放行/拦截判断 = 用错了。
  · 拒因词汇表是稳定接口（keep 的行不落 sidecar，只有拒；reason 顺序
    见 triage.triage docstring）。
  · 写失败不挡主路径：sidecar 是旁听席，旁听席塌了不许砸正厅
    （except 一切，静默吞——诊断面自己不能变成新的故障源）。

行形状：{"ts": 写入时刻 ISO, "organ_id": str, "reason": 拒因, "field": 命中字段}
  field ∈ {"payload_summary", "event_type"}——v1.2 D 把 event_type 拉进
  扫描面后，侧车记录命中哪个字段（mingming问的「扫描面在哪」可答）。
纯函数 + 一个 write_rejections 落盘器；零第三方依赖，不 import 记忆库。
"""

import json
import os
from datetime import datetime


def _now_iso(now=None):
    dt = now if now is not None else datetime.now().astimezone()
    return dt.isoformat(timespec="seconds")


def record_row(organ_id, reason, field, now=None):
    """纯函数：组一行 sidecar 记录（不落盘）。"""
    return {"ts": _now_iso(now), "organ_id": str(organ_id),
            "reason": str(reason), "field": str(field)}


def write_rejections(path, verdict, event, now=None):
    """把一条拒裁决落 sidecar。keep=True 一行不落（幸存者不进旁听席）。

    设计钉子：写失败静默吞（except Exception: pass）——旁听席塌了不许
    砸正厅。诊断面不是消费面，本函数返回 None，无返回值供决策使用。
    """
    if verdict.get("keep", True):
        return
    row = record_row(event.get("organ_id", "?"), verdict.get("reason", "?"),
                     "event_type" if verdict.get("reason") == "event_type_injection"
                     else "payload_summary", now=now)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 旁听席塌了不许砸正厅（诊断面不成为故障源）


def load_stats(path):
    """读 sidecar 全量（脏行跳过）。只给人看/审计工具看，不给运行时决策供料。"""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def summarize(rows):
    """人眼视图：按拒因计数。诊断用途（「门在不在干活」一屏可见）。"""
    out = {}
    for r in rows:
        key = f"{r.get('reason', '?')}[{r.get('field', '?')}]"
        out[key] = out.get(key, 0) + 1
    return out
