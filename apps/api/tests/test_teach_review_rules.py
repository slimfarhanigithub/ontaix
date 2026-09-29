"""Regression tests from the security review: adversarial model answers against the extraction
rules. Scripted fake client; no network."""

from __future__ import annotations

import json

import pytest

from app.clients.llm_client import LlmAnswer, LlmRequest, estimate_tokens, set_llm_client
from tests.conftest import TenantFixture
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import submit

pytestmark = pytest.mark.asyncio(loop_scope="session")


class ScriptFake:
    provider = "fake"
    model = "fake-model-1"

    def __init__(self, fn):
        self.fn = fn
        self.requests: list[LlmRequest] = []

    def estimate_input_tokens(self, request):
        return estimate_tokens(request)

    async def complete(self, request):
        self.requests.append(request)
        ctx = json.loads(request.user)
        out = self.fn(ctx)
        if isinstance(out, BaseException):
            raise out
        return LlmAnswer(out, 812, 64, 0.002, 10)


def install(fn) -> ScriptFake:
    f = ScriptFake(fn)
    set_llm_client(f)
    return f


def handle(ctx, label, company=None):
    for c in ctx["candidates"]:
        if c["label"] == label and (company is None or c.get("company") == company):
            return {"candidate": c["handle"]}
    raise AssertionError(f"{label} not sent: {[c['label'] for c in ctx['candidates']][:10]}")


def intent(subject, obj, start, end, action="has", **extra):
    base = {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.9,
        "source": {"start": start, "end": end},
    }
    if extra.get("kind") == "spec":
        base.pop("action")
    base.update(extra)
    return base


def answer(*intents, segments=None):
    out = {"intents": list(intents), "unresolved": []}
    if segments is not None:
        out["segments"] = segments
    return json.dumps(out, ensure_ascii=False)


async def post(client, tenant, company_id, text, origin=None):
    body = {"companyId": str(company_id), "text": text}
    if origin:
        body["origin"] = origin
    r = await client.post("/teach/parse", json=body, headers=tenant.builder.headers)
    assert r.status_code == 200, r.text
    return r.json()


C0 = {"candidate": "c0"}


def new(label):
    return {"newLabel": label}


# ---------------------------------------------------------------- grounding


async def test_grounding_mid_word_source_range(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these services use a database"
    at = s.index("database")
    install(lambda ctx: answer(intent(C0, new("Data"), at, at + 4, "uses")))
    r1 = await post(client, tenant, company_id, s)
    install(lambda ctx: answer(intent(C0, new("Base"), at + 4, at + 8, "uses")))
    r2 = await post(client, tenant, company_id, s)
    for r in (r1, r2):
        assert r["drafts"] == [], "a label grounded inside 'database' via a mid-word source range"
        assert [u["reason"] for u in r["unresolved"]] == ["ungrounded_label"]


async def test_grounded_label_is_not_revalidated(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these apps <data run fast"
    install(lambda ctx: answer(intent(C0, new("Apps Data"), 0, len(s), "runs")))
    r = await post(client, tenant, company_id, s)
    assert r["drafts"] == []
    assert r["unresolved"] == [{"text": s, "reason": "ungrounded_label"}]


async def test_reuse_only_for_sent_candidates(client, tenant: TenantFixture):
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    drafts = [
        {
            "type": "concept",
            "companyId": str(company_id),
            "parentId": str(root_id),
            "label": f"Widget{i:03d}",
            "domainKey": "sales",
            "action": "has",
        }
        for i in range(200)
    ]
    await submit(client, tenant, drafts)
    s = "these services sell stuff"
    fake = install(lambda ctx: answer(intent(C0, new("Widget000"), 0, len(s), "sells")))
    r = await post(client, tenant, company_id, s)
    sent = [c["label"] for c in json.loads(fake.requests[-1].user)["candidates"]]
    assert "Widget000" not in sent
    assert r["drafts"] == []
    assert r["unresolved"][0]["reason"] == "ungrounded_label"


async def test_self_join_after_reuse(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these insights own insight"
    install(lambda ctx: answer(intent(C0, new("Insights"), 0, len(s), "owns")))
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output"
    install(
        lambda ctx: answer(
            intent(C0, new("Offerings"), 0, len(s), "has", members=[new("App"), new("Insight")])
        )
    )
    r = await post(client, tenant, company_id, "these offerings app and insight")
    assert r["llmOutcome"] == "invalid_output"


# ---------------------------------------------------------------- actions


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", "ｉｓ　ａ"),
        ("action", "equivalent  to"),
        ("memberAction", "ｉｓ　ａ"),
        ("memberAction", "equivalent　to"),
        ("memberAction", "IS A"),
    ],
)
async def test_refused_actions(client, tenant: TenantFixture, field, value):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these services has offerings app and data"
    extra = {"members": [new("App"), new("Data")]}
    act = value if field == "action" else "has"
    if field == "memberAction":
        extra["memberAction"] = value
    install(lambda ctx: answer(intent(C0, new("Offerings"), 0, len(s), act, **extra)))
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output"
    assert r["drafts"] == [] or r["extractor"] == "rules"


# ---------------------------------------------------------------- taught company


async def _cross(client, tenant):
    company_id, _ = await add_company(tenant, "Insight")
    other_id, other_root = await add_company(tenant, "Rival")
    await configure(tenant, cross_company=True)
    await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": str(other_id),
                "parentId": str(other_root),
                "label": "Widgets",
                "domainKey": "sales",
                "action": "has",
            }
        ],
    )
    return company_id


async def test_foreign_candidate_with_new_label_in_plain_rel(client, tenant: TenantFixture):
    company_id = await _cross(client, tenant)
    s = "these widgets feed gadgets"
    install(
        lambda ctx: answer(
            intent(handle(ctx, "Widgets", "Rival"), new("Gadgets"), 0, len(s), "feeds")
        )
    )
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output", (
        "plain rel citing a foreign candidate with a new label was drafted"
    )


async def test_foreign_in_spec_and_grouping(client, tenant: TenantFixture):
    company_id = await _cross(client, tenant)
    s = "these widgets are gadgets"
    install(
        lambda ctx: answer(
            {
                "kind": "spec",
                "subject": new("Gadgets"),
                "object": handle(ctx, "Widgets", "Rival"),
                "confidence": 0.9,
                "source": {"start": 0, "end": len(s)},
            }
        )
    )
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output"
    s2 = "these offerings are widgets and gadgets"
    install(
        lambda ctx: answer(
            intent(
                C0,
                new("Offerings"),
                0,
                len(s2),
                "has",
                members=[handle(ctx, "Widgets", "Rival"), new("Gadgets")],
            )
        )
    )
    r = await post(client, tenant, company_id, s2)
    assert r["llmOutcome"] == "invalid_output"


async def test_unsent_handle(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these services sell"
    install(lambda ctx: answer(intent(C0, {"candidate": "c199"}, 0, len(s), "sells")))
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output"


# ---------------------------------------------------------------- characters, caps, ranges


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i: i.update(object=new("Da​ta")),
        lambda i: i.update(object=new("Data ")),
        lambda i: i.update(object=new("Da ta")),
        lambda i: i.update(action="sel‮ls"),
        lambda i: i.update(action="sells\U000e0041"),
        lambda i: i.update(explanation="ok \U0001d173 x"),
        lambda i: i.update(explanation="<b>x</b>"),
        lambda i: i.update(span="a\u0085b"),
        lambda i: i.update(object=new(" Data")),
    ],
)
async def test_refused_characters(client, tenant: TenantFixture, mutate):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these services use data"

    def fn(ctx):
        i = intent(C0, new("Data"), 0, len(s), "uses")
        mutate(i)
        return answer(i)

    install(fn)
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "invalid_output", r


async def test_ranges_and_caps(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    s = "these services use data"
    # An end past the text is clamped to the text's length, not refused.
    install(lambda ctx: answer(intent(C0, new("Data"), 0, len(s) + 1, "uses")))
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "used" and [d["label"] for d in r["drafts"]] == ["Data"]
    cases = {
        "start past text": answer(intent(C0, new("Data"), len(s), len(s) + 2, "uses")),
        "21 intents": answer(*[intent(C0, new("Data"), 0, len(s), "uses")] * 21),
        "start==end": answer(intent(C0, new("Data"), 3, 3, "uses")),
    }
    for name, raw in cases.items():
        install(lambda ctx, raw=raw: raw)
        r = await post(client, tenant, company_id, s)
        assert r["llmOutcome"] == "invalid_output", name
    t = "we sell services. services have data. um data matters"
    seg = [{"index": 0, "start": 0, "end": 17}, {"index": 1, "start": 18, "end": 38}]
    speech_cases = {
        # A segment inside the previous one; one that only starts before it ends is repaired.
        "inside": [{"index": 0, "start": 0, "end": 38}, {"index": 1, "start": 18, "end": 30}],
        "bad index": [{"index": 0, "start": 0, "end": 17}, {"index": 2, "start": 18, "end": 38}],
        "too long": None,
    }
    for name, segs in speech_cases.items():
        if segs is None:
            continue
        install(
            lambda ctx, segs=segs: answer(
                intent(C0, new("Services"), 3, 16, "sells", segment=0), segments=segs
            )
        )
        r = await post(client, tenant, company_id, t, "speech")
        assert r["llmOutcome"] == "invalid_output", name
    overlap = [{"index": 0, "start": 0, "end": 20}, {"index": 1, "start": 18, "end": 38}]
    install(
        lambda ctx: answer(intent(C0, new("Services"), 3, 16, "sells", segment=0), segments=overlap)
    )
    r = await post(client, tenant, company_id, t, "speech")
    assert r["llmOutcome"] == "used"
    install(lambda ctx: answer(intent(C0, new("Data"), 3, 30, "has", segment=0), segments=seg))
    r = await post(client, tenant, company_id, t, "speech")
    assert r["llmOutcome"] == "invalid_output"
    install(lambda ctx: answer(intent(C0, new("Services"), 3, 16, "sells"), segments=seg))
    r = await post(client, tenant, company_id, t, "speech")
    assert r["llmOutcome"] == "invalid_output"


async def test_spans_relative_to_original_input(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    original = "   In sales, these services use data"
    stripped_text = "these services use data"
    at = stripped_text.index("data")
    install(lambda ctx: answer(intent(C0, new("Data"), at, at + 4, "uses")))
    r = await post(client, tenant, company_id, original)
    span = r["draftNotes"][0]["sourceSpan"]
    assert original[span["start"] : span["end"]] == "data"
    [segment] = r["segments"]
    assert original[segment["span"]["start"] : segment["span"]["end"]] == original.strip()


async def test_grounded_words_must_be_separated_by_whitespace_and_fit_a_label(
    client, tenant: TenantFixture
):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    listed = "these services cover app, data and more"
    install(lambda ctx: answer(intent(C0, new("App Data"), 0, len(listed), "covers")))
    r = await post(client, tenant, company_id, listed)
    assert r["drafts"] == [] and r["unresolved"][0]["reason"] == "ungrounded_label"
    long = "these services use " + "     ".join(["data"] * 20)
    install(lambda ctx: answer(intent(C0, new(" ".join(["Data"] * 20)), 0, len(long), "uses")))
    r = await post(client, tenant, company_id, long)
    assert r["drafts"] == [] and r["unresolved"][0]["reason"] == "ungrounded_label"
    spaced = "these services use big   data"
    install(lambda ctx: answer(intent(C0, new("Big data"), 0, len(spaced), "uses")))
    r = await post(client, tenant, company_id, spaced)
    assert [d["label"] for d in r["drafts"]] == ["Big   data"]


async def test_a_relation_between_two_sent_candidates_may_cross_companies(
    client, tenant: TenantFixture
):
    company_id = await _cross(client, tenant)
    s = "these widgets feed insight"
    install(lambda ctx: answer(intent(handle(ctx, "Widgets", "Rival"), C0, 0, len(s), "feeds")))
    r = await post(client, tenant, company_id, s)
    assert r["llmOutcome"] == "used"
    assert [d["type"] for d in r["drafts"]] == ["relation"]


@pytest.mark.parametrize(
    ("sentence", "fragment"),
    [
        ("these services cover résumés", "Sume"),
        ("these services cover กิน", "ก"),
        ("these services cover काम", "क"),
        ("these services cover node.js", "Js"),
        ("these services cover insight’s", "S"),
    ],
)
async def test_a_fragment_of_one_word_never_grounds(
    client, tenant: TenantFixture, sentence, fragment
):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    seg = [{"index": 0, "start": 0, "end": len(sentence)}]
    install(
        lambda ctx: answer(
            intent(C0, new(fragment), 0, len(sentence), "covers", segment=0), segments=seg
        )
    )
    r = await post(client, tenant, company_id, sentence, "speech")
    assert r["llmOutcome"] == "used"
    assert r["drafts"] == []
    assert [u["reason"] for u in r["unresolved"]] == ["ungrounded_label"]


@pytest.mark.parametrize(
    ("sentence", "label", "drafted"),
    [
        ("these services cover résumés", "Résumés", "Résumés"),
        ("these services cover node.js", "Node.js", "Node.js"),
        ("these services cover काम", "काम", "काम"),
    ],
)
async def test_a_whole_word_with_marks_or_joiners_grounds(
    client, tenant: TenantFixture, sentence, label, drafted
):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    seg = [{"index": 0, "start": 0, "end": len(sentence)}]
    install(
        lambda ctx: answer(
            intent(C0, new(label), 0, len(sentence), "covers", segment=0), segments=seg
        )
    )
    r = await post(client, tenant, company_id, sentence, "speech")
    assert [d["label"] for d in r["drafts"]] == [drafted]


@pytest.mark.parametrize(
    ("sentence", "fragment"),
    [
        ("these services cover می‌خواهم", "خواهم"),
        ("these services cover data­base", "Base"),
        ("these services cover data⁠base", "Base"),
        ("these services cover node．js", "Js"),
        ("these services cover a‧b", "B"),
    ],
)
async def test_format_characters_and_uax29_joiners_keep_a_word_whole(
    client, tenant: TenantFixture, sentence, fragment
):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    seg = [{"index": 0, "start": 0, "end": len(sentence)}]
    install(
        lambda ctx: answer(
            intent(C0, new(fragment), 0, len(sentence), "covers", segment=0), segments=seg
        )
    )
    r = await post(client, tenant, company_id, sentence, "speech")
    assert r["llmOutcome"] == "used"
    assert r["drafts"] == []
    assert [u["reason"] for u in r["unresolved"]] == ["ungrounded_label"]
