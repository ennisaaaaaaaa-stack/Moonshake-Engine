"""事件日志（Moonshake phase02 第二件，2026-10-05）。

设计出处：docs/phase02-design.md T3。三枚拍板已落（2026-10-05）：
  存储 = 日切 JSONL（tail/grep 可审、轮转=文件名、追加不改写）；
  只记幸存者（reject = 零行，日志永远纯事件）；
  登记默认严格（strict=True 未查登记就不许写——fail-closed）。

铁律：只 import 同仓纯函数（contract / consent_gate / registry），
不 import 记忆库。写入路径薄：形状检查 → 登记检查 → 序列化 → 追加一行。
不做任何变形——降级发生在 gate；但 write_degraded 行由本模块自己套
degraded_event（调用方传原始事件+裁决即可），杜绝「忘了降级就落库」
的人祸口子：存储里永远不可能出现「标着降级却带着原始 ref」的行。

row_id = <YYYYMMDD>#<seq>（当日文件内序号，4 位零填充）——字符串
字典序即时间序（日期定宽 8 + 序号定宽 4），read_since 的游标比较
直接用字符串比较，无时钟依赖。
文件名带横杠（2026-10-05.jsonl，设计稿钉的形状，人眼可读）；
row_id 紧凑无横杠——两个名字两种口径，互不混用。
"""

import json
import os
from datetime import datetime

from contract import validate_event
from consent_gate import degraded_event
from registry import is_registered

_ACTIONS = ("reject", "write_degraded", "write_full")


def _now_iso(now=None):
    """logged_at：默认本机时区，测试可注入。"""
    dt = now if now is not None else datetime.now().astimezone()
    return dt.isoformat(timespec="seconds")


def _dashed(ymd):
    """紧凑日期 → 文件名日期：'20261005' → '2026-10-05'。"""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}" if len(ymd) == 8 else ymd


def _row_id_for(log_dir, date_str):
    """当日序号 = 现存最大 seq + 1。脏行不挡追加（跳过），审计层负责看见。"""
    path = os.path.join(log_dir, f"{_dashed(date_str)}.jsonl")
    seq = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    seq = max(seq, int(json.loads(line)["row_id"].split("#")[1]))
                except (ValueError, KeyError, IndexError, json.JSONDecodeError):
                    continue
    return f"{date_str}#{seq + 1:04d}"


def log_gated(log_dir, event, verdict, registry=None, strict=True, now=None):
    """把 gate 裁决落一行。返回落库的 row；reject 返回 None（零行）。

    strict=True（默认）：必须传 registry 且器官在岗，否则 ValueError——
    fail-closed：「ear.rdaio 死在门口，不死在数据里」。
    write_degraded：存储的就是剥好的降级形态（本函数套 degraded_event）。
    """
    action = verdict.get("action")
    if action == "reject":
        return None
    if action not in _ACTIONS:
        raise ValueError(f"gate verdict 非法 action: {action!r}")

    ok, errs = validate_event(event)
    if not ok:
        raise ValueError(f"事件不合契约（bug 不是数据，不静默兼容）: {errs}")

    oid = event["organ_id"].strip()
    if strict:
        if registry is None:
            raise ValueError("strict=True 需要 registry（fail-closed：不查登记就不许写）")
        if not is_registered(registry, oid):
            raise ValueError(f"未登记器官 fail-closed: {oid!r}（死在门口，不死在数据里）")

    row_event = degraded_event(event) if action == "write_degraded" else dict(event)
    logged_at = _now_iso(now)
    date_str = logged_at[:10].replace("-", "")
    row = {
        "row_id": _row_id_for(log_dir, date_str),
        "logged_at": logged_at,
        "gate_action": action,
        "gate_reason": verdict.get("reason", ""),
        "event": row_event,
    }
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"{_dashed(date_str)}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _iter_rows(log_dir):
    """按文件名序遍历全部行（日切文件名排序=时间序）。脏行跳过。"""
    if not os.path.isdir(log_dir):
        return
    for name in sorted(os.listdir(log_dir)):
        if not (name.endswith(".jsonl") and name[:1].isdigit()):
            continue
        with open(os.path.join(log_dir, name), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def scan(log_dir, date=None):
    """整日志 / 某日。date 接受 '2026-10-05' 或 '20261005'。"""
    if date is None:
        return list(_iter_rows(log_dir))
    norm = str(date).replace("-", "")
    return [r for r in _iter_rows(log_dir) if r.get("row_id", "").split("#")[0] == norm]


def read_since(log_dir, cursor):
    """增量读：cursor = 上次看到的最后 row_id（None = 从头）。

    返回 (rows, new_cursor)。row_id 字符串字典序 = 时间序（见模块注释），
    游标比较即字符串比较。无新行时 new_cursor 原样返回。
    """
    rows = [r for r in _iter_rows(log_dir)
            if cursor is None or r.get("row_id", "") > cursor]
    new_cursor = rows[-1]["row_id"] if rows else cursor
    return rows, new_cursor
