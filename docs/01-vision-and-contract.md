# Wizja i kontrakt produktu

## Po co istnieje Moiryx

Moiryx to cienki, konfigurowalny runtime Pythona dla agentów LLM. Usuwa
powtarzalny kod związany z providerami, tool callingiem, walidacją, pętlą
agenta i typed output, pozostawiając użytkownikowi zwykły Python jako warstwę
orkiestracji.

Docelowy użytkownik chce:

- przełączać model lub providera bez zmiany kodu aplikacji;
- definiować rolę agenta w czytelnym Markdownzie;
- otrzymywać `str` albo prawdziwy obiekt Pydantic;
- dodawać narzędzia przez zwykłą funkcję i `@tool`;
- rozumieć każdy krok wykonania i każdy błąd.

## Publiczny kontrakt v0.1

Podstawowe API zawiera dwa symbole:

```python
from moiryx import Agent, tool

reviewer = Agent("agents/reviewer.md")
review = await reviewer("Review src/cache.py")
```

Z tego wynikają twarde reguły:

1. Konstruktor `Agent` przyjmuje wyłącznie ścieżkę pliku definicji.
2. Agent jest wywoływany przez `await agent(prompt)`.
3. Agent bez `output` zwraca finalny `str`.
4. Agent z `output` zwraca bezpośrednią instancję wskazanego `BaseModel`.
5. `@tool` nie przyjmuje nazwy; nazwa pochodzi z funkcji.
6. Kod aplikacji nie zna konkretnego providera ani identyfikatora modelu.
7. Każde wywołanie agenta ma własny stan i historię.

Nie wprowadzamy wrapperów wyników jako domyślnego API, metod `run`/`invoke`,
ani runtime overrides modelu w konstruktorze.

## Zasady produktu

- **Orkiestracja to Python.** Warunki, pętle i współbieżność należą do kodu
  aplikacji.
- **Markdown opisuje agenta.** Frontmatter zawiera metadane, body instrukcję
  systemową.
- **YAML opisuje deployment.** Alias modelu rozwiązuje się do providera i
  konkretnego modelu.
- **Pydantic jest kontraktem danych.** Nie wycinamy JSON-a z tekstu.
- **Runtime ma być nudny.** Małe abstrakcje, jawne błędy, przewidywalny stan.
- **Błąd jest lepszy niż zgadywanie.** Dotyczy szczególnie nazw oraz argumentów
  narzędzi.

## Cele v0.1

- stabilny loader `moiryx.yaml` i definicji agentów;
- tekstowa oraz structured pętla agenta;
- custom tools i bezpieczne built-in tools;
- adaptery `openai_compatible`, `openrouter`, `azure_openai`,
  `azure_foundry` i `vertex_ai`;
- retry, timeouty, bezpieczny tool-call repair;
- logowanie i opcjonalny trace JSONL;
- deterministyczny fake provider oraz pełny zestaw testów bez kluczy API.

## Poza zakresem v0.1

Nie budujemy DSL-a workflow/graph, pamięci trwałej, RAG frameworka, vector
store, schedulerów, serwera HTTP, GUI, bazy danych, distributed workers,
streamingu publicznego, automatycznej kompresji kontekstu, MCP, policy engine
ani automatycznych fallbacków modeli.

Te elementy mogą powstać później tylko jako jawne rozszerzenia, gdy co najmniej
dwa realne przypadki użycia uzasadnią wspólną abstrakcję.

## Mierniki powodzenia

Wydanie v0.1 jest wartościowe, jeżeli:

- trzy podstawowe scenariusze — tekst, tool loop i nested structured output —
  działają bez obejść;
- ten sam agent działa na co najmniej dwóch providerach po samej zmianie YAML;
- niepoprawny tool call jest poprawiany bez wykonania błędnej lub zgadywanej
  operacji;
- równoległe wywołania tej samej instancji nie mieszają stanu;
- użytkownik potrafi zdiagnozować run na podstawie wyjątków, logów i trace;
- publiczne API nadal mieści się w `Agent` i `tool`.
