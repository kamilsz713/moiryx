# Moiryx — specyfikacja implementacyjna

> **Decyzja nazewnicza:** `moiryx` jest finalną nazwą biblioteki i pakietu.
> Względem dokumentu wejściowego zmieniono także powiązane identyfikatory:
> `moiryx.yaml`, `MOIRYX_CONFIG`, `.moiryx/`,
> `__moiryx_submit_result` i `MoiryxError`.
>
> **Status:** projekt v0.1 / dokument implementacyjny
>
> **Język:** Python 3.11+
>
> **Cel:** lekka biblioteka do budowania własnych flow agentowych w zwykłym Pythonie. Biblioteka ma ukrywać boilerplate związany z providerami LLM, tool callingiem, walidacją argumentów narzędzi, agent loopem i structured output, ale **nie** ma narzucać żadnego systemu workflow, graphów, chainów ani orkiestratora.

---

## 0. Najważniejsze decyzje — przeczytać przed implementacją

To są decyzje kontraktowe. Implementacja nie powinna ich „ulepszać” przez zmianę publicznego API.

1. **Agent jest callable.**

   ```python
   agent = Agent("agents/reviewer.md")
   result = await agent("Przeanalizuj ten problem")
   ```

   Nie ma podstawowego API `agent.run()`, `agent.invoke()`, `agent.execute()` itd.

2. **Konstruktor `Agent` przyjmuje wyłącznie plik definicji agenta.**

   ```python
   Agent("path/to/agent.md")
   ```

   Nie przekazujemy w konstruktorze:

   - providera,
   - modelu,
   - tools,
   - instructions,
   - output schema,
   - provider clienta,
   - temperature,
   - workflow,
   - pamięci.

   Agent `.md` wskazuje **logiczny alias modelu**, a globalny `moiryx.yaml` mapuje alias modelu na konkretny provider i model/deployment. Pozostałe elementy pochodzą z pliku agenta lub globalnej konfiguracji.

3. **Flow/orchestracja to zwykły Python.**

   Biblioteka NIE implementuje DSL-a do graphów, node'ów, chainów, crew, workflow itd.

   ```python
   plan = await planner(problem)
   review = await reviewer(plan.model_dump_json())

   if review.score < 0.8:
       plan = await planner(f"Popraw plan na podstawie uwag: {review.issues}")

   implementation = await coder(plan.model_dump_json())
   ```

4. **Definicja agenta siedzi w pliku Markdown z YAML frontmatter.**

   Plik `.md` definiuje:

   - logiczny alias modelu,
   - instrukcje/system prompt,
   - dostępne narzędzia,
   - opcjonalny Pydantic output model,
   - limit kroków,
   - podstawowe opcje generacji.

5. **Structured output to Pydantic, nie dict.**

   Jeżeli agent ma zadeklarowany model wyjściowy:

   ```python
   review = await reviewer(prompt)

   review.score
   review.decision
   review.issues
   ```

   Nie:

   ```python
   review["score"]
   result.output.score
   result.data["score"]
   ```

   Zwrócony obiekt ma być **bezpośrednio instancją konkretnej klasy `pydantic.BaseModel`**.

6. **Agent bez output modelu zwraca `str`.**

   Jeżeli w definicji agenta nie ma `output`, wynikiem jest tekst ostatniej finalnej wiadomości asystenta po zakończeniu całego agent loopa.

7. **Nie parsujemy „JSON-a wyplutego w tekście”.**

   Structured output musi korzystać z mechanizmu, który pozwala faktycznie zweryfikować schemat: final tool / native structured output. Jeśli provider nie potrafi zagwarantować tego kontraktu, ma być błąd capability zamiast heurystycznego wycinania JSON-a z Markdownu.

8. **Custom tool definiuje się samym dekoratorem `@tool`.**

   ```python
   @tool
   async def get_build_status(build_id: int) -> BuildStatus:
       """
       Return current CI build status.

       Args:
           build_id: Unique identifier of the build.
       """
       ...
   ```

   Nazwa toola jest nazwą funkcji. Dekorator nie przyjmuje nazwy.

9. **Metadane toola wynikają z funkcji.**

   Biblioteka wyciąga automatycznie:

   - nazwę z `__name__`,
   - opis z docstringa,
   - parametry i ich required/default z sygnatury,
   - typy z type hints,
   - opisy argumentów z docstringa,
   - return type z type hint.

10. **Built-in tools są częścią biblioteki.**

    Built-in oznacza: biblioteka je dostarcza i rejestruje. Agent dostaje tylko te narzędzia, które są wymienione w jego `.md`.

11. **Providerzy i modele są konfigurowani w YAML.**

    Agent `.md` wskazuje tylko logiczny alias modelu, np. `reviewer_reasoning`. Sekcja `models:` w `moiryx.yaml` mapuje ten alias na alias providera oraz konkretny identyfikator modelu/deploymentu. Kod aplikacji nie zna providera ani nazwy modelu.

12. **Tool calle muszą mieć mechanizmy naprawcze.**

    Modele czasem zwracają niepoprawne argumenty, zły typ, uszkodzony JSON albo nieistniejącą nazwę toola. Runtime ma wykrywać takie przypadki, wykonywać wyłącznie bezpieczne naprawy syntaktyczne i dawać modelowi precyzyjny feedback do ponowienia calla. Nie wolno wykonywać niejednoznacznych fuzzy-matchy ani zgadywać semantyki argumentów.

13. **Biblioteka ma być cienka, przewidywalna i łatwa do wyrzucenia/wymiany.**

    Zero LangChain/LangGraph. Zero frameworkowej magii. Ma być mało własnych abstrakcji, dobre typy i prosty agent loop.

---

# 1. Cel projektu

Biblioteka ma rozwiązać powtarzający się boilerplate przy tworzeniu lokalnych i chmurowych agentów LLM:

- wysyłanie requestów do różnych providerów,
- normalizacja ich odpowiedzi,
- tool calling,
- walidacja argumentów tooli,
- wykonywanie sync/async tooli,
- obsługa kolejnych kroków agenta,
- structured output,
- walidacja structured output przez Pydantic,
- podstawowe retry i timeouty,
- spójna konfiguracja providerów i logicznych aliasów modeli,
- minimalne logowanie/trace do debugowania.

Biblioteka NIE jest końcowym „systemem agentowym”. Ma być zestawem klocków, dzięki którym każdy większy system będzie budowany zwykłym Pythonem.

Przykład docelowego użycia:

```python
from moiryx import Agent

planner = Agent("agents/planner.md")
reviewer = Agent("agents/reviewer.md")

plan = await planner(problem)
review = await reviewer(plan.model_dump_json())

if review.score < 0.8:
    plan = await planner(
        f"""
        Popraw plan na podstawie tej recenzji:
        {review.model_dump_json(indent=2)}
        """
    )
```

Kod orkiestrujący ma pozostać prosty i całkowicie kontrolowany przez użytkownika.

---

# 2. Non-goals

W v0.1 **nie implementować**:

- graph DSL,
- workflow DSL,
- node/edge API,
- chain abstractions,
- multi-agent swarm,
- automatycznego planera globalnego,
- schedulerów agentów,
- persistent memory,
- vector store,
- RAG frameworka,
- distributed workers,
- message bus,
- serwera HTTP,
- GUI,
- bazy danych,
- systemu ticketów,
- streamingu tokenów w publicznym API,
- automatycznej kompresji kontekstu,
- magicznego wykrywania tooli przez skanowanie całego filesystemu,
- własnego formatu schema zamiast Pydantic.

Jeżeli w przyszłości któryś z tych elementów okaże się realnie potrzebny, może zostać dodany jako osobny moduł. Rdzeń biblioteki nie powinien od niego zależeć.

---

# 3. Publiczne API

Publiczne API v0.1 powinno być minimalne.

```python
from moiryx import Agent, tool
```

To powinny być dwa główne symbole używane przez aplikację.

## 3.1. Tworzenie agenta

```python
agent = Agent("agents/reviewer.md")
```

Sygnatura:

```python
class Agent:
    def __init__(
        self,
        agent_file: str | Path,
    ) -> None:
        ...
```

Publiczny konstruktor nie przyjmuje modelu ani providera. Plik `reviewer.md` zawiera logiczny alias modelu:

```yaml
model: reviewer_reasoning
```

a `moiryx.yaml` mapuje go na konkretny backend:

```yaml
models:
  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1
```

Dzięki temu zmiana providera/modelu nie wymaga zmiany kodu Pythona ani instrukcji agenta. Ten sam kod:

```python
reviewer = Agent("agents/reviewer.md")
```

może zostać przełączony np. z OpenRouter na lokalny `llama-server` wyłącznie przez edycję `moiryx.yaml`.

## 3.2. Wywołanie agenta

```python
result = await agent(prompt)
```

Agent implementuje:

```python
async def __call__(self, prompt: str):
    ...
```

Nie implementujemy jako głównego API:

```python
agent.run(...)
agent.invoke(...)
agent.execute(...)
```

## 3.3. Agent tekstowy

Jeżeli plik `.md` nie definiuje `output`:

```python
agent = Agent("agents/architect.md")
answer = await agent("Zaprojektuj rozwiązanie")

assert isinstance(answer, str)
```

Zwrócony tekst jest finalnym `assistant.content` z ostatniego kroku agenta.

## 3.4. Agent structured output

Jeżeli `.md` zawiera:

```yaml
output: my_project.schemas.review:ReviewOutput
```

oraz istnieje:

```python
from typing import Literal
from pydantic import BaseModel, Field

class ReviewOutput(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str]
    summary: str
```

wynik ma być bezpośrednio:

```python
review = await agent(prompt)

review.decision
review.score
review.issues
review.summary
```

`review` musi być faktycznie instancją `ReviewOutput`.

Nie tworzyć wrappera typu:

```python
AgentResult
StructuredResponse
ResponseEnvelope
```

w normalnym publicznym API.

---

# 4. Statyczne typowanie a dynamiczny Markdown

Plik `.md` jest ładowany runtime'owo, więc type checker nie będzie potrafił automatycznie wywnioskować, że dany `Agent` zwróci np. `ReviewOutput`.

To jest **akceptowalne w v0.1**.

Runtime ma gwarantować prawdziwy typ Pydantic, więc:

```python
review.score
```

działa normalnie.

Nie komplikować API tylko po to, aby statyczny checker znał typ wyczytany z Markdowna.

Jeżeli użytkownik potrzebuje statycznego typu w konkretnym miejscu, może użyć:

```python
from typing import cast

review = cast(ReviewOutput, await reviewer(prompt))
```

Generowanie `.pyi`, plugin do mypy albo codegen typed agentów może być kiedyś osobnym rozszerzeniem, ale nie jest częścią v0.1.

---

# 5. Definicja agenta w Markdown

## 5.1. Format

Plik agenta składa się z:

1. opcjonalnego YAML frontmatter,
2. Markdown body będącego instrukcją/system promptem.

Przykład:

```markdown
---
name: reviewer
model: reviewer_reasoning
tools:
  - read_file
  - grep
  - get_build_status
output: my_project.schemas.review:ReviewOutput
max_steps: 20
generation:
  temperature: 0.2
  max_tokens: 8192
---

# Role

You are a strict technical reviewer.

# Instructions

Analyze the proposed solution critically.

Pay attention to:

- correctness,
- maintainability,
- testability,
- hidden assumptions,
- error handling.

Use available tools when necessary.
```

## 5.2. Pola frontmatter

### `model`

**Wymagane.** Logiczny alias modelu z sekcji `models:` w `moiryx.yaml`.

```yaml
model: reviewer_reasoning
```

Agent nie zna konkretnego providera ani model ID. Loader rozwiązuje alias:

```text
reviewer.md
  model: reviewer_reasoning
        ↓
moiryx.yaml
  models.reviewer_reasoning
        ↓
provider: openrouter
model: deepseek/deepseek-v4.1
```

Brak aliasu lub alias nieistniejący w configu ma powodować `UnknownModelError` podczas tworzenia `Agent`.

### `name`

Opcjonalne.

```yaml
name: reviewer
```

Służy wyłącznie do logów/trace/debugowania. Jeśli brak, użyć stemu pliku, np. `reviewer.md -> reviewer`.

### `tools`

Opcjonalna lista nazw narzędzi.

```yaml
tools:
  - read_file
  - grep
  - get_build_status
```

Nazwy muszą istnieć w registry podczas inicjalizacji agenta.

Jeżeli `tools` brak lub lista jest pusta, agent nie dostaje user-facing tooli.

### `output`

Opcjonalna referencja do klasy Pydantic.

```yaml
output: my_project.schemas.review:ReviewOutput
```

Format:

```text
python.module.path:ClassName
```

Klasa musi dziedziczyć po `pydantic.BaseModel`.

Brak `output` oznacza wynik tekstowy.

### `max_steps`

Opcjonalny dodatni integer.

```yaml
max_steps: 20
```

Jeśli brak, użyć globalnego defaultu z configu.

Krok oznacza **jedno wywołanie modelu**. Liczba tool calli zwróconych w jednym response nie zwiększa licznika kroków osobno.

### `generation`

Opcjonalny słownik wspólnych ustawień generacji.

```yaml
generation:
  temperature: 0.2
  max_tokens: 8192
  top_p: 0.95
```

V0.1 powinno wspierać mały wspólny zestaw:

- `temperature`,
- `max_tokens`,
- `top_p`,
- `seed` jeśli provider wspiera.

Nieznane opcje powinny skutkować czytelnym błędem albo być przekazywane jako jawne provider-specific extras dopiero w przyszłej wersji. Nie ignorować ich po cichu.

## 5.3. Body Markdown

Po usunięciu frontmatter cały pozostały Markdown staje się system instruction.

Nie trzeba konwertować Markdownu na plain text. Provider dostaje body jako tekst.

## 5.4. Walidacja pliku agenta

Błędy mają być wykrywane w konstruktorze `Agent`, nie dopiero przy pierwszym model callu.

Walidować:

- czy plik istnieje,
- czy YAML jest poprawny,
- czy `model` istnieje i jest stringiem,
- czy alias modelu istnieje w `models:` globalnego configu,
- czy wskazany przez model provider istnieje,
- czy `tools` jest listą stringów,
- czy każdy tool istnieje,
- czy `output` da się zaimportować,
- czy output class dziedziczy po `BaseModel`,
- czy `max_steps > 0`,
- czy generation options mają poprawne typy.

---

# 6. Konfiguracja globalna

## 6.1. Domyślny plik

Domyślna nazwa:

```text
moiryx.yaml
```

Biblioteka powinna znaleźć konfigurację według kolejności:

1. ścieżka z `MOIRYX_CONFIG`,
2. `./moiryx.yaml` w aktualnym working directory.

Na start nie implementować złożonego systemu wielu plików config.

Konfigurację można cachować po pierwszym poprawnym odczycie.

## 6.2. Przykład

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://localhost:8080/v1
    api_key: dummy
    timeout_seconds: 180

  openrouter:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}
    timeout_seconds: 180
    headers:
      HTTP-Referer: https://example.local
      X-Title: Moiryx

  gcp:
    type: vertex_ai
    project: my-gcp-project
    location: europe-west1
    timeout_seconds: 180

  azure:
    type: azure_openai
    endpoint: ${AZURE_OPENAI_ENDPOINT}
    api_key: ${AZURE_OPENAI_KEY}
    api_version: ${AZURE_OPENAI_API_VERSION}
    timeout_seconds: 180

  foundry:
    type: azure_foundry
    endpoint: ${AZURE_FOUNDRY_ENDPOINT}
    api_key: ${AZURE_FOUNDRY_KEY}
    timeout_seconds: 180

models:
  fast_local:
    provider: local
    model: qwen3.8-flash-next

  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1

  gemini_research:
    provider: gcp
    model: gemini-model

  work_gpt:
    provider: azure
    model: my-deployment

tool_modules:
  - my_project.tools.release
  - my_project.tools.repository

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
```

## 6.3. Provider aliases i model aliases

Klucze pod `providers:` są aliasami konfiguracji transportu/API. Nie są używane bezpośrednio przez kod tworzący `Agent`.

```yaml
providers:
  mylocal:
    type: openai_compatible
    base_url: http://localhost:8080/v1

models:
  coding_fast:
    provider: mylocal
    model: qwen3.8-flash-next
```

Agent `.md` wskazuje:

```yaml
model: coding_fast
```

a kod pozostaje:

```python
agent = Agent("agents/foo.md")
```

Nie hardkodować nazw `local`, `openrouter`, `gcp`, `azure` ani konkretnych modeli w klasie `Agent`.

Alias modelu jest stabilnym logicznym identyfikatorem przeznaczenia, np.:

```text
coding_fast
reasoning_strong
reviewer_reasoning
research_long_context
```

Dzięki temu można zmienić:

```yaml
models:
  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1
```

na:

```yaml
models:
  reviewer_reasoning:
    provider: local
    model: deepseek-v4.1-flash
```

bez zmiany `reviewer.md` ani kodu Pythona.

## 6.4. Konfiguracja modelu

Każdy wpis `models:` musi mieć co najmniej:

```yaml
models:
  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1
```

Opcjonalnie model może definiować wspólne defaulty generacji lub provider-specific options:

```yaml
models:
  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1
    generation:
      temperature: 0.2
      max_tokens: 8192
    provider_options:
      # opcjonalne i przekazywane wyłącznie adapterowi providera
      # dokładny zestaw zależy od adaptera
      reasoning_effort: high
```

Kolejność scalania ustawień generacji:

```text
runtime defaults
    ↓
model defaults z moiryx.yaml
    ↓
agent generation z agent.md
```

Agent-level settings mają pierwszeństwo. Nie przewidywać w v0.1 runtime override providera/modelu w konstruktorze `Agent`.

Wewnętrzny typ może wyglądać tak:

```python
@dataclass(frozen=True)
class ModelConfig:
    alias: str
    provider: str
    model: str
    generation: GenerationOptions
    provider_options: dict[str, Any]
```

---

## 6.5. Environment interpolation

Wartości string w YAML mogą zawierać:

```text
${ENV_VAR}
```

Implementacja ma rekurencyjnie interpolować env vars w dict/listach.

Brak wymaganej zmiennej środowiskowej ma powodować błąd configu z nazwą brakującej zmiennej.

Literalne klucze w YAML mogą działać, ale dokumentacja powinna zalecać env vars.

## 6.6. `tool_modules`

Dekorator `@tool` rejestruje funkcję dopiero, gdy jej moduł zostanie zaimportowany.

Aby nie wymagać ręcznych importów w każdym skrypcie, config może podać:

```yaml
tool_modules:
  - my_project.tools
  - my_project.integrations.azure
```

Przy inicjalizacji globalnego runtime'u biblioteka importuje te moduły przez `importlib.import_module()`.

Nie skanować automatycznie całego repozytorium.

---

# 7. Provider abstraction

## 7.1. Cel

`Agent` nie zna SDK OpenRoutera, Azure, Google ani llama.cpp.

Agent wie tylko, jaki **model alias** został wskazany w jego Markdownzie. Runtime rozwiązuje alias modelu do:

```text
model alias
   ↓
provider alias + concrete model/deployment id
```

Całą różnicę ma obsługiwać konfiguracja modeli + adapter providera.

## 7.2. Wymagani providerzy v0.1

Architektura musi przewidywać i najlepiej implementować:

1. `openai_compatible`
   - lokalny `llama-server`,
   - vLLM,
   - SGLang,
   - inne endpointy OpenAI-compatible.

2. `openrouter`
   - może reuse'ować dużą część `openai_compatible`,
   - osobny typ ułatwia headers, usage/cost i przyszłe różnice.

3. `azure_openai`
   - model part traktowany jako deployment/model identifier zgodnie z adapterem.

4. `vertex_ai`
   - GCP / Gemini przez oficjalny adapter Google.

5. `azure_foundry`
   - osobny adapter lub cienka warstwa nad właściwym klientem, zależnie od rodzaju endpointu.

Jeżeli Azure Foundry używa w konkretnym przypadku protokołu OpenAI-compatible, adapter może delegować do wspólnego transportu. Publiczne API ma pozostać identyczne.

## 7.3. Interfejs

Przykładowy wewnętrzny kontrakt:

```python
class ProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities:
        ...

    async def complete(self, request: ModelRequest) -> ModelResponse:
        ...

    async def close(self) -> None:
        ...
```

`Agent` nie powinien bezpośrednio importować provider SDK.

## 7.4. Provider capabilities

```python
@dataclass(frozen=True)
class ProviderCapabilities:
    tool_calling: bool
    native_structured_output: bool
    parallel_tool_calls: bool
```

Można rozszerzyć później.

Capabilities mogą mieć sensowne defaulty z adaptera i opcjonalne override w YAML dla niestandardowych lokalnych endpointów.

## 7.5. Normalized request

Wewnętrzny `ModelRequest` powinien zawierać co najmniej:

```python
@dataclass
class ModelRequest:
    model: str
    messages: list[Message]
    tools: list[ToolSchema]
    output_schema: dict[str, Any] | None
    generation: GenerationOptions
```

Nie przeciekać tutaj provider-specific response objects.

## 7.6. Normalized response

```python
@dataclass
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall]
    structured_output: dict[str, Any] | None
    finish_reason: str | None
    usage: Usage | None
    raw: Any | None = None
```

`raw` służy tylko debuggingowi.

## 7.7. Tool call normalization

Provider adapter **nie powinien zabijać całego runu tylko dlatego, że model zwrócił uszkodzone arguments**. Musi zachować tyle danych, aby warstwa tool-call repair mogła spróbować naprawy albo poprosić model o ponowienie.

Przykładowy typ:

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None
    raw_arguments: str | dict[str, Any] | None = None
    parse_error: str | None = None
```

Provider adapter odpowiada za:

- sparsowanie provider-specific tool call,
- znormalizowanie/preserved ID,
- zachowanie surowych argumentów,
- próbę zwykłego, jednoznacznego parsowania arguments,
- zapisanie `parse_error` zamiast natychmiastowego przerwania runu, jeśli payload tool calla da się zidentyfikować, ale arguments są uszkodzone.

Dopiero wspólna warstwa tool-call repair decyduje, czy call można bezpiecznie naprawić, czy model musi go wygenerować ponownie.

---

# 8. Model messages

Wewnętrznie warto mieć niewielkie własne typy message zamiast operować na surowych dictach providerów.

Minimalnie:

```python
@dataclass
class SystemMessage:
    content: str

@dataclass
class UserMessage:
    content: str

@dataclass
class AssistantMessage:
    content: str | None
    tool_calls: list[ToolCall]

@dataclass
class ToolMessage:
    tool_call_id: str
    name: str
    content: str
```

Adapter providera tłumaczy je na format SDK/API.

Nie implementować na start rozbudowanego multimodalnego modelu message. Można zostawić architekturę otwartą na przyszłe content parts.

---

# 9. Tool system

## 9.1. Publiczne API

Custom tool:

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

Nie:

```python
@tool("get_build_status")
```

Nie:

```python
Tool(...)
```

w normalnym kodzie użytkownika.

## 9.2. Nazwa

Nazwa toola:

```python
func.__name__
```

Jeżeli funkcja nazywa się:

```python
get_build_status
```

tool ma identyczną nazwę.

Nazwa musi być poprawnym Python identifierem i kompatybilna z providerami.

## 9.3. Opis toola

Opis jest pobierany z docstringa.

Przykład:

```python
@tool
def read_ticket(ticket_id: str) -> Ticket:
    """
    Read a ticket from the project tracker.

    Args:
        ticket_id: Ticket identifier, e.g. PROJ-123.
    """
    ...
```

Tool description:

```text
Read a ticket from the project tracker.
```

Opis parametru `ticket_id`:

```text
Ticket identifier, e.g. PROJ-123.
```

Warto użyć istniejącej lekkiej biblioteki do parsowania Google-style/Numpy-style docstringów zamiast pisać pełny parser samemu. Jeśli parser nie rozpozna sekcji `Args`, summary docstringa nadal musi działać.

## 9.4. Wymagania względem sygnatury

V0.1:

- każdy parametr musi mieć type hint,
- funkcja powinna mieć return type hint,
- wspierane są parametry pozycyjne/nazwane o normalnej sygnaturze,
- nie wspierać `*args` ani `**kwargs`,
- default value oznacza parametr opcjonalny,
- brak defaultu oznacza required.

Przy rejestracji niepoprawnej funkcji rzucić `ToolDefinitionError`.

## 9.5. Generowanie input schema

Nie pisać ręcznego generatora JSON Schema.

Na podstawie `inspect.signature()` i `typing.get_type_hints()` należy utworzyć dynamiczny Pydantic model wejściowy, np. przez `pydantic.create_model()`.

Następnie:

```python
input_model.model_json_schema()
```

Typy, które powinny działać co najmniej:

- `str`,
- `int`,
- `float`,
- `bool`,
- `str | None`,
- `list[T]`,
- `dict[str, T]`,
- `Literal[...]`,
- Enum,
- nested `BaseModel`,
- proste dataclasses jeśli Pydantic je obsługuje przez `TypeAdapter`.

## 9.6. Walidacja inputu

Model może zwrócić błędne argumenty.

Przed wykonaniem funkcji:

```python
validated = input_model.model_validate(tool_call.arguments)
```

Dopiero potem wołamy funkcję.

W przypadku błędu Pydantic nie przerywać od razu całego agenta. Zwrócić modelowi czytelny tool error, np.:

```text
Tool validation failed for read_file:
- path: expected string, got integer
```

Model dostaje możliwość poprawienia wywołania w kolejnym kroku.

## 9.7. Sync i async

Obie wersje muszą działać:

```python
@tool
def add(a: int, b: int) -> int:
    return a + b
```

```python
@tool
async def fetch_ticket(ticket_id: str) -> Ticket:
    ...
```

Executor sprawdza wynik lub funkcję i odpowiednio `await`uje.

Sync tool może być wykonany bezpośrednio w v0.1, ale jeśli ma potencjalnie blokować event loop, lepiej uruchamiać go przez `asyncio.to_thread()`.

Rekomendacja: **sync tools przez `asyncio.to_thread()`**.

## 9.8. Return value

Tool może zwrócić:

- string,
- number,
- bool,
- list,
- dict,
- `BaseModel`,
- dataclass,
- `None`.

Serializacja powinna preferować return annotation + `pydantic.TypeAdapter`.

Dla Pydantic:

```python
result.model_dump(mode="json")
```

Dla stringa nie trzeba go opakowywać w JSON string, można wysłać tekst bezpośrednio.

Wynik toola musi zostać znormalizowany do tekstowego `ToolMessage.content` dla providera.

## 9.9. Tool errors

Rozróżnić:

1. `ToolValidationError` — złe argumenty modelu,
2. `ToolExecutionError` — wyjątek z funkcji,
3. `ToolTimeoutError` — przekroczony timeout.

Domyślnie wszystkie trzy są zwracane modelowi jako wynik nieudanego tool calla i agent może kontynuować.

Nie wysyłać pełnego stack trace do modelu, chyba że debug mode wyraźnie tego wymaga.

Log lokalny może zawierać stack trace.

## 9.10. Timeout

Każdy tool call ma globalny timeout z configu:

```yaml
runtime:
  tool_timeout_seconds: 60
```

W przyszłości można dodać tool-specific timeout, ale nie jest potrzebny do v0.1.

## 9.11. Limit outputu

Aby przypadkowy `grep` lub `shell` nie wrzucił megabajtów do kontekstu:

```yaml
runtime:
  max_tool_output_chars: 50000
```

Po przekroczeniu output jest ucinany i dostaje jawny marker, np.:

```text
...[TRUNCATED BY MOIRYX: original output exceeded 50000 chars]
```

Nie ucinać po cichu.

## 9.12. Tool-call repair — wymagany mechanizm

Tool calling w praktyce nie jest idealne, szczególnie dla lokalnych modeli. Runtime ma posiadać wspólną warstwę naprawczą niezależną od providera.

Konfiguracja:

```yaml
runtime:
  tool_call_repair_attempts: 2
```

`tool_call_repair_attempts` oznacza maksymalną liczbę rund korekty dla błędnego tool calla / błędnej paczki tool calli. Jest to osobny budżet od `provider_retry_attempts` i `structured_output_retries`.

### 9.12.1. Zasada bezpieczeństwa

Repair może automatycznie wykonywać tylko **jednoznaczne naprawy syntaktyczne/transportowe**. Nie może zgadywać intencji modelu.

Dozwolone przykłady:

- usunięcie otaczających whitespaces z nazwy toola,
- zwykłe `json.loads()` na stringu arguments,
- jednokrotne rozpakowanie podwójnie zakodowanego JSON-a, jeżeli pierwszy parse zwróci string, a drugi jednoznacznie zwróci obiekt,
- rozpakowanie oczywistego wrappera `{"arguments": {...}}`, ale tylko jeśli tool nie ma parametru o nazwie `arguments` i wewnętrzny obiekt przechodzi pełną walidację schema,
- standardowa walidacja/coercion Pydantic dla wartości takich jak `"42" -> 42`, o ile model Pydantic na to pozwala.

Niedozwolone automatycznie:

- fuzzy wybór innego toola i jego wykonanie,
- wymyślanie brakującego path/id/query,
- zmiana wartości na podstawie semantycznego domysłu,
- usuwanie nieznanych argumentów tylko po to, aby schema przeszła,
- wykonywanie calla, którego naprawa pozostaje niejednoznaczna.

Szczególnie dla mutujących tooli (`write_file`, `edit_file`, `shell`, custom integrations) runtime ma preferować **model retry zamiast zgadywania**.

### 9.12.2. Pipeline walidacji przed wykonaniem

Dla każdego response z tool calls runtime wykonuje najpierw fazę preflight dla **wszystkich** calli:

```text
provider response
      ↓
normalize tool call
      ↓
resolve exact tool name
      ↓
parse / conservative syntax repair arguments
      ↓
Pydantic input validation
      ↓
ALL calls valid?
   ├── yes -> execute
   └── no  -> execute NONE; send repair feedback to model
```

Ważne: nie wykonywać części batcha, jeśli inny call z tego samego response jest błędny. Zapobiega to sytuacji, w której model wykona np. `write_file`, a dopiero potem runtime odkryje, że drugi tool call był uszkodzony i prosi o wygenerowanie całego kroku ponownie.

### 9.12.3. Nieznana nazwa toola

Jeżeli model zwróci:

```text
read_files
```

a dostępny jest tylko:

```text
read_file
```

runtime **nie odpala automatycznie** `read_file`.

Może wyliczyć sugestie przez `difflib.get_close_matches()` wyłącznie do feedbacku:

```text
Unknown tool 'read_files'.
Available tools: read_file, grep, glob_files.
Did you mean 'read_file'? Submit a corrected tool call.
```

Model musi ponowić call z poprawną nazwą.

### 9.12.4. Błędne argumenty

Przykład modelu:

```json
{
  "path": 123,
  "start_line": "abc"
}
```

Jeśli Pydantic nie może tego poprawnie zwalidować, runtime zwraca do modelu możliwie mały, precyzyjny komunikat:

```text
Tool call validation failed for read_file.
Correct the tool call and try again.

Validation errors:
- path: expected string
- start_line: expected integer or null

Expected parameters:
- path: string (required)
- start_line: integer | null
- end_line: integer | null
```

Nie wysyłać całego Pydantic stack trace.

### 9.12.5. Malformed JSON arguments

Jeśli provider zwraca nazwę toola i ID, ale `arguments` jest uszkodzonym JSON-em:

1. spróbować tylko dozwolonych deterministic repairs,
2. jeśli nadal nie można otrzymać dict -> nie wykonywać toola,
3. wysłać modelowi repair feedback z informacją, że arguments muszą być poprawnym obiektem zgodnym ze schema,
4. zwiększyć licznik repair attempt,
5. po wyczerpaniu budżetu -> `ToolCallRepairError`.

Nie stosować regexów, które próbują „wydobyć co model miał na myśli”.

### 9.12.6. Feedback do modelu

Jeżeli istnieje prawidłowy provider tool-call ID, preferować zwrócenie błędu jako tool result powiązanego z tym ID, bo zachowuje naturalny protokół tool calling.

Jeżeli payload jest uszkodzony tak mocno, że nie da się zbudować poprawnego tool result, runtime może dodać krótką wewnętrzną wiadomość korekcyjną do następnego model requestu. Ta wiadomość:

- nie jest traktowana jako nowy user prompt,
- jest oznaczona wewnętrznie jako protocol/repair instruction,
- nie zmienia publicznej historii użytkownika,
- zawiera tylko błąd + oczekiwany format, bez nowych założeń merytorycznych.

Adapter providera odpowiada za poprawne odwzorowanie takiej instrukcji na wspierany format wiadomości.

### 9.12.7. Repeated invalid call

Runtime powinien fingerprintować błędny call, np. po:

```text
(tool name, canonicalized raw arguments, validation error signature)
```

Jeśli model powtarza dokładnie ten sam błędny call, nadal zużywa budżet repair. Nie tworzyć nieskończonej pętli.

Po przekroczeniu `tool_call_repair_attempts`:

```python
raise ToolCallRepairError(...)
```

Wyjątek powinien zawierać:

- agent name,
- model alias,
- provider + concrete model id,
- tool name jeśli znana,
- ostatni raw arguments,
- zwięzły validation/parse error,
- liczbę wykonanych prób.

### 9.12.8. Repair nie zużywa dodatkowego „tool execution”

Niepoprawny call, który nie został wykonany, nie powinien być logowany jako `tool_completed` ani jako realne wykonanie narzędzia. Jest osobnym zdarzeniem `tool_call_repair_*`.

Model retry jest natomiast normalnym kolejnym wywołaniem modelu i zwiększa `step`, bo zużywa request/tokeny.

### 9.12.9. Structured final tool korzysta z tych samych fundamentów

`__moiryx_submit_result` również przechodzi przez wspólne:

- parsowanie arguments,
- conservative syntax repair,
- Pydantic validation,
- repair feedback.

Jednocześnie zachowuje osobny `structured_output_retries`, ponieważ jest finalnym kontraktem wyniku agenta. Implementacja może współdzielić kod naprawczy, ale budżety retry pozostają logicznie osobne.

---

# 10. Tool registry

## 10.1. Globalny registry

Biblioteka utrzymuje registry:

```text
name -> ToolDefinition
```

Built-in tools są rejestrowane podczas inicjalizacji biblioteki.

Custom `@tool` rejestruje funkcję podczas importu modułu.

## 10.2. Duplicate names

Jeżeli istnieje już tool o tej samej nazwie, rejestracja custom toola ma zakończyć się `DuplicateToolError`.

Nie nadpisywać built-in tooli po cichu.

## 10.3. Rozwiązywanie tooli agenta

Przy:

```yaml
tools:
  - read_file
  - grep
  - get_build_status
```

Agent initialization robi:

```text
registry.resolve("read_file")
registry.resolve("grep")
registry.resolve("get_build_status")
```

Brak toola -> `UnknownToolError` podczas tworzenia `Agent`.

## 10.4. Decorator implementation requirement

`@tool` powinien zachować możliwość normalnego wywołania funkcji z Pythona.

To znaczy:

```python
@tool
def add(a: int, b: int) -> int:
    return a + b

assert add(1, 2) == 3
```

Dekorator może:

- zachować oryginalną funkcję,
- przypisać metadata attribute, np. `__moiryx_tool__`,
- zarejestrować `ToolDefinition` w registry.

Nie zmuszać użytkownika do wołania `add.call()` itp.

---

# 11. Built-in tools

Built-in tools mają być dostarczone przez bibliotekę i dostępne po nazwie w `.md`.

**Ważne:** „built-in” nie oznacza „automatycznie przekazany każdemu modelowi”. Agent dostaje tylko tool names wymienione w swoim `.md`.

## 11.1. Minimalny zestaw v0.1

### Filesystem

- `read_file`
- `write_file`
- `edit_file`
- `list_files`
- `glob_files`
- `grep`

### Shell

- `shell`

Opcjonalnie później:

- `http_get`,
- `python`,
- git helpers,
- web search,
- provider-specific integrations.

Nie trzeba ładować wszystkiego do v0.1.

## 11.2. Workspace safety

Filesystem tools i shell muszą mieć `workspace_root`.

Domyślnie:

```yaml
runtime:
  workspace_root: .
  allow_paths_outside_workspace: false
```

Path należy canonicalizować przez `Path.resolve()` i sprawdzać, czy znajduje się pod workspace root.

Próba wyjścia `../../...` poza root ma zakończyć się tool error.

Jeżeli użytkownik jawnie ustawi:

```yaml
allow_paths_outside_workspace: true
```

tool może działać poza rootem.

## 11.3. `read_file`

Rekomendowana sygnatura:

```python
async def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    ...
```

Ma wspierać zakres linii, aby model nie musiał czytać całego wielkiego pliku.

## 11.4. `write_file`

```python
async def write_file(path: str, content: str) -> str:
    ...
```

Powinien tworzyć katalog rodzica w rozsądny sposób albo zgłaszać czytelny błąd. Wybrać jedno zachowanie i pokryć testami.

## 11.5. `edit_file`

Nie robić na start bardzo skomplikowanego patch engine.

Możliwy prosty kontrakt:

```python
async def edit_file(
    path: str,
    old_text: str,
    new_text: str,
) -> str:
    ...
```

Wymagać dokładnie jednego dopasowania `old_text`; zero lub >1 dopasowań -> błąd toola.

## 11.6. `grep`

```python
async def grep(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    max_results: int = 100,
) -> str:
    ...
```

Może używać `ripgrep` jeśli dostępny, z bezpiecznym subprocess API bez `shell=True`.

Fallback do Pythona jest opcjonalny.

## 11.7. `shell`

Minimalna sygnatura:

```python
async def shell(
    command: str,
    timeout_seconds: int | None = None,
) -> str:
    ...
```

Jest to z definicji potężny tool, ale użytkownik jawnie dodaje go w `.md`.

Output stdout/stderr powinien być czytelnie połączony lub zwrócony w ustrukturyzowanym tekście.

Globalny timeout nadal obowiązuje.

---

# 12. Agent loop

## 12.1. Agent jest stateless pomiędzy wywołaniami

```python
agent = Agent(...)

r1 = await agent("task A")
r2 = await agent("task B")
```

`r2` nie widzi historii `r1`.

Każde `await agent(prompt)` tworzy nowy `RunContext` i nową historię wiadomości.

To jest ważne dla:

- przewidywalności,
- concurrency,
- budowania flow w Pythonie,
- braku ukrytej pamięci.

Persistent conversation może być kiedyś osobną abstrakcją `Session`, ale nie jest częścią v0.1.

## 12.2. Początek runu

Historia:

```text
system: <Markdown body>
user: <prompt przekazany do agent(...)>
```

Dodatkowe wewnętrzne instrukcje protokołu mogą być dołączone przez runtime, np. dla structured output, ale nie powinny zmieniać semantyki body użytkownika.

## 12.3. Jeden krok

1. Wyślij messages + tool schemas do providera.
2. Znormalizuj odpowiedź.
3. Jeśli są tool calls:
   - dopisz assistant message z tool calls,
   - wykonaj preflight całego batcha: resolve names -> parse/repair args -> Pydantic validation,
   - jeśli którykolwiek call jest niepoprawny: nie wykonuj żadnego; dodaj repair feedback i przejdź do kolejnego model step,
   - jeśli wszystkie są poprawne: wykonaj calls,
   - dopisz tool messages,
   - przejdź do kolejnego kroku.
4. Jeśli nie ma tool calls:
   - agent tekstowy -> zwróć final content,
   - structured agent -> zastosuj reguły structured output.

## 12.4. Multiple tool calls

Model może w jednym response zwrócić kilka tool calls.

W v0.1 wykonywać je **sekwencyjnie w kolejności zwróconej przez model**.

Nie komplikować od razu parallel execution. Jest to łatwiejsze do debugowania i bezpieczniejsze dla tooli mutujących stan.

`parallel_tool_calls` można dodać później.

## 12.5. Step limit

Każdy model response inkrementuje `step`.

Po osiągnięciu limitu bez finalnego wyniku:

```python
raise MaxStepsExceeded(...)
```

Nie zwracać ostatniego losowego tool outputu ani częściowej odpowiedzi jako sukcesu.

Exception powinien zawierać:

- agent name,
- model alias,
- provider name + concrete model id,
- max steps,
- run id.

---

# 13. Structured output — najważniejsza część

## 13.1. Cel

Jeżeli agent deklaruje:

```yaml
output: my_project.schemas.review:ReviewOutput
```

to sukces runu oznacza:

```python
isinstance(result, ReviewOutput) is True
```

Nie ma stanu „prawie poprawny JSON”.

## 13.2. Pydantic jako source of truth

Runtime ładuje:

```python
ReviewOutput
```

następnie:

```python
schema = ReviewOutput.model_json_schema()
```

Schemat providerowy jest generowany z Pydantic.

Po uzyskaniu danych:

```python
result = ReviewOutput.model_validate(data)
```

Dopiero wtedy wynik jest zwracany do użytkownika.

## 13.3. Preferowana strategia: synthetic final tool

Dla providerów z tool callingiem najbardziej uniwersalny mechanizm to dodanie przez runtime wewnętrznego toola, np.:

```text
__moiryx_submit_result
```

Jego parameter schema = JSON Schema Pydantic output modelu.

Przykładowo runtime wysyła modelowi user tools:

```text
read_file
grep
get_build_status
```

plus wewnętrzny:

```text
__moiryx_submit_result
```

Model może wykonywać zwykłe toole, a gdy skończy, wywołuje:

```text
__moiryx_submit_result(
    decision="revise",
    score=0.62,
    issues=[...],
    summary="..."
)
```

Runtime:

1. nie wykonuje tego jako prawdziwej funkcji,
2. bierze arguments,
3. robi `ReviewOutput.model_validate(arguments)`,
4. zwraca `ReviewOutput`.

To eliminuje parsowanie Markdownu i ręczne `json.loads()` z finalnego tekstu.

## 13.4. Nazwa internal tool

Nazwa ma być zarezerwowana:

```text
__moiryx_submit_result
```

Custom tool o tej nazwie nie może zostać zarejestrowany.

## 13.5. Instrukcja protokołu

Dla structured agenta runtime może dołączyć krótki system suffix, np.:

```text
When the task is complete, return the final answer by calling
__moiryx_submit_result exactly once with arguments matching the required schema.
Do not return the final structured answer as plain text.
```

Nie wrzucać pełnego JSON Schema do tekstowego prompta, skoro provider dostaje je jako tool definition.

## 13.6. Invalid structured call

Jeżeli model wywoła final tool z niepoprawnymi argumentami:

- Pydantic zwraca validation error,
- runtime dodaje tool error message,
- model dostaje szansę poprawienia,
- limit napraw określa `structured_output_retries`.

Po przekroczeniu limitu:

```python
raise StructuredOutputError(...)
```

## 13.7. Model zwraca plain text zamiast final toola

Nie próbować wycinać JSON-a z tekstu.

Runtime powinien:

1. potraktować to jako protocol violation,
2. dodać krótką wiadomość naprawczą: wynik musi zostać zwrócony przez final tool,
3. kontynuować do limitu structured retries.

Po przekroczeniu limitu -> `StructuredOutputError`.

## 13.8. Final tool razem z normalnym toolem

Jeżeli response zawiera jednocześnie:

```text
read_file(...)
__moiryx_submit_result(...)
```

traktować to jako nieprawidłową odpowiedź protokołu.

Nie zgadywać, czy final result powstał przed czy po odczycie pliku.

Runtime powinien odesłać modelowi informację, że final result musi wystąpić samodzielnie po zakończeniu pozostałych tool calls.

## 13.9. Native structured output

Provider może mieć native JSON schema / response schema.

Adapter może z tego korzystać, jeśli jest to pewne i nie koliduje z agentowym tool callingiem.

Zachowanie publiczne musi pozostać identyczne.

Rekomendowana polityka v0.1:

1. jeśli provider wspiera tool calling -> użyj synthetic final tool,
2. jeśli nie wspiera tool callingu, ale wspiera native structured output i agent nie ma user tools -> użyj native structured output,
3. jeśli agent wymaga tools/structured output, a provider nie potrafi tego zagwarantować -> `ProviderCapabilityError`.

Nie implementować jako domyślnego fallbacku „prompt JSON i spróbuj sparsować tekst”.

## 13.10. Agent tekstowy

Dla agenta bez `output` zakończenie następuje wtedy, gdy response:

- nie ma tool calls,
- ma final `content`.

Wtedy:

```python
return response.content
```

Jeżeli `content is None` i brak tool calls, rzucić `AgentProtocolError` zamiast zwracać przypadkowe `None`.

---

# 14. Provider retry i błędy

## 14.1. Retry providerów

Retry dotyczy błędów przejściowych:

- timeout połączenia,
- connection reset,
- HTTP 429,
- wybrane 5xx.

Globalny config:

```yaml
runtime:
  provider_retry_attempts: 3
```

Użyć exponential backoff + jitter.

Nie retryować automatycznie oczywistych 4xx typu zły klucz, zły model, malformed request.

## 14.2. Error taxonomy

Zdefiniować czytelne wyjątki dziedziczące po jednym bazowym:

```python
class MoiryxError(Exception): ...

class ConfigurationError(MoiryxError): ...
class AgentDefinitionError(MoiryxError): ...
class ProviderNotFoundError(MoiryxError): ...
class UnknownModelError(MoiryxError): ...
class ProviderCapabilityError(MoiryxError): ...
class ProviderRequestError(MoiryxError): ...
class UnknownToolError(MoiryxError): ...
class DuplicateToolError(MoiryxError): ...
class ToolDefinitionError(MoiryxError): ...
class ToolCallParseError(MoiryxError): ...
class ToolCallRepairError(MoiryxError): ...
class StructuredOutputError(MoiryxError): ...
class AgentProtocolError(MoiryxError): ...
class MaxStepsExceeded(MoiryxError): ...
```

Tool execution errors przekazywane modelowi nie muszą wychodzić jako publiczny exception, chyba że runtime nie może kontynuować.

## 14.3. Nie ukrywać błędów configu

Przykładowo:

```text
Provider 'azure' requires environment variable AZURE_OPENAI_KEY, but it is not set.
```

jest lepsze niż generyczny stack trace z `KeyError`.

---

# 15. Concurrency i lifecycle

## 15.1. Reuse Agent

Ten sam `Agent` ma być bezpieczny dla równoległych runów:

```python
results = await asyncio.gather(
    agent("task 1"),
    agent("task 2"),
    agent("task 3"),
)
```

Dlatego:

- messages nie mogą być trzymane na obiekcie Agent,
- step counter nie może być na obiekcie Agent,
- tool state runu nie może być globalny,
- każdy call tworzy własny `RunContext`.

## 15.2. Provider clients

Klientów HTTP/SDK można cachować per provider alias, aby nie tworzyć połączenia od zera w każdym kroku.

Globalny `ProviderRegistry` / runtime może posiadać client pool.

## 15.3. Cleanup

Ponieważ główne API ma być proste, nie zmuszać użytkownika do:

```python
async with Agent(...) as agent:
```

Można utrzymać klientów przez lifecycle procesu i zapewnić wewnętrzny cleanup/atexit albo globalne `close()` jako zaawansowane API.

Nie może to wpływać na podstawowe:

```python
agent = Agent(...)
result = await agent(...)
```

---

# 16. Run context

Wewnętrzny obiekt `RunContext` jest potrzebny, ale nie powinien być elementem normalnego publicznego API.

Przykład:

```python
@dataclass
class RunContext:
    run_id: str
    agent_name: str
    model_alias: str
    provider_name: str
    model_id: str
    messages: list[Message]
    step: int
    started_at: datetime
```

Może też trzymać usage i trace events.

Każdy call generuje UUID/ULID run ID.

---

# 17. Logging i tracing

Nie budować systemu observability klasy LangSmith.

Potrzebne są jednak podstawy do debugowania, bo agent robi wiele kroków.

## 17.1. Standard logging

Użyć modułu `logging`.

Logować na sensownych poziomach:

- INFO: start/end run, model, liczba kroków,
- DEBUG: tool calls, provider request metadata, validation,
- WARNING: retries, tool errors,
- ERROR: fatal run failure.

Nie logować sekretów.

## 17.2. Opcjonalny JSONL trace

Jeżeli:

```yaml
logging:
  trace_dir: .moiryx/runs
```

runtime zapisuje np.:

```text
.moiryx/runs/<run-id>/events.jsonl
```

Minimalne eventy:

```text
run_started
model_requested
model_responded
tool_requested
tool_call_repair_started
tool_call_repaired
tool_call_repair_failed
tool_completed
tool_failed
structured_output_validated
run_completed
run_failed
```

Każdy event powinien zawierać timestamp i run_id.

## 17.3. Sekrety

Nigdy nie zapisywać:

- API keys,
- Authorization headers,
- service account secrets.

Provider config musi mieć redaction w `repr`/logach.

## 17.4. Raw responses

Raw provider response można logować tylko w explicit debug mode albo przechowywać wewnętrznie z ostrożnością.

Nie jest potrzebny do standardowego działania.

---

# 18. Security i wykonywanie lokalnych narzędzi

Biblioteka jest lokalnym harnessem i użytkownik może świadomie dać agentowi `shell`, ale defaulty mają być rozsądne.

Wymagania:

- filesystem tools ograniczone do workspace root domyślnie,
- `Path.resolve()` + sprawdzanie parent relation,
- subprocess bez `shell=True`, gdzie to możliwe,
- timeouty,
- limit długości outputu,
- czytelne logowanie mutujących tooli,
- żadnego automatycznego udostępniania wszystkich tooli każdemu agentowi.

W przyszłości można dodać tool permissions/sandbox, ale v0.1 nie potrzebuje policy engine.

---

# 19. Sugerowane zależności

Minimalnie:

```text
pydantic >= 2
PyYAML
httpx
```

Przydatne:

```text
docstring-parser
```

Provider-specific:

```text
openai
google-genai / odpowiedni oficjalny Google SDK
azure SDK tylko jeśli rzeczywiście potrzebny przez Foundry adapter
```

Testy/dev:

```text
pytest
pytest-asyncio
ruff
mypy lub pyright
```

Nie dodawać ciężkich frameworków agentowych jako dependency.

---

# 20. Sugerowana struktura repozytorium

```text
moiryx/
├── pyproject.toml
├── README.md
├── src/
│   └── moiryx/
│       ├── __init__.py
│       ├── agent.py
│       ├── runtime.py
│       ├── config.py
│       ├── agent_spec.py
│       ├── messages.py
│       ├── models.py
│       ├── model_registry.py
│       ├── errors.py
│       ├── tracing.py
│       │
│       ├── output/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   └── structured.py
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── decorator.py
│       │   ├── registry.py
│       │   ├── definition.py
│       │   ├── executor.py
│       │   ├── repair.py
│       │   ├── serialization.py
│       │   └── builtin/
│       │       ├── __init__.py
│       │       ├── filesystem.py
│       │       └── shell.py
│       │
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           ├── registry.py
│           ├── openai_compatible.py
│           ├── openrouter.py
│           ├── azure_openai.py
│           ├── azure_foundry.py
│           └── vertex_ai.py
│
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_agent_spec.py
│   │   ├── test_tool_decorator.py
│   │   ├── test_tool_schema.py
│   │   ├── test_tool_executor.py
│   │   ├── test_structured_output.py
│   │   ├── test_agent_loop.py
│   │   └── test_concurrency.py
│   │
│   ├── providers/
│   │   ├── test_openai_compatible.py
│   │   ├── test_openrouter.py
│   │   ├── test_azure_openai.py
│   │   └── test_vertex_ai.py
│   │
│   └── integration/
│       └── ...
│
└── examples/
    ├── moiryx.yaml
    ├── simple_text_agent.py
    ├── structured_reviewer.py
    ├── custom_tool.py
    └── agents/
        ├── assistant.md
        └── reviewer.md
```

Struktura może zostać lekko uproszczona, ale odpowiedzialności nie powinny zostać wrzucone do jednego wielkiego `agent.py`.

---

# 21. Wewnętrzne modele danych

Przykładowe typy. Nie są wymagane 1:1, ale implementacja powinna mieć podobnie czyste granice.

```python
@dataclass(frozen=True)
class GenerationOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None
```

```python
@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
```

```python
@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]
```

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None
    raw_arguments: str | dict[str, Any] | None = None
    parse_error: str | None = None
```

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    function: Callable[..., Any]
    input_model: type[BaseModel]
    return_adapter: TypeAdapter | None
```

---

# 22. AgentSpec

`AgentSpec` jest wewnętrznym wynikiem sparsowania `.md`.

```python
@dataclass(frozen=True)
class AgentSpec:
    name: str
    model_alias: str
    instructions: str
    tool_names: tuple[str, ...]
    output_model: type[BaseModel] | None
    max_steps: int
    generation: GenerationOptions
```

Nie eksportować go jako wymaganej części publicznego API.

`Agent.__init__()` może od razu:

1. załadować global config,
2. załadować/importować tool modules,
3. sparsować agent markdown,
4. odczytać `model_alias` z `agent.md`,
5. rozwiązać alias przez `models:` w configu,
6. znaleźć wskazanego providera,
7. rozwiązać tool names,
8. rozwiązać output model,
9. scalić generation defaults modelu i agenta,
10. zwalidować provider capabilities tam, gdzie da się to zrobić od razu.

---

# 23. Pseudokod `Agent`

```python
class Agent:
    def __init__(self, agent_file: str | Path):
        self._runtime = get_runtime()
        self._spec = load_agent_spec(agent_file, self._runtime.tool_registry)
        self._model = self._runtime.models.resolve(self._spec.model_alias)
        self._provider = self._runtime.providers.resolve(self._model.provider)

        validate_capabilities(
            provider=self._provider,
            spec=self._spec,
        )

    async def __call__(self, prompt: str):
        return await self._runtime.execute(
            provider=self._provider,
            provider_name=self._model.provider,
            model_id=self._model.model,
            model_alias=self._spec.model_alias,
            spec=self._spec,
            prompt=prompt,
        )
```

Publiczny `Agent` ma pozostać cienki.

---

# 24. Pseudokod runtime loop — agent tekstowy

```python
async def execute_text_agent(...):
    ctx = create_run_context(...)

    ctx.messages.append(SystemMessage(spec.instructions))
    ctx.messages.append(UserMessage(prompt))

    for step in range(spec.max_steps):
        ctx.step = step + 1

        response = await provider.complete(
            ModelRequest(
                model=model_id,
                messages=ctx.messages,
                tools=user_tool_schemas,
                generation=spec.generation,
            )
        )

        if response.tool_calls:
            ctx.messages.append(
                AssistantMessage(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            preflight = preflight_tool_calls(
                response.tool_calls,
                available_tools=user_tools,
            )

            if not preflight.valid:
                ctx.messages.extend(
                    build_tool_repair_feedback(preflight.errors)
                )
                ensure_tool_repair_budget(ctx, preflight)
                continue

            # Dopiero po poprawnym preflight CAŁEGO batcha.
            for call in preflight.calls:
                tool_message = await execute_tool_call(call)
                ctx.messages.append(tool_message)

            continue

        if response.content is None:
            raise AgentProtocolError(...)

        return response.content

    raise MaxStepsExceeded(...)
```

---

# 25. Pseudokod runtime loop — structured agent

```python
async def execute_structured_agent(...):
    output_model = spec.output_model
    final_tool = build_final_output_tool(output_model)

    tools = [*user_tools, final_tool]

    ctx.messages.append(
        SystemMessage(
            spec.instructions + STRUCTURED_OUTPUT_PROTOCOL_SUFFIX
        )
    )
    ctx.messages.append(UserMessage(prompt))

    structured_failures = 0

    for step in range(spec.max_steps):
        response = await provider.complete(...)

        if response.tool_calls:
            preflight = preflight_tool_calls(
                response.tool_calls,
                available_tools=tools,
            )

            if not preflight.valid:
                ctx.messages.extend(
                    build_tool_repair_feedback(preflight.errors)
                )
                ensure_tool_repair_budget(ctx, preflight)
                continue

            valid_calls = preflight.calls

            final_calls = [
                c for c in valid_calls
                if c.name == FINAL_TOOL_NAME
            ]
            normal_calls = [
                c for c in valid_calls
                if c.name != FINAL_TOOL_NAME
            ]

            if final_calls and normal_calls:
                structured_failures += 1
                ctx.messages.append(
                    protocol_error_message(
                        "Final output tool cannot be called together with normal tools."
                    )
                )
                ensure_structured_retry_budget(structured_failures)
                continue

            if len(final_calls) > 1:
                structured_failures += 1
                ...
                continue

            if final_calls:
                try:
                    return output_model.model_validate(
                        final_calls[0].arguments
                    )
                except ValidationError as exc:
                    structured_failures += 1
                    ctx.messages.append(
                        structured_validation_error_message(exc)
                    )
                    ensure_structured_retry_budget(structured_failures)
                    continue

            # normal tools only
            ctx.messages.append(...)
            for call in normal_calls:
                ctx.messages.append(await execute_tool_call(call))
            continue

        # plain text without final tool
        structured_failures += 1
        ctx.messages.append(
            AssistantMessage(content=response.content, tool_calls=[])
        )
        ctx.messages.append(
            UserMessage(
                "Return the final result using the required structured output tool."
            )
        )
        ensure_structured_retry_budget(structured_failures)

    raise MaxStepsExceeded(...)
```

Implementacja może różnić się detalami, ale kontrakt i semantyka powinny być takie.

---

# 26. Custom tool — pełny przykład

```python
from pydantic import BaseModel
from moiryx import tool


class BuildStatus(BaseModel):
    build_id: int
    state: str
    failed_steps: list[str]


@tool
async def get_build_status(build_id: int) -> BuildStatus:
    """
    Return current CI build status.

    Args:
        build_id: Unique numeric identifier of the build.
    """
    # dowolna implementacja
    return BuildStatus(
        build_id=build_id,
        state="failed",
        failed_steps=["unit-tests"],
    )
```

Po imporcie modułu registry powinien znać:

```text
name: get_build_status
description: Return current CI build status.
```

z parameter schema wynikającym z `build_id: int`.

Agent:

```markdown
---
model: reasoning_default
tools:
  - get_build_status
---

You investigate CI failures.
```

Kod:

```python
agent = Agent("agents/ci_debugger.md")
answer = await agent("Sprawdź build 123")
```

---

# 27. Structured output — pełny przykład

## Schema

```python
# my_project/schemas/review.py

from typing import Literal
from pydantic import BaseModel, Field


class Issue(BaseModel):
    severity: Literal["low", "medium", "high"]
    description: str
    recommendation: str


class ReviewOutput(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    score: float = Field(ge=0.0, le=1.0)
    issues: list[Issue]
    summary: str
```

## Agent

```markdown
---
name: reviewer
model: reviewer_reasoning
tools:
  - read_file
  - grep
output: my_project.schemas.review:ReviewOutput
max_steps: 20
generation:
  temperature: 0.2
---

# Role

You are a strict software architecture reviewer.

# Rules

- Verify claims instead of assuming they are correct.
- Use repository tools when the answer depends on implementation details.
- Reject solutions with unresolved high-severity issues.
```

## Użycie

```python
from moiryx import Agent

reviewer = Agent("agents/reviewer.md")

review = await reviewer("Oceń implementację modułu cache.")

if review.score < 0.7:
    for issue in review.issues:
        print(issue.severity, issue.description)
```

Nie ma żadnego:

```python
review["score"]
review.output.score
json.loads(review)
```

---

# 28. Przykład ręcznej orkiestracji wielu agentów

```python
planner = Agent("agents/planner.md")
reviewer = Agent("agents/reviewer.md")

coder = Agent("agents/coder.md")

plan = await planner(problem)
review = await reviewer(plan.model_dump_json())

if review.decision == "revise":
    plan = await planner(
        f"""
        Popraw swój plan.

        Recenzja:
        {review.model_dump_json(indent=2)}
        """
    )

implementation_summary = await coder(
    plan.model_dump_json(indent=2)
)
```

To jest pożądany styl.

Jeżeli po kilku miesiącach powtarza się np. `review_loop`, można napisać zwykłą funkcję:

```python
async def review_loop(planner, reviewer, problem, max_rounds=3):
    ...
```

Nie trzeba budować frameworkowego Graph API.

---

# 29. Ładowanie Pydantic output modelu

Funkcja wewnętrzna:

```python
def load_output_model(ref: str) -> type[BaseModel]:
    module_name, sep, class_name = ref.partition(":")
    if not sep:
        raise AgentDefinitionError(...)

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    if not isinstance(cls, type) or not issubclass(cls, BaseModel):
        raise AgentDefinitionError(...)

    return cls
```

Błąd powinien mówić dokładnie:

```text
Could not load output model 'my_project.schemas.review:ReviewOutput'
from agent 'agents/reviewer.md'.
```

---

# 30. Provider registry i model registry

Na podstawie YAML runtime tworzy adaptery providerów:

```python
providers = {
    "local": OpenAICompatibleProvider(...),
    "openrouter": OpenRouterProvider(...),
    "gcp": VertexAIProvider(...),
    "azure": AzureOpenAIProvider(...),
}
```

oraz osobny registry logicznych modeli:

```python
models = {
    "fast_local": ModelConfig(
        alias="fast_local",
        provider="local",
        model="qwen3.8-flash-next",
        ...,
    ),
    "reviewer_reasoning": ModelConfig(
        alias="reviewer_reasoning",
        provider="openrouter",
        model="deepseek/deepseek-v4.1",
        ...,
    ),
}
```

`Agent("agents/reviewer.md")` robi dwa lookupy:

```text
AgentSpec.model_alias
        ↓
ModelRegistry.resolve(alias)
        ↓
ModelConfig.provider
        ↓
ProviderRegistry.resolve(provider)
```

Nie tworzyć wielkiego `if provider == ...` w `Agent`.

Factory może wyglądać:

```python
PROVIDER_FACTORIES = {
    "openai_compatible": OpenAICompatibleProvider.from_config,
    "openrouter": OpenRouterProvider.from_config,
    "azure_openai": AzureOpenAIProvider.from_config,
    "azure_foundry": AzureFoundryProvider.from_config,
    "vertex_ai": VertexAIProvider.from_config,
}
```

Nieznany `type` -> `ConfigurationError`.

---

# 31. OpenAI-compatible adapter

Powinien obsłużyć lokalne endpointy i inne serwery kompatybilne z Chat Completions/Responses w zakresie potrzebnym bibliotece.

Wymagania:

- async client,
- base URL z configu,
- API key opcjonalny/literalny,
- model z rozwiązanego `ModelConfig.model`,
- tool schemas,
- tool calls,
- usage jeśli dostępne,
- timeout,
- retry przez wspólną warstwę runtime.

Nie zakładać, że każdy lokalny endpoint obsługuje wszystkie parametry OpenAI. Adapter powinien wysyłać tylko to, co jest potrzebne.

Dla capability differences można później pozwolić na:

```yaml
capabilities:
  tool_calling: true
  native_structured_output: false
```

---

# 32. OpenRouter adapter

Może dziedziczyć/delegować do OpenAI-compatible transportu.

Powinien obsługiwać:

- `base_url` domyślne dla OpenRoutera,
- API key,
- dodatkowe headers z configu,
- model IDs zawierające `/`,
- usage/cost jeśli API je zwraca.

Nie wiązać reszty biblioteki z OpenRouter-specific formatem.

---

# 33. Azure OpenAI / Foundry

Dwa provider types mogą istnieć osobno, nawet jeśli część kodu jest wspólna.

Powód: konfiguracja, autoryzacja i endpoint semantics mogą się różnić.

`Agent` nie powinien tego wiedzieć.

Przykład:

```yaml
providers:
  azure:
    type: azure_openai
    endpoint: ${AZURE_OPENAI_ENDPOINT}
    api_key: ${AZURE_OPENAI_KEY}
    api_version: ${AZURE_OPENAI_API_VERSION}
```

```yaml
models:
  work_gpt:
    provider: azure
    model: my-deployment
```

```markdown
---
model: work_gpt
---
```

Model identifier jest przekazywany adapterowi bez dodatkowej interpretacji przez `Agent`.

---

# 34. GCP / Vertex AI

Provider alias:

```yaml
providers:
  gcp:
    type: vertex_ai
    project: project-id
    location: europe-west1
```

Preferować standardowe mechanizmy auth GCP (ADC/service account environment) zamiast trzymania prywatnych credentials w kodzie.

Adapter tłumaczy:

- messages,
- tools/function declarations,
- structured/native schema jeśli potrzebne,
- response tool calls,
- usage.

Reszta runtime'u pozostaje provider-agnostic.

---

# 35. Cancellation

Jeżeli task asyncio zostanie anulowany:

```python
job = asyncio.create_task(agent(prompt))
job.cancel()
```

`CancelledError` powinien propagować się prawidłowo.

Nie łapać bezmyślnie `BaseException`.

Tool/subprocess powinien zostać przerwany jeśli to możliwe.

---

# 36. Prompt size i context management

V0.1 nie implementuje automatycznego summary/truncation historii.

Powód: takie mechanizmy łatwo ukrywają błędy i zmieniają zachowanie agenta.

Jeżeli provider zwróci context-length error, adapter/runtime ma przekazać czytelny `ProviderRequestError`.

W przyszłości można dodać jawny `ContextPolicy`.

---

# 37. Deterministyczność i brak ukrytej magii

Biblioteka nie powinna:

- automatycznie zmieniać modelu,
- fallbackować do innego providera bez wiedzy użytkownika,
- automatycznie dodawać niewymienionych user tools,
- wykonywać toola niewymienionego w agent MD,
- poprawiać system prompta heurystycznie poza krótkim wewnętrznym protokołem,
- parsować structured output JSON regexami,
- wykonywać fuzzy-matched toola bez ponownego potwierdzenia przez model,
- semantycznie zgadywać brakujących argumentów tool calla,
- ignorować błędnych schema,
- po cichu ucinać tool outputu,
- po cichu ignorować błędów configu.

Jeśli coś nie może zostać wykonane zgodnie z kontraktem, lepszy jest czytelny wyjątek.

---

# 38. Test strategy

Projekt ma mieć dużo testów jednostkowych, bo jego wartość polega na przewidywalnym plumbing'u.

## 38.1. Config tests

Testować:

- prawidłowe YAML,
- brak pliku,
- env interpolation,
- brak env var,
- unknown provider type,
- provider alias lookup,
- model alias lookup,
- unknown model alias,
- model wskazujący nieistniejącego providera,
- model ID zawierający `/` bez specjalnego parsowania przez `Agent`,
- merge generation defaults: runtime -> model -> agent.

## 38.2. Agent markdown tests

Testować:

- brak frontmatter / brak wymaganego `model` -> czytelny `AgentDefinitionError`,
- pełny frontmatter z `model`,
- unknown model alias,
- empty tools,
- unknown tool,
- invalid max_steps,
- invalid generation,
- valid output model,
- missing output module,
- class not BaseModel,
- default name from filename.

## 38.3. Tool decorator tests

Testować:

- nazwa z funkcji,
- opis z docstringa,
- argument descriptions,
- required/default,
- Optional,
- Literal,
- list,
- nested BaseModel,
- Enum,
- sync tool,
- async tool,
- missing type annotation,
- `*args` rejection,
- duplicate name,
- function remains directly callable.

## 38.4. Tool executor tests

Testować:

- poprawny input,
- validation error,
- execution error,
- timeout,
- result serialization,
- output truncation,
- sync through thread,
- async execution.

## 38.5. Agent loop tests

Użyć fake providera.

Scenariusze:

1. final text w pierwszym kroku,
2. tool -> final text,
3. kilka tool calls -> final text,
4. tool error -> model poprawia -> final text,
5. max steps,
6. response bez content i tools -> protocol error,
7. dwa równoległe calls tego samego Agent nie dzielą messages.

## 38.6. Tool-call repair tests

Testować co najmniej:

1. valid call przechodzi bez repair,
2. arguments jako JSON string -> parse -> valid call,
3. double-encoded JSON -> jednoznaczne rozpakowanie,
4. wrapper `{"arguments": {...}}` -> naprawa tylko jeśli wewnętrzny obiekt przechodzi schema,
5. Pydantic-safe coercion, np. `"42" -> 42`,
6. malformed JSON -> feedback -> model zwraca poprawiony call,
7. unknown tool -> sugestia, ale brak automatycznego wykonania podobnej nazwy,
8. missing required arg -> model retry, bez zgadywania wartości,
9. dodatkowy nieznany argument -> validation feedback, nie silent drop,
10. batch z jednym valid i jednym invalid call -> żaden nie zostaje wykonany przed korektą,
11. repeated identical invalid call -> repair budget się wyczerpuje,
12. po wyczerpaniu -> `ToolCallRepairError`,
13. repair events trafiają do trace,
14. mutujący tool nie jest wykonywany przed zakończeniem całego preflightu.

## 38.7. Structured output tests

1. valid final tool -> Pydantic object,
2. invalid final args -> validation feedback -> poprawka,
3. plain text zamiast final tool -> corrective round,
4. final tool + normal tool jednocześnie -> protocol correction,
5. kilka final tool calls -> error/correction,
6. retry budget exhausted -> `StructuredOutputError`,
7. nested Pydantic output,
8. Enum/Literal/constraints,
9. provider bez tools/native structured -> `ProviderCapabilityError`.

## 38.8. Provider adapter tests

Mockować transport/SDK. Nie wymagać prawdziwych kluczy w CI.

Testy live oznaczyć jako `integration` i uruchamiać tylko po ustawieniu odpowiednich env vars.

---

# 39. Acceptance criteria v0.1

Implementacja jest gotowa, jeśli poniższe przykłady działają bez hacków.

## AC1 — tekstowy agent bez tooli

`agents/simple.md`:

```markdown
---
model: fast_local
---

Answer the user.
```

```python
agent = Agent("agents/simple.md")
result = await agent("Hello")

assert isinstance(result, str)
```

## AC2 — agent wykonujący built-in tool

`agents/reader.md`:

```markdown
---
model: fast_local
tools:
  - read_file
---

Read the requested file and answer the question.
```

```python
agent = Agent("agents/reader.md")
result = await agent("What is in README.md?")
```

Runtime wykonuje `read_file`, przekazuje wynik do modelu i zwraca dopiero finalną wiadomość modelu.

## AC3 — custom `@tool`

```python
@tool
async def get_number(name: str) -> int:
    """
    Return a number for a name.

    Args:
        name: Name to look up.
    """
    return 123
```

Po imporcie modułu agent może użyć `get_number` wpisanego w `.md` bez ręcznego schema definition.

## AC4 — structured output

```python
agent = Agent("agents/reviewer.md")
review = await agent("Review this")

assert isinstance(review, ReviewOutput)
assert isinstance(review.score, float)
```

Użycie:

```python
review.score
review.issues
```

bez wrapperów i dictów.

## AC5 — nested structured output

```python
review.issues[0].severity
review.issues[0].recommendation
```

działa normalnie jako Pydantic objects.

## AC6 — agent bez schema zwraca ostatnią wiadomość

Model może zrobić 5 tool calls, ale user dostaje wyłącznie:

```python
str
```

z finalnego assistant message.

## AC7 — model alias rozwiązuje provider i model

```yaml
providers:
  myrouter:
    type: openrouter
    ...

models:
  strong_reasoning:
    provider: myrouter
    model: vendor/model
```

`agents/foo.md`:

```markdown
---
model: strong_reasoning
---
```

```python
Agent("agents/foo.md")
```

działa bez podawania providera/modelu w kodzie.

## AC8 — model id ze slashami

```yaml
models:
  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1
```

`Agent("agents/foo.md")` zachowuje concrete model ID dokładnie jako `deepseek/deepseek-v4.1`; `Agent` nie parsuje go po slashach.

## AC9 — concurrency

```python
results = await asyncio.gather(
    agent("A"),
    agent("B"),
)
```

nie miesza historii.

## AC10 — brak parsowania JSON z tekstu

Test powinien jawnie potwierdzić, że structured agent zwracający:

````text
```json
{"score": 1.0}
```
````

jako plain text nie jest uznany automatycznie za sukces structured output.

## AC11 — błędny tool call jest naprawiany bez niebezpiecznego zgadywania

Fake provider zwraca kolejno:

1. call do `read_files` zamiast `read_file`,
2. po feedbacku poprawny `read_file`,
3. final answer.

Runtime ma:

- nie wykonać automatycznie `read_file` za pierwszym razem,
- przekazać modelowi sugestię poprawnej nazwy,
- wykonać dopiero jawnie poprawiony call,
- zakończyć run sukcesem.

Analogiczny test dla invalid arguments ma potwierdzić, że żaden call z batcha nie jest wykonany, dopóki cały batch nie przejdzie preflight validation.

---

# 40. Kolejność implementacji

Codex powinien implementować w małych etapach z testami.

## Etap 1 — skeleton i config

- `pyproject.toml`,
- package layout,
- error hierarchy,
- config loader,
- env interpolation,
- provider registry config,
- model registry + model aliases,
- generation defaults merge,
- tests.

## Etap 2 — agent spec loader

- YAML frontmatter,
- Markdown body,
- `AgentSpec`,
- output model loader,
- tests.

Na tym etapie tool registry może mieć stub.

## Etap 3 — tool system

- registry,
- `@tool`,
- introspection,
- dynamic Pydantic input model,
- docstring parsing,
- sync/async executor,
- serialization,
- timeout,
- errors,
- tool-call preflight + repair policy,
- repair feedback i retry budget,
- tests.

## Etap 4 — fake provider + runtime loop

Najpierw bez prawdziwych providerów.

- message models,
- provider protocol,
- fake scripted provider,
- text agent loop,
- tool loop,
- max steps,
- tests.

## Etap 5 — structured output

- output schema,
- internal final tool,
- Pydantic validation,
- repair rounds,
- retry budget,
- tests.

To jest krytyczny etap. Nie implementować go regexami ani tekstowym JSON parsingiem.

## Etap 6 — OpenAI-compatible

- async client,
- tool schema mapping,
- tool call parsing,
- usage,
- integration test z mockiem,
- opcjonalny live test z lokalnym endpointem.

## Etap 7 — built-in filesystem/shell tools

- workspace boundary,
- read/write/edit/list/glob/grep/shell,
- timeout,
- truncation,
- tests.

## Etap 8 — OpenRouter

- config,
- headers,
- model mapping,
- adapter tests.

## Etap 9 — Azure OpenAI / Foundry

- adapter(y),
- config,
- tests z mock transportem.

## Etap 10 — GCP Vertex AI

- adapter,
- auth handling,
- tools mapping,
- usage,
- tests.

## Etap 11 — tracing i polish

- run IDs,
- standard logging,
- optional JSONL trace,
- secret redaction,
- README/examples.

---

# 41. Definition of done dla Codexa

Codex nie powinien kończyć pracy tylko dlatego, że „kod się kompiluje”.

Wymagane:

1. `pytest` przechodzi.
2. `ruff check` przechodzi.
3. Typowanie (`mypy`/`pyright`) przechodzi dla kodu biblioteki w sensownym strictness.
4. Publiczny przykład z README działa.
5. Structured output zwraca instancję Pydantic, nie dict/wrapper.
6. Tekstowy agent zwraca `str` z ostatniego assistant message.
7. `@tool` generuje schema z funkcji i docstringa.
8. Agent bierze tool list wyłącznie z `.md`.
9. Agent constructor ma podstawową formę dokładnie:

   ```python
   Agent("agent.md")
   ```

   Provider i concrete model są rozwiązywane przez `model:` w Markdown -> `models:` w YAML.

10. Wywołanie ma podstawową formę dokładnie:

    ```python
    result = await agent(prompt)
    ```

11. Nie ma dependency na LangChain, LangGraph ani podobny framework.
12. Nie ma własnego workflow DSL.
13. Dwa concurrent calls jednego agenta nie mieszają stanu.
14. Unknown tool/output/model/provider daje czytelny błąd podczas inicjalizacji, jeśli możliwe.
15. Invalid tool calls mają repair feedback i ograniczony retry budget.
16. Runtime nie wykonuje fuzzy-matched tooli ani nie zgaduje brakujących argumentów.
17. Batch tool calli przechodzi pełny preflight przed wykonaniem któregokolwiek calla.
18. Sekrety nie trafiają do logów/trace.

---

# 42. Anti-patterns — czego NIE implementować

## Nie robić tak

```python
agent = Agent(
    model="...",
    tools=[...],
    instructions="...",
    output=ReviewOutput,
)
```

Ma być:

```python
agent = Agent("agents/reviewer.md")
```

Model wybiera frontmatter agenta, a `moiryx.yaml` mapuje logiczny alias na provider + concrete model/deployment.

---

## Nie robić tak

```python
result = await agent.run(prompt)
```

Ma być:

```python
result = await agent(prompt)
```

---

## Nie robić tak

```python
result.output.score
```

Ma być:

```python
result.score
```

---

## Nie robić tak

```python
result["score"]
```

Ma być:

```python
result.score
```

---

## Nie robić tak

```python
@tool("read_ticket")
def read_ticket(...):
    ...
```

Ma być:

```python
@tool
def read_ticket(...):
    ...
```

---

## Nie robić tak

```python
content = response.content
content = content.replace("```json", "")
data = json.loads(content)
```

Structured output ma być wymuszony protokołem/provider capability i walidowany Pydanticiem.

---

## Nie robić tak

```python
graph.add_node(...)
graph.add_edge(...)
graph.compile()
```

Flow to Python:

```python
a = await agent_a(...)
b = await agent_b(a)

if b.score < 0.8:
    a = await agent_a(...)
```

---

# 43. Przykładowy minimalny projekt używający biblioteki

```text
my-app/
├── moiryx.yaml
├── main.py
├── agents/
│   ├── planner.md
│   ├── reviewer.md
│   └── coder.md
└── my_app/
    ├── __init__.py
    ├── schemas/
    │   ├── __init__.py
    │   ├── plan.py
    │   └── review.py
    └── tools/
        ├── __init__.py
        ├── repo.py
        └── ci.py
```

`moiryx.yaml`:

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://localhost:8080/v1
    api_key: dummy

  openrouter:
    type: openrouter
    api_key: ${OPENROUTER_API_KEY}

models:
  planner_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1

  reviewer_reasoning:
    provider: openrouter
    model: deepseek/deepseek-v4.1

  coder_local:
    provider: local
    model: qwen3.8-flash-next

tool_modules:
  - my_app.tools.repo
  - my_app.tools.ci

runtime:
  default_max_steps: 20
  tool_call_repair_attempts: 2
  tool_timeout_seconds: 60
  workspace_root: .
```

`agents/planner.md`:

```markdown
---
model: planner_reasoning
output: my_app.schemas.plan:Plan
---

You are a planning agent. Produce an implementation plan.
```

`agents/reviewer.md`:

```markdown
---
model: reviewer_reasoning
output: my_app.schemas.review:Review
---

Review the supplied plan critically.
```

`agents/coder.md` może analogicznie wskazywać `model: coder_local`.

`main.py`:

```python
import asyncio

from moiryx import Agent


async def main():
    planner = Agent("agents/planner.md")
    reviewer = Agent("agents/reviewer.md")

    plan = await planner("Design feature X")
    review = await reviewer(plan.model_dump_json())

    print(review.score)
    print(review.decision)


if __name__ == "__main__":
    asyncio.run(main())
```

To powinno być normalnym, preferowanym sposobem używania biblioteki.

---

# 44. Przyszłe rozszerzenia — NIE implementować teraz

Architektura może pozwalać później na:

- streaming,
- Session/conversation state,
- multimodal input,
- tool permissions,
- approval przed mutującym toolem,
- MCP adapter,
- remote tools,
- dynamic model-alias routing / provider fallback,
- automatic model fallback,
- budgets/cost limits,
- context policies,
- checkpointing,
- replay runów,
- OpenTelemetry,
- cache,
- parallel tool execution,
- typed agent codegen,
- sandbox container,
- per-tool concurrency limits,
- per-agent provider overrides,
- dynamic tool availability.

Ale rdzeń v0.1 nie może zostać skomplikowany tylko po to, żeby przygotować abstrakcję pod hipotetyczną przyszłość.

Zasada:

> Dodaj abstrakcję dopiero wtedy, gdy co najmniej dwa realne use-case'y wymuszają ten sam powtarzalny pattern.

---

# 45. Podsumowanie architektury

```text
                           Python user flow
                                 │
                                 │
                    result = await agent(prompt)
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │        Agent        │
                      │      agent.md       │
                      └─────────┬───────────┘
                                │
                                ▼
                      ┌─────────────────────┐
                      │      AgentSpec      │
                      │ model alias         │
                      │ instructions        │
                      │ tools               │
                      │ output Pydantic     │
                      │ max_steps           │
                      └─────────┬───────────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
      ┌─────────────────────┐       ┌─────────────────────┐
      │   Model Registry    │       │    Tool Registry    │
      │ alias -> provider   │       │ built-ins           │
      │ alias -> model id   │       │ @tool custom        │
      └──────────┬──────────┘       └──────────┬──────────┘
                 │                             │
                 ▼                             │
      ┌─────────────────────┐                  │
      │  Provider Adapter   │                  │
      │   normalized I/O    │                  │
      └──────────┬──────────┘                  │
                 │                             │
                 └──────────────┬──────────────┘
                                ▼
                      ┌─────────────────────┐
                      │    AgentRuntime     │
                      │ model/tool loop     │
                      │ tool-call repair    │
                      │ structured output   │
                      └─────────┬───────────┘
                                │
                                ▼
              ┌───────────────────────────────────┐
              │ local / OpenRouter / GCP / Azure │
              └───────────────────────────────────┘
```

Najważniejsza filozofia projektu:

```text
Python      = orchestration
Markdown    = agent definition
Pydantic    = data contracts
YAML        = provider/model/runtime configuration
@tool       = custom capabilities
Runtime     = boring plumbing
```

Biblioteka ma być właśnie tym ostatnim: **nudnym, stabilnym plumbingiem**, dzięki któremu kod właściwego systemu jest prosty.

---

# 46. Ostateczny przykład oczekiwanego UX

### Tool

```python
@tool
async def get_release(release_id: int) -> Release:
    """
    Return release data.

    Args:
        release_id: Release identifier.
    """
    ...
```

### Schema

```python
class ReleaseReview(BaseModel):
    ready: bool
    score: float
    blockers: list[str]
```

### Model config

```yaml
models:
  release_reviewer:
    provider: azure
    model: gpt-deployment
```

### Agent

```markdown
---
model: release_reviewer
tools:
  - get_release
output: my_app.schemas:ReleaseReview
max_steps: 15
---

You are a release reviewer.
Verify the release using available tools and determine whether it is ready.
```

### Kod

```python
reviewer = Agent("agents/release_reviewer.md")

review = await reviewer("Review release 42")

if not review.ready:
    print(review.blockers)
```

Jeżeli ten kod pozostaje prosty niezależnie od tego, czy pod spodem providerem jest lokalny llama.cpp, OpenRouter, Vertex AI czy Azure, biblioteka spełnia swój cel.

---

# 47. Publikacja biblioteki — GitHub i PyPI

Ta sekcja nie jest częścią wymaganej implementacji runtime v0.1, ale opisuje zalecany sposób przygotowania projektu do publicznego użycia.

## 47.1. Pozycjonowanie projektu

Nie pozycjonować projektu jako kolejnego „multi-agent frameworka”. Jego wartość jest węższa i bardziej konkretna:

> Thin, config-driven Python agent runtime with Markdown agent definitions, typed Pydantic outputs, provider abstraction, built-in/custom tools and defensive tool-call repair — while orchestration stays plain Python.

Najważniejsze wyróżniki:

- `Agent("agents/foo.md")` jako całe podstawowe API tworzenia agenta,
- agent jest callable: `await agent(prompt)`,
- `agent.md` definiuje model alias, instrukcje, tools i output contract,
- `moiryx.yaml` oddziela agent definition od deploymentu providera/modelu,
- Pydantic output jest zwracany bezpośrednio, bez wrappera i bez dict API,
- brak graph/workflow DSL,
- custom tools przez zwykłe `@tool`, sygnaturę, type hints i docstring,
- defensywny tool-call preflight + repair,
- lokalne endpointy OpenAI-compatible traktowane jako first-class use case,
- ten sam agent może zostać przepięty między local/OpenRouter/GCP/Azure przez config.

## 47.2. Nazwa pakietu

Finalna nazwa biblioteki i pakietu importowanego to `moiryx`.
Przed publikacją nadal trzeba sprawdzić dostępność nazwy dystrybucji na PyPI.
Jeżeli nazwa dystrybucji okaże się zajęta, można wybrać inną nazwę artefaktu
PyPI, ale publiczny import pozostaje:

```python
from moiryx import Agent, tool
```

## 47.3. Kiedy publikować

Git repository warto utworzyć od początku, nawet jeśli projekt jest jeszcze prywatny.

Publiczne PyPI rekomendowane dopiero po dogfoodingu co najmniej kilku realnych scenariuszy, np.:

1. prosty agent tekstowy bez tooli,
2. coding/file agent z wieloma krokami i built-in tools,
3. structured reviewer zwracający nested Pydantic model,
4. custom integration przez `@tool`,
5. ten sam agent uruchomiony co najmniej na dwóch różnych providerach,
6. realny przypadek malformed tool call obsłużony przez repair loop.

Pierwsze publiczne wydanie powinno być oznaczone jako alpha, np. `0.1.0`.

Nie obiecywać stabilności API przed realnym użyciem biblioteki w kilku własnych flow.

## 47.4. Provider dependencies jako extras

Nie zmuszać użytkownika lokalnego llama.cpp do instalowania SDK Google/Azure.

Preferowany układ:

```toml
[project]
dependencies = [
    "pydantic>=2",
    "PyYAML>=6",
    "httpx>=0.27",
    "docstring-parser>=0.16",
]

[project.optional-dependencies]
openai = ["openai>=..."]
google = ["google-genai>=..."]
azure = ["..."]
all = [
    "openai>=...",
    "google-genai>=...",
    "...",
]
```

Dokładne dependencies mają wynikać z finalnych adapterów.

Przykładowe instalacje:

```bash
pip install <package-name>
pip install '<package-name>[openai]'
pip install '<package-name>[google]'
pip install '<package-name>[all]'
```

`openai_compatible` oparty wyłącznie o `httpx` może pozostać w core i nie wymagać oficjalnego OpenAI SDK, jeśli implementacja jest dzięki temu prostsza i stabilniejsza.

## 47.5. Minimalne wymagania przed pierwszym publicznym release

- pełny test suite bez kluczy API,
- fake/scripted provider do deterministycznych testów agent loopa,
- test matrix dla wspieranych wersji Pythona,
- `ruff`, type checker i pytest w CI,
- przykłady local/OpenRouter/GCP/Azure,
- dokumentacja wszystkich publicznych wyjątków,
- changelog,
- semver,
- jawne oznaczenie alpha/beta,
- brak sekretów i realnych endpointów w examples,
- osobne testy live providerów wyłączone domyślnie,
- wheel + sdist budujące się bez warningów,
- sprawdzenie nazwy na PyPI przed konfiguracją publikacji.

## 47.6. Stabilność publicznego API

Najważniejszy kontrakt do utrzymania po publikacji:

```python
agent = Agent("agents/reviewer.md")
result = await agent(prompt)
```

oraz:

```python
@tool
def my_tool(...):
    ...
```

Wewnętrzne klasy takie jak:

- `AgentSpec`,
- `RunContext`,
- `ProviderAdapter`,
- `ToolDefinition`,
- normalized messages,
- repair internals,

nie powinny być przypadkowo eksportowane jako stabilne publiczne API v0.1.

Im mniejsza powierzchnia publiczna, tym łatwiej rozwijać implementację bez łamania użytkowników.

## 47.7. README powinien zaczynać się od UX, nie architektury

Pierwszy przykład publicznej biblioteki powinien wyglądać mniej więcej tak:

`moiryx.yaml`:

```yaml
providers:
  local:
    type: openai_compatible
    base_url: http://localhost:8080/v1

models:
  reviewer:
    provider: local
    model: qwen
```

`agents/reviewer.md`:

```markdown
---
model: reviewer
tools:
  - read_file
output: my_app.schemas:Review
---

Review the implementation critically.
Use repository tools when necessary.
```

Python:

```python
reviewer = Agent("agents/reviewer.md")
review = await reviewer("Review src/cache.py")

print(review.score)
print(review.issues)
```

Dopiero później README powinien wyjaśniać provider adapters, runtime loop i registry.
