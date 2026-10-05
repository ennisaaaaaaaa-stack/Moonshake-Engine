"""事件日志（Moonshake phase02 第二件，2026-10-05）。

设计出处：docs/phase02-design.md T3。三枚拍板已落（2026-10-05）：
  存储 = 日切 JSONL（tail/grep 可审、轮转=文件名、追加不改写）；
  只记幸存者（reject = 零行，日志永远纯事件）；
  登记默认严格（strict=True 未查登记就不许写——fail-closed）。

铁律：只 import 同仓纯函数（contract / consent_gate / registry），不 import
记忆库。写入路径薄：形状检查 → 登记检查 → 声明对照 → 序列化 → 追加一行。
不做任何变形——降级发生在 gate；但 write_degraded 行由本模块自己套
degraded_event（调用方传原始事件+裁决即可），杜绝「忘了降级就落库」
的人祸口子：存储里永远不可能出现「标着降级却带着原始 ref」的行。

声明对照墙（v1.2，zhaozhaoA/E——「声明了没人读」同族病一次治）：
  modality  : 事件自报 modality 必须与 slot 声明一致，失配 fail-closed。
               modality 是器官的事实声明不是许可——写路径对照事实不越权
               （防选键攻击：policy 只给 audio 开 min_tier_full=2，任何器官
               自称 modality=audio 就吃到全量口子）。
  emits_tier: 声明不是许可，但声明了就得被读——slot 声明 emits_tier=N 时，
               事件 consent_tier > N 一律 fail-closed（zhaozhaoE：emits_tier=0
               的器官发 tier3 事件一路绿灯=死字段；牙齿长在对照上，不长在
               「登记了就信」上）。
  registry 无声明字段（如老 registry 未写 emits_tier）= 不对照，照旧放行
  ——牙齿对照「声明与行为不符」，不强迫声明（registry 是电话簿不是警察局）。

row_id = <YYYYMMDD>#<seq>（当日文件内序号，4 位零填充）——v1.2 起游标
比较不再信字符串字典序：read_since 按 (日期, 序号数值) 比较（zhaozhaoC：
#9999 > #10000 字符串序反转，当日满万行时游标停在 #9999 会漏掉
#10000 起的全部行——定宽 4 假设在 seq 破万时本身裂）。
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


def _check_declarations(event, registry, oid):
    """A/E 声明对照墙（v1.2）：slot 声明的 modality / emits_tier 对照事件自报。

    返回错误字符串（None=通过）。registry 无声明 = 不对照（电话簿不是警察局，
    牙齿对照「声明与行为不符」，不强迫声明）。
    """
    slot = registry.get("slots", {}).get(oid, {})

    slot_mod = slot.get("modality")
    if slot_mod and event.get("modality") != slot_mod:
        return (f"modality 失配 fail-closed: {oid} 声明 {slot_mod!r}，"
                f"事件自报 {event.get('modality')!r}（zhaozhaoA：防选键攻击）")

    slot_tier = slot.get("emits_tier")
    evt_tier = event.get("consent_tier")
    if (isinstance(slot_tier, int) and not isinstance(slot_tier, bool)
            and isinstance(evt_tier, int) and not isinstance(evt_tier, bool)
            and evt_tier > slot_tier):
        return (f"consent_tier 超声明 fail-closed: {oid} 声明 emits_tier={slot_tier}，"
                f"事件 consent_tier={evt_tier}（zhaozhaoE：声明不是许可，但声明了就被读）")

    return None


def log_gated(log_dir, event, verdict, registry=None, strict=True, now=None):
    """把 gate 裁决落一行。返回落库的 row；reject 返回 None（零行）。

    strict=True（默认）：必须传 registry 且器官在岗，否则 ValueError——
    fail-closed：「ear.rdaio 死在门口，不死在数据里」。
    strict=True 且器官已登记：slot 的 modality / emits_tier 声明对照事件
    自报，失配 ValueError（A/E 墙，v1.2）。
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
        decl_err = _check_declarations(event, registry, oid)
        if decl_err:
            raise ValueError(decl_err)

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


def _row_key(row_id):
    """row_id → (日期串, 序号数值)（zhaozhaoC，v1.2）：比较用元组，不信定宽字符串序。

    非法形状（无 # / 序号非数字）→ (原串, -1)：永远排在最前，永不挡增量读
    ——脏行不吞后面的合法行。
    """
    try:
        date_part, seq_part = str(row_id).split("#", 1)
        return (date_part, int(seq_part))
    except (ValueError, AttributeError):
        return (str(row_id), -1)


def read_since(log_dir, cursor):
    """增量读：cursor = 上次看到的最后 row_id（None = 从头）。

    返回 (rows, new_cursor)。游标比较按 (日期, 序号数值)（v1.2，zhaozhaoC）——
    #9999/#10000 定宽字符串序反转不再漏行。无新行时 new_cursor 原样返回。
    """
    cur_key = _row_key(cursor) if cursor is not None else None
    rows = [r for r in _iter_rows(log_dir)
            if cur_key is None or _row_key(r.get("row_id", "")) > cur_key]
    new_cursor = rows[-1]["row_id"] if rows else cursor
    return rows, new_cursor
