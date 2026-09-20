# Roadmapa v0.1

Roadmapa prowadzi od deterministycznego core do adapterów i publikacji. Numery
ticketów odsyłają do [backlogu](tickets/README.md). Rozmiary w backlogu są
względne i służą do dzielenia pracy, nie są zobowiązaniem kalendarzowym.

## Zasady realizacji

- Najpierw budujemy i testujemy kontrakty bez prawdziwego providera.
- Każdy milestone kończy się działającym, możliwym do zademonstrowania
  przyrostem.
- Adapter nie może wymuszać zmian w publicznym API ani core.
- Bezpieczeństwo repair i structured output jest częścią funkcjonalności, nie
  etapem polish.
- Ticket zależny nie wchodzi do `In progress` przed domknięciem zależności
  kontraktowej.

## M0 — kontrakt i repozytorium

**Zakres:** MRYX-001–MRYX-004.

Rezultat: projekt ma package layout, narzędzia jakości, kanoniczne nazwy i
podstawowe typy/błędy.

Brama:

- `from moiryx import Agent, tool` jest jedynym planowanym eksportem użytkowym;
- testy, lint i type checking uruchamiają się lokalnie;
- w plikach projektu nie występują stare identyfikatory nazwy.

## M1 — konfiguracja i definicje agentów

**Zakres:** MRYX-101–MRYX-106 oraz MRYX-201–MRYX-203.

Rezultat: `Agent("agent.md")` wykonuje pełną walidację inicjalizacji na fake
registry, bez requestu do modelu.

Brama:

- odkrywanie `MOIRYX_CONFIG` / `./moiryx.yaml` działa;
- env interpolation i redakcja sekretów mają testy;
- alias modelu, provider, tools i output model są rozwiązywane eager;
- generation options scalają się w ustalonej kolejności.

## M2 — tool system

**Zakres:** MRYX-301–MRYX-307.

Rezultat: custom sync/async tools rejestrują się, generują schema, walidują
argumenty i wykonują się z timeoutem. Preflight blokuje cały błędny batch.

Brama:

- udekorowana funkcja nadal działa jako zwykła funkcja;
- schema odzwierciedla typy, defaults i docstring;
- repair wykonuje wyłącznie dozwolone transformacje;
- test mutującego toola dowodzi, że częściowy batch nie został wykonany.

## M3 — tekstowy runtime na fake providerze

**Zakres:** MRYX-401–MRYX-406.

Rezultat: deterministyczny agent tekstowy obsługuje zero/wiele tool calli,
retry, limity, cancellation i współbieżność.

Brama:

- AC1, AC2, AC3, AC6, AC9 i tekstowa część AC11 przechodzą;
- każde wywołanie posiada oddzielny `RunContext`;
- brak final contentu kończy się jawnym błędem protokołu.

## M4 — structured output

**Zakres:** MRYX-501–MRYX-504.

Rezultat: agent zwraca konkretną instancję Pydantic przez synthetic final tool
lub pewny native schema path.

Brama:

- AC4, AC5 i AC10 przechodzą;
- final tool + zwykły tool oraz multiple final calls są odrzucane;
- wyczerpanie retry kończy się `StructuredOutputError`;
- nie istnieje fallback parsujący JSON z tekstu.

To jest feature-complete core i pierwsza sensowna granica wewnętrznego preview.

## M5 — OpenAI-compatible i built-in tools

**Zakres:** MRYX-601–MRYX-603 oraz MRYX-701–MRYX-706.

Rezultat: Moiryx działa z lokalnym endpointem i ma kompletny minimalny zestaw
narzędzi workspace.

Brama:

- mock transport pokrywa text/tool/malformed/usage/retry;
- opcjonalny live smoke działa z lokalnym serwerem;
- traversal poza workspace jest blokowany;
- write/edit/shell mają testy timeoutu, błędu i output limit.

## M6 — provider matrix

**Zakres:** MRYX-801–MRYX-802, MRYX-901–MRYX-903, MRYX-1001–MRYX-1002.

Rezultat: wszystkie deklarowane provider types mają adapter, mock testy i
extras dependency.

Brama:

- zachowanie core jest wspólne i nie zostało skopiowane do adapterów;
- slash-containing model IDs zachowują się bez zmian;
- capabilities i błędy retryable są mapowane spójnie;
- CI nadal nie wymaga prawdziwych credentials.

## M7 — obserwowalność, dokumentacja i alpha

**Zakres:** MRYX-1101–MRYX-1107.

Rezultat: użytkownik może zainstalować artefakt, uruchomić przykłady,
zdiagnozować run i przeczytać ograniczenia bezpieczeństwa.

Brama:

- wszystkie AC1–AC11 są śledzone w [macierzy](traceability.md);
- logi i JSONL trace nie ujawniają sekretów;
- wheel/sdist przechodzą clean-install smoke test;
- co najmniej dwa providery oraz wszystkie scenariusze dogfood są zaliczone;
- publikacja jest oznaczona `0.1.0-alpha.1`.

## Krytyczna ścieżka

```text
MRYX-001
  -> konfiguracja i modele
  -> AgentSpec / eager Agent
  -> tool core i preflight
  -> normalized provider protocol + fake
  -> text loop
  -> structured output
  -> OpenAI-compatible
  -> built-ins + dogfood
  -> packaging / alpha
```

OpenRouter, Azure/Foundry i Vertex AI mogą rozpocząć się po ustabilizowaniu
kontraktu adaptera oraz OpenAI-compatible mappingu, równolegle względem siebie.

## Świadomie odłożone po v0.1

Streaming, Session, multimodal, permissions/approvals, MCP, remote tools,
fallback routing, budgets, context policies, replay, OpenTelemetry, cache,
parallel tool execution, codegen i sandbox container pozostają poza milestone
M7. Dodanie ich do bieżącego zakresu wymaga osobnej decyzji produktowej.
