#!/usr/bin/env python3
"""Moonshake phase01 夹具：契约 + consent出关 + digest收件箱（三件全钉）。

✅ GREEN 2026-10-05（phase01 收官跑，25/25）：
   contract.py 为当夜重建版（原件 write_file 回执虚报、盘上无文件，依本夹具+
   tideline sensory_write 语义+存活模块 import 三源重建），重建后本夹具全绿。
   修复记录：M1e 首跑暴露夹具自身废弃行（恒真空转检查裸调抛错函数）——已删，
   分诊=夹具错非代码错，契约抛 ValueError 行为正确。

验收点：
  M1 契约：必填齐/缺字段拒/organ_id 两级拆分/两级空段拒/裸器官→general
  M2 契约：consent_tier 0-3 整数（bool 拒）/confidence、saliency_hint 0-1
  M3 出关：默认档 tier0 拒、tier1+ 降级（剥 ref 留 dropped 痕）、999 不可达=永不全量
  M4 出关：显式策略全量可达；无"*"兜底的白名单策略 fail-closed
  M5 出关：enforce 不改原事件（纯函数）；degraded_event 剥 ref 不动原件
  M6 digest：去重聚合（同目标 5 次=1 条目 count=5）、raw_events 计数保留去重前
  M7 digest：top-3 按权重排、tie 按 summary 字典序稳定
  M8 digest：organ 过滤（器官级 ear / 通道级 ear.radio）
  M9 digest：token 帽显式标记不静默丢（dropped_by_cap）
  M10 digest：空事件流/器官缺 organ_id 不炸（优雅降级到 "?"）
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))  # digest/consent_gate 内部 `from contract import ...` 依赖同目录解析

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    contract = _load("contract")
    consent = _load("consent_gate")
    digest_m = _load("digest")

    def ev(**kw):
        base = {"ts": "2026-10-05T12:00:00Z", "organ_id": "ear.radio", "modality": "audio",
                "event_type": "song_detected", "payload_summary": "验证·副歌段",
                "confidence": 0.9, "consent_tier": 2, "saliency_hint": 0.4}
        base.update(kw)
        return base

    # ── M1/M2 契约 ──
    print("── M1/M2 事件契约 ──")
    ok, errs = contract.validate_event(ev())
    check("M1a 必填齐通过", ok, str(errs))
    ok, errs = contract.validate_event(ev(modality=None))
    check("M1b 缺必填拒", not ok and any("modality" in e for e in errs), str(errs))
    check("M1c organ_id 两级拆分", contract.split_organ_id("ear.radio") == ("ear", "radio"))
    check("M1d 裸器官→general", contract.split_organ_id("ear") == ("ear", "general"))
    try:
        contract.split_organ_id("ear.")
        check("M1e 两级空段拒（真断言）", False, "应抛 ValueError")
    except ValueError:
        check("M1e 两级空段拒（真断言）", True)
    ok, errs = contract.validate_event(ev(consent_tier=True))
    check("M2a bool 冒充 tier 拒", not ok, str(errs))
    ok, errs = contract.validate_event(ev(consent_tier=4))
    check("M2b tier=4 越界拒", not ok)
    ok, errs = contract.validate_event(ev(confidence=1.5))
    check("M2c confidence>1 拒", not ok)
    ok, errs = contract.validate_event(ev(saliency_hint=-0.1))
    check("M2d saliency<0 拒", not ok)

    # ── M3/M4/M5 consent 出关 ──
    print("── M3/M4/M5 consent 出关 ──")
    v0 = consent.enforce_policy(ev(consent_tier=0))
    check("M3a 默认档 tier0 拒写", not v0["ok"] and v0["action"] == "reject", v0["reason"])
    v1 = consent.enforce_policy(ev(consent_tier=1))
    check("M3b 默认档 tier1 降级", v1["ok"] and v1["action"] == "write_degraded")
    v3 = consent.enforce_policy(ev(consent_tier=3))
    check("M3c 默认档 tier3 仍降级（999 不可达=永不全量）",
          v3["ok"] and v3["action"] == "write_degraded")
    pol = {"audio": {"min_degraded": 1, "min_tier_full": 2}}
    vf = consent.enforce_policy(ev(consent_tier=2), policy=pol)
    check("M4a 显式策略全量可达", vf["ok"] and vf["action"] == "write_full")
    wl = {"audio": {"min_degraded": 1, "min_tier_full": 2}}  # 无 "*" 键
    vx = consent.enforce_policy(ev(modality="video"), policy=wl)
    check("M4b 白名单策略 fail-closed（video 无键无兜底=拒）",
          not vx["ok"] and vx["action"] == "reject")
    orig = ev(payload_ref="raw/x.wav")
    consent.enforce_policy(orig)
    check("M5a enforce 不改原事件（纯函数）", orig.get("payload_ref") == "raw/x.wav"
          and "original_ref_dropped" not in orig)
    deg = consent.degraded_event(orig)
    check("M5b degraded 剥 ref 打标记", deg.get("payload_ref") is None
          and deg.get("original_ref_dropped") is True)
    check("M5c degraded 不动原件", orig.get("payload_ref") == "raw/x.wav")

    # ── M6-M10 digest ──
    print("── M6-M10 digest 收件箱 ──")
    stream = []
    for i in range(5):
        stream.append(ev(payload_summary="同一首歌循环", saliency_hint=0.9))  # 权重 0.81=全场最高
    for i in range(3):
        stream.append(ev(payload_summary=f"电台歌单 #{100+i}", saliency_hint=0.5 + i * 0.1))
    stream.append(ev(organ_id="eye.cam_a", modality="image", event_type="motion",
                     payload_summary="门口有动静", saliency_hint=0.8))
    stream.append(ev(organ_id="eye.map", modality="image", event_type="poi",
                     payload_summary="常去的店开了分店", saliency_hint=0.6))
    d = digest_m.digest(stream)
    ear_radio = d["organs"]["ear"]["channels"]["radio"]
    check("M6a 同目标5次=1条目count=5（通道共4条目：循环1+歌单3）",
          ear_radio["count"] == 4 and ear_radio["top"][0]["count"] == 5,
          f"count={ear_radio['count']}, top={ear_radio['top'][0]}")
    check("M6b raw_events 保留去重前计数", ear_radio["raw_events"] == 8, f"raw={ear_radio['raw_events']}")
    check("M7a top-3 按权重排", [t["summary"] for t in ear_radio["top"]] ==
          ["同一首歌循环", "电台歌单 #102", "电台歌单 #101"],
          str([t['summary'] for t in ear_radio['top']]))
    d_ear = digest_m.digest(stream, organ_filter="ear")
    check("M8a 器官级过滤只剩耳朵", set(d_ear["organs"].keys()) == {"ear"})
    d_ch = digest_m.digest(stream, organ_filter="ear.radio")
    check("M8b 通道级过滤只剩 ear.radio", set(d_ch["organs"].keys()) == {"ear"}
          and set(d_ch["organs"]["ear"]["channels"].keys()) == {"radio"})
    d_cap = digest_m.digest(stream, token_cap=1)
    check("M9 token 帽显式标记不静默丢", d_cap["dropped_by_cap"] is True)
    d_empty = digest_m.digest([])
    check("M10a 空事件流不炸", d_empty["organs"] == {} and d_empty["dropped_by_cap"] is False)
    d_bad = digest_m.digest([{"modality": "audio"}])
    check("M10b 缺 organ_id 优雅降级到 '?'", "?" in d_bad["organs"])
    d_mal = digest_m.digest([ev(organ_id="a.b.c", payload_summary="畸形id不炸聚合")])
    check("M10c 畸形 organ_id（三级）消费侧兜底不炸，落 '?' 桶（审计④）",
          "?" in d_mal["organs"]
          and d_mal["organs"]["?"]["channels"] and "a.b.c" in str(d_mal["organs"]["?"]),
          str(d_mal["organs"].get("?", "")))

    # ── M4c/M4d 显式空键不被 or 回落吞（审计zhaozhao3） ──
    # * 桶故意给 min_tier_full=1：or 回落版会把 tier3 判成 write_full，
    # in 版按 audio 显式空键（默认档 999）判 write_degraded——两版可分，钉才有效
    pol_empty = {"audio": {}, "*": {"min_degraded": 1, "min_tier_full": 1}}
    ve = consent.enforce_policy(ev(consent_tier=3), policy=pol_empty)
    check("M4c 显式空 audio 键=显式收紧（默认档999），不回落 *（tier3 仍降级）",
          ve["ok"] and ve["action"] == "write_degraded", ve["reason"])
    vempty0 = consent.enforce_policy(ev(consent_tier=0), policy=pol_empty)
    check("M4d 显式空键档位语义照走（tier0 < min_degraded 1 = 拒）",
          not vempty0["ok"] and vempty0["action"] == "reject", vempty0["reason"])

    n = len(results)
    failed = [name for name, ok in results if not ok]
    print(f"\n{'🎉' if not failed else '💥'} {n - len(failed)}/{n} passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


main()
