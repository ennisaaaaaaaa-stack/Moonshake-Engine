"""consent 出关纯函数（自 tideline-memory sensory_write.py DEFAULT_POLICY 语义迁出，2026-10-05）。

设计师拍板（2026-10-02，v2.11 进码；2026-10-05 随契约迁入 Moonshake）：
「最低档授权就够了，不然太占空间了吧？器官毕竟是没有经过真实判断筛选的内容」
→ 全模态兜底 min_tier_full=999 不可达 = 原始样本默认永不跟着事件走；
  哪个器官想存全量，单独传 policy 点头。

铁律：本模块零依赖——不 import 任何记忆库、不碰任何存储、零副作用。
策略语义与 tideline sensory_write 的 DEFAULT_POLICY 完全等价（两家库同一枚拍板），
Tideline 侧守卫保留当纵深防御（已建已审，白留的保险不拆）。
"""

DEFAULT_POLICY = {"*": {"min_degraded": 1, "min_tier_full": 999}}


def enforce_policy(event, policy=None):
    """纯函数：事件出关裁决。

    返回 (verdict, action)：
      verdict = dict(ok=bool, action=str, reason=str, modality=str)
      action ∈ {"reject", "write_degraded", "write_full"}

    规则（与 tideline sensory_write 对齐）：
      tier < min_degraded          → reject（拒写，零落行）
      min_degraded ≤ tier < full   → write_degraded（降级：剥 payload_ref，只留蒸馏摘要）
      tier ≥ min_tier_full         → write_full（全量放行）
    策略匹配：先精确 modality 键，miss 后回落 "*" 兜底——无 "*" 键的策略是
    白名单 fail-closed（审阅时签的口径：与「器官单独点头」语义自洽）。
    """
    from contract import DEFAULT_POLICY as _DEF  # 便于单文件独立测试；包内导入另走相对路径

    pol = policy if policy is not None else _DEF
    modality = event.get("modality", "")
    rule = pol.get(modality) or pol.get("*")
    if rule is None:
        return ({"ok": False, "action": "reject",
                 "reason": f"策略无 '{modality}' 键且无 '*' 兜底（fail-closed）", "modality": modality})

    tier = event.get("consent_tier")
    min_deg = rule.get("min_degraded", 1)
    min_full = rule.get("min_tier_full", 999)

    if tier is None or isinstance(tier, bool) or not isinstance(tier, int) or not (0 <= tier <= 3):
        return ({"ok": False, "action": "reject",
                 "reason": f"consent_tier 非法: {tier!r}", "modality": modality})
    if tier < min_deg:
        return ({"ok": False, "action": "reject",
                 "reason": f"tier {tier} < min_degraded {min_deg}", "modality": modality})
    if tier >= min_full:
        return ({"ok": True, "action": "write_full",
                 "reason": f"tier {tier} ≥ min_tier_full {min_full}", "modality": modality})

    # 降级：返回降级事件本体（剥 payload_ref），调用方拿去落库/转发
    return ({"ok": True, "action": "write_degraded",
             "reason": f"tier {tier} < min_tier_full {min_full}，剥 payload_ref 只留蒸馏摘要",
             "modality": modality})


def degraded_event(event):
    """降级拷贝：剥 payload_ref，打 original_ref_dropped 标记。不修改原事件。"""
    d = dict(event)
    if "payload_ref" in d:
        del d["payload_ref"]
    d["original_ref_dropped"] = True
    return d
