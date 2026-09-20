# Moiryx

Moiryx pozwala opisać agenta w Markdownzie, wybrać model przez YAML i uruchomić
go jak zwykły obiekt async w Pythonie. Ten sam agent może przejść z lokalnego
`llama-server` na OpenRouter, Azure lub Vertex AI bez zmian w jego kodzie.

Projekt jest obecnie w fazie alpha. Publiczny kontrakt użytkowy jest celowo
mały: `Agent`, `@tool` oraz konfiguracja `moiryx.yaml`.

## Instalacja

Wydanie `0.1.0a1` jest przygotowywane i nie zostało jeszcze opublikowane na
PyPI. Aktualnie instaluj projekt z katalogu źródłowego:

```bash
python -m pip install -e .
```

Po publikacji będzie można użyć `python -m pip install moiryx==0.1.0a1`.

Dla Vertex AI zainstaluj opcjonalny Google Gen AI SDK:

```bash
pip install "moiryx[google]"
```

## Pierwszy agent z lokalnym llama-server

Uruchom endpoint zgodny z OpenAI API, a następnie utwórz `moiryx.yaml`:

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8080/v1

models:
  local_chat:
    provider: local
    model: local-model
```

Zapisz definicję w `agents/chat.md`:

```markdown
---
model: local_chat
---
Odpowiadaj konkretnie i zaznaczaj niepewność.
```

Wywołanie agenta jest asynchroniczne:

```python
import asyncio

from moiryx import Agent


async def main() -> None:
    agent = Agent("agents/chat.md")
    answer = await agent("Wyjaśnij różnicę między procesem i wątkiem.")
    print(answer)


asyncio.run(main())
```

Jeśli tworzysz wiele agentów w dłużej działającym procesie, po użyciu wywołaj
`await agent.aclose()` albo użyj `async with Agent(...)`. To zwalnia połączenia
HTTP providera; prosty skrypt jednorazowy nie wymaga dodatkowej obsługi.

## Built-in tools

Narzędzia nie są udostępniane automatycznie. Agent dostaje wyłącznie nazwy
wpisane w jego frontmatter:

```markdown
---
model: local_chat
tools: [read_file, list_files, grep]
---
Analizuj pliki w workspace i podawaj ścieżki użytych źródeł.
```

Dostępne built-ins to `read_file`, `list_files`, `glob_files`, `grep`,
`write_file`, `edit_file` i `shell`. Operacje plikowe pozostają domyślnie w
`runtime.workspace_root`.

> `shell` nie jest pełnym sandboxem. Udostępniaj go tylko agentom i w
> środowiskach, którym ufasz.

## Własne narzędzie

```python
from moiryx import tool


@tool
def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())
```

Dodaj moduł do konfiguracji i nazwę toola do agenta:

```yaml
tool_modules: [my_tools]
```

```markdown
---
model: local_chat
tools: [word_count]
---
Używaj narzędzia do dokładnego liczenia słów.
```

## Structured output

Model wyniku jest zwykłym modelem Pydantic:

```python
from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    accepted: bool
    score: float = Field(ge=0, le=1)
    findings: list[str]
```

Agent wskazuje go przez `moduł:Klasa`:

```markdown
---
model: local_chat
output: review_models:ReviewResult
---
Oceń zmianę i zwróć wynik zgodny ze schematem.
```

`await agent(...)` zwróci bezpośrednio instancję `ReviewResult`. Moiryx nie
uznaje JSON-u ukrytego w zwykłym tekście za poprawny structured output.

## Zmiana providera przez YAML

Kod i plik agenta mogą pozostać bez zmian. Wystarczy przepiąć alias modelu:

```yaml
providers:
  router:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}
    headers:
      HTTP-Referer: https://example.invalid
      X-OpenRouter-Title: Moiryx example

models:
  local_chat:
    provider: router
    model: anthropic/claude-sonnet-4.5
```

Obsługiwane typy providerów:

- `openai_compatible` — llama-server, vLLM, SGLang i podobne endpointy;
- `openrouter`;
- `azure_openai`;
- `azure_foundry`;
- `vertex_ai` — przez ADC lub service account environment.

## Logowanie i trace

```yaml
logging:
  level: INFO
  trace_dir: .moiryx/runs
  include_raw_response: false
```

Każdy run ma własny identyfikator i opcjonalny plik
`.moiryx/runs/<run-id>/events.jsonl`. Raw response jest wyłączony domyślnie;
jego jawne włączenie nadal stosuje centralną redakcję kluczy, tokenów i
credentials.

## Pełne przykłady i rozwój

Gotowe pliki znajdują się w [`examples/`](examples/). Dokumentacja projektu,
architektura, ograniczenia bezpieczeństwa i backlog są w [`docs/`](docs/).

Lokalne bramy jakości:

```bash
python scripts/check.py
python -m pytest -m acceptance -q
python -m build
python scripts/audit_artifacts.py dist
```

Zestaw `acceptance` ćwiczy publiczne API na deterministycznych providerach
testowych, bez sieci i kluczy. Obejmuje też przykładowych agentów tekstowego,
edycji pliku, własnego narzędzia i zagnieżdżonego review.

Test live lokalnego endpointu jest jawnie opt-in przez zmienne
`MOIRYX_OPENAI_COMPATIBLE_LIVE_URL` i `MOIRYX_OPENAI_COMPATIBLE_LIVE_MODEL`.
