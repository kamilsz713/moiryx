# Konfiguracja i definicje agentów

## Odkrywanie konfiguracji

Kolejność jest stała:

1. ścieżka wskazana przez `MOIRYX_CONFIG`;
2. `./moiryx.yaml` względem bieżącego katalogu roboczego.

Po pierwszym poprawnym odczycie konfiguracja może być cachowana. Nie
wprowadzamy w v0.1 łączenia wielu plików ani automatycznego przeszukiwania
katalogów nadrzędnych.

## Minimalny przykład

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://localhost:8080/v1

models:
  reviewer:
    provider: local
    model: qwen

runtime:
  default_max_steps: 20
  provider_retry_attempts: 3
  structured_output_retries: 2
  tool_call_repair_attempts: 2
  tool_timeout_seconds: 60
  workspace_root: .
  allow_paths_outside_workspace: false
  max_tool_output_chars: 50000

logging:
  level: INFO
  trace_dir: .moiryx/runs
  include_raw_response: false
```

## Konfiguracja providerów i modeli

Klucz w `providers` jest aliasem połączenia, a klucz w `models` logiczną nazwą
przeznaczenia. Agent wskazuje wyłącznie alias modelu:

```yaml
providers:
  router:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}

models:
  reasoning_strong:
    provider: router
    model: vendor/model
    generation:
      temperature: 0.2
    provider_options:
      reasoning_effort: high
```

Identyfikator modelu jest nieprzezroczystym stringiem; slash nie ma specjalnego
znaczenia dla `Agent`.

## Interpolacja środowiska

Interpolacja działa rekurencyjnie dla stringów w dictach i listach. Brak
wymaganej zmiennej powoduje `ConfigurationError` zawierający jej nazwę.
Sekrety pozostają zredagowane w `repr`, logach i trace.

## Logowanie i diagnostyka

`logging.level` ustawia próg standardowego loggera `moiryx.run`. INFO obejmuje
start i koniec runu, DEBUG kroki modelu i poprawne wykonania tooli, WARNING
retry/repair/błędy tooli, a ERROR końcową porażkę runu.

`trace_dir` jest opcjonalne. Po ustawieniu każdy run zapisuje niezależny
`<trace_dir>/<run-id>/events.jsonl`; brak ustawienia nie tworzy żadnych plików.
`include_raw_response` jest domyślnie `false`. Jego jawne włączenie dodaje raw
response wyłącznie do zdarzenia diagnostycznego i nadal stosuje centralną
redakcję sekretów.

## Scalanie generation options

Kolejność od najniższego do najwyższego priorytetu:

1. runtime defaults;
2. `models.<alias>.generation`;
3. `generation` z pliku agenta.

Wspierany wspólny zestaw v0.1 to `temperature`, `max_tokens`, `top_p` i `seed`.
Nieznane opcje nie mogą być ignorowane po cichu. Opcje specyficzne dla
providera należą do jawnego `provider_options` modelu.

## Moduły z custom tools

`tool_modules` zawiera jawne ścieżki importu. Runtime importuje je przed
rozwiązywaniem nazw narzędzi. Nie skanuje filesystemu:

```yaml
tool_modules:
  - my_project.tools.repository
  - my_project.tools.release
```

## Format pliku agenta

Plik składa się z YAML frontmatter oraz body Markdown będącego system promptem:

```markdown
---
name: reviewer
model: reasoning_strong
tools:
  - read_file
  - grep
output: my_project.schemas.review:ReviewOutput
max_steps: 20
generation:
  temperature: 0.2
---

# Role

You are a strict technical reviewer.
```

### Pola

| Pole | Wymagane | Semantyka |
|---|---:|---|
| `model` | tak | logiczny alias z `models` |
| `name` | nie | nazwa do logów; domyślnie stem pliku |
| `tools` | nie | jawna lista nazw; brak oznacza zero user tools |
| `output` | nie | `module.path:ClassName` dziedziczące po `BaseModel` |
| `max_steps` | nie | dodatni int; inaczej default runtime |
| `generation` | nie | nadpisania wspólnych opcji generacji |

## Walidacja w konstruktorze

`Agent("agents/reviewer.md")` ma od razu wykryć:

- brak pliku lub błędny YAML;
- brak/błędny/nieznany model alias;
- brak wskazanego providera;
- `tools` inne niż lista stringów lub nieznane nazwy;
- błędną ścieżkę output, brak klasy lub klasę inną niż `BaseModel`;
- niedodatni `max_steps`;
- błędne typy lub nieznane generation options;
- brak wymaganych capabilities providera.

Ta walidacja zapobiega częściowo rozpoczętym runom i upraszcza obsługę błędów w
aplikacji.
