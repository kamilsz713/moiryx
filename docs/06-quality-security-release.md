# Jakość, bezpieczeństwo i wydanie

## Taksonomia błędów

Wszystkie publiczne błędy dziedziczą po `MoiryxError`. Minimalny zestaw:

- `ConfigurationError`, `AgentDefinitionError`;
- `ProviderNotFoundError`, `UnknownModelError`,
  `ProviderCapabilityError`, `ProviderRequestError`;
- `UnknownToolError`, `DuplicateToolError`, `ToolDefinitionError`,
  `ToolCallParseError`, `ToolCallRepairError`;
- `StructuredOutputError`, `AgentProtocolError`, `MaxStepsExceeded`.

Komunikaty zawierają kontekst operacyjny — nazwę agenta, alias modelu,
providera, run ID i limit/próby, gdy jest to istotne — ale nie sekrety.

## Logowanie i trace

Standardowe `logging`:

- INFO: start i koniec runu, model, liczba kroków;
- DEBUG: metadane requestu, tool calle i walidacja;
- WARNING: retry oraz błędy tooli;
- ERROR: fatal run failure.

Opcjonalny `.moiryx/runs/<run-id>/events.jsonl` zapisuje:

- `run_started`, `model_requested`, `model_responded`;
- `tool_requested`, `tool_completed`, `tool_failed`;
- `tool_call_repair_started`, `tool_call_repaired`,
  `tool_call_repair_failed`;
- `structured_output_validated`;
- `run_completed`, `run_failed`.

Każdy event ma timestamp i run ID. Nieudany, niewykonany call nie może być
zapisany jako `tool_completed`.

Trace jest wyłączony, dopóki użytkownik nie ustawi `logging.trace_dir`. Każdy
run zapisuje oddzielny `<run-id>/events.jsonl`, dlatego równoległe wywołania nie
mieszają historii. Raw odpowiedź providera wymaga dodatkowo jawnego
`logging.include_raw_response: true`; nie zmienia to zasad redakcji.

## Bezpieczeństwo

- API keys, Authorization headers i credentials nigdy nie trafiają do logów,
  trace ani `repr` konfiguracji.
- Centralna redakcja rozpoznaje `SecretStr`, nazwy pól związane z kluczami,
  tokenami i service accounts oraz znane wartości sekretów osadzone w tekście.
- Filesystem tools pozostają w `workspace_root`, chyba że użytkownik jawnie
  zmieni politykę.
- Preflight całego batcha chroni przed częściowym wykonaniem.
- Runtime nie zgaduje nazw ani argumentów narzędzi.
- Built-in tools nie są automatycznie wystawiane modelowi.
- Subprocess unika `shell=True`, ma timeout i limit outputu.
- Mutujące narzędzia mają czytelne logi.

V0.1 nie obiecuje pełnego sandboxa. Dokumentacja musi jasno zaznaczać, że jawne
udostępnienie `shell` daje modelowi potężną lokalną możliwość.

## Quality gates

Każdy merge do głównej gałęzi powinien przechodzić:

1. `pytest`;
2. `ruff check` i ustalone formatowanie;
3. `mypy` albo `pyright` w uzgodnionym strictness dla `src/moiryx`;
4. build wheel i sdist;
5. test importu artefaktu w czystym środowisku;
6. test publicznego przykładu README.

Testy jednostkowe nie wymagają sieci ani kluczy. Fake/scripted provider jest
obowiązkowy, bo umożliwia deterministyczne testy pętli.

## Krytyczne scenariusze regresji

- final text w pierwszym kroku;
- tool → final text, kilka tooli i tool error → poprawka;
- pełny batch preflight przed mutacją;
- wyczerpanie step oraz repair budgets;
- nested structured output;
- plain JSON text nie jest structured sukcesem;
- final tool nie współwystępuje z normalnym toolem;
- dwie równoległe sesje jednej instancji nie dzielą historii;
- model ID ze slashami pozostaje bez zmian;
- sekrety są zredagowane.

## Zależności i extras

Core: Python 3.11+, Pydantic 2, PyYAML, httpx i lekki parser docstringów.
Provider SDK są opcjonalnymi extras, aby użytkownik lokalnego endpointu nie
instalował Google/Azure.

Dostępne grupy to `google`, `azure`, `all` oraz `dev`. `google` instaluje
`google-genai`; adaptery Azure używają wspólnego HTTPX, więc ich stabilny extra
nie dodaje zbędnego SDK. Macierz CI instaluje extras i sprawdza Python 3.11/3.12.

## Release gates 0.1.0-alpha.1

Przed pierwszą publikacją:

- cały backlog `Must` jest ukończony;
- wszystkie AC1–AC11 mają automatyczne testy;
- przykłady text, tools, structured output i dwa providery zostały
  dogfoodowane;
- malformed call oraz concurrency zostały sprawdzone end-to-end;
- dokumentacja publicznych wyjątków i konfiguracji jest kompletna;
- `CHANGELOG.md`, licencja, metadata, SemVer oraz CI publikacyjne są gotowe;
- wheel i sdist instalują się bez warningów;
- brak realnych sekretów, prywatnych endpointów i surowych payloadów w
  artefaktach;
- dostępność nazwy dystrybucji na PyPI została sprawdzona, przy zachowaniu
  importu `moiryx`.

Stabilność API nie jest obiecywana przed dogfoodingiem, ale każda zmiana
`Agent("...")`, `await agent(...)` lub `@tool` wymaga świadomej decyzji i wpisu
w changelogu.
