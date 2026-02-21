# 🤖 Assistente Acadêmico Inteligente (IA + RAG)

Este projeto é uma solução completa de atendimento automatizado para alunos via Telegram. Ele utiliza a técnica de **RAG (Retrieval-Augmented Generation)**, permitindo que a Inteligência Artificial responda dúvidas baseando-se em documentos reais e atualizados (PDFs, Horários, Ementas, etc.), com foco especial em privacidade, velocidade e baixo custo de manutenção.

O sistema foi otimizado para rodar em hardware doméstico (Windows/Mac/Linux) ou em servidores de pequeno porte como o **Raspberry Pi 4 (8GB)**.

---

## 🌟 Funcionalidades de Elite

*   **Busca Semântica Avançada (RAG)**: O bot não apenas conversa, ele "lê" seus documentos. Suporta arquivos `.pdf`, `.docx`, `.txt`, `.csv` e `.md`.
*   **Gestão Híbrida de Provedores**:
    *   **Local (Ollama)**: Privacidade total e custo zero usando modelos como `Llama3` ou `Qwen3`.
    *   **Nuvem (OpenRouter)**: Acesso a modelos de ponta (GPT-4o, Claude 3.5) com latência reduzida.
*   **Limpeza Inteligente de Fórmulas Matémativas**: Tradução automática de LaTeX para texto simples (ex: `\frac{a}{b} -> (a/b)`), garantindo que o aluno receba respostas legíveis no celular.
*   **Controle de Fluxo e Segurança**:
    *   **Rate Limiting**: Proteção contra spam de mensagens por usuário.
    *   **Admin Dashboard**: Uma interface PyQt6 completa para monitorar logs, trocar modelos e gerenciar a base de conhecimento.
*   **Comandos Dinâmicos via Telegram**: Administradores podem gerenciar o bot sem sair do celular.
*   **Otimização para Raspberry Pi**: Modo "Headless" (CLI) com script de instalação automatizado.

---

## 🛠️ Arquitetura do Sistema

O projeto é dividido em módulos para garantir estabilidade:
- **`main_window.py`**: Interface administrativa (PyQt6). centraliza configurações e monitoramento.
- **`telegram_controller.py`**: O "cérebro" das interações. Gerencia sessões, comandos e fluxo RAG.
- **`rag_repository.py`**: Motor de busca vetorial utilizando **ChromaDB**.
- **`ingest_worker.py`**: Processo em segundo plano que evita travamentos da interface e conflitos de escrita no banco de dados.

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
**O que o script faz?**
- Instala o **Ollama** automaticamente.
- Baixa os modelos de embedding recomendados: `nomic-embed-text` (Leve) e `qwen3-embedding` (Preciso).
- Cria o ambiente virtual e instala dependências.
- Configura o serviço de inicialização automática (**systemd**).

### Fluxo de Trabalho de Alta Performance
Dica de mestre: Você pode gerar o banco de dados de conhecimento no seu PC (mais rápido) e simplesmente copiar a pasta `db_atendimento` para o Raspberry Pi. O sistema reconhecerá os arquivos instantaneamente!

---

## 🕹️ Comandos de Administrador (Telegram)

Para IDs configurados como administrador, os seguintes comandos são habilitados:

*   `/ia [nome_do_modelo]`: Lista modelos disponíveis ou troca o modelo de geração.
*   `/embedding [modelo]`: Lista ou altera o modelo de busca vetorial.
*   `/limpar`: Apaga toda a base de conhecimento (necessário ao trocar de modelo de embedding).
*   `/status`: Relatório de saúde, uso de memória e latência do sistema.
*   `/aviso [texto]`: Envia um comunicado para TODOS os usuários do bot.
*   `/admin_summary [dias]`: A IA analisa os logs e gera um resumo dos principais problemas levantados pelos alunos.
*   **Envio de Arquivos**: Envie um PDF/TXT diretamente para o bot no chat privado para adicioná-lo à base instantaneamente.

---

## 📁 Organização de Pastas de Conhecimento

O bot monitora a pasta `arquivos` e indexa:
1.  **`horario*.*`**: Arquivos de PDF/Imagens vinculados ao botão "Horário".
2.  **`cronograma*.*`**: Arquivos vinculados ao botão "Cronograma".
3.  **`materiais.txt`**: Link de pastas ou orientações fixas.
4.  **`faq.txt`**: Base de perguntas frequentes para resposta rápida.

---

## ⚙️ Configurações Técnicas (`config.json`)

| Parâmetro | Descrição | Sugestão |
| :--- | :--- | :--- |
| `ai_provider` | `ollama` ou `openrouter` | `openrouter` (para RPi4) |
| `embedding_provider` | `ollama` ou `openrouter` | `ollama` (Velocidade local) |
| `ollama_embedding_model` | Modelo de busca local | `nomic-embed-text` |
| `rag_k` | Quantidade de trechos recuperados | `8` |
| `rate_limit_per_minute` | Teto de mensagens/usuário | `10` |
| `chroma_dir` | Local físico do banco | `C:/bot/db` ou `/home/pi/db` |

---

## 📊 Privacidade e Segurança

Nenhuma conversa é enviada para treinamento de modelos de terceiros se você usar o modo 100% local. Caso use o modo híbrido, as mensagens passam pelo OpenRouter de forma anonimizada. Os arquivos originais (PDFs) permanecem localmente no seu hardware, sendo enviados para a IA apenas trechos específicos para resposta.

---
**Desenvolvido para facilitar o suporte acadêmico e democratizar o acesso à informação.** 📚🤖
