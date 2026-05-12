# Agente: Monitor Cardiago (Medical Telemetry System)

## 🎯 Objetivo
Prover monitoramento cardíaco em tempo real para médicos e pacientes, utilizando a API do Pulsoid para BPM contínuo e a IA do Gemini para insights clínicos preditivos.

## 🏗️ Arquitetura do Sistema
- **Backend:** FastAPI (Python) servindo rotas da API e templates HTML.
- **Banco de Dados:** SQLite (vitals.db).
- **Frontend:** HTML/JS puro com Tailwind CSS (Arquitetura BioLink/Dark Mode).
- **IoT/Streaming:** WebSocket client-side usando `@pulsoid/socket`.

## 🛡️ Regras de Negócio e UX (Visão Cardiológica)
1. **Login Inteligente (Sem senha complexa para o MVP):**
   - Input formato CRM (ex: CRM/SP123456): redireciona para `/dashboard/medico`.
   - Input formato CPF (apenas números): redireciona para `/dashboard/paciente`.
2. **Painel do Médico (Central de Triagem):**
   - Exibe em grid os "Cards" de cada paciente.
   - Cada card mostra: BPM Atual, Status de Conexão (Adesão do wearable).
   - Botão "Gerar Insight IA" em cada paciente.
3. **Painel do Paciente:** Viewport exclusivo para ver o próprio batimento animado.
