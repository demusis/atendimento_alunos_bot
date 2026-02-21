# Bot de Atendimento Acadêmico com IA (RAG)

Este projeto é um assistente inteligente para atendimento de alunos via Telegram. Ele utiliza **RAG (Retrieval-Augmented Generation)** para responder perguntas com base em documentos PDF/TXT fornecidos (ementas, horários, calendários) e interage através de uma interface local amigável.

![Interface Gráfica](https://via.placeholder.com/800x400.png?text=Interface+do+Sistema)

## 🚀 Funcionalidades Principais

1.  **Respostas Contextuais (RAG)**: O bot lê seus documentos e responde apenas com base neles.
2.  **Contexto Temporal Inteligente**: Sabe que dia é hoje para responder perguntas como "Tem aula hoje?".
3.  **Suporte Híbrido de IA**:
    *   **Local (Ollama)**: Totalmente gratuito e privado, rodando no seu PC.
    *   **Nuvem (OpenRouter)**: Opcional, para usar modelos como GPT-4 ou Claude se desejar maior precisão.
4.  **Botões Interativos**: Menu visual no Telegram (/start) para facilitar a navegação.
5.  **Modo Administrador**:
    *   **Ingestão Remota**: Adicione PDFs arrastando-os para o chat do Telegram.
    *   **Resumo IA**: Gere relatórios automáticos sobre o que os alunos estão perguntando.

---

## 🛠️ Instalação e Configuração

### Pré-requisitos
- Python 3.10+
- [Ollama](https://ollama.com) instalado (para modo local).

### Passo a Passo
1.  **Clone/Baixe** este repositório.
2.  **Instale as dependências**:
    ```bash
    pip install -r requirements.txt
    ```
    *Bibliotecas principais: `python-telegram-bot`, `langchain`, `chromadb`, `PyQt6`.*
3.  **Execute a interface**:
    ```bash
    python main.py
    ```

### Na Interface
1.  Vá na aba **Configuração**.
2.  Insira seu **Token do Telegram** (crie um com o @BotFather).
3.  Escolha o Provedor (Ollama ou OpenRouter).
4.  **Salve** (o salvamento é automático).
5.  Vá na aba **Terminal** e clique em **Iniciar Bot**.

---

## 🔧 Configuração Avançada (Modo Admin)

Para usar comandos exclusivos de administrador, você precisa definir seu ID do Telegram.

1.  Abra o arquivo `config.json` na pasta do projeto.
2.  Localize a chave `"admin_id": ""`.
3.  Insira seu ID numérico (ex: `"admin_id": "123456789"`).
    *   *Dica: Mande uma mensagem para o @userinfobot no Telegram para descobrir seu ID.*
4.  Reinicie o bot.

### Comandos de Admin
| Comando | Descrição |
| :--- | :--- |
| `/admin_ingest` | Exibe instruções. Arraste um arquivo PDF/TXT para o chat para adicioná-lo à base. |
| `/admin_summary` | Abre menu para gerar **Resumo via IA** das interações (24h, 7 dias, 30 dias). |
| `/insight` | Pergunta livre para a IA analisar os logs. Ex: `/insight 7 O que falam do professor X?` |

---

## 🎨 Personalização dos Botões

Os botões do menu `/start` são configurados no código para máxima flexibilidade.

**Arquivo**: `telegram_controller.py`
**Método**: `_cmd_start`

```python
keyboard = [
    [
        InlineKeyboardButton("NOVO BOTÃO", callback_data="btn_novo"),
        # ...
    ]
]
```

Para alterar a **resposta** do botão, edite o método `_handle_button` no mesmo arquivo:

```python
elif query.data == "btn_novo":
    await query.edit_message_text(text="Sua resposta personalizada aqui.")
```

---

## 📊 Analytics e Logs

O sistema salva um histórico anonimizado de interações em `history.jsonl`.
-   **Formato**: JSON Lines.
-   **Dados**: Timestamp, Hash do Usuário, Pergunta, Tamanho da Resposta.
-   **Privacidade**: O ID do usuário é criptografado (Hash SHA-256).

O comando `/admin_summary` lê este arquivo para gerar insights sobre as dúvidas mais comuns dos alunos.

---

## 🧠 Arquitetura

O sistema segue uma arquitetura modular limpa:
-   `main_window.py`: Interface Gráfica (PyQt6).
-   `telegram_controller.py`: Lógica do Bot e Comandos.
-   `rag_repository.py`: Gerenciamento do Banco Vetorial (ChromaDB).
-   `ollama_client.py` / `openrouter_client.py`: Adaptadores de IA.
-   `analytics_manager.py`: Gestão de logs e métricas.
