"""器官插槽登记处（Moonshake phase02 第一件，2026-10-05）。

设计出处：docs/phase02-design.md T2。拍板已落（2026-10-05）：
登记默认严格——未登记器官在写日志时 fail-closed（eventlog 侧执法），
「ear.rdaio 死在门口，不死在数据里」。

铁律同 contract/consent_gate/digest：零第三方依赖、不 import 记忆库、
纯函数。登记处不是警察局：emits_tier 是声明不是许可，执法永远在
gate + policy，本模块永不做任何放行/拦截裁决。

registry 形状：{"slots": {organ_id: slot, ...}}
序列化 = registry.json（原子写：tmp + os.replace），文件只是序列化，
读写工具薄到只做 open/json/replace。

复活口径：register_slot 拒绝一切已存在的 organ_id（含 inactive）——
复活是一次显式的手动编辑（直接改 json 后重载），不做隐式复活绕过审计。
"""

import json
import os

from contract import split_organ_id

REQUIRED_FIELDS = ("organ_id", "modality")


def validate_slot(slot):
    """校验插槽声明。返回 (ok, errors)；ok 时 errors 为空。

    规则：
      organ_id    : 必填，过 contract.split_organ_id（两级制）
      modality    : 必填，非空字符串（与 consent policy 的匹配键同域）
      description : 可空；非空时字符串
      emits_tier  : 可空；非空时整数（非 bool）∈[0,3]
                    ——声明不是许可，但脏数据照抓（4 不是更高授权是笔误）
      registered_at: 可空；非空时字符串
      active      : 默认 True；必须 bool
      其他键      : 照放（器官自定义元数据），不裁
    """
    errors = []
    if not isinstance(slot, dict):
        return (False, ["slot 必须是 dict"])

    for f in REQUIRED_FIELDS:
        v = slot.get(f)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"必填字段缺失或为空: {f}")

    if not any("organ_id" in e for e in errors):
        try:
            split_organ_id(slot.get("organ_id", ""))
        except ValueError as e:
            errors.append(str(e))

    desc = slot.get("description")
    if desc is not None and not isinstance(desc, str):
        errors.append("description 非空时必须是字符串")

    tier = slot.get("emits_tier")
    if tier is not None and (not isinstance(tier, int) or isinstance(tier, bool)
                             or not (0 <= tier <= 3)):
        errors.append(f"emits_tier 非法: {tier!r}（声明不是许可，但整数 0-3 之外是脏数据）")

    ra = slot.get("registered_at")
    if ra is not None and not isinstance(ra, str):
        errors.append("registered_at 非空时必须是字符串")

    active = slot.get("active", True)
    if not isinstance(active, bool):
        errors.append("active 必须是 bool")

    return (not errors), errors


def register_slot(registry, slot):
    """登记插槽（copy-on-write，返回新 registry）。已存在的 organ_id 一律
    ValueError——含 inactive：复活须显式手动编辑，不隐式绕过审计。
    """
    ok, errs = validate_slot(slot)
    if not ok:
        raise ValueError(f"slot 非法: {errs}")
    oid = slot["organ_id"].strip()
    if oid in registry.get("slots", {}):
        raise ValueError(f"organ_id 已登记: {oid}（复活=显式手动编辑，不走 register）")
    new = {"slots": dict(registry.get("slots", {}))}
    entry = dict(slot)
    entry["organ_id"] = oid
    new["slots"][oid] = entry
    return new


def retire_slot(registry, organ_id):
    """器官退休：active=False，历史不动。不存在的 organ_id = ValueError。"""
    oid = (organ_id or "").strip()
    slots = registry.get("slots", {})
    if oid not in slots:
        raise ValueError(f"organ_id 未登记，无从退休: {oid!r}")
    new = {"slots": {k: dict(v) for k, v in slots.items()}}
    new["slots"][oid]["active"] = False
    return new


def is_registered(registry, organ_id):
    """只认 active 槽位（退休=不在岗）。"""
    oid = (organ_id or "").strip()
    slot = registry.get("slots", {}).get(oid)
    return bool(slot) and slot.get("active", True) is True


def list_organs(registry, active_only=True):
    """插槽清单，按 organ_id 排序。默认只列在岗器官。"""
    slots = registry.get("slots", {})
    items = [dict(v) for _, v in sorted(slots.items())]
    if active_only:
        items = [s for s in items if s.get("active", True)]
    return items


def load_registry(path):
    """读 registry.json（文件只是序列化）。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_registry(path, registry):
    """原子写（tmp + os.replace）。返回 path。"""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path
