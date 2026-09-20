# Decyzje architektoniczne

Poniższe decyzje mają status `Accepted for v0.1`. Ich zmiana wymaga aktualizacji
pełnej specyfikacji, konsekwencji w backlogu oraz osobnej decyzji zastępującej.

## ADR-001: minimalne publiczne API

**Decyzja:** publicznym wejściem są `Agent` i `tool`; agent jest callable, a
konstruktor przyjmuje tylko plik Markdown.

**Powód:** konfiguracja modelu, narzędzi i outputu pozostaje poza kodem
orkiestrującym, a powierzchnia kompatybilności jest mała.

**Konsekwencja:** ergonomiczne metody `run`, `invoke` i rozbudowany builder są
poza zakresem.

## ADR-002: orkiestracja pozostaje w Pythonie

**Decyzja:** Moiryx nie implementuje graph/workflow/chain DSL.

**Powód:** użytkownik zachowuje kontrolę nad przepływem, debugowaniem,
warunkami i współbieżnością bez frameworkowej semantyki.

**Konsekwencja:** powtarzalny flow może być zwykłą funkcją aplikacji.

## ADR-003: Pydantic jako jedyne źródło structured output

**Decyzja:** sukces structured runu zwraca konkretną instancję `BaseModel`.
Preferowany protokół to zarezerwowany `__moiryx_submit_result` albo native
structured output gwarantowany przez providera.

**Powód:** parsowanie JSON-a z treści Markdown nie gwarantuje kontraktu.

**Konsekwencja:** brak właściwej capability jest błędem, a nie sygnałem do
heurystycznego fallbacku.

## ADR-004: preflight całego batcha tool calli

**Decyzja:** wszystkie calle w odpowiedzi są rozwiązywane, parsowane i
walidowane przed wykonaniem któregokolwiek.

**Powód:** częściowe wykonanie batcha mogłoby mutować stan przed wykryciem
błędu w innym callu.

**Konsekwencja:** jeden błędny call blokuje cały batch i uruchamia repair round.

## ADR-005: repair tylko konserwatywny

**Decyzja:** runtime może poprawiać jednoznaczne problemy transportowe i
syntaktyczne, ale nie wykonuje fuzzy-matched toola ani nie wymyśla argumentów.

**Powód:** bezpieczeństwo i powtarzalność są ważniejsze niż pozorny success
rate.

**Konsekwencja:** sugestia podobnej nazwy trafia do modelu, który musi jawnie
ponowić call.

## ADR-006: izolowany stan runu

**Decyzja:** każdy `await agent(prompt)` tworzy nowy `RunContext`.

**Powód:** brak ukrytej pamięci i bezpieczne `asyncio.gather` na jednej
instancji.

**Konsekwencja:** trwała rozmowa może w przyszłości powstać jako osobny,
wyraźny typ, ale nie jest zachowaniem `Agent`.

## ADR-007: sekwencyjne wykonanie tooli w v0.1

**Decyzja:** poprawny batch tool calli jest wykonywany w kolejności otrzymanej
od modelu.

**Powód:** łatwiejsze debugowanie i bezpieczniejsza semantyka dla operacji
mutujących.

**Konsekwencja:** `parallel_tool_calls` opisuje capability providera, lecz
równoległy executor nie należy do v0.1.

## ADR-008: finalna nazwa Moiryx

**Decyzja:** import, przykłady i identyfikatory projektu używają `moiryx`.

**Powód:** nazwa została ustalona przed rozpoczęciem implementacji.

**Konsekwencja:** stare identyfikatory nie otrzymują aliasów kompatybilności,
bo nie istnieje jeszcze publiczna wersja wymagająca migracji.
