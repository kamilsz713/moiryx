# Dokumentacja Moiryx

Ten folder jest źródłem prawdy dla projektu biblioteki `moiryx`. Dokument
wejściowy został zachowany i ujednolicony nazewniczo w
[specification.md](specification.md). Krótsze dokumenty poniżej służą do
codziennej implementacji, planowania i przeglądów.

## Kontrakt nazewniczy

Obowiązuje jeden zestaw nazw:

| Element | Wartość |
|---|---|
| biblioteka i import Pythona | `moiryx` |
| konfiguracja | `moiryx.yaml` |
| nadpisanie ścieżki konfiguracji | `MOIRYX_CONFIG` |
| katalog trace | `.moiryx/runs` |
| bazowy wyjątek | `MoiryxError` |
| wewnętrzny final tool | `__moiryx_submit_result` |
| metadane dekoratora | `__moiryx_tool__` |

Powyższe nazwy są decyzją produktu, a nie placeholderami.

## Mapa dokumentacji

- [Wizja i kontrakt produktu](01-vision-and-contract.md) — cele, granice oraz
  nienegocjowalne API.
- [Architektura](02-architecture.md) — komponenty, przepływ danych i
  odpowiedzialności.
- [Konfiguracja i definicje agentów](03-configuration-and-agents.md) — formaty
  YAML oraz Markdown.
- [Tools, runtime i structured output](04-tools-runtime-and-output.md) —
  wykonanie, bezpieczeństwo oraz naprawa wywołań.
- [Providerzy](05-providers.md) — wspólny kontrakt i zakres adapterów v0.1.
- [Jakość, bezpieczeństwo i wydanie](06-quality-security-release.md) — testy,
  obserwowalność i release gates.
- [Decyzje architektoniczne](decisions.md) — krótkie ADR-y utrwalające
  najważniejsze wybory.
- [Roadmapa](roadmap.md) — kolejność i kamienie milowe.
- [Backlog](tickets/README.md) — epiki, tickety, zależności oraz kryteria
  akceptacji.
- [Macierz śledzenia wymagań](traceability.md) — mapowanie kryteriów
  specyfikacji na tickety i testy.
- [Rejestr ryzyk](risks.md) — ryzyka techniczne, sygnały i działania
  ograniczające.
- [Szablon ticketu](tickets/TEMPLATE.md) — format nowych elementów backlogu.

## Hierarchia źródeł

1. Nienegocjowalne decyzje z [pełnej specyfikacji](specification.md).
2. Zaakceptowane wpisy w [decyzjach architektonicznych](decisions.md).
3. Dokumenty tematyczne w tym folderze.
4. Tickety implementacyjne.

Ticket może doprecyzować sposób wykonania, ale nie może zmienić publicznego API
ani semantyki bezpieczeństwa bez aktualizacji specyfikacji i odpowiedniego ADR.

## Jak prowadzić pracę

Każdy ticket powinien:

- mieć jednego właściciela i jeden zamykalny rezultat;
- wskazywać zależności oraz testy;
- nie mieszać refaktoryzacji niezwiązanej z celem;
- kończyć się przejściem lokalnych kryteriów akceptacji;
- aktualizować dokumentację, jeżeli zmienia kontrakt lub konfigurację.

Statusy backlogu: `Proposed`, `Ready`, `In progress`, `Blocked` i `Done`.
Przejście do `Done` wymaga kodu, testów, lintowania, typowania i aktualnych
dokumentów w zakresie ticketu.
