# ADR 0013: Speech Recognition

Status: Accepted. Owner decision, final (decision row 128).

## Context

The teach bar microphone uses the browser's built-in `SpeechRecognition`. Its quality varies by browser, it is not available in every browser, it sends audio to whatever service the browser vendor chose (outside the Ontaix environment and with no residency statement), and it cannot be told the company's own vocabulary, so names such as `ADNOC` or `L&S` come back misspelt. The owner decided that voice recognition moves to Azure AI Speech in France Central, English only, primed with the company's concept labels, keyless, with no visible UI change and the browser recogniser as the fallback.

## Decision

### Architecture

```mermaid
sequenceDiagram
  participant S as Studio (browser)
  participant A as Ontaix API
  participant M as Managed identity id-ontaix-speech-dev-frc
  participant E as Microsoft Entra ID
  participant SP as Azure AI Speech, France Central (custom subdomain)
  S->>A: POST /speech/token {companyId} (bearer)
  A->>A: proposal.create in scope, voice on, speech budget, audit
  A->>M: DefaultAzureCredential / ManagedIdentityCredential
  M->>E: token for https://cognitiveservices.azure.com/.default
  E-->>A: access token (Speech User on one resource only)
  A-->>S: 200 {token: aad#resourceId#accessToken, region, expiresAt, language} no-store
  S->>S: SpeechConfig.fromAuthorizationToken(token, region), speechRecognitionLanguage en-GB
  S->>S: PhraseListGrammar.fromRecognizer - up to 500 company labels from the scene
  S->>SP: WebSocket audio stream (continuous recognition)
  SP-->>S: interim and final results
  S->>A: POST /teach/parse origin speech, one finished sentence per request (row 127)
```

- The Speech resource is a dedicated Azure AI Speech (or AI Services) resource `spch-ontaix-<env>-frc` in France Central with a custom subdomain and local (key) authentication disabled. Microsoft Entra authentication with the Speech SDK requires the custom subdomain, and the subdomain cannot be changed once set.
- `POST /speech/token` returns a Microsoft Entra access token for the scope `https://cognitiveservices.azure.com/.default`, wrapped as `aad#<resourceId>#<accessToken>`, the form the JavaScript Speech SDK takes in `SpeechConfig.fromAuthorizationToken(token, region)` for Entra authentication.
- The token comes from a dedicated user-assigned managed identity, `id-ontaix-speech-<env>-frc`, not from the API's workload identity. That identity holds only the built-in role Cognitive Services Speech User on the Speech resource, and nothing else. A token for `cognitiveservices.azure.com` is valid on every Cognitive Services resource where its identity holds a role, so the API's own identity, which may call the Foundry model deployments, must never hand its token to a browser. With the dedicated identity, a token taken from the browser can only run speech recognition on this one resource until it expires.
- No key exists (local auth off) and no key or managed-identity secret reaches the browser. The token grants nothing in Ontaix.

### Recognition

- English only. `speechRecognitionLanguage` is `en-GB` by default (`ONTAIX_SPEECH_LANGUAGE`, `en-GB` or `en-US`). `en-GB` is kept as the default because the owner and the first tenants work in British and international English in Europe and the Middle East; `en-US` is the better choice only for a tenant whose speakers are mostly North American, and it is one setting away. No automatic language detection.
- Continuous recognition with interim results, exactly as the browser path today: interim text only shows in the input, and each final result becomes one `speech` request to `POST /teach/parse` in the recording's `sessionId` (row 127). The visible UI is unchanged.
- Phrase list: when the microphone starts, the Studio builds a phrase list from the scene it already holds (`GET /scene`, no new call): the company name, then the labels of the active company's live and pending concepts, ranked - concepts in the focused domain or cell's neighbourhood first, then the most recently born - up to 500 labels, each at most 120 characters, deduplicated case-insensitively. It is applied with `PhraseListGrammar.fromRecognizer(recognizer)` and `addPhrase`, at the default weight. 500 stays well under the service's guidance of at most 2,000 phrases, beyond which quality and latency suffer. Characters the service does not accept are removed by the service. Only labels of the company being taught are sent; no other company's labels.

### Token Lifetime And Refresh

- `expiresAt` is the Entra token's own expiry (Entra access tokens for managed identities typically last up to 24 hours and cannot be shortened by the caller).
- The Studio requests a fresh token at every microphone start and, while recording, at least 5 minutes before `expiresAt`, setting it on the running recogniser (`recognizer.authorizationToken`), so a long recording never drops. Tokens are held in memory only.
- The API caches the managed identity's token server-side (the credential's own cache) and never logs it; responses carry `Cache-Control: no-store`.

### Fallback

The Studio falls back to the browser's `SpeechRecognition`, as today, when `POST /speech/token` answers `503` (no Speech resource configured, or the token cannot be obtained), when the SDK fails to connect or cancels with an error, or when the browser blocks the WebSocket. `403`, `409 channel_disabled` and `429` do not fall back: they show the refusal toast (row 86), since the caller may not teach by voice at that moment. The fallback is per recording; the next microphone start tries Azure Speech again.

### Data Residency

The audio stream goes from the browser straight to the Speech resource in France Central; it never passes through the Ontaix API. For real-time speech to text the service processes audio in memory only and stores no data at rest; Microsoft does not retain or store it. Audio and transcription logging is a Speech SDK option that is off by default; Ontaix never enables it (`enableAudioLogging` is never called) and uses no batch transcription or custom model. The phrase list (company labels) goes to the same resource. Transcribed text then enters Ontaix through `POST /teach/parse`, under ADR 0008. Unlike the browser recogniser, the audio no longer leaves the EU for a browser vendor's service.

### Cost

Real-time speech to text is billed per hour of audio streamed (standard pay-as-you-go, per second), on the Insight Azure subscription. Phrase lists cost nothing extra. The cost is bounded by recording time: recording stops after 1.5 seconds of silence (row 127), and the `speech` budget bounds how often a caller can start. Speech cost is Azure consumption on the subscription and does not appear in `GET /cost`, which reports Ontaix's own model calls.

### Rate Limit And Audit

- Each `POST /speech/token` spends one unit of the caller's hourly `speech` budget in `rate_budget_window` (new budget value, default 60 per user or agent per hour, `ONTAIX_SPEECH_TOKENS_PER_HOUR`); `429 rate_limited` with `Retry-After` when spent.
- Each successful call writes one audit entry through the existing audit mechanism: kind `speech`, what `Speech recognition token issued`, `ok` true, `companyIds` the company being taught, no proposal. The token itself is never in the audit entry, a log line or an event. No new table and no new event.

### Permission

The same as teaching: `proposal.create` in the scope of the company being taught (Owner, Builder, Agent in scope, or Member while `everyoneTeaches` is on, ADR 0003 check point 1), and the `voice` setting on (`409 channel_disabled` otherwise, as `speech` teach requests).

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ONTAIX_SPEECH_RESOURCE_ID` | none | The Speech resource's full Azure resource id; unset gives `503` and the browser fallback |
| `ONTAIX_SPEECH_REGION` | `francecentral` | The resource's region, returned to the Studio |
| `ONTAIX_SPEECH_CLIENT_ID` | none | Client id of the managed identity `id-ontaix-speech-<env>-frc` used to mint tokens |
| `ONTAIX_SPEECH_LANGUAGE` | `en-GB` | `en-GB` or `en-US`; anything else stops the API at start-up |
| `ONTAIX_SPEECH_TOKENS_PER_HOUR` | 60 | The per-caller hourly `speech` budget |

The Speech resource, its custom subdomain, the managed identity, its role assignment and the federated credential that lets the API pod use it are an infrastructure change in `infra/terraform/azure`, not part of this contract change. The Content Security Policy of the Studio must allow `wss://<custom subdomain>.cognitiveservices.azure.com` (or the regional `wss://francecentral.stt.speech.microsoft.com` endpoint the SDK uses with `fromAuthorizationToken`).

## Consequences

- Recognition quality no longer depends on the browser, works in every browser the Speech SDK supports, and knows the company's names.
- Audio stays in France Central and is not stored; voice teaching is English only.
- One new endpoint, one new budget value, one new audit kind; no new table, no new event.
- A leaked token allows speech recognition on one resource until it expires, billed to Ontaix, and nothing else; the dedicated identity and the `speech` budget bound that exposure.

## References

- Microsoft Learn, [How to configure Microsoft Entra authentication](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-configure-azure-ad-auth): a custom subdomain is required and cannot be changed; the roles Cognitive Services Speech User or Contributor; the scope `https://cognitiveservices.azure.com/.default`; the `aad#<resourceId>#<token>` authorization token for SDK paths that take a token.
- Microsoft Learn, [SpeechConfig class (JavaScript)](https://learn.microsoft.com/en-us/javascript/api/microsoft-cognitiveservices-speech-sdk/speechconfig): `fromAuthorizationToken(authorizationToken, region)` and the `authorizationToken` property for refresh.
- Microsoft Learn, [Improve recognition accuracy with phrase list](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list): phrase lists apply at runtime to real-time transcription through the Speech SDK, `PhraseListGrammar.fromRecognizer` and `addPhrase` in JavaScript, at most 2,000 phrases, weight 0.0 to 2.0.
- Microsoft Learn, [Data, privacy, and security for speech to text](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/speech-service/speech-to-text/data-privacy-security): real-time audio is processed in server memory only, no data is stored at rest, and Microsoft does not retain real-time data.
- Microsoft Learn, [How to log audio and transcriptions for speech recognition](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/logging-audio-transcription): logging is opt-in through `enableAudioLogging`.
- Microsoft Learn, [Access tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens): token lifetime.
