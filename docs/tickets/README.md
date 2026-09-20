# Backlog implementacyjny v0.1

Backlog jest ułożony według epików zgodnych z [roadmapą](../roadmap.md).
Priorytet `Must` oznacza zakres wymagany do alpha. Rozmiary są względne:
`S` — mały, `M` — średni, `L` — duży; ticket `L` powinien zostać ponownie
oceniony po doprecyzowaniu adaptera, ale nadal ma jeden weryfikowalny rezultat.

Wspólne Definition of Done dla każdego ticketu:

- implementacja i testy adekwatne do ryzyka;
- `ruff check` oraz type checker przechodzą dla zmienionego kodu;
- publiczne błędy są konkretne i nie ujawniają sekretów;
- dokumentacja lub przykłady są aktualne, jeśli zmienia się zachowanie;
- brak niepowiązanej zmiany publicznego API.

## E0 — fundament projektu

### MRYX-001 — Utworzyć package skeleton

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** brak

Zakres: `pyproject.toml`, layout `src/moiryx`, `tests`, minimalny
`__init__.py` i konfiguracja Python 3.11+.

Akceptacja:

- editable install oraz import `moiryx` działają;
- publiczne placeholdery `Agent` i `tool` są eksportowane bez dodatkowych
  symboli core;
- wheel i sdist mogą zostać zbudowane.

### MRYX-002 — Skonfigurować quality toolchain

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-001

Akceptacja:

- pytest z async support, ruff i wybrany type checker mają wersjonowaną
  konfigurację;
- pojedyncze komendy lokalne wykonują wszystkie trzy bramki;
- test smoke jest uruchamiany bez sieci.

### MRYX-003 — Zdefiniować taksonomię wyjątków

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-001

Akceptacja:

- wyjątki ze specyfikacji dziedziczą po `MoiryxError`;
- komunikaty mogą nieść agent/model/provider/run context;
- test potwierdza publiczny import bazowego błędu tylko wtedy, gdy zostanie
  świadomie uznany za publiczny; pozostałe internals nie są re-exportowane
  przypadkiem.

### MRYX-004 — Dodać wspólne modele danych

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-001

Akceptacja:

- istnieją typed modele generation, messages, usage, request/response, tool call
  i capabilities;
- raw provider payload jest opcjonalny i nie wpływa na normalny przepływ;
- modele nie importują SDK providerów.

## E1 — konfiguracja i registry

### MRYX-101 — Zaimplementować odkrywanie `moiryx.yaml`

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-003

Akceptacja:

- `MOIRYX_CONFIG` ma pierwszeństwo przed `./moiryx.yaml`;
- brak pliku daje `ConfigurationError` z przeszukanymi lokalizacjami;
- config można cachować i jawnie resetować w testach.

### MRYX-102 — Zaimplementować rekurencyjną interpolację env

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-101

Akceptacja:

- stringi w zagnieżdżonych dict/list są interpolowane;
- brak zmiennej wskazuje jej nazwę bez ujawniania innych sekretów;
- literalne wartości pozostają bez zmian.

### MRYX-103 — Zwalidować sekcje providerów i runtime

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-101, MRYX-102, MRYX-004

Akceptacja:

- nieznany provider type i niepoprawne typy ustawień są odrzucane;
- retry, timeouty, workspace oraz output limit mają sensowne defaulty i
  ograniczenia;
- reprezentacja obiektu config redaguje klucze i nagłówki autoryzacji.

### MRYX-104 — Zaimplementować ModelRegistry

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-103

Akceptacja:

- alias zwraca provider alias, niezmieniony model ID, generation i
  provider_options;
- unknown alias daje `UnknownModelError`;
- wskazanie nieistniejącego providera jest wykrywane podczas ładowania.

### MRYX-105 — Zaimplementować merge generation options

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-104

Akceptacja:

- priorytet to runtime → model → agent;
- wspierane są `temperature`, `max_tokens`, `top_p` i `seed`;
- nieznane klucze nie są ignorowane.

### MRYX-106 — Zaimplementować ProviderRegistry i factory

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-103, MRYX-004

Akceptacja:

- factory mapuje jawne type na adapter;
- unknown type daje czytelny `ConfigurationError`;
- instancje klientów mogą być cachowane per alias i zamykane bez wpływu na
  publiczne API.

## E2 — definicja agenta

### MRYX-201 — Sparsować Markdown z YAML frontmatter

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-003, MRYX-004

Akceptacja:

- body po frontmatter pozostaje niezmienioną instrukcją;
- name domyślnie pochodzi ze stemu pliku;
- model, tools, max_steps i generation mają walidację typów;
- błędny lub brakujący model daje `AgentDefinitionError`.

### MRYX-202 — Ładować Pydantic output model

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-201

Akceptacja:

- format `module.path:ClassName` jest importowany;
- brak modułu/klasy oraz typ inny niż `BaseModel` mają błąd z agent path;
- nested model i constraints zachowują się bez dodatkowego codegen.

### MRYX-203 — Zaimplementować eager konstruktor `Agent`

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-104, MRYX-105, MRYX-106, MRYX-201, MRYX-202, MRYX-302

Akceptacja:

- sygnatura publiczna to wyłącznie `Agent(agent_file)`;
- model, provider, tools, output i capabilities rozwiązują się przed runem;
- nieznany tool/model/provider kończy inicjalizację konkretnym błędem;
- obiekt nie przechowuje mutable run state.

## E3 — custom tools, executor i repair

### MRYX-301 — Zaimplementować ToolRegistry i `@tool`

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-003, MRYX-004

Akceptacja:

- nazwa pochodzi z `__name__`;
- dekorator bez argumentów rejestruje metadata `__moiryx_tool__`;
- funkcja pozostaje bezpośrednio wywoływalna;
- duplikat i zarezerwowana nazwa są odrzucane.

### MRYX-302 — Generować schema i opisy toola

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-301

Akceptacja:

- dynamiczny Pydantic input model zachowuje required/default i wspierane typy;
- input model ma politykę extra fields `forbid`;
- summary oraz argument descriptions pochodzą z docstringa;
- brak adnotacji, `*args` i `**kwargs` daje `ToolDefinitionError`;
- testy pokrywają Optional, Literal, Enum, list i nested model.

### MRYX-303 — Zaimplementować ToolExecutor

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-302

Akceptacja:

- arguments są walidowane przed call;
- async function jest awaitowana, sync function działa przez thread;
- timeout, validation i execution error są rozróżnione;
- cancellation nie jest połykane.

### MRYX-304 — Zaimplementować serializację i truncation

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-303

Akceptacja:

- str, JSON types, BaseModel, dataclass i None tworzą poprawny tool message;
- return annotation może używać `TypeAdapter`;
- przekroczenie limitu dodaje marker `TRUNCATED BY MOIRYX` z limitem;
- obcięcie nigdy nie jest ciche.

### MRYX-305 — Zaimplementować batch preflight

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-302, MRYX-004

Akceptacja:

- exact lookup, parse/repair i Pydantic validation obejmują każdy call;
- gdy jeden call jest błędny, żaden z batcha nie jest wykonany;
- raw arguments i parse error pozostają dostępne do feedbacku;
- test z mutującym toolem wykazuje brak efektu ubocznego.

### MRYX-306 — Dodać konserwatywne naprawy arguments

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-305

Akceptacja:

- działa JSON string, double encoding i jednoznaczny wrapper;
- Pydantic-safe coercion działa zgodnie z input modelem;
- nieznane pola nie są usuwane, brakujące wartości nie są wymyślane;
- uszkodzony JSON nie jest odzyskiwany regexem.

### MRYX-307 — Dodać repair feedback, fingerprint i budżet

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-305, MRYX-306

Akceptacja:

- unknown tool zawiera available/suggestion, ale niczego nie wykonuje;
- feedback walidacji jest zwięzły i związany z call ID, jeśli możliwe;
- identyczny call nadal zużywa budżet;
- wyczerpanie daje `ToolCallRepairError` z kontekstem i liczbą prób.

## E4 — provider protocol i agent tekstowy

### MRYX-401 — Zdefiniować ProviderAdapter i mapowanie wiadomości

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-004

Akceptacja:

- protocol ma capabilities, async complete i close;
- typy message/request/response są provider-agnostic;
- protocol/repair instruction da się reprezentować bez udawania nowego promptu
  użytkownika.

### MRYX-402 — Zbudować scripted fake provider

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-401

Akceptacja:

- test może ustawić sekwencję text/tool/error responses;
- fake zapisuje requesty do asercji;
- nie wymaga sieci, czasu rzeczywistego ani kluczy.

### MRYX-403 — Zaimplementować pętlę agenta tekstowego

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-203, MRYX-303, MRYX-304, MRYX-305, MRYX-307, MRYX-402

Akceptacja:

- final content pierwszego lub późniejszego kroku zwraca `str`;
- tool messages wracają do następnego requestu we właściwej kolejności;
- response bez content/tools daje `AgentProtocolError`;
- limit kroków daje `MaxStepsExceeded` z run context.

### MRYX-404 — Obsłużyć multiple tool calls sekwencyjnie

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-403

Akceptacja:

- poprawne calle wykonują się w kolejności odpowiedzi;
- preflight kończy się przed pierwszym wykonaniem;
- wszystkie tool messages zachowują ID i nazwę.

### MRYX-405 — Dodać provider retry i klasyfikację błędów

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-401, MRYX-403

Akceptacja:

- timeout/reset/429/wybrane 5xx używają exponential backoff z jitterem;
- oczywiste 4xx nie są retryowane;
- provider retry nie zużywa tool lub structured repair budgetu.

### MRYX-406 — Zapewnić izolację concurrency i cancellation

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-403

Akceptacja:

- każde wywołanie tworzy osobny run ID, messages i counters;
- `asyncio.gather` na jednej instancji nie miesza historii;
- `CancelledError` propaguje się i przerywa możliwe child operations.

## E5 — structured output

### MRYX-501 — Generować synthetic final tool

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-202, MRYX-302, MRYX-401

Akceptacja:

- nazwa to `__moiryx_submit_result`;
- parameter schema pochodzi bezpośrednio z output modelu;
- tool jest dostępny tylko wewnętrznie dla structured agenta;
- użytkownik nie może zarejestrować konfliktującej nazwy.

### MRYX-502 — Zaimplementować structured runtime loop

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-403, MRYX-501

Akceptacja:

- valid final call zwraca konkretny `BaseModel`;
- nested modele, Literal, Enum i constraints są walidowane;
- zwykłe tools mogą poprzedzać final call;
- żaden wrapper/dict nie jest publicznym wynikiem.

### MRYX-503 — Obsłużyć structured protocol violations

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-502, MRYX-307

Akceptacja:

- invalid args, plain text, final+normal oraz multiple final calls uruchamiają
  właściwy corrective feedback;
- budżet jest niezależny od provider i tool repair;
- wyczerpanie daje `StructuredOutputError`;
- JSON w Markdownzie nigdy nie jest automatycznie parsowany.

### MRYX-504 — Dodać capability routing dla structured output

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-106, MRYX-502

Akceptacja:

- tool calling preferuje synthetic final tool;
- native schema działa tylko bez user tools, gdy adapter je gwarantuje;
- niewystarczające capabilities dają `ProviderCapabilityError` przed runem, gdy
  jest to możliwe.

## E6 — OpenAI-compatible

### MRYX-601 — Zaimplementować async request transport

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-401, MRYX-405

Akceptacja:

- base URL, optional key, timeout, model, messages i generation są mapowane;
- wysyłany jest minimalny zestaw parametrów;
- klient używa connection pool i ma cleanup;
- auth data jest redagowana.

### MRYX-602 — Normalizować responses i tool calls

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-601, MRYX-305

Akceptacja:

- text, finish reason i usage są mapowane;
- tool call ID/nazwa/arguments są zachowane;
- malformed arguments tworzą parse error i raw payload zamiast natychmiastowego
  fatal error;
- wiele calli zachowuje kolejność.

### MRYX-603 — Pokryć adapter mock i live smoke tests

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-602, MRYX-503

Akceptacja:

- mock testy obejmują text, tools, structured, usage i błędy;
- optional live marker działa z lokalnym endpointem;
- CI bez endpointu pomija live test bez fałszywego sukcesu core.

## E7 — built-in tools

### MRYX-701 — Zaimplementować wspólny workspace path guard

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-103, MRYX-301

Akceptacja:

- każda ścieżka jest resolve'owana;
- traversal i symlink escape poza root są blokowane;
- `allow_paths_outside_workspace` działa wyłącznie po jawnym ustawieniu.

### MRYX-702 — Dodać `read_file`

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-701, MRYX-304

Akceptacja:

- pełny plik i inclusive zakres linii są udokumentowane i testowane;
- błędny zakres/encoding/path daje czytelny tool error;
- output podlega globalnemu limitowi.

### MRYX-703 — Dodać `list_files`, `glob_files` i `grep`

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-701, MRYX-304

Akceptacja:

- wszystkie operacje respektują root i max results;
- grep używa argument list bez `shell=True`;
- brak `rg` ma udokumentowany błąd albo testowany fallback.

### MRYX-704 — Dodać `write_file`

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-701

Akceptacja:

- polityka tworzenia parent directory jest jawna i testowana;
- zapis poza root jest blokowany przed mutacją;
- sukces zwraca zwięzłe potwierdzenie.

### MRYX-705 — Dodać `edit_file`

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-701

Akceptacja:

- dokładnie jedno dopasowanie jest wymagane;
- zero lub wiele dopasowań nie zmienia pliku;
- test obejmuje atomiczność względem walidacji.

### MRYX-706 — Dodać `shell`

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-303, MRYX-304, MRYX-701

Akceptacja:

- tool jest dostępny tylko po wpisaniu w agent MD;
- cwd pozostaje w workspace zgodnie z polityką;
- timeout kończy proces, stdout/stderr są czytelne i limitowane;
- dokumentacja wyjaśnia ryzyko braku pełnego sandboxa.

## E8 — OpenRouter

### MRYX-801 — Zaimplementować adapter OpenRouter

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-602

Akceptacja:

- domyślny endpoint, API key i custom headers działają;
- adapter deleguje wspólny transport zamiast duplikować runtime;
- model ID ze slashami jest przesyłany bez interpretacji.

### MRYX-802 — Dodać usage/cost i testy OpenRouter

**Priorytet/rozmiar:** Must / S<br>
**Status:** Done<br>
**Zależności:** MRYX-801

Akceptacja:

- dostępne usage/cost są normalizowane;
- brak pola nie jest traktowany jako zero;
- mock testy obejmują redakcję custom headers.

## E9 — Azure OpenAI i Foundry

### MRYX-901 — Zaimplementować adapter Azure OpenAI

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-401, MRYX-503, MRYX-602

Akceptacja:

- endpoint, key, API version i deployment ID są mapowane;
- text/tools/structured i malformed calls mają mock testy;
- Azure SDK objects nie przeciekają do core.

### MRYX-902 — Zaimplementować adapter Azure Foundry

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-901

Akceptacja:

- type pozostaje oddzielny mimo współdzielonego transportu;
- różnice auth i endpoint semantics są zamknięte w adapterze;
- capabilities są jawnie testowane.

### MRYX-903 — Wydzielić extras i test matrix Azure

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-901, MRYX-902

Akceptacja:

- core install nie pobiera Azure SDK;
- extra `azure` instaluje dokładnie potrzebne zależności;
- CI mock matrix pokrywa oba provider types bez credentials.

## E10 — Vertex AI

### MRYX-1001 — Zaimplementować adapter Vertex AI

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-401, MRYX-503

Akceptacja:

- project, location, model, messages i tools są mapowane;
- ADC/service account environment jest użyte bez credentials w config logs;
- responses i usage są normalizowane.

### MRYX-1002 — Dodać Google extra i mock test matrix

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-1001

Akceptacja:

- core install nie pobiera Google SDK;
- extra `google` jest wystarczające dla adaptera;
- text/tools/structured/error mapping działa bez live credentials.

## E11 — tracing, dokumentacja i publikacja

### MRYX-1101 — Dodać standard logging i RunContext events

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-403, MRYX-502

Akceptacja:

- każdy run ma ID, timestamps, model/provider oraz start/end/error;
- poziomy logów odpowiadają dokumentacji;
- failed preflight nie jest logowany jako wykonany tool.

### MRYX-1102 — Dodać opcjonalny JSONL trace

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-1101, MRYX-307

Akceptacja:

- trace powstaje wyłącznie po konfiguracji `trace_dir`;
- wymagane event types oraz run ID są zapisane jako poprawny JSONL;
- równoległe runy nie mieszają plików.

### MRYX-1103 — Zaimplementować centralną redakcję sekretów

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-103, MRYX-1101, MRYX-1102

Akceptacja:

- API keys, Authorization i service-account secrets są zredagowane;
- test przeszukuje log i trace pod kątem sentinel secret;
- raw response jest dostępny tylko w explicit debug mode.

### MRYX-1104 — Napisać README i przykłady użytkownika

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-603, MRYX-703, MRYX-705, MRYX-802

Akceptacja:

- README zaczyna się od UX, nie od diagramu internals;
- przykłady obejmują text, built-in, custom tool, structured output i zmianę
  providera przez YAML;
- wszystkie przykłady używają nazw Moiryx i nie zawierają sekretów.

### MRYX-1105 — Skonfigurować CI i build artefaktów

**Priorytet/rozmiar:** Must / M<br>
**Status:** Done<br>
**Zależności:** MRYX-002, MRYX-903, MRYX-1002

Akceptacja:

- matrix wspieranych wersji Pythona uruchamia test/lint/types;
- wheel i sdist są budowane oraz instalowane w czystym środowisku;
- live provider tests są jawnie opt-in.

### MRYX-1106 — Wykonać dogfood i acceptance suite

**Priorytet/rozmiar:** Must / L<br>
**Status:** Done<br>
**Zależności:** MRYX-1103, MRYX-1104, MRYX-1105

Akceptacja:

- AC1–AC11 przechodzą jako automatyczna suite;
- text, coding/files, nested reviewer i custom integration są sprawdzone;
- ten sam agent działa na dwóch providerach przez zmianę config;
- wyniki i znalezione ograniczenia są zapisane w release notes.

### MRYX-1107 — Przygotować `0.1.0-alpha.1`

**Priorytet/rozmiar:** Must / M<br>
**Status:** In progress<br>
**Zależności:** MRYX-1106

Akceptacja:

- changelog, license, metadata, SemVer i instrukcja instalacji są kompletne;
- nazwa dystrybucji PyPI jest zweryfikowana, import pozostaje `moiryx`;
- nie ma sekretów/prywatnych endpointów w sdist/wheel;
- release checklist z [dokumentu jakości](../06-quality-security-release.md)
  jest podpisana.

## Kolejność pobierania pracy

Pierwszy gotowy zestaw: MRYX-001. Następnie MRYX-002, MRYX-003 i MRYX-004.
Po modelach core można równoleglić config (E1) z ToolRegistry (MRYX-301/302).
Tekstowy runtime zaczyna się dopiero po fake providerze i preflight. Provider
matrix zaczyna się po ustabilizowaniu OpenAI-compatible. Ostatnim elementem
każdej ścieżki jest wspólna acceptance suite, nie osobny ręczny wyjątek.
