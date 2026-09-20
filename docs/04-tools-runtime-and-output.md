# Tools, runtime i structured output

## Publiczne API toola

Custom tool jest zwykłą funkcją:

```python
from moiryx import tool

@tool
async def get_build_status(build_id: int) -> BuildStatus:
    """
    Return current CI build status.

    Args:
        build_id: Unique identifier of the build.
    """
    ...
```

Dekorator zachowuje normalne wywołanie funkcji, rejestruje definicję pod
`func.__name__` oraz przypisuje metadane `__moiryx_tool__`. Nie przyjmuje
argumentu z nazwą.

## Introspekcja i schema

Przy rejestracji runtime:

1. odczytuje `inspect.signature()` i `typing.get_type_hints()`;
2. odrzuca brakujące adnotacje, `*args` oraz `**kwargs`;
3. parsuje summary i opisy parametrów z docstringa;
4. buduje dynamiczny model Pydantic przez `create_model()`;
5. generuje JSON Schema przez `model_json_schema()`;
6. przygotowuje `TypeAdapter` do serializacji wyniku.

Minimalnie wspieramy typy proste, Optional/union z `None`, listy, słowniki,
`Literal`, Enum, nested `BaseModel` i proste dataclasses obsługiwane przez
Pydantic. Dynamiczny input model zabrania nadmiarowych pól, aby runtime nie
ignorował argumentów, których tool nie deklaruje.

Duplikat nazwy jest błędem. Nazwa `__moiryx_submit_result` jest zarezerwowana.

## Walidacja i wykonanie

Argumenty przechodzą przez input model przed wywołaniem funkcji. Sync tools są
uruchamiane przez `asyncio.to_thread()`, async tools są awaitowane. Każdy call
ma timeout.

Wynik jest serializowany do tekstowego `ToolMessage.content`. Wspierane są
stringi, typy JSON, Pydantic, dataclasses oraz `None`. Przekroczenie
`max_tool_output_chars` daje jawny marker:

```text
...[TRUNCATED BY MOIRYX: original output exceeded 50000 chars]
```

Rozróżniamy walidację argumentów, wyjątek funkcji oraz timeout. Błędy wykonania
są domyślnie zwracane modelowi bez pełnego stack trace; lokalny log może
zachować wyjątek do diagnostyki.

## Preflight i repair

Cały batch przechodzi kolejno:

```text
normalize
  -> exact tool-name lookup
  -> conservative argument parsing/repair
  -> Pydantic validation
  -> wszystkie poprawne?
       tak: wykonaj sekwencyjnie
       nie: wykonaj zero, odeślij feedback
```

Dozwolone naprawy są deterministyczne:

- trim whitespace w nazwie;
- zwykły parse JSON stringa;
- jednokrotne rozpakowanie double-encoded JSON;
- rozpakowanie oczywistego wrappera `arguments` tylko przy jednoznacznym
  dopasowaniu schema;
- standardowa coercion Pydantic, jeżeli model wejściowy ją dopuszcza.

Niedozwolone są fuzzy wykonanie podobnego toola, dopowiadanie brakujących
wartości, semantyczna zmiana danych, silent drop nieznanych pól i regexowe
wydobywanie domniemanych argumentów.

Nieznana nazwa może dostać sugestię w feedbacku, ale model musi ponowić call.
Powtarzany błędny call zużywa `tool_call_repair_attempts`. Wyczerpanie budżetu
daje `ToolCallRepairError`.

Feedback korzysta z `ToolMessage`, gdy dostępny jest call ID. Przy braku
poprawnego ID runtime używa wewnętrznego `RepairMessage`, który nie jest nowym
promptem użytkownika.

## Built-in tools v0.1

Agent dostaje tylko nazwy wymienione w swoim Markdownzie.

| Kategoria | Tools |
|---|---|
| odczyt | `read_file`, `list_files`, `glob_files`, `grep` |
| zapis | `write_file`, `edit_file` |
| proces | `shell` |

Definicje built-inów są wiązane z konfiguracją przy tworzeniu agenta. Nie są
rejestrowane jako custom tools ani automatycznie przekazywane modelowi.

Filesystem resolve'uje root oraz każdą ścieżkę, blokuje traversal i wyjście
przez symlink/junction. Dostęp poza rootem wymaga jawnego
`allow_paths_outside_workspace: true`.

- `read_file` czyta UTF-8; bez zakresu zachowuje pełną treść, a `start_line` i
  `end_line` są one-based oraz inclusive;
- `list_files` pokazuje bez rekurencji posortowane dzieci katalogu;
- `glob_files` przyjmuje względny pattern bez `..` i zwraca wyłącznie pliki;
- `grep` używa `rg` przez argument list z `shell=False`; gdy `rg` nie jest
  dostępny, używa deterministycznego fallbacku Python dla plików UTF-8;
- `write_file` tworzy katalogi nadrzędne i wykonuje atomowy zapis przez plik
  tymczasowy w katalogu docelowym;
- `edit_file` modyfikuje atomowo tylko wtedy, gdy `old_text` występuje dokładnie
  raz; zero lub wiele dopasowań nie zmienia pliku.

Wyniki listowania i grepa respektują `max_results`, a każdy wynik toola nadal
podlega globalnemu `max_tool_output_chars`.

`shell` jest dostępny tylko po jawnym dodaniu do agent MD. Zawsze startuje w
canonical `workspace_root`, raportuje exit code oraz osobne stdout/stderr, a po
timeout lub anulowaniu kończy drzewo procesu. To narzędzie **nie jest pełnym
sandboxem bezpieczeństwa**: sama powłoka może odczytywać i modyfikować zasoby
dostępne dla procesu użytkownika. Należy udostępniać je wyłącznie zaufanym
agentom.

## Pętla agenta tekstowego

Każdy response providera zwiększa licznik kroków. Tool calls uruchamiają
preflight i wykonanie, a odpowiedź bez tool calli musi zawierać finalny content.
Zwracany jest wyłącznie ten ostatni content. Brak contentu oraz tool calli to
`AgentProtocolError`. Osiągnięcie limitu to `MaxStepsExceeded`, nigdy częściowy
sukces.

## Structured output

Klasa wskazana przez `output` jest źródłem JSON Schema oraz walidacji końcowej.
Preferowana strategia:

1. dodaj wewnętrzny `__moiryx_submit_result` z parameter schema output modelu;
2. pozwól agentowi używać normalnych tooli;
3. przy finalnym callu zwaliduj arguments przez
   `OutputModel.model_validate(...)`;
4. zwróć wynik bez wrappera.

Final tool nie może wystąpić z normalnym toolem ani więcej niż raz w jednym
response. Plain text nie jest parsowany jako JSON; uruchamia corrective round.
Problemy te zużywają osobny `structured_output_retries`.

Polityka capabilities:

1. tool calling dostępny — synthetic final tool;
2. bez tool calling, ale z native structured output i bez user tools — native
   schema;
3. brak gwarantowanego mechanizmu — `ProviderCapabilityError`.

## Retry i cancellation

`provider_retry_attempts` dotyczy wyłącznie przejściowych timeoutów, resetów,
HTTP 429 i wybranych 5xx; używa exponential backoff z jitterem. Błędny klucz,
model lub request nie są retryowane automatycznie.

`CancelledError` ma propagować się bez opakowania. Runtime próbuje anulować
tool/subprocess, ale nie łapie `BaseException`.
