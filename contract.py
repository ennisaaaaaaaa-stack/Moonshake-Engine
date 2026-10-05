"""事件契约 v1（Moonshake phase01 第一件，2026-10-05 定稿）。

出身：自 tideline-memory（同作者的记忆系统，github.com/ennisaaaaaaaa-stack/tideline-memory）
v2.10 organ ports 迁出。Moonshake 是器官层运行时，契约
独立成根文件——器官生态不依赖任何记忆库实现。

铁律：本文件是 Moonshake 的根依赖（consent_gate / digest 都 import 它），自身
零依赖、零副作用——纯数据结构与纯函数，永不 import 记忆库、永不碰存储。
记忆库想消费器官事件，通过 adapter 依赖本契约，方向不可反。

重建记录（诚实档）：2026-10-05 开工夜 write_file 回执称本文件已落盘（verified:true），
实际盘上无文件——写层静默失败（真意图+未验证断言：回执说 verified，盘上没有）。
当夜新 session 依三份证据重建：①夹具 tests/fixture_phase01_contract.py 钉死的
API 与边界 ②tideline sensory_write.py 的原始语义 ③consent_gate/digest 的 import。
重建后夹具全绿才算本文件存在。

organ_id 两级制：「器官.通道」（ear.radio / eye.cam_a / eye.map）。
  - 裸器官名（ear）合法，通道缺省 general；
  - 空段（"ear." / ".radio" / "."）非法，ValueError；
  - 超过两级（ear.radio.fm）非法——契约钉死两级，三级需求出现时升契约版本，
    不做静默兼容（拍板①同思路：默认档跟契约走，不跟存储走）。

consent_tier 四档制（与 tideline DEFAULT_POLICY 同尺度）：
  0=无授权 1=仅蒸馏信号 2=可存原始样本 3=可参与 DREAM。
  与 tideline 校验的已声差异：tideline validate 允许任意 ≥0 整数；Moonshake 契约
  钉死 0-3——3 已是尺度顶端（可参与 DREAM），比 3 大的不是更高授权而是脏数据。
"""

CONTRACT_VERSION = "v1"

# ─── consent 默认策略 ────────────────────────────────────────────────────
# 设计师拍板（2026-10-02 v2.11 进码；2026-10-05 随契约迁入 Moonshake）：
# 「最低档授权就够了，不然太占空间了吧？器官毕竟是没有经过真实判断筛选的内容」
# → tier0（无授权）拒写；tier1+ 一律降级；999 不可达 = 原始样本默认永不跟着
#   事件走。哪个器官想存全量，接入时单独传 policy 把 min_tier_full 设为可达档位
#   （器官单独点头，白名单语义见 consent_gate.enforce_policy）。
DEFAULT_POLICY = {"*": {"min_degraded": 1, "min_tier_full": 999}}

REQUIRED_FIELDS = ("ts", "organ_id", "modality", "event_type", "payload_summary")


def split_organ_id(organ_id):
    """organ_id 两级拆分：'ear.radio' → ('ear', 'radio')；裸器官 'ear' → ('ear', 'general')。

    非法输入（空 / 非字符串 / 空段 / 超两级）抛 ValueError——契约违反是 bug
    不是数据，不做静默兼容。消费方拿脏数据时（如 digest 收到缺 organ_id 的
    事件）应先兜底成 "?" 再进本函数（优雅降级是消费方的选择，不是契约的）。
    """
    if not isinstance(organ_id, str) or not organ_id.strip():
        raise ValueError(f"organ_id 非法（空或非字符串）: {organ_id!r}")
    sid = organ_id.strip()
    if sid.count(".") > 1:
        raise ValueError(f"organ_id 超两级（契约钉死 organ.channel 两级制）: {organ_id!r}")
    if "." in sid:
        organ, channel = sid.split(".", 1)
        if not organ or not channel:
            raise ValueError(f"organ_id 空段: {organ_id!r}")
        return (organ, channel)
    return (sid, "general")


def validate_event(evt):
    """校验感官事件信封。返回 (ok, errors)；errors 为字符串清单，ok 时为空。

    规则：
      必填五字段 ts / organ_id / modality / event_type / payload_summary：
          非空字符串
      organ_id    : 过 split_organ_id（两级制，见模块注释）
      confidence  : 必填，数值（非 bool），∈[0, 1]
      consent_tier: 必填，整数（非 bool），∈[0, 3]（四档制，3=顶端）
      saliency_hint: 可空；非空时数值（非 bool）∈[0, 1]
                    （0.0 合法 = 显式评过分为零；None = 未过滤原始流，照过）
      payload_ref : 可空；非空时字符串
      meta        : 可选 dict（器官自定义元数据）

    入境 ≠ 注意：显著性不参与合法性判定（hint 只影响固化优先级，见源头 spec §5）。
    本函数只裁形状，不裁 consent——执法在 consent_gate.enforce_policy。
    """
    errors = []
    if not isinstance(evt, dict):
        return (False, ["event 必须是 dict"])

    for f in REQUIRED_FIELDS:
        v = evt.get(f)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"必填字段缺失或为空: {f}")

    try:
        split_organ_id(evt.get("organ_id", ""))
    except ValueError as e:
        errors.append(str(e))

    conf = evt.get("confidence")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        errors.append("confidence 必须是数值（非 bool）")
    elif not (0.0 <= conf <= 1.0):
        errors.append(f"confidence 越界: {conf}（须 ∈[0,1]）")

    tier = evt.get("consent_tier")
    if not isinstance(tier, int) or isinstance(tier, bool):
        errors.append("consent_tier 必须是整数（非 bool）")
    elif not (0 <= tier <= 3):
        errors.append(f"consent_tier 越界: {tier}（四档制 0-3，3=可参与 DREAM 已是顶端）")

    hint = evt.get("saliency_hint")  # 可空
    if hint is not None:
        if not isinstance(hint, (int, float)) or isinstance(hint, bool):
            errors.append("saliency_hint 非空时必须是数值")
        elif not (0.0 <= hint <= 1.0):
            errors.append(f"saliency_hint 越界: {hint}（须 ∈[0,1]）")

    ref = evt.get("payload_ref")  # 可空
    if ref is not None and not isinstance(ref, str):
        errors.append("payload_ref 非空时必须是字符串")

    meta = evt.get("meta")
    if meta is not None and not isinstance(meta, dict):
        errors.append("meta 必须是 dict")

    return (not errors), errors
