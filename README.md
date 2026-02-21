# 🤖 Bot de Atendimento Acadêmico com IA (RAG)

Este projeto é um assistente inteligente projetado para o atendimento de alunos via Telegram. Ele utiliza a técnica de **RAG (Retrieval-Augmented Generation)** para responder perguntas baseando-se em documentos reais (Cronogramas, Horários, Ementas) e pode ser executado tanto em computadores pessoais quanto em servidores de baixo custo como o **Raspberry Pi 4**.

---

## 🌟 Funcionalidades Principais

*   **Busca Semântica (RAG)**: Responde dúvidas acadêmicas com base exclusiva no conteúdo dos seus documentos.
*   **Menu de Acesso Rápido**: Botões interativos para "Horário", "Cronograma" e "Materiais".
*   **Gestão de Arquivos**: Envio direto de documentos PDF/DOCX/JPG através de pastas físicas ou via chat (para admins).
*   **Híbrido de IA**: Suporte para modelos locais (**Ollama**) ou em nuvem (**OpenRouter**).
*   **Dual Mode**: Interface Gráfica (GUI) para iniciantes e Modo Linha de Comando (CLI) para servidores.

---

## 🖥️ Instalação no PC (Windows)

A versão para Windows possui uma interface amigável para gerenciamento e visualização de logs em tempo real.

### Pré-requisitos
- Python 3.10 ou superior instalado.
- [Ollama](https://ollama.com) (opcional, se for usar IA local).

### Passo a Passo
1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/demusis/atendimento_alunos_bot.git
    cd atendimento_alunos_bot
    ```
2.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure o arquivo inicial:**
    - Renomeie o arquivo `config_example.json` para `config.json`.
    - Insira seu **Token do Telegram** e sua chave **OpenRouter** (se for o caso).
4.  **Inicie o aplicativo:**
    ```bash
    python main.py
    ```
5.  **Na Interface:**
    - Use a aba **Configuração** para ajustar modelos, temperatura e o parâmetro **K (Memória de Busca)**.
    - Na aba **Terminal**, clique em **Iniciar Bot**.

---

## 🍓 Instalação no Raspberry Pi 4 (Linux / Headless)

O bot foi otimizado para rodar em modo silencioso no Raspberry Pi 4, economizando memória e CPU.

### Pré-requisitos
- **Raspberry Pi OS (64-bit)** recomendado.
- Python 3.10+.

### Instalação Automatizada
Para facilitar a instalação no RPi4, utilize o script de automação incluso:

1.  **Dê permissão ao instalador:**
    ```bash
    chmod +x install_rp4.sh
    ```
2.  **Execute a instalação:**
    ```bash
    ./install_rp4.sh
    ```
    *Este script criará o ambiente virtual (venv), instalará as dependências do sistema e do Python, e configurará a pasta do banco de dados automaticamente.*

3.  **Configuração:**
    - Edite o arquivo `config.json` que foi criado automaticamente na pasta raiz com suas credenciais do Telegram e OpenRouter.

4.  **Inicie o bot:**
    ```bash
    ./start_rp4.sh
    ```

---

## 🕹️ Modos de Operação

### Modo GUI (Interface Gráfica)
Basta rodar `python main.py`. Ideal para configuração inicial e monitoramento visual.

### Modo CLI (Texto / Terminal)
Ideal para rodar 24h por dia em servidores. Se o sistema não detectar um monitor, ele entrará neste modo automaticamente, ou você pode forçar via:
```bash
python main.py --cli
```
*   **Encerrar com segurança**: Pressione `CTRL+C` no terminal. O bot salvará os logs e fechará as sessões antes de sair.

---

## 📁 Estrutura da Pasta `arquivos`

O bot gerencia os botões do menu principal baseando-se nos nomes dos arquivos dentro desta pasta:

*   **Botão Horário**: Envia todos os arquivos iniciados com `horario` (ex: `horario_2024.pdf`).
*   **Botão Cronograma**: Envia todos os arquivos iniciados com `cronograma` (ex: `cronograma_algoritmos.docx`).
*   **Botão Materiais**: Exibe o texto personalizado contido no arquivo `materiais.txt`.

---

## 🛠️ Comandos de Administrador

Se o seu ID do Telegram estiver configurado no campo `admin_id` do `config.json`, você terá acesso a:

*   `/status`: Relatório completo da saúde do sistema, latência da IA e estatísticas do banco de dados.
*   `/aviso [mensagem]`: Envia um broadcast para todos os usuários cadastrados.
*   `/ia [modelo]`: Troca o modelo de IA em tempo real via chat.
*   `/prompt [texto]`: Altera as instruções de comportamento da IA sem reiniciar o bot.
*   **Upload de Documentos**: Basta arrastar um arquivo para o chat com o bot e ele será ingerido automaticamente na base RAG.

---

## ⚙️ Configurações Importantes (`config.json`)

*   `rag_k`: Define quantos trechos de documentos a IA lerá antes de responder. (Padrão: 8).
*   `chroma_dir`: Caminho absoluto para a pasta onde o banco vetorial será salvo.
*   `ai_provider`: Define se o bot usa `ollama` ou `openrouter`.

---

## 📊 Analytics e Privacidade

As interações são salvas em `history.jsonl`. O sistema anonimiza os IDs dos usuários via Hash SHA-256 para garantir a privacidade dos alunos, permitindo apenas a análise estatística das dúvidas enviadas.
