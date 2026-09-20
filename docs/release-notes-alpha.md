# 0.1.0a1 — status przed publikacją

Pakiet nie jest jeszcze opublikowany na PyPI. To robocze podsumowanie testów
i ograniczeń pierwszej wersji alpha.

## Zweryfikowano lokalnie

- Testy AC1–AC11, pełną suite offline, lint i mypy.
- Wheel i sdist: metadane MIT, changelog, brak lokalnych sekretów oraz instalację
  wheel w czystym Pythonie 3.12.
- Macierz GitHub CI na Pythonie 3.11 i 3.12 oraz job budowy artefaktów
  przeszły po pierwszym pushu do repozytorium.
- Mały smoke test tekstowy tego samego agenta na lokalnym llama-swap (Bonsai)
  i OpenRouter (`inclusionai/ling-3.0-flash-vl:free`). Testy function calling
  i JSON schema wykonano lokalnie. Konfiguracja użyta do live testów pozostaje
  prywatna i nie jest częścią repozytorium.

## Otwarte kroki

- Potwierdzić dostępność nazwy i skonfigurować publikację na PyPI. Samo
  przygotowanie artefaktów nie jest zgodą na publikację.

`shell` nie jest sandboxem. Obsługa function calling i JSON schema przez
lokalne modele zależy od modelu i jego chat template; smoke test jednego modelu
nie stanowi gwarancji dla innych.
