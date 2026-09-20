# Architektura

## Widok całości

```text
Kod aplikacji
  │  await agent(prompt)
  ▼
Agent ── ładuje ──> AgentSpec
  │                    │
  │                    ├── model alias ──> ModelRegistry
  │                    ├── tool names ───> ToolRegistry
  │                    └── output ref ───> Pydantic model
  ▼
AgentRuntime
  ├── RunContext i wiadomości
  ├── tool-call preflight / repair / execution
  ├── structured output
  ├── retry i limity
  └── logging / trace
  │
  ▼
ProviderAdapter ──> lokalny endpoint / OpenRouter / Azure / Vertex AI
```

## Granice komponentów

### `Agent`

Jest cienką fasadą. Konstruktor ładuje i waliduje definicję, rozwiązuje model,
providera, narzędzia oraz output model. `__call__` deleguje wykonanie do
runtime'u. Nie przechowuje historii pojedynczego runu.

### Konfiguracja i registry

`ConfigLoader` odpowiada za znalezienie pliku, interpolację środowiska i
walidację. `ModelRegistry` mapuje alias logiczny na `ModelConfig`, a
`ProviderRegistry` tworzy i utrzymuje adaptery. `ToolRegistry` przechowuje
built-in oraz zaimportowane custom tools.

### `AgentSpec`

Niemutowalny wynik parsowania Markdownu:

- nazwa;
- logiczny alias modelu;
- instrukcje;
- lista nazw tooli;
- opcjonalna klasa Pydantic;
- limit kroków;
- ustawienia generacji.

Nie jest publicznym API v0.1.

### `AgentRuntime` i `RunContext`

Runtime realizuje pętlę model/tool/final result. Dla każdego `await agent(...)`
powstaje osobny `RunContext` z run ID, wiadomościami, licznikami prób i usage.
Dzięki temu jedna instancja `Agent` może być bezpiecznie używana współbieżnie.

### Adapter providera

Adapter tłumaczy wspólny `ModelRequest` na SDK/API i zwraca
`ModelResponse`. Zachowuje raw arguments oraz parse errors tool calli, aby
wspólny repair layer mógł podjąć bezpieczną decyzję. Obiekty SDK nie przeciekają
do `Agent` ani tool systemu.

## Przepływ inicjalizacji

1. Znajdź i zwaliduj `moiryx.yaml`.
2. Zaimportuj jawnie wymienione `tool_modules`.
3. Sparsuj frontmatter i body pliku agenta.
4. Rozwiąż model alias, provider alias oraz nazwy tooli.
5. Załaduj klasę output i sprawdź dziedziczenie po `BaseModel`.
6. Scal generation options: runtime, model, agent.
7. Sprawdź capabilities providera.
8. Zwróć gotową, niemutowalną konfigurację agenta.

Błędy wykrywalne statycznie mają wystąpić w konstruktorze, nie przy pierwszym
requestcie.

## Przepływ pojedynczego runu

1. Utwórz `RunContext` i wiadomości system/user.
2. Wywołaj providera; jedno wywołanie to jeden krok.
3. Jeśli odpowiedź zawiera tool calls, wykonaj preflight całego batcha.
4. Jeżeli dowolny call jest błędny, nie wykonuj żadnego i odeślij repair
   feedback.
5. Jeśli batch jest poprawny, wykonuj narzędzia sekwencyjnie.
6. Kontynuuj aż do finalnego tekstu albo poprawnego final toola.
7. Zakończ sukcesem albo jawnym błędem limitu/protokołu.

## Wewnętrzne modele

Minimalny zestaw obejmuje:

- `GenerationOptions`;
- `SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`;
- `ModelRequest`, `ModelResponse`, `Usage`;
- `ToolSchema`, `ToolCall`, `ToolDefinition`;
- `ProviderCapabilities`;
- `RunContext`.

Preferowane są małe dataclasses i protokoły zamiast głębokiego drzewa klas.

## Kierunek zależności

`agent.py` może zależeć od spec loadera, registry i runtime'u. Runtime zależy od
znormalizowanych wiadomości, provider protocol oraz tool systemu. Adaptery
zależą od kontraktów core, ale core nie zależy od konkretnego SDK.

W szczególności:

- `Agent` nie zawiera `if provider == ...`;
- tool system nie importuje adapterów;
- built-in tools nie znają modelu ani providera;
- tracing obserwuje zdarzenia, ale nie steruje pętlą.

## Proponowany układ pakietu

```text
src/moiryx/
├── __init__.py
├── agent.py
├── runtime.py
├── config.py
├── agent_spec.py
├── messages.py
├── models.py
├── model_registry.py
├── errors.py
├── tracing.py
├── output/
├── tools/
│   └── builtin/
└── providers/
```

Testy dzielimy na unit, testy adapterów z mock transportem oraz opcjonalne testy
live oznaczone markerem `integration`.
