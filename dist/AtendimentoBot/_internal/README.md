# 🤖 Assistente Acadêmico Inteligente (IA + RAG)

Este projeto é uma solução completa de atendimento automatizado para alunos via Telegram. Ele utiliza a técnica de **RAG (Retrieval-Augmented Generation)**, permitindo que a Inteligência Artificial responda dúvidas baseando-se em documentos reais e atualizados (PDFs, Horários, Ementas, etc.), com foco especial em privacidade, velocidade e baixo custo de manutenção.

O sistema foi otimizado para rodar em hardware doméstico (Windows/Mac/Linux) ou em servidores de pequeno porte como o **Raspberry Pi 4 (8GB)**.

---

## 🌟 Funcionalidades de Elite

*   **Busca Semântica Avançada (RAG)**: O bot não apenas conversa, ele "lê" seus documentos. Suporta arquivos `.pdf`, `.docx`, `.txt`, `.csv` e `.md`.
*   **Gestão de Lembretes Inteligentes**: Agende comandos de voz ou texto via `/lembrete` para que o bot envie avisos automáticos em datas específicas (ex: vésperas de prova).
*   **Gestão Híbrida de Provedores**:
    *   **Local (Ollama)**: Privacidade total e custo zero usando modelos como `Llama3` ou `Qwen3`.
    *   **Nuvem (OpenRouter)**: Acesso a modelos de ponta (GPT-4o, Claude 3.5) com latência reduzida.
*   **Limpeza Inteligente de Fórmulas Matémativas**: Tradução automática de LaTeX para texto simples, garantindo que o aluno receba respostas legíveis no celular.
*   **Controle de Fluxo e Segurança**:
    *   **Rate Limiting**: Proteção contra spam de mensagens por usuário.
    *   **Admin Dashboard**: Interface PyQt6 completa para monitorar logs detalhados, trocar modelos e gerenciar a base de conhecimento.
*   **Gestão Remota Total**: Administradores podem monitorar hardware, atualizar o sistema e reiniciar o bot diretamente pelo Telegram.

---

## 🛠️ Arquitetura do Sistema

O projeto é dividido em módulos para garantir estabilidade:
- **`main_window.py`**: Interface administrativa (PyQt6). centraliza configurações e monitoramento.
- **`telegram_controller.py`**: O "cérebro" das interações. Gerencia sessões, comandos, agendamentos e fluxo RAG.
- **`rag_repository.py`**: Motor de busca vetorial utilizando **ChromaDB**.
- **`log_observer.py`**: Interceptor de logs que permite visualizar a atividade do bot tanto no terminal quanto na interface gráfica.

---

## 🖥️ Instalação no Computador (Windows/Linux/Mac)

1.  **Requisitos**: Python 3.13+ e o gerenciador de pacotes `pip`.
2.  **Clone e Instalação**:
    ```bash
    git clone https://github.com/demusis/atendimento_alunos_bot.git
    cd atendimento_alunos_bot
    pip install -r requirements.txt
    ```
3.  **Configuração Inicial**:
    - Renomeie `config_example.json` para `config.json`.
    - Insira seu **Telegram Token** (obtido via @BotFather).
    - Insira seu **Admin ID** (seu ID numérico, use `/meuid` no bot para descobrir).
4.  **Execução**:
    ```bash
    python main.py
    ```

---

## 🍓 Servidor Raspberry Pi 4 (8GB)

O bot foi desenhado para ser resiliente no RPi4. A recomendação é usar o **Modo Híbrido**: Busca local rápida + Geração na Nuvem.

### Instalação em um Comando
No terminal do seu Raspberry, execute:
```bash
bash install_rp4.sh
```

---

## 🕹️ Painel de Controle Remoto (Comandos de Admin)

Para administradores, o bot oferece um conjunto completo de ferramentas de gestão:

### 🧠 IA & Conhecimento
*   `/ia [modelo]`: Troca o modelo de geração (ex: `Llama3`).
*   `/embedding [modelo]`: Troca o modelo de busca vetorial.
*   `/conhecimento [texto]`: Adiciona uma informação diretamente à base sem precisar de arquivos.
*   `/listar`: Lista todos os documentos indexados.
*   `/remover [nome]`: Apaga um documento específico da base.
*   `/limpar`: Reseta totalmente o banco de dados.

### 📢 Comunicação & Agendamento
*   `/aviso [texto]`: Envia uma mensagem imediata para TODOS os alunos.
*   `/lembrete DD/MM HH:MM [texto]`: Agenda um aviso para ser enviado automaticamente no futuro.
*   `/faq`: Visualiza a base de perguntas frequentes.

### 🖥️ Gestão de Sistema (Hardware)
*   `/status`: Relatório completo de hardware (IP, Memória RAM, Disco, GPU e Latência).
*   `/monitor_cpu`: Lista os processos que mais consomem processamento no momento.
*   `/speedtest`: Realiza um teste de velocidade de internet no servidor.
*   `/ping_ia`: Mede o tempo de resposta do Ollama e OpenRouter.
*   `/atualizar`: Baixa atualizações via Git e reinstala dependências.
*   `/reiniciar_bot`: Reinicia o processo do bot remotamente.

---

## ⚙️ Parâmetros Recentes e Requisitos

| Dependência | Versão Mínima | Finalidade |
| :--- | :--- | :--- |
| `psutil` | `5.9.0` | Monitoramento de RAM/Disco |
| `GPUtil` | `1.4.0` | Monitoramento de GPU |
| `speedtest-cli` | `2.1.3` | Teste de conexão |
| `python-telegram-bot` | `21.5` | Motor do chat |

---

## 📊 Privacidade e Segurança

Nenhuma conversa é enviada para treinamento de modelos de terceiros se você usar o modo 100% local. No modo híbrido, as mensagens passam pelo OpenRouter de forma anonimizada. Os arquivos originais (PDFs) permanecem localmente no seu hardware, sendo processados em fragmentos apenas quando necessário para responder aos alunos.

---
**Desenvolvido para facilitar o suporte acadêmico e democratizar o acesso à informação.** 📚🤖
