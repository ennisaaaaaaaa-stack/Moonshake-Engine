"""事件契约 v1（Moonshake phase01 第一件，2026-10-05 定稿）。

出身：自 tideline-memory（同作者的记忆系统，github.com/ennisaaaaaaaa-stack/tideline-memory）
v2.10 organ ports 迁出。Moonshake 是器官层运行时，契约
独立成根文件——器官生态不依赖任何记忆库实现。

铁律：本文件是 Moonshake 的根依赖（consent_gate / digest 都 import 它），自身
零第三方依赖、零副作用——纯数据结构与纯函数，永不 import 记忆库、永不碰存储
（re/json 是标准库纯函数用法，不算破戒）。记忆库想消费器官事件，通过 adapter
依赖本契约，方向不可反。

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

# ─── organ_id 段字符集（mingming②/v1.2 补欠账：v1.1 答应未落） ────────────────
# 段内只许字母数字和 - _（ORGAN_SEG_RE）；'|' 是 triage 限流键的分隔符，
# 'ear. radio' 带空格的段也不许——字符集从源头钉死，分隔符永远不会被撞
# （mingming②：字符集没限制是契约暗坑第三颗）。
import re as _re

ORGAN_SEG_RE = _re.compile(r"^[A-Za-z0-9_-]+$")

# ─── 三条长度帽（v1.2：zhaozhaoB/F + mingming②同族欠账） ──────────────────────────
# tier1 承诺「只留蒸馏信号」——任何文本通道不带帽，全量就有一条侧门进 digest
# 的 token 帽和 tier1 落库（zhaozhaoB：meta 通道照带原始内容；mingming②：payload_summary
# 无长度上限直通 token 帽）。帽是机械规则，进契约形状层——变形（截断）是调用方
# 的事，本层只拒收。
MAX_SUMMARY_LEN = 200      # payload_summary：蒸馏摘要不是转写全文
MAX_EVENT_TYPE_LEN = 32    # event_type：事件类型名，不是第二个 summary
MAX_META_TEXT_LEN = 500    # meta 值域里任何 str 值（含嵌套）——B 的「降级剥 ref 不剥 meta」同刀

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

    非法输入（空 / 非字符串 / 空段 / 超两级 / 段字符集越界）抛 ValueError——
    契约违反是 bug 不是数据，不做静默兼容。段字符集 = 字母数字和 - _
    （ORGAN_SEG_RE，v1.2）：'|' 会撞 triage 限流键分隔符，空格/控制字符
    不许进段。消费方拿脏数据时（如 digest 收到缺 organ_id 的事件）应先
    兜底成 "?" 再进本函数（优雅降级是消费方的选择，不是契约的）。
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
        for seg in (organ, channel):
            if not ORGAN_SEG_RE.fullmatch(seg):
                raise ValueError(f"organ_id 段字符集越界（只许 [A-Za-z0-9_-]）: {organ_id!r}")
        return (organ, channel)
    if not ORGAN_SEG_RE.fullmatch(sid):
        raise ValueError(f"organ_id 段字符集越界（只许 [A-Za-z0-9_-]）: {organ_id!r}")
    return (sid, "general")


def validate_event(evt):
    """校验感官事件信封。返回 (ok, errors)；errors 为字符串清单，ok 时为空。

    规则：
      必填五字段 ts / organ_id / modality / event_type / payload_summary：
          非空字符串
      organ_id    : 过 split_organ_id（两级制 + 段字符集，见模块注释）
      event_type  : ≤ MAX_EVENT_TYPE_LEN（类型名不是第二个 summary）
      payload_summary : ≤ MAX_SUMMARY_LEN（蒸馏摘要不是转写全文——mingming②：
                    巨型摘要直通 digest token 帽，无上限=全量侧门）
      confidence  : 必填，数值（非 bool），∈[0, 1]
      consent_tier: 必填，整数（非 bool），∈[0, 3]（四档制，3=顶端）
      saliency_hint: 可空；非空时数值（非 bool）∈[0, 1]
                    （0.0 合法 = 显式评过分为零；None = 未过滤原始流，照过）
      payload_ref : 可空；非空时字符串
      meta        : 可选 dict（器官自定义元数据）；值域里任何 str 值
                    （含嵌套）≤ MAX_META_TEXT_LEN（zhaozhaoB/F：tier1 承诺只留
                    蒸馏信号，meta 不带帽=降级剥 ref 不剥 meta，原始内容
                    从侧门进 tier1 落库）

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

    et = evt.get("event_type", "")
    if isinstance(et, str) and len(et) > MAX_EVENT_TYPE_LEN:
        errors.append(f"event_type 超长: {len(et)} > {MAX_EVENT_TYPE_LEN}（类型名不是第二个 summary）")

    summary = evt.get("payload_summary", "")
    if isinstance(summary, str) and len(summary) > MAX_SUMMARY_LEN:
        errors.append(f"payload_summary 超长: {len(summary)} > {MAX_SUMMARY_LEN}（蒸馏摘要不是转写全文）")

    meta = evt.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            errors.append("meta 必须是 dict")
        else:
            for bad in _meta_over(meta):
                errors.append(bad)
                break  # 报一条即可定位（机械层，不刷屏）

    return (not errors), errors


def _meta_over(meta, path="meta"):
    """meta 值域 str 帽检查（含嵌套）。产出错误清单（yield 式懒产出，报一条定位）。"""
    if isinstance(meta, str):
        if len(meta) > MAX_META_TEXT_LEN:
            yield (f"meta 文本值超长: {path} = {len(meta)} chars > {MAX_META_TEXT_LEN}"
                   f"（zhaozhaoB/F：降级剥 ref 不剥 meta，无帽=原始内容侧门）")
    elif isinstance(meta, dict):
        for k, v in meta.items():
            yield from _meta_over(v, f"{path}.{k}")
    elif isinstance(meta, (list, tuple)):
        for i, v in enumerate(meta):
            yield from _meta_over(v, f"{path}[{i}]")
