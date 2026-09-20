# Providerzy

## Wspólny kontrakt

Adapter implementuje capabilities, asynchroniczne `complete(request)` oraz
`close()`. Przyjmuje znormalizowany `ModelRequest` i zwraca
`ModelResponse`:

```python
class ProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
    async def close(self) -> None: ...
```

Request zachowuje opcjonalny `output_schema`, gdy runtime wybierze gwarantowany
native structured output. Odpowiedź zachowuje content, tool calls, jawny
`structured_output`, finish reason, usage i opcjonalny raw payload wyłącznie do
debugowania. Adapter nie umieszcza native structured payloadu w polu tekstowym.

`ProviderRequestError` zachowuje opcjonalny status HTTP oraz flagę
`retryable`. Domyślna klasyfikacja ponawia 429, 500, 502, 503 i 504; timeout
transportu i reset połączenia są klasyfikowane przez wspólny runtime. Typowe
4xx oraz pozostałe błędy kończą się bez automatycznego retry.

Tool call zachowuje ID, nazwę, sparsowane arguments, raw arguments i parse
error. Adapter nie kończy runu tylko dlatego, że same arguments są uszkodzone;
wspólny repair layer potrzebuje surowych danych.

## Capability model

Minimalne flagi:

- `tool_calling`;
- `native_structured_output`;
- `parallel_tool_calls`.

Adapter dostarcza sensowne defaulty. Niestandardowy lokalny endpoint może mieć
jawny override w konfiguracji. Walidację wykonujemy możliwie wcześnie podczas
tworzenia `Agent`.

## Adaptery v0.1

### `openai_compatible`

Pierwszy adapter produkcyjny i baza dla lokalnych `llama-server`, vLLM, SGLang
oraz podobnych endpointów. Jest domyślnie zarejestrowany dla provider type
`openai_compatible` i używa jednego `httpx.AsyncClient` na instancję providera.
Implementacja obejmuje:

- async HTTP client i konfigurowalny base URL;
- opcjonalny API key;
- messages i tool schemas;
- zachowanie tool-call IDs i raw arguments;
- timeout oraz usage, jeśli dostępne;
- wysyłanie tylko wspieranego, niezbędnego podzbioru parametrów.

Request trafia do `chat/completions`. Puste tools i nieustawione opcje generation
są pomijane. `output_schema` jest mapowany na
`response_format.type=json_schema`; tylko w tym trybie dokładny JSON content
może zostać znormalizowany do `structured_output`.

HTTP 429 oraz przejściowe 5xx zachowują klasyfikację retryable. Timeout jest
przekazywany do wspólnego retry jako `TimeoutError`, a błędy transportu i
niepoprawne odpowiedzi nie ujawniają body ani danych autoryzacyjnych.

### Scripted fake

`ScriptedFakeProvider` realizuje ten sam protokół bez sieci. Przyjmuje kolejkę
znormalizowanych odpowiedzi lub wyjątków, zwraca je w kolejności i zapisuje
snapshot każdego requestu. Służy do deterministycznych testów pętli runtime,
tool calli, structured output oraz błędów providera.

### `openrouter`

Cienka specjalizacja delegująca cały request, response i lifecycle do adaptera
OpenAI-compatible. Domyślnie używa `https://openrouter.ai/api/v1`, mapuje
`api_key` na Bearer auth i pozwala dodać dowolne nagłówki, w tym opcjonalne
`HTTP-Referer` oraz `X-OpenRouter-Title`.

Model ID jest przekazywany nieprzezroczyście, więc identyfikatory takie jak
`vendor/model` zachowują slash. Zwrócone `prompt_tokens`, `completion_tokens`,
`total_tokens` i `cost` są normalizowane do wspólnego `Usage`; brak wartości
pozostaje `None`, a nie sztucznym zerem. Ponieważ wsparcie parametrów zależy od
wybranego modelu OpenRouter, native structured output nie jest gwarantowany
domyślnie i może zostać włączony jawnym capability override.

### `azure_openai`

Traktuje `ModelConfig.model` jako deployment ID. Adapter buduje trasę
`openai/deployments/{deployment}/chat/completions`, przekazuje wymagany
`api-version` w query i domyślnie mapuje `api_key` na nagłówek `api-key`.
Jawny nagłówek `Authorization` pozwala zamiast tego przekazać Bearer token.
Pole `model` nie jest dublowane w body requestu.

### `azure_foundry`

Pozostaje osobnym provider type, mimo że deleguje HTTP, serializację odpowiedzi,
błędy i lifecycle do wspólnego transportu. Skonfigurowany `endpoint` jest bazą
dla `chat/completions`, model/deployment pozostaje w body, a opcjonalny
`api_version` trafia do query. API key używa nagłówka `api-key`; Bearer auth
można dostarczyć przez custom `Authorization`.

Oba adaptery korzystają wyłącznie z obecnego już w core `httpx`. Extra
`moiryx[azure]` jest dlatego celowo pustym, stabilnym punktem instalacji: nie
ma nieużywanego Azure SDK, a typy SDK nie mogą przeciec do publicznego core.

### `vertex_ai`

Używa opcjonalnego `google-genai` i jego klienta async. `project`, `location`
oraz model są mapowane jawnie, a auth pozostaje w standardowym ADC/service
account environment. Inline `api_key` i custom auth headers są odrzucane, aby
credentials nie trafiały do konfiguracji aplikacji.

Adapter tłumaczy role wiadomości, function declarations/responses, generation
options i native JSON Schema. Tekst, function calls, finish reason oraz
`prompt_token_count`, `candidates_token_count` i `total_token_count` wracają
wyłącznie jako typy core Moiryx; obiekty SDK nie przeciekają przez `raw`.
Instalacja wymaga `pip install "moiryx[google]"`, podczas gdy core pozostaje bez
Google SDK.

## Fabryka i lifecycle

`PROVIDER_FACTORIES` mapuje type na konstruktor adaptera. Nieznany type to
`ConfigurationError`. Jeden `Agent` używa tego samego klienta między krokami
i wywołaniami; różne obiekty `Agent` nie współdzielą connection pool ani
historii runu.

Podstawowe API nie wymaga context managera. Przy dłużej żyjących procesach
można jawnie wywołać `await agent.aclose()` lub użyć `async with Agent(...)`;
oba sposoby zamykają połączenia providera po zakończeniu pracy.

## Strategia testów adapterów

Każdy adapter dostaje:

- test mapowania requestu;
- test tekstowej odpowiedzi;
- test jednego i wielu tool calli;
- test malformed arguments z zachowaniem raw payload;
- test usage;
- test klasyfikacji błędów retryable/non-retryable;
- test capabilities;
- test redakcji sekretów.

CI korzysta wyłącznie z mock transportu/SDK. Live tests są oznaczone
`integration`, domyślnie wyłączone i wymagają jawnych zmiennych środowiskowych.
Smoke dla lokalnego endpointu wymaga jednocześnie
`MOIRYX_OPENAI_COMPATIBLE_LIVE_URL` i
`MOIRYX_OPENAI_COMPATIBLE_LIVE_MODEL`; opcjonalny klucz przyjmuje
`MOIRYX_OPENAI_COMPATIBLE_LIVE_API_KEY`.
