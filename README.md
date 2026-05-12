# Monitor Cardiago - MedCare MVP 🚀

Sistema de telemetria médica em tempo real com análise preditiva por IA.

## Tecnologias
- **Backend:** FastAPI, SQLite
- **Frontend:** Tailwind CSS, JavaScript Vanilla
- **Integrações:** Pulsoid API (WebSockets para BPM real-time), Google Gemini (LLM para Insights Clínicos)

## Como rodar o MVP
1. Crie o ambiente virtual: `python -m venv venv` e ative.
2. Instale as dependências: `pip install fastapi uvicorn google-genai jinja2`
3. Adicione suas chaves de API (`GEMINI_API_KEY` e o Token do Pulsoid) no `.env`.
4. Rode o servidor: `uvicorn main:app --reload`
5. Acesse `http://localhost:8000`.
