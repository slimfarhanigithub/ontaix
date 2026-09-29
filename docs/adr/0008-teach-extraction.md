# ADR 0008: Teach Extraction

Status: Proposed. The owner's decisions (rows 70 to 74) are final; the derived choices (rows 75 to 79) wait for the owner to confirm.

## Context

The teach bar parses sentences with the rule-based grammar ported verbatim from the reference (requirements addendum, section 3). It handles the reference's lexicon and patterns and nothing else. Two sentences the owner teaches show where it stops:

- `Insight sells services` - `sells` is not in the lexicon (only `sells to` is), so the grammar understands nothing. The owner expects a new concept `Services` born from the company root `Insight` with the action `sells`.
- `these services are focused around three areas, app, data and AI` - the grammar strips `these` as a determiner, matches the specialisation pattern and drafts `Service is a Focused around three areas, app, data and ai`. The owner expects three concepts `App`, `Data` and `AI` born from `Services` with an action such as `focuses on`, where `these services` means the `Services` of the previous sentence.

The owner decided (rows 70 to 74) to add a language model extraction step as a fallback behind the grammar, with Claude Sonnet 5 as the default model behind a provider-neutral adapter, and to keep every model result a draft that a human approves.

## Decision

### Pipeline

```mermaid
flowchart TD
  input[Sentence from text, speech transcript or importRef] --> gates[Channel gates and parse budget as today]
  gates --> rules[Rule-based grammar - always first]
  rules --> triggers{Any fallback trigger?}
  triggers -->|no| result_rules[Result from rules - llmOutcome not_triggered]
  triggers -->|yes| configured{Model configured and llmMonthlyTokenCap above 0?}
  configured -->|no| degraded[Rules result, degraded, sentence in unresolved]
  configured -->|yes| actor_budget{Caller llm budget - rate_budget_window}
  actor_budget -->|exhausted| degraded
  actor_budget -->|unit charged| reserve{Reserve tokens - llm_month_usage}
  reserve -->|cap reached| degraded
  reserve -->|reserved| context[Build context - sentence, session turns, company name, up to 200 candidates, domain templates, action guidance]
  context --> call[Adapter calls the configured model - 15 s timeout, no retry]
  call -->|timeout or provider error| settle_fail[Settle tokens, write llm_call row]
  settle_fail --> degraded
  call -->|answer| validate{Valid against teach-extraction.schema.json and cited candidates?}
  validate -->|no| settle_invalid[Settle tokens, write llm_call row]
  settle_invalid --> degraded
  validate -->|yes| settle_ok[Settle tokens, write llm_call row]
  settle_ok --> map[Map intents to drafts with the grammar's mapping table]
  map --> merge{Trigger was partly_understood alone?}
  merge -->|yes| both[Keep rules intents, add model intents without duplicates - rules+llm]
  merge -->|no| llm_only[Model intents replace the rules intents - llm]
  both --> turn[Store the session turn]
  llm_only --> turn
  result_rules --> turn
  degraded --> turn
  turn --> response[200 TeachResult - drafts only, nothing written]
  response --> batch[Client submits drafts to POST /proposals/batch]
  batch --> human[A human approves or rejects each proposal]
```

### Fallback Triggers

The grammar always runs first. The model step runs only when at least one of these holds:

1. The grammar outcome is `not_understood`.
2. The grammar outcome is `partly_understood`.
3. The sentence holds a back-reference word as a whole word: `these`, `those`, `it`, `they`, `them`, `this`.
4. The sentence holds a list preamble: a count word (`two` to `twelve`) or a number, then one to three words, then `,` or `:` (as in `three areas, app, data and AI`).
5. The sentence holds a verb form that is not a variant of the reference lexicon. The API checks the words against a verb word list it ships for this purpose only; the lexicon itself never changes, so the grammar stays the verbatim port.

Triggers 3 to 5 mark the grammar's own result as suspect, so a valid model answer replaces it (`extractor` `llm`). Trigger 1 has no grammar result to keep (`llm`). When trigger 2 holds alone, the grammar's intents are kept and the model's are added, dropping any model intent that resolves to the same subject, action and object (`rules+llm`, or `rules` when the model adds nothing).

### Teach Session

The Studio generates a `sessionId` (uuid) when it loads and whenever the taught company changes, and sends it with every `POST /teach/parse`. The server stores each sentence as one `teach_session_turn` row keyed by tenant, caller (`actor_kind`, `actor_id`), company and session, with the extractor used, the ids of the existing concepts the sentence referenced (`concept_ids`) and the labels it introduced (`new_labels`). Limits: the last 8 turns per session (the insert of turn n and the deletion of turns up to n - 8 run in one transaction), each turn expires 2 hours after it was stored, at most 50 ids and 50 labels per turn, sentences of at most 400 characters. A purge every 15 minutes deletes expired turns; reads ignore them before that. Only the caller that created a session reads it; an unknown or expired `sessionId` is an empty session, never an error. When the next sentence is parsed, each stored label is resolved again against the company's concepts, so a label whose proposal has since been submitted (a pending concept) or approved resolves to its id; a label nobody submitted stays a label.

### What The Server Sends The Model

The adapter receives one request built by the API. This ADR fixes its content, not its wording; the prompt text lives in `apps/api/app/ai/prompts/`.

- The sentence (after the domain prefix is stripped, with the prefix's domain key given separately).
- The session's recent turns, oldest first: each turn's sentence and the candidate handles or labels it referenced and introduced.
- The name of the company being taught.
- Up to 200 candidate concepts of that company, each as a handle (`c0` to `c199`, valid for this call only), label, domain key, parent handle and a pending flag. `c0` is always the company root. Ranking, until 200: the root; concepts referenced by session turns, newest first; concepts whose label matches a word of the sentence (case-insensitive, singular or plural, as the grammar's `resolve`); the parents and children of those; concepts of the prefixed domain; the most recently born. Concept ids never leave the API; the handle table maps each handle back to an id when the answer is read.
- Other companies' concepts only when the `crossCompany` setting is on and the caller may read that company, only those whose label matches a word of the sentence, at most 50 of the 200, each marked with its company name. An intent between two existing concepts of different companies becomes a `RelationDraft` and meets every existing cross-company check when it is proposed; a new concept is always born in the company being taught.
- The nine domain templates (key and name).
- Action guidance: actions are lower-case present-tense verb phrases read subject to object; the reference lexicon's canonical predicates are listed and preferred when one has the same meaning; `is a` is expressed as a `spec` intent, never as an action; `equivalent to` is not available to the model.

The server never sends: user or agent names, emails or ids; the tenant id or name; concept, proposal or source ids; sources, connector hosts, scopes, bindings, attributes or record counts; settings; audit entries; proposers; any credential or secret; other companies' data outside the rule above.

### Output Contract

The model returns JSON only, validated against `contracts/teach-extraction.schema.json`: up to 20 intents (`rel` or `spec`, subject and object each a candidate handle or a new label, action for `rel`, optional rule for `spec`, optional domain key, confidence 0 to 1, optional plain-text explanation of at most 300 characters, optional span) and up to 10 unresolved phrases. The API then checks what a schema cannot: every cited handle was sent, no intent joins a concept to itself, and no `rel` action is `is a` or `equivalent to`. Any failure makes the whole answer invalid (`llmOutcome` `invalid_output`): no model draft is returned, the sentence is listed in `unresolved` with reason `model_invalid_output`, and nothing is written.

A valid answer is turned into drafts by the grammar's own mapping (requirements addendum, section 3.4): an existing subject and a new object give a `ConceptDraft` with `parentId`; a new subject and an existing object give a `ConceptDraft` with `reverse` true; two existing concepts give a `RelationDraft` by id; two new concepts give a concept born from the root with `has` and a second one born from it by `parentLabel`. A new label that matches an existing concept is resolved to it, as the grammar does. The domain key is the sentence's prefix, else the model's `domainKey`, else the parent's domain, else `production`. Intents with a confidence below 0.4 are not drafted and are listed in `unresolved` with reason `low_confidence`. Drafts keep their existing schemas; each draft's extractor, confidence and explanation travel in `TeachResult.draftNotes`, in draft order, and are never submitted.

For the owner's two sentences, with `Insight` as `c0`:

- `Insight sells services` gives `rel c0 sells newLabel Services`, drafted as `ConceptDraft` (parent `Insight`, label `Services`, action `sells`).
- `these services are focused around three areas, app, data and AI`, with `Services` pending from the first sentence and sent as a candidate, gives three `rel` intents from that candidate with action `focuses on` to `App`, `Data` and `AI`, drafted as three `ConceptDraft`s with `parentId` set to `Services`.

### Costs And Budgets

- Every call to the provider, including failed and timed-out ones, writes one `llm_call` row: tenant, caller, company, purpose `teach_extraction`, provider, model, input and output tokens, estimated euro cost from the deployment's price table, latency and outcome. It never holds the sentence, prompt, answer or key. Rows are kept 400 days.
- `GET /cost` returns the month's totals as `CostSummary.llm` (`LlmUsage`), separate from the agent figures (`measuredEur`, `byPlatform`), which stay agent reads through the gateway. The Cost management page shows no new element until `docs/ui-contract.md` records one.
- Per caller: each model call spends one unit of the hourly `llm` budget in `rate_budget_window` (default 200 calls per user or agent per hour, from configuration like the other budgets). When it is spent the step is skipped with `llmOutcome` `rate_limited`.
- Per tenant: the setting `llmMonthlyTokenCap` (default 2,000,000 tokens, `0` turns the step off) bounds input plus output tokens per calendar month in UTC, whatever `costCap` says (`costCap` stops agents at their euro allocation). Before a call the API reserves the call's upper bound (estimated input tokens plus the maximum of 1,024 output tokens) in `llm_month_usage` with one conditional upsert; zero rows returned means the cap is reached and the step is skipped with `llmOutcome` `budget_exhausted`. After the call the reservation is settled to the actual count.
- An exhausted budget never fails the request: the response is `200` with the grammar's result, `degraded` true and the reason in `llmOutcome`. The existing `429 rate_limited` stays for the parse budget, which is charged before the grammar runs, as today.
- No event is published for cost records. They change no state another client draws; Cost management reads `GET /cost` when it opens.

### Failure Modes

| Situation | `llmOutcome` | Response |
|---|---|---|
| No trigger | `not_triggered` | `200`, grammar result, `extractor` `rules`, `degraded` false |
| No provider or key configured, or cap `0` | `not_configured` or `budget_exhausted` | `200`, grammar result, `degraded` true, sentence in `unresolved` (`model_unavailable`) |
| Caller's hourly `llm` budget spent | `rate_limited` | same |
| Tenant's monthly cap reached | `budget_exhausted` | same |
| No answer within 15 seconds | `timeout` | same; the call is abandoned, not retried |
| Provider error, refusal or rate limit | `provider_error` | same |
| Answer fails the schema or the handle checks | `invalid_output` | same, reason `model_invalid_output` |
| Valid answer | `used` | `200`, `extractor` `llm` or `rules+llm` |

The model step never produces a `5xx`. The 15-second timeout covers the whole step from the adapter's first byte sent to the last byte read.

### Adapter, Configuration And Secrets

- The adapter lives in `apps/api/app/clients/` behind one provider-neutral interface: it takes the request above and returns JSON text plus token counts, or a timeout or error. No provider type, SDK class or model name appears outside it, in any contract or in any response.
- Deployment configuration: `ONTAIX_LLM_PROVIDER` (default `anthropic`), `ONTAIX_LLM_MODEL` (default `claude-sonnet-5`), `ONTAIX_LLM_TIMEOUT_SECONDS` (default 15, at most 15). Changing provider or model needs no contract change.
- The Anthropic API key lives only in Azure Key Vault as the secret `anthropic-api-key`, read at start-up by the API's workload identity, and locally in the ignored `.env` as `ONTAIX_ANTHROPIC_API_KEY`. It is never in settings, responses, events, audit entries, logs, tests, fixtures or documentation. The adapter's HTTP client redacts authentication headers from every log line; prompts and answers are not logged.
- With no key configured the step reports `not_configured`, so local development and tests run without a key.

### Security

- The sentence is untrusted input to the model. The model's only power is to return intents, which the schema, the handle table and the draft validation bound like any client's drafts, and every draft still needs a human approval. A prompt injection can at worst produce wrong drafts that a reviewer rejects.
- Labels from the model meet the same limits as labels from any client (1 to 120 characters, no markup or control characters); explanations are plain text, HTML-escaped wherever the server interpolates them and rendered as text.
- Only the caller that created a session reads its turns, in its tenant and company.

## Consequences

- The owner's natural sentences produce drafts; the grammar stays the verbatim port and the screenshot suite is unaffected, because the Studio renders the same drafts and captions.
- A sentence that triggers the step waits up to 15 seconds longer; sentences the grammar fully understands pay nothing.
- Sentences that trigger the step, recent session sentences and candidate labels leave the Azure environment for the configured provider. A tenant that forbids this sets `llmMonthlyTokenCap` to `0`.
- Model spend is measured per call, capped per caller per hour and per tenant per month, and visible in `GET /cost`.
- `confidence` and `explanation` reach the API client only; showing them in the Studio needs a UI contract decision first.
