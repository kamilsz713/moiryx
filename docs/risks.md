# Rejestr ryzyk v0.1

Skala: prawdopodobieństwo i wpływ `Low / Medium / High`. Właścicielem ryzyka
jest epik; konkretna osoba może zostać przypisana po rozpoczęciu prac.

| ID | Ryzyko | Prawd. | Wpływ | Sygnał | Mitigacja / ticket |
|---|---|---:|---:|---|---|
| R-01 | Różne endpointy OpenAI-compatible tylko częściowo wspierają tools | High | High | te same requesty działają wyłącznie u jednego serwera | minimalny request, capabilities overrides, contract tests; MRYX-601–603 |
| R-02 | SDK providerów narzucą typy do core | Medium | High | import SDK pojawia się poza `providers/` | normalized protocol i test granic; MRYX-401, MRYX-901, MRYX-1001 |
| R-03 | Tool repair wykona niezamierzoną mutację | Medium | High | fuzzy mapping lub częściowy batch | conservative repair, full preflight i side-effect sentinel tests; MRYX-305–307 |
| R-04 | Structured output będzie pozornie poprawny, ale niezgodny z modelem | Medium | High | parsowanie final text lub zwrot dict | final tool/native schema + `model_validate`; MRYX-501–504 |
| R-05 | Równoległe runy wymieszają historię lub trace | Medium | High | flaky testy albo messages z innego promptu | per-call `RunContext` i osobne pliki run ID; MRYX-406, MRYX-1102 |
| R-06 | Sekret trafi do logów/raw response | Medium | High | sentinel secret znaleziony w artefakcie | centralna redakcja i opt-in raw debug; MRYX-1103 |
| R-07 | `shell` będzie miał niejednoznaczną semantykę między systemami | High | Medium | quoting działa inaczej na Windows/Linux | jawnie zdefiniować parsing/platform behavior przed implementacją i dodać matrix testów; MRYX-706 |
| R-08 | Extras providerów spowodują konflikty lub ciężki core install | Medium | Medium | instalacja core pobiera Azure/Google SDK | osobne extras i clean-env build matrix; MRYX-903, MRYX-1002, MRYX-1105 |
| R-09 | Konfiguracja cachowana utrudni testy i zmianę env | Medium | Medium | zależność od kolejności testów | wewnętrzny reset/isolated loader fixture; MRYX-101 |
| R-10 | Trace i tool output nadmiernie powiększą kontekst/dysk | Medium | Medium | wielkie JSONL lub requesty | jawny output limit, trace opt-in, brak raw domyślnie; MRYX-304, MRYX-1102 |
| R-11 | Nazwa dystrybucji PyPI będzie niedostępna | Medium | Medium | collision podczas przygotowania release | wcześnie sprawdzić nazwę dystrybucji; import package pozostaje `moiryx`; MRYX-1107 |
| R-12 | Scope creep opóźni stabilny core | High | Medium | praca nad streamingiem/Session przed AC1–AC11 | non-goals i milestone gates; ADR-002, MRYX-1106 |

## Ryzyka wymagające spike'a

Przed rozpoczęciem odpowiedniego ticketu należy ograniczyć spike do ustalenia
jednego kontraktu i krótkiego proof of concept:

- Azure Foundry: rzeczywisty wariant endpointu i biblioteka kliencka
  (MRYX-902);
- Vertex AI: odwzorowanie function calling i native schema w wybranym SDK
  (MRYX-1001);
- `shell`: jednoznaczne zachowanie command string na wspieranych platformach
  (MRYX-706).

Spike nie zmienia publicznego API. Jeśli wynik wymaga zmiany kontraktu,
powstaje nowy ADR i aktualizacja specyfikacji przed implementacją.

## Przegląd ryzyk

Rejestr należy przejrzeć na bramkach M2, M4, M6 i przed MRYX-1107. Ryzyko może
zostać zamknięte dopiero z linkiem do testu, decyzji albo wyniku dogfood, który
potwierdza mitigację.
