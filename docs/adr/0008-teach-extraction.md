# ADR 0008: Teach Extraction

Status: Accepted. The owner's decisions (rows 70 to 74) are final; the derived choices (rows 75 to 79, 83 and 84) are approved under owner delegation (2026-09-29); row 87 (owner decision, final) sets the model step on by default; row 88 (owner decision, final) makes the model the first extractor for speech and documents; row 89 records the derived choices for it.

## Context

The teach bar parses sentences with the rule-based grammar ported verbatim from the reference (requirements addendum, section 3). It handles the reference's lexicon and patterns and nothing else. Two sentences the owner teaches show where it stops:

- `Insight sells services` - `sells` is not in the lexicon (only `sells to` is), so the grammar understands nothing. The owner expects a new concept `Services` born from the company root `Insight` with the action `sells`.
- `these services are focused around three areas, app, data and AI` - the grammar strips `these` as a determiner, matches the specialisation pattern and drafts `Service is a Focused around three areas, app, data and ai`. The owner expects three concepts `App`, `Data` and `AI` born from `Services` with an action such as `focuses on`, where `these services` means the `Services` of the previous sentence.

The owner then found speech imprecise: a spoken transcript has no punctuation, fillers and false starts, and several statements that refer to each other, which a sentence grammar cannot handle. Row 88 makes the model the first extractor for `speech` and `document`, and keeps the grammar first for typed `text`.

The owner decided (rows 70 to 74) to add a language model extraction step as a fallback behind the grammar, with Claude Sonnet 5 as the default model behind a provider-neutral adapter, and to keep every model result a draft that a human approves.

## Decision

### Pipeline

```mermaid
flowchart TD
  input[POST /teach/parse] --> gates[Channel gates and parse budget]
  gates --> route{Origin}
  route -->|text, up to 400 chars| rules[Rule-based grammar first]
  rules --> triggers{Any fallback trigger?}
  triggers -->|no| result_rules[Grammar result - llmOutcome not_triggered]
  triggers -->|yes| available
  route -->|speech, whole transcript up to 4000 chars| available
  route -->|document, cited sentence plus 2 neighbours each side| available
  available{Model configured, cap above 0, caller llm budget, tokens reserved in own short transaction?}
  available -->|no| fallback[Grammar result, degraded, sentence in unresolved - a transcript is split into segments first]
  available -->|yes| context[Build context - text, session turns, company name, up to 200 candidates, domain templates, action guidance]
  context --> call[Adapter calls the configured model - 15 s for text and document, 45 s for a speech transcript, wall clock including connect, no retry, no transaction open]
  call -->|timeout or provider error| settle_fail[Settle tokens in the reserved month, write llm_call row]
  settle_fail --> fallback
  call -->|answer| validate{Valid against the schema, handles, segments and spans?}
  validate -->|no| settle_invalid[Settle tokens in the reserved month, write llm_call row]
  settle_invalid --> fallback
  validate -->|yes| settle_ok[Settle tokens in the reserved month, write llm_call row]
  settle_ok --> map[Map intents to drafts with the grammar's mapping table - cap 60, or 150 for a transcript]
  map --> merge{text origin and partly_understood alone?}
  merge -->|yes| both[Keep grammar intents, add model intents without duplicates - rules+llm]
  merge -->|no| llm_only[Model result - llm]
  both --> turns[Store one session turn per segment - own short transaction under the session advisory lock]
  llm_only --> turns
  result_rules --> turns
  fallback --> turns
  turns --> response[200 TeachResult - drafts with draftNotes and source spans, nothing written]
  response --> batch[Client submits drafts to POST /proposals/batch]
  batch --> human[A human approves or rejects each proposal]
```

### Routing By Origin

| Origin | First extractor | Model input | When the model is off, out of budget, failing or invalid |
|---|---|---|---|
| `text` (typed, at most 400 characters) | Grammar; the model only on a fallback trigger below | The sentence | Grammar result; `degraded` true only when a trigger fired |
| `speech` (whole transcript, at most 4,000 characters) | Model | The whole transcript as one request | Grammar on the transcript split into segments on sentence punctuation and newlines (a segment over 400 code points is cut at its last space before 400, or at exactly 400 when it has none; at most 40 segments are kept and the rest of the transcript is listed as one `unresolved` entry with reason `too_many_segments`); `degraded` true |
| `document` (`importRef`) | Model | The cited sentence, plus up to two sentences before and two after it from the same stored import as context, read by the server | Grammar on the cited sentence; `degraded` true |

For `speech` and `document`, a valid model answer is the result (`extractor` `llm`); the grammar does not run. For `text`, the fallback rules below apply unchanged.

### Speech Transcripts

A `speech` request carries the whole final transcript of one recording as `text`, at most 4,000 characters, and spends one parse unit per started 400 characters. The model:

- segments the transcript into sentences and returns each as a code-point range; fillers, false starts, repeated words and self-corrections it applied stay outside every segment;
- resolves back-references with the session's turns and with earlier segments of the same transcript;
- returns, per segment, the concepts, the parent each is born from, the action of each birth relation, further relations between concepts with their actions, and domain keys, as intents that name their segment and the source range of the words they come from;
- lists talk that is not teaching (questions, asides) as `unresolved` with reason `not_a_statement`.

Caps for a transcript: at most 40 segments of at most 400 code points each, 60 intents and 30 unresolved phrases in the answer; at most 150 drafts, 150 intents and 40 unresolved entries in the result (60 and 20 for `text` and `document`). 150 covers 60 intents that each draft one concept plus the root-and-child pairs of intents with two new ends, and stays under the 200-draft limit of `POST /proposals/batch`. Past the cap the rule of the Output Contract applies (`too_many_drafts`). A transcript gets a 45-second timeout, wall clock with connect included, instead of the 15 seconds of `text` and `document` (decision row 91), so a long transcript is not cut off and degraded to the grammar. The output bound is 12,288 tokens for a transcript and 1,024 otherwise, and the adapter sets the provider's maximum output tokens to exactly that bound, so an answer within the caps is never cut short and settlement never exceeds the reservation. Explanations in a transcript answer are at most 120 characters (an API check), which keeps a full answer at the caps inside 12,288 tokens. A transcript whose answer does not finish within 45 seconds times out and degrades to the grammar; there is no chunking. The model's segment `{index, start, end}` becomes the API's `SourceSegment` `{index, span: {start, end}}`, with offsets translated as in the Output Contract. The reservation sizing is in Costs And Budgets.

Each segment is stored as one session turn, in order, in the same short transaction under the session's advisory lock, so a later recording can refer to what an earlier one said; with at most 8 turns kept, a long transcript leaves its last 8 segments. `TeachResult.segments` lists the segments, and each `DraftNote` carries the draft's `segment` and `sourceSpan`, so a reviewer sees which words produced each draft.

### Fallback Triggers For Text

For `text` the grammar always runs first. The model step runs only when at least one of these holds:

1. The grammar outcome is `not_understood`.
2. The grammar outcome is `partly_understood`.
3. The sentence holds a back-reference word as a whole word: `these`, `those`, `it`, `they`, `them`, `this`.
4. The sentence holds a list preamble: a count word (`two` to `twelve`) or a number, then one to three words, then `,` or `:` (as in `three areas, app, data and AI`).
5. The sentence holds a verb form that is not a variant of the reference lexicon. The API checks the words against a verb word list it ships for this purpose only; the lexicon itself never changes, so the grammar stays the verbatim port.

Triggers 3 to 5 mark the grammar's own result as suspect, so a valid model answer replaces it (`extractor` `llm`). Trigger 1 has no grammar result to keep (`llm`). When trigger 2 holds alone, the grammar's intents are kept and the model's are added, dropping any model intent that resolves to the same subject, action and object (`rules+llm`, or `rules` when the model adds nothing).

### Teach Session

The Studio generates a `sessionId` (uuid) when it loads and whenever the taught company changes, and sends it with every `POST /teach/parse`. The server stores each sentence as one `teach_session_turn` row keyed by tenant, caller (`actor_kind`, `actor_id`), company and session, with the extractor used, the ids of the existing concepts the sentence referenced (`concept_ids`) and the labels it introduced (`new_labels`). Limits: the last 8 turns per session, each turn expires 2 hours after it was stored, at most 50 ids and 50 labels per turn, sentences of at most 400 characters. A purge every 15 minutes deletes expired turns; reads ignore them before that. Only the caller that created a session reads it; an unknown or expired `sessionId` is an empty session, never an error. When the next sentence is parsed, each stored label is resolved again against the company's concepts, so a label whose proposal has since been submitted (a pending concept) or approved resolves to its id; a label nobody submitted stays a label.

Concurrent sentences of one session (fast typing, import sentences parsed in parallel, retries) are safe. The turn is stored after the result is built, in its own short transaction: `pg_advisory_xact_lock` on a 64-bit hash (`hashtextextended`) of tenant, caller, company and session; `INSERT ... SELECT coalesce(max(turn_index) + 1, 0)` over that session; deletion of the session's turns with `turn_index <= n - 8`. The lock serialises the session's writers only, so turn numbers never collide (8 concurrent inserts into one session were verified on PostgreSQL 16 to give turns 0 to 7 with no error). If storing the turn fails anyway, the turn is not kept and the parse still answers `200`; storing a turn is never an error.

Stored `concept_ids` are re-checked every time they are read: an id is used only if the concept still exists and would be a valid candidate now - a concept of the taught company, or of another company only while `crossCompany` is on and the caller may read that company. Anything else is dropped before the context is built, so a turn never carries a concept past a change of settings or roles.

### What The Server Sends The Model

The adapter receives one request built by the API. This ADR fixes its content, not its wording; the prompt text lives in `apps/api/app/ai/prompts/`.

- The sentence (after the domain prefix is stripped, with the prefix's domain key given separately).
- The session's recent turns, oldest first: each turn's sentence and the candidate handles or labels it referenced and introduced, after the re-check above.
- The name of the company being taught.
- Up to 200 candidate concepts of that company, each as a handle (`c0` to `c199`, valid for this call only), label, domain key, parent handle and a pending flag. `c0` is always the company root. Ranking, until 200: the root; concepts referenced by session turns, newest first; concepts whose label matches a word of the sentence (case-insensitive, singular or plural, as the grammar's `resolve`); the parents and children of those; concepts of the prefixed domain; the most recently born. Concept ids never leave the API; the handle table maps each handle back to an id when the answer is read.
- Other companies' concepts only when the `crossCompany` setting is on and the caller may read that company, only those whose label matches a word of the sentence, at most 50 of the 200, each marked with its company name. An intent between two existing concepts of different companies becomes a `RelationDraft` and meets every existing cross-company check when it is proposed; a new concept is always born in the company being taught.
- The nine domain templates (key and name).
- Candidate labels, session sentences and document context sentences travel in delimited data fields, marked as data and never as instructions; only the API's fixed instructions are instructions.
- Action guidance: actions are lower-case present-tense verb phrases read subject to object; the reference lexicon's canonical predicates are listed and preferred when one has the same meaning; `is a` is expressed as a `spec` intent, never as an action; `equivalent to` is not available to the model.

The server never sends: user or agent names, emails or ids; the tenant id or name; concept, proposal or source ids; sources, connector hosts, scopes, bindings, attributes or record counts; settings; audit entries; proposers; any credential or secret; other companies' data outside the rule above.

### Output Contract

The model returns JSON only, validated against `contracts/teach-extraction.schema.json`: up to 20 intents and 10 unresolved phrases for `text` and `document`, 60 and 30 for a `speech` transcript (intents are `rel` or `spec`, subject and object each a candidate handle or a new label, action for `rel`, optional rule for `spec`, optional domain key, confidence 0 to 1, optional plain-text explanation of at most 300 characters, or 120 in a transcript answer, a required source range, and for a grouping `rel` intent `members`, `memberAction`, `statedCount`, or `listId` for a descriptive list). Every free-text field of the answer refuses markup, C0 and C1 control characters, U+00A0, U+2028, U+2029 and every Unicode format character (category Cf, which includes the bidirectional controls, the zero-width characters, U+00AD, U+180E, U+2060 to U+2064 and U+FEFF; the schema lists the ones in the Basic Multilingual Plane and the API refuses the rest), so an action cannot look like `is a` or `equivalent to` without being it; actions and new labels have no leading or trailing space, so a whitespace-only label fails. The API then normalises each action exactly as every path that sets a relation action does for any client - new relations, relation edits (`RelationEdit.action`), concept birth actions (`ConceptDraft.action`), drafts, batch and teach extraction (NFKC, whitespace runs collapsed to one space, trimmed, lower-cased); the duplicate-relation check compares the normalised forms of both the stored label and the new action. The API then checks what a schema cannot, on every field of every intent that carries an action or a handle - `action`, `memberAction`, `subject`, `object` and each of `members`: every cited handle was sent; every normalised action, `memberAction` included, is neither `is a` nor `equivalent to`; no intent joins a concept to itself, and in a grouping intent no member repeats the subject, the object or another member; the subject, object and members of a grouping intent, and both ends of a `spec` intent, are new labels or candidates of the taught company - only a plain `rel` intent between two existing concepts may cite another company's candidate, and then only as the cross-company `RelationDraft` rule below allows; every `spec` intent has one of the draftable forms below; `statedCount` appears only with `members` or `listId`. Any failure makes the whole answer invalid (`llmOutcome` `invalid_output`): no model draft is returned, the sentence is listed in `unresolved` with reason `model_invalid_output`, and nothing is written.

The API also checks segments and ranges: every range has `start < end` and lies inside the text the model was given; `segments[i].index` equals `i`, so indexes are unique and ordered; segments ascend without overlapping, each at most 400 code points; every intent has a source range - for a transcript it names an existing segment and lies inside it, for a `document` request it lies inside the cited sentence and never inside a context sentence, which the model receives as separate fields. Offsets are Unicode code points into the text the model was given, which is the input after any domain prefix (`In sales, ...`) is stripped; the server adds the length of the stripped prefix, separator included, in code points, before it returns a `SourceSpan`, so every `SourceSpan` is relative to the caller's original input. Unresolved text is taken from the given range when it is valid, else located in the text.

Grounding (decision row 92): every new label the model proposes - `subject`, `object` or a member given as `newLabel` - must appear in the caller's own input, inside the intent's source range: the typed sentence, the transcript, or the cited document sentence, never a context sentence, a session turn or a candidate label. The check compares after normalisation (NFKC, whitespace collapsed, case-insensitive) and allows the grammar's simple inflection (singular or plural, as `singular` and `resolve` do) and the label casing rule. An intent with an ungrounded new label is not drafted; its source text is listed in `unresolved` with reason `ungrounded_label`. Handles of existing concepts are exempt, since those concepts already exist. So text the caller does not control - another user's label, a neighbouring document sentence - can never mint a new concept.

A valid answer is turned into drafts by the grammar's own mapping (requirements addendum, section 3.4). For a `rel` intent: an existing subject and a new object give a `ConceptDraft` with `parentId`; a new subject and an existing object give a `ConceptDraft` with `reverse` true; two existing concepts give a `RelationDraft` by id; two new concepts give a concept born from the root with `has` and a second one born from it by `parentLabel`. For a `spec` intent (subject is the child, object the parent), both ends must be the taught company's candidates or new labels; a `spec` intent citing another company's candidate makes the answer invalid. Then: new child and existing parent give a `SpecDraft` with `parentId` and the intent's `rule`; new child and new parent give a `ConceptDraft` born from the root with `has` and a `SpecDraft` under it by `parentLabel`; existing child and new parent give a `ConceptDraft` for the parent born from the child with action `is a kind of` and `reverse` true; two existing concepts give a `RelationDraft` with action `is a`. These are the grammar's four `spec` rows. A new label that matches an existing concept is resolved to it, as the grammar does. The domain key is the sentence's prefix, else the model's `domainKey`, else the parent's domain, else `production`. Intents with a confidence below 0.4 are not drafted and are listed in `unresolved` with reason `low_confidence`. A result holds at most 60 drafts for `text` and `document` and 150 for a `speech` transcript, grammar and model drafts counted together: the server keeps intents in input order (grammar intents first for `rules+llm`) while their drafts fit and fewer intents than the same cap are kept, counting intents that produce no draft (a self-join or an existing triple), drops the rest with their drafts, and lists their text as one `unresolved` entry with reason `too_many_drafts`; `intents`, `drafts` and `draftNotes` each hold at most 60 (150 for a transcript) and `unresolved` at most 20 (40 for a transcript). `unresolved` text is always a substring of the sentence the server holds (or the whole sentence), never text copied from the answer. Drafts keep their existing schemas; each draft's extractor, confidence and explanation travel in `TeachResult.draftNotes`, in draft order, and are never submitted.

### Extraction Rules

Grouping nouns (decision row 90). When a sentence names a list with a noun, the model decides which of two cases applies:

- The noun is a concept of the business - a grouping concept. Canonical example: `Services has 3 offerings, Apps, Data and AI`. The model returns one `rel` intent: subject `Services`, action `has` (the speaker's verb), object new label `Offerings`, `members` `Apps`, `Data`, `AI`, `memberAction` `includes`, `statedCount` 3. Drafts: `Offerings` born from `Services` with action `has`, then `Apps`, `Data` and `AI` each born from `Offerings` (by `parentLabel`) with action `includes`. A member that is an existing candidate gives a `RelationDraft` `Offerings includes <member>` instead. The subject, the object and every member of a grouping intent are new labels or candidates of the taught company; `memberAction` passes the same normalisation and checks as every action, so it is never `is a` or `equivalent to`; no member repeats the subject, the object or another member; and every new label, members included, must pass the grounding rule.
- The noun only describes the list - a descriptive grouping noun. Canonical examples: `these services are focused around three areas, app, data and AI`, and the same with `in three regions`. No grouping concept is drafted. The model returns one `rel` intent per member from the subject with the speaker's verb as the action (`focuses on`), all with the same `listId` and `statedCount` 3.

Labels keep the speaker's casing under the existing label rule: the first character is capitalised and the rest is kept, so `Apps`, `Data` and `AI` stay as spoken. A new label that repeats one introduced by an earlier intent of the same answer names the same new concept and is drafted by `parentLabel`.

Stated counts: when the stated number disagrees with the length of the list (`3 offerings` followed by four names), the drafts follow the list, never the number, and the server adds to the `DraftNote.explanation` of every draft from that list the note `stated <n>, listed <m>`, appended to the model's explanation within the 300-character limit. A grouping intent counts as one intent and `1 + members` drafts toward the caps.

For the owner's two sentences, with `Insight` as `c0`:

- `Insight sells services` gives `rel c0 sells newLabel Services`, drafted as `ConceptDraft` (parent `Insight`, label `Services`, action `sells`).
- `these services are focused around three areas, app, data and AI`, with `Services` pending from the first sentence and sent as a candidate, gives three `rel` intents from that candidate with action `focuses on` to `App`, `Data` and `AI`, drafted as three `ConceptDraft`s with `parentId` set to `Services`.

### Costs And Budgets

- Every call to the provider, including failed and timed-out ones, writes one `llm_call` row: tenant, caller, company, purpose `teach_extraction`, provider, model, input and output tokens, estimated euro cost from the deployment's price table, latency and outcome. It never holds the sentence, prompt, answer or key. Rows are kept 400 days.
- `GET /cost` returns the month's totals as `CostSummary.llm` (`LlmUsage`), separate from the agent figures (`measuredEur`, `byPlatform`), which stay agent reads through the gateway. The Cost management page shows no new element until `docs/ui-contract.md` records one.
- Per caller: each model call spends one unit of the hourly `llm` budget in `rate_budget_window` (default 200 calls per user or agent per hour, from configuration like the other budgets). When it is spent the step is skipped with `llmOutcome` `rate_limited`. The per-caller limit is hourly only, by decision (row 92): there is no per-caller monthly share, so one caller can use the whole tenant cap (at the default, about 70 full transcripts at the reservation below). The parse budget (default 2,000 units per caller per hour, 10 per transcript) and this call budget bound the rate; a tenant administrator sees spend per caller in `llm_call` and can lower `llmMonthlyTokenCap`.
- Submitting: the Studio submits all drafts of one parse as one `POST /proposals/batch`, which is all-or-nothing and spends one proposal unit per draft. The default proposal budget, 5,000 units per caller per hour, is far above the 150-draft maximum of one transcript; a batch refused with `429` is retried whole after `Retry-After`, never split.
- Per tenant: the setting `llmMonthlyTokenCap` (default 2,000,000 for every tenant; `0` turns the step off) bounds input plus output tokens per calendar month in UTC, whatever `costCap` says (`costCap` stops agents at their euro allocation). Before a call the API reserves the call's upper bound in `llm_month_usage`: the input estimate is the larger of the whole assembled request's code points divided by 2 and its UTF-8 bytes divided by 3, rounded up (instructions, text, context sentences, session turns, candidates, templates and guidance). The code-point term covers Latin scripts; the byte term covers scripts such as Chinese or Japanese, where one character can be a token or more. The output bound is added: 1,024 tokens, or 12,288 for a `speech` transcript. For a full 4,000-character Latin-script transcript with 8 session turns and 200 candidates the assembled request is at most about 30,000 characters, so the reservation is at most about 15,000 + 12,288, roughly 27,300 tokens, against about 7,000 for a typed sentence. The reservation is taken with one conditional upsert; zero rows returned means the cap is reached and the step is skipped with `llmOutcome` `budget_exhausted`. The reservation commits in its own short transaction before the provider is called; no transaction, and so no row lock on the tenant's month row, stays open during the call, and the request's own transaction never includes the reservation. After the call, in another short transaction, the reservation is settled to the actual count on the month it was made in (a call that starts on the last second of a month settles into that month), and the `llm_call` row is inserted. A timed-out, failed or invalid call settles its actual count, 0 when the provider reports none, which releases the rest of the reservation. A reservation whose process dies before settling stays counted until the month ends.
- An exhausted budget never fails the request: the response is `200` with the grammar's result, `degraded` true and the reason in `llmOutcome`. The existing `429 rate_limited` stays for the parse budget, which is charged before the grammar runs, as today.
- No event is published for cost records. They change no state another client draws; Cost management reads `GET /cost` when it opens.

### Failure Modes

| Situation | `llmOutcome` | Response |
|---|---|---|
| No trigger | `not_triggered` | `200`, grammar result, `extractor` `rules`, `degraded` false |
| No provider or key configured, or cap `0` | `not_configured` or `budget_exhausted` | `200`, grammar result, `degraded` true, sentence in `unresolved` (`model_unavailable`) |
| Caller's hourly `llm` budget spent | `rate_limited` | same |
| Tenant's monthly cap reached | `budget_exhausted` | same |
| No answer within 15 seconds (`text`, `document`) or 45 seconds (`speech` transcript) | `timeout` | same; the call is abandoned, not retried |
| Provider error, refusal or rate limit | `provider_error` | same |
| Answer fails the schema or the handle checks | `invalid_output` | same, reason `model_invalid_output` |
| Valid answer | `used` | `200`, `extractor` `llm` or `rules+llm` |
| Any row above except the last two, for `speech` or `document` | as above | `200`, grammar result on the transcript segments or cited sentence, `degraded` true |

The model step never produces a `5xx`. The timeout is 15 seconds for `text` and `document` and 45 seconds for a `speech` transcript (decision row 91), wall clock from the start of the adapter call to the last byte read, DNS, connect and TLS included; the provider SDK's own retries are set to 0, so no retry adds time. The storing of the session turn and the cost row are short writes outside that window, and none of them holds a lock another request waits on across the call.

### Adapter, Configuration And Secrets

- The adapter lives in `apps/api/app/clients/` behind one provider-neutral interface: it takes the request above and returns JSON text plus token counts, or a timeout or error. No provider type, SDK class or model name appears outside it, in any contract or in any response.
- Deployment configuration: `ONTAIX_LLM_PROVIDER` (default `anthropic`), `ONTAIX_LLM_MODEL` (default `claude-sonnet-5`), `ONTAIX_LLM_TIMEOUT_SECONDS` (text and document, default 15; a value above 15 or at most 0 stops the API at start-up), `ONTAIX_LLM_SPEECH_TIMEOUT_SECONDS` (speech transcript, default 45; a value above 45 or at most 0 stops the API at start-up). Changing provider or model needs no contract change.
- The Anthropic API key lives only in Azure Key Vault as the secret `anthropic-api-key`, read at start-up by the API's workload identity, and locally in the ignored `.env` as `ONTAIX_ANTHROPIC_API_KEY`. It is never in settings, responses, events, audit entries, logs, tests, fixtures or documentation. The adapter's HTTP client redacts authentication headers from every log line; prompts and answers are not logged.
- With no key configured the step reports `not_configured`, so local development and tests run without a key.

### Security

- The sentence is untrusted input to the model. The model's only power is to return intents, which the schema, the handle table and the draft validation bound like any client's drafts, and every draft still needs a human approval.
- Text the caller does not control also reaches the model: candidate labels written by other users or agents (pending ones included) and, for documents, neighbouring sentences. The request carries them in delimited data fields, marked as data and never as instructions. The grounding rule stops them from minting concepts: a new label must appear in the caller's own words. An injection can still pick wrong actions or links between grounded labels and existing concepts. The Studio submits a parse's drafts, at most 150, as pending proposals under the teaching user's name; each one still needs a human approval, Approve all included, so reviewers see them as that user's proposals.
- Labels from the model meet the same limits as labels from any client (1 to 120 characters, no markup or control characters) and also refuse bidirectional and zero-width characters and surrounding spaces; `rule`, `explanation` and `span` refuse the same characters; explanations are plain text, HTML-escaped wherever the server interpolates them and rendered as text; `unresolved` text is taken from the server's own copy of the sentence.
- Only the caller that created a session reads its turns, in its tenant and company.

### Data Residency

The rest of Ontaix runs in Azure France Central. The model step is the one place where tenant content leaves that environment. What leaves, per call: the sentence being taught (typed text, a speech transcript or an imported document sentence), up to 8 earlier sentences of the session, the company name, up to 200 concept labels with their domain keys and pending flags, other companies' names and matching labels when `crossCompany` is on, the domain templates and the action guidance. Nothing in the never-sent list above leaves.

With the default configuration it goes to Anthropic's API (`ONTAIX_LLM_PROVIDER` `anthropic`), a service operated by Anthropic outside Azure. This configuration gives no guarantee that the data stays in France or in the EU; where Anthropic processes it is set by Anthropic's API terms, not by Ontaix. Retention of prompts and answers by the provider follows the provider's API terms in force for the account that owns the key; Ontaix itself stores neither. The adapter's provider setting is the lever for a different residency, for example a provider endpoint in an EU region, and needs no contract change.

Egress is on by default (decision row 87). `llmMonthlyTokenCap` defaults to 2,000,000 tokens per month for every tenant, so once a provider key is configured, every sentence that triggers the model step leaves Azure France Central for the provider, with the context listed above, without any tenant action. A tenant administrator opts out by setting `llmMonthlyTokenCap` to `0` (`PATCH /settings`, `settings.write`, audited); from then on nothing leaves for that tenant.

## Consequences

- The owner's natural sentences produce drafts; the grammar stays the verbatim port and the screenshot suite is unaffected, because the Studio renders the same drafts and captions.
- A typed sentence that triggers the step, or a document sentence, waits up to 15 seconds longer, and a speech transcript up to 45 seconds; typed sentences the grammar fully understands pay nothing. The Studio adds no waiting indicator: it shows what the reference shows while a sentence is being taught, and nothing new.
- Sentences that trigger the step, recent session sentences and candidate labels leave Azure France Central for the configured provider (see Data Residency). This happens by default; a tenant administrator opts out with `llmMonthlyTokenCap` set to `0`.
- Model spend is measured per call, capped per caller per hour and per tenant per month, and visible in `GET /cost`.
- `confidence` and `explanation` reach the API client only; showing them in the Studio needs a UI contract decision first.
