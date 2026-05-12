# Monitor Cardiago - MedCare MVP 🚀

Sistema de telemetria médica em tempo real com análise preditiva por IA.

## Tecnologias
- **Backend:** FastAPI, SQLite
- **Frontend:** Tailwind CSS, JavaScript Vanilla
- **Integrações:** Pulsoid API (WebSockets para BPM real-time), Google Gemini (LLM para Insights Clínicos)

## Como rodar o MVP
1. Crie o ambiente virtual: `python -m venv venv` e ative.
2. Instale as dependências: `pip install fastapi uvicorn google-genai python-dotenv jinja2`
3. Crie seu `.env`: `cp .env.example .env` (ou use o `.env` já incluído no projeto).
4. Preencha as variáveis:
   - `GEMINI_API_KEY="cole_sua_chave_do_google_aqui"`
   - `PULSOID_TOKEN="cole_seu_token_manual_do_pulsoid_aqui"`
5. Rode o servidor: `uvicorn main:app --reload`
6. Acesse `http://localhost:8000`.
