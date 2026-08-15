# Andanzas — AI Evals

Eval suite for Andanzas, an LLM trip-planning assistant. This repo is the eval
harness, not the product.

## Stack
- deepeval 4.1.8, pytest 9.1.1
- Judge model: Google Gemini via `GeminiModel` (key in `.env` as `GEMINI_API_KEY`)
- venv at `./venv` — always activate before running anything

## Commands
- Run all evals: `venv\Scripts\python.exe -m pytest -v`
- Run one file: `venv\Scripts\python.exe -m pytest test_eval.py -v`

## Conventions
- One eval concern per test file, named `test_<capability>.py`
- Never hardcode API keys; always `os.getenv`
- Test cases live as data, separate from metric definitions