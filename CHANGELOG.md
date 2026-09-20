# Changelog

Wszystkie istotne zmiany projektu są zapisywane tutaj. Wersje używają
semantyki PEP 440; `0.1.0a1` oznacza pierwszą wersję alpha, jeszcze
nieopublikowaną na PyPI.

## 0.1.0a1 — przygotowywane

### Dodano

- Deklaratywnych agentów Markdown z konfiguracją `moiryx.yaml`, aliasami
  modeli i publicznym API `Agent` oraz `@tool`.
- Pętlę tekstową z narzędziami, walidacją argumentów, konserwatywną naprawą
  błędnych wywołań i niezależnymi budżetami retry.
- Wyniki Pydantic, także zagnieżdżone, przez synthetic final tool lub
  natywny JSON schema, zależnie od capabilities providera.
- Adaptery OpenAI-compatible (w tym llama-server/llama-swap), OpenRouter,
  Azure OpenAI, Azure Foundry i Vertex AI.
- Narzędzia workspace do odczytu, wyszukiwania, zapisu i edycji plików,
  a także jawnie włączany `shell`.
- Zdarzenia runu, opcjonalny JSONL trace i centralną redakcję sekretów.
- Deterministyczną suite AC1–AC11, przykłady użytkowe i macierz CI.

### Ograniczenia alpha

- Brak streamingu, sesji, multimodalności i automatycznego fallbacku.
- `shell` nie jest sandboxem; udostępniaj go tylko w zaufanym środowisku.
- Zgodność modeli lokalnych z function calling i JSON schema zależy od modelu
  oraz jego chat template.

Szczegóły dogfoodingu i otwarte bramy wydania są w
[`docs/release-notes-alpha.md`](docs/release-notes-alpha.md).
