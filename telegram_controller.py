import logging
import asyncio
import os
import time
from typing import Optional, Dict, Any, List
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config_manager import ConfigurationManager
from ollama_client import OllamaAdapter
from analytics_manager import AnalyticsManager

# Configure logging for this module
logger = logging.getLogger(__name__)

class TelegramBotController:
    """
    Controller class to manage the Telegram Bot.
    Orchestrates message reception, context retrieval, and response generation.
    """

    def __init__(self) -> None:
        """
        Initialize the TelegramBotController.
        Loads configuration and initializes dependencies.
        """
        self.config_manager = ConfigurationManager()
        self.ollama_adapter = OllamaAdapter(base_url=self.config_manager.get("ollama_url", "http://127.0.0.1:11434"))
        
        # ChromaDB config for subprocess worker
        self._chroma_dir = self.config_manager.get("chroma_dir", "") or ""
        self._embedding_model = self.config_manager.get("embedding_model", "llama3:latest")
        self._worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        self.analytics = AnalyticsManager()
        
        self.application: Optional[Application] = None
        self._is_running = False
        self._user_last_greeting: Dict[int, str] = {}  # user_id -> 'YYYY-MM-DD'
        
        # Feature 1: Per-user chat history
        self._chat_history: Dict[int, deque] = {}  # user_id -> deque of (question, answer)
        
        # Feature 3: Rate limiting
        self._user_message_times: Dict[int, list] = {}  # user_id -> list of timestamps

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Strip markdown formatting from LLM responses."""
        import re
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*(.+?)\*', r'\1', text)       # *italic*
        text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)  # ### headers
        return text.strip()

    async def _run_chroma_worker(self, action_data: Dict[str, Any]) -> Any:
        """
        Run a ChromaDB operation in a subprocess to avoid SQLite DLL conflicts with PyQt6.
        """
        import json, subprocess, sys
        
        action_data["chroma_dir"] = self._chroma_dir
        action_data["model_name"] = self._embedding_model
        worker_data = json.dumps(action_data)
        
        loop = asyncio.get_running_loop()
        
        def _run():
            result = subprocess.run(
                [sys.executable, self._worker_script],
                input=worker_data,
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Processo encerrado inesperadamente"
                raise RuntimeError(f"ChromaDB worker failed (exit {result.returncode}): {error_msg}")
            output = result.stdout.strip()
            if not output:
                raise RuntimeError("ChromaDB worker retornou sem dados")
            last_line = output.split('\n')[-1]
            data = json.loads(last_line)
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "Erro desconhecido"))
            return data["result"]
        
        return await loop.run_in_executor(None, _run)

    async def start(self) -> None:
        """
        Start the Telegram Bot (Long Polling).
        """
        token = self.config_manager.get("telegram_token")
        if not token:
            logger.error("Token do Telegram não encontrado na configuração.")
            return

        # Build Application
        self.application = Application.builder().token(token).build()

        # Add Handlers - User commands
        self.application.add_handler(CommandHandler("inicio", self._cmd_start))
        self.application.add_handler(CommandHandler("start", self._cmd_start))  # alias
        self.application.add_handler(CommandHandler("ajuda", self._cmd_ajuda))
        self.application.add_handler(CommandHandler("listar", self._cmd_list_documents))
        self.application.add_handler(CommandHandler("remover", self._cmd_delete_document))
        self.application.add_handler(CommandHandler("ia", self._cmd_list_models))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("aviso", self._cmd_aviso))
        self.application.add_handler(CommandHandler("prompt", self._cmd_prompt))
        self.application.add_handler(CommandHandler("conhecimento", self._cmd_add_knowledge_text))
        self.application.add_handler(CommandHandler("meuid", self._cmd_my_id))
        self.application.add_handler(CommandHandler("estatisticas", self._cmd_admin_summary))
        # Admin commands
        self.application.add_handler(CommandHandler("bd", self._cmd_admin_help))
        self.application.add_handler(CommandHandler("limpar", self._cmd_clear_database))
        self.application.add_handler(CommandHandler("admin_summary", self._cmd_admin_summary))
        self.application.add_handler(CommandHandler("insight", self._cmd_admin_insight))
        self.application.add_handler(CommandHandler("faq", self._cmd_faq))
        self.application.add_handler(CallbackQueryHandler(self._handle_button))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        # Start Polling
        self._is_running = True
        logger.info("Iniciando Bot Telegram...")
        
        # Initialize and Start
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling() # type: ignore
        
        # Keep running until stopped
        while self._is_running:
            await asyncio.sleep(1)

        # Stop
        await self.application.updater.stop() # type: ignore
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Bot Telegram Parado.")

    async def stop(self) -> None:
        """
        Stop the Telegram Bot.
        """
        self._is_running = False

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command with interactive buttons."""
        if not update.effective_user or not update.message:
            return
        
        # Mark greeting for today
        import datetime
        self._user_last_greeting[update.effective_user.id] = datetime.date.today().isoformat()
        
        await self._send_start_menu(update)

    async def _cmd_ajuda(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /ajuda command - show available commands."""
        if not update.message:
            return
            
        is_admin = self._is_admin(update)
        
        if is_admin:
            msg = (
                "<b>Comandos de Administrador:</b>\n\n"
                "/listar - Lista arquivos na base de conhecimento\n"
                "/remover <code>[arquivo]</code> - Remove um arquivo da base\n"
                "/ia <code>[modelo]</code> - Lista ou troca o modelo de IA\n"
                "/limpar - Apaga toda a base de dados\n"
                "/bd - Ajuda para ingestão de arquivos\n"
                "/status - Status do sistema e da base\n"
                "/aviso <code>[mensagem]</code> - Envia aviso para todos os alunos\n"
                "/conhecimento <code>[texto]</code> - Adiciona texto direto à base\n"
                "/prompt <code>[mensagem]</code> - Vê ou altera o System Prompt\n"
                "/estatisticas - Relatório de interações\n\n"
                "<b>Comandos Gerais:</b>\n"
                "/inicio - Menu principal\n"
                "/meuid - Ver seu ID do Telegram\n"
                "/ajuda - Mostra esta lista"
            )
        else:
            msg = (
                "<b>Comandos disponíveis:</b>\n\n"
                "/inicio - Menu principal interativo\n"
                "/meuid - Ver seu ID do Telegram\n"
                "/ajuda - Mostra esta lista\n\n"
                "Você também pode enviar sua dúvida diretamente por texto a qualquer momento."
            )
            
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_list_documents(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /listar command - list documents in the vector store."""
        if not update.message:
            return
            
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado. Apenas administradores podem listar arquivos da base.")
            return
            
        status_msg = await update.message.reply_text("Consultando arquivos na base de conhecimento...")
        
        try:
            result = await self._run_chroma_worker({"action": "list"})
            
            if result is not None and isinstance(result, list):
                if not result:
                    await status_msg.edit_text("A base de conhecimento está vazia.")
                else:
                    files_list = "\n".join([f"- {f}" for f in result])
                    await status_msg.edit_text(
                        f"<b>Arquivos na base de conhecimento:</b>\n\n{files_list}",
                        parse_mode="HTML"
                    )
            else:
                await status_msg.edit_text("Não foi possível listar os arquivos no momento.")
        except Exception as e:
            logger.error(f"Erro ao listar documentos: {e}")
            await status_msg.edit_text("Erro ao processar a solicitação.")

    async def _cmd_delete_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /remover command - delete a document from the vector store."""
        if not update.message:
            return
            
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado. Apenas administradores podem remover documentos.")
            return
            
        if not context.args:
            await update.message.reply_text("Uso: `/remover nome_do_arquivo.pdf`", parse_mode="Markdown")
            return
            
        filename = " ".join(context.args)
        status_msg = await update.message.reply_text(f"🗑️ Removendo '{filename}'...")
        
        try:
            result = await self._run_chroma_worker({
                "action": "delete",
                "filename": filename
            })
            
            if result.get("ok"):
                count = result.get("deleted_count", 0)
                await status_msg.edit_text(f"✅ Sucesso! {count} fragmentos de '{filename}' foram removidos.")
            else:
                error = result.get("error", "Erro desconhecido")
                await status_msg.edit_text(f"❌ Erro: {error}")
        except Exception as e:
            logger.error(f"Erro ao deletar documento: {e}")
            await status_msg.edit_text("Erro ao processar a solicitação de remoção.")

    async def _cmd_list_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /ia command - list or switch AI models."""
        if not update.message:
            return
            
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado. Apenas administradores podem gerenciar modelos de IA.")
            return
            
        current_model = self.config_manager.get("ollama_model", "Sem modelo configurado")
        
        # Scenario 1: Just List Models
        if not context.args:
            status_msg = await update.message.reply_text("🔎 Consultando modelos disponíveis no Ollama...")
            try:
                models = self.ollama_adapter.list_models()
                if not models:
                    await status_msg.edit_text(f"Nenhum modelo encontrado no Ollama.\n\nModelo atual: <code>{current_model}</code>", parse_mode="HTML")
                    return
                
                import html
                models_list = "\n".join([f"- {html.escape(m)}" for m in models])
                await status_msg.edit_text(
                    f"🤖 <b>Modelos disponíveis:</b>\n\n{models_list}\n\n"
                    f"<b>Modelo atual:</b> <code>{html.escape(current_model)}</code>\n\n"
                    "Para trocar, use: <code>/ia [nome_do_modelo]</code>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Erro ao listar modelos: {e}")
                await status_msg.edit_text(f"Erro ao consultar modelos.\n\nModelo atual: <code>{html.escape(current_model)}</code>", parse_mode="HTML")
            return

        # Scenario 2: Switch Model
        import html
        new_model = context.args[0]
        status_msg = await update.message.reply_text(f"⚙️ Trocando modelo para: <code>{html.escape(new_model)}</code>...", parse_mode="HTML")
        
        try:
            # Check if model exists first
            available_models = self.ollama_adapter.list_models()
            if new_model not in available_models:
                # Try simple match (case insensitive or without suffix)
                match = next((m for m in available_models if m.lower() == new_model.lower()), None)
                if not match:
                    await status_msg.edit_text(f"❌ Erro: O modelo `{new_model}` não foi encontrado no Ollama.")
                    return
                new_model = match

            self.config_manager.set("ollama_model", new_model)
            await status_msg.edit_text(f"✅ Sucesso! O bot agora está utilizando o modelo: <code>{html.escape(new_model)}</code>", parse_mode="HTML")
            logger.info(f"Modelo alterado pelo administrador para: {new_model}")
            
        except Exception as e:
            logger.error(f"Erro ao trocar modelo: {e}")
            await status_msg.edit_text(f"❌ Erro ao trocar modelo: {e}")

    async def _cmd_clear_database(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /limpar command - clear the entire database."""
        if not update.message:
            return
            
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado. Apenas administradores podem limpar a base de dados.")
            return
            
        status_msg = await update.message.reply_text("🧨 Limpando base de dados... aguarde.")
        
        try:
            result = await self._run_chroma_worker({
                "action": "clear"
            })
            # result should be "Database cleared." or "Database already empty."
            await status_msg.edit_text(f"✅ {result}")
            logger.info("Base de dados limpa pelo administrador.")
        except Exception as e:
            logger.error(f"Erro ao limpar base de dados: {e}")
            await status_msg.edit_text(f"❌ Erro ao limpar base: {e}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /status command."""
        if not update.message: return
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.")
            return

        status_msg = await update.message.reply_text("⏳ Coletando informações do sistema...")
        
        try:
            # 1. Check Ollama
            import time
            start_time = time.time()
            models = self.ollama_adapter.list_models()
            latency = (time.time() - start_time) * 1000
            ollama_status = "✅ Online" if models else "❌ Offline"
            
            # 2. Get DB Stats
            db_stats = await self._run_chroma_worker({"action": "stats"})
            
            current_model = self.config_manager.get("ollama_model", "N/A")
            provider = self.config_manager.get("ai_provider", "ollama")
            
            import html
            report = (
                "📊 <b>Status do Sistema</b>\n\n"
                f"🤖 <b>IA Provider:</b> <code>{provider.upper()}</code>\n"
                f"🧠 <b>Modelo Ativo:</b> <code>{html.escape(str(current_model))}</code>\n"
                f"📡 <b>Ollama:</b> {ollama_status} ({latency:.0f}ms)\n\n"
                "📂 <b>Base de Conhecimento:</b>\n"
                f"- Arquivos: <code>{db_stats.get('file_count', 0)}</code> unidades\n"
                f"- Fragmentos (Chunks): <code>{db_stats.get('chunk_count', 0)}</code> registros\n"
            )
            await status_msg.edit_text(report, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erro no status: {e}")
            await status_msg.edit_text(f"❌ Erro ao obter status: {e}")

    async def _cmd_aviso(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /aviso command - broadcast message to all users."""
        if not update.message: return
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.")
            return

        if not context.args:
            await update.message.reply_text("📝 <b>Uso:</b> <code>/aviso Sua mensagem aqui...</code>", parse_mode="HTML")
            return

        broadcast_msg = " ".join(context.args)
        status_msg = await update.message.reply_text("📢 Preparando envio de aviso...")
        
        try:
            user_ids = self.analytics.get_unique_users()
            if not user_ids:
                await status_msg.edit_text("ℹ️ Nenhum usuário encontrado no histórico para envio.")
                return

            await status_msg.edit_text(f"🚀 Enviando para {len(user_ids)} usuários...")
            
            success_count = 0
            fail_count = 0
            
            import html
            text_to_send = f"📢 <b>Aviso do Professor:</b>\n\n{html.escape(broadcast_msg)}"
            
            for u_id in user_ids:
                try:
                    await context.bot.send_message(chat_id=u_id, text=text_to_send, parse_mode="HTML")
                    success_count += 1
                except Exception as e:
                    logger.warning(f"Falha ao enviar para {u_id}: {e}")
                    fail_count += 1
                await asyncio.sleep(0.05) # Small delay to avoid flood limits
            
            await status_msg.edit_text(f"✅ <b>Aviso enviado!</b>\n\n- Sucesso: <code>{success_count}</code>\n- Falhas: <code>{fail_count}</code>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erro no envio de aviso: {e}")
            await status_msg.edit_text(f"❌ Erro crítico no envio: {e}")

    async def _cmd_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /prompt command - show or update system prompt."""
        if not update.message: return
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.")
            return

        current_prompt = self.config_manager.get("system_prompt", "")
        
        if not context.args:
            import html
            await update.message.reply_text(
                f"📝 <b>System Prompt Atual:</b>\n\n<code>{html.escape(str(current_prompt))}</code>\n\n"
                "Para alterar, use: <code>/prompt Novo texto de comportamento...</code>",
                parse_mode="HTML"
            )
            return

        new_prompt = " ".join(context.args)
        try:
            self.config_manager.set("system_prompt", new_prompt)
            await update.message.reply_text("✅ **System Prompt atualizado com sucesso!**")
            logger.info(f"System Prompt alterado pelo admin.")
        except Exception as e:
            logger.error(f"Erro ao atualizar prompt: {e}")
            await update.message.reply_text(f"❌ Erro ao salvar prompt: {e}")

    async def _cmd_add_knowledge_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /conhecimento command - ingest text directly."""
        if not update.message: return
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.")
            return

        if not context.args:
            await update.message.reply_text(
                "📝 <b>Uso:</b> <code>/conhecimento Seu texto aqui...</code>\n\n"
                "Isso adicionará o texto diretamente à base de dados como um registro permanente.",
                parse_mode="HTML"
            )
            return

        text_to_add = " ".join(context.args)
        status_msg = await update.message.reply_text("🧠 Adicionando ao conhecimento...")
        
        try:
            # Generate filename: mensagem_YYYYMMDD_HHMMSS.txt
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"mensagem_{timestamp}.txt"
            
            # Temporary path for ingestion
            temp_path = os.path.join(os.getcwd(), "temp_ingest")
            os.makedirs(temp_path, exist_ok=True)
            file_path = os.path.join(temp_path, file_name)
            
            # Save text to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text_to_add)
            
            # Use the existing worker logic to ingest
            result = await self._run_chroma_worker({
                "action": "ingest",
                "file_path": file_path
            })
            
            chunks = result.get('chunks_count', 0)
            await status_msg.edit_text(
                f"✅ <b>Conhecimento adicionado!</b>\n\n"
                f"- Arquivo: <code>{file_name}</code>\n"
                f"- Fragmentos: <code>{chunks}</code>\n"
                f"- Origem: Texto direto via Telegram",
                parse_mode="HTML"
            )
            logger.info(f"Texto direto adicionado à base: {file_name}")
            
            # Cleanup temp file
            if os.path.exists(file_path):
                os.remove(file_path)
                
        except Exception as e:
            logger.error(f"Erro no /conhecimento: {e}")
            await status_msg.edit_text(f"❌ Erro ao injetar texto: {e}")

    async def _cmd_my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /meuid command."""
        if not update.message:
            return
        await update.message.reply_text(f"Seu ID do Telegram é: <code>{update.effective_user.id}</code>", parse_mode="HTML")

    def _get_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Return the standard menu keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("Horário", callback_data="btn_horarios"),
                InlineKeyboardButton("Cronograma", callback_data="btn_cronogramas"),
            ],
            [
                InlineKeyboardButton("Materiais", callback_data="btn_materiais"),
                InlineKeyboardButton("FAQ", callback_data="btn_faq"),
            ],
            [
                InlineKeyboardButton("Falar com o Professor", callback_data="btn_professor"),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if a user has exceeded the rate limit. Returns True if allowed."""
        limit = self.config_manager.get("rate_limit_per_minute", 10)
        now = time.time()
        
        if user_id not in self._user_message_times:
            self._user_message_times[user_id] = []
        
        # Remove timestamps older than 60 seconds
        self._user_message_times[user_id] = [
            t for t in self._user_message_times[user_id] if now - t < 60
        ]
        
        if len(self._user_message_times[user_id]) >= limit:
            return False  # Over limit
        
        self._user_message_times[user_id].append(now)
        return True

    def _add_to_history(self, user_id: int, question: str, answer: str) -> None:
        """Add a question/answer pair to the user's chat history."""
        max_size = self.config_manager.get("chat_history_size", 5)
        if max_size <= 0:
            return
        
        if user_id not in self._chat_history:
            self._chat_history[user_id] = deque(maxlen=max_size)
        
        # Update maxlen if config changed
        if self._chat_history[user_id].maxlen != max_size:
            old = list(self._chat_history[user_id])
            self._chat_history[user_id] = deque(old, maxlen=max_size)
        
        self._chat_history[user_id].append((question, answer))

    def _get_history_text(self, user_id: int) -> str:
        """Get formatted chat history for a user."""
        if user_id not in self._chat_history or not self._chat_history[user_id]:
            return ""
        
        lines = []
        for q, a in self._chat_history[user_id]:
            lines.append(f"Aluno: {q}")
            lines.append(f"Assistente: {a}")
        
        return "\n".join(lines)

    async def _notify_admin(self, message: str) -> None:
        """Send an error notification to the admin via Telegram."""
        try:
            admin_id = self.config_manager.get("admin_id", "")
            if admin_id and self.application:
                await self.application.bot.send_message(
                    chat_id=int(admin_id),
                    text=f"⚠️ ALERTA DO BOT:\n\n{message}"
                )
        except Exception as e:
            logger.error(f"Falha ao notificar admin: {e}")

    async def _cmd_faq(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /faq command."""
        if not update.message:
            return
        await self._show_faq_content(update.message)

    async def _show_faq_content(self, target) -> None:
        """Read and display FAQ content from 'arquivos/faq.txt'."""
        try:
            arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
            file_path = os.path.join(arquivos_dir, "faq.txt")
            
            if not os.path.exists(file_path):
                await target.reply_text(
                    "Crie um arquivo chamado <code>faq.txt</code> na pasta <code>arquivos</code> "
                    "para exibir as perguntas frequentes.",
                    parse_mode="HTML"
                )
                return

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if not content.strip():
                await target.reply_text("O arquivo de FAQ está vazio.")
                return

            await target.reply_text(
                f"<b>❓ Perguntas Frequentes</b>\n\n{content}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erro ao ler FAQ: {e}")
            await target.reply_text(f"Erro ao processar FAQ: {e}")

    async def _send_start_menu(self, update: Update) -> None:
        """Send the start menu with interactive buttons."""
        await update.message.reply_text(
            f"Olá, {update.effective_user.first_name}. Sou o assistente acadêmico.\n"
            "Selecione uma opção ou digite sua dúvida:",
            reply_markup=self._get_menu_keyboard()
        )

    async def _show_horarios(self, query) -> None:
        """List and send horario files from the 'arquivos' folder."""
        await query.edit_message_text(text="Buscando arquivos de horário...")
        
        try:
            arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
            if not os.path.exists(arquivos_dir):
                await query.edit_message_text(text="Pasta de arquivos não encontrada.")
                return
            
            # List files starting with 'horario'
            files = [f for f in os.listdir(arquivos_dir) if f.lower().startswith("horario")]
            
            if not files:
                await query.edit_message_text(text="Nenhum horário disponível no momento.")
                return

            await query.edit_message_text(text=f"Encontrei {len(files)} arquivo(s) de horário. Enviando...")
            
            for filename in files:
                file_path = os.path.join(arquivos_dir, filename)
                with open(file_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"📅 {filename}"
                    )
            # Re-send menu buttons
            await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        except Exception as e:
            logger.error(f"Erro ao buscar horários: {e}")
            await query.edit_message_text(text=f"Erro ao processar horários: {e}")

    async def _show_cronogramas(self, query) -> None:
        """List and send cronograma files from the 'arquivos' folder."""
        await query.edit_message_text(text="Buscando arquivos de cronograma...")
        
        try:
            arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
            if not os.path.exists(arquivos_dir):
                await query.edit_message_text(text="Pasta de arquivos não encontrada.")
                return
            
            # List files starting with 'cronograma'
            files = [f for f in os.listdir(arquivos_dir) if f.lower().startswith("cronograma")]
            
            if not files:
                await query.edit_message_text(text="Nenhum cronograma disponível no momento.")
                return

            await query.edit_message_text(text=f"Encontrei {len(files)} arquivo(s) de cronograma. Enviando...")
            
            for filename in files:
                file_path = os.path.join(arquivos_dir, filename)
                with open(file_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"📄 {filename}"
                    )
            # Re-send menu buttons
            await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        except Exception as e:
            logger.error(f"Erro ao buscar cronogramas: {e}")
            await query.edit_message_text(text=f"Erro ao processar cronogramas: {e}")

    async def _show_materials(self, query) -> None:
        """Read and show content from 'arquivos/materiais.txt'."""
        await query.edit_message_text(text="Buscando informações sobre materiais...")
        
        try:
            arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
            file_path = os.path.join(arquivos_dir, "materiais.txt")
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    text="Crie um arquivo chamado <code>materiais.txt</code> na pasta <code>arquivos</code> para exibir neste botão.",
                    parse_mode="HTML"
                )
                return

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if not content.strip():
                await query.edit_message_text(text="O arquivo de materiais está vazio.")
                return

            await query.edit_message_text(
                text=f"<b>📚 Materiais das Disciplinas</b>\n\n{content}",
                parse_mode="HTML"
            )
            await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        except Exception as e:
            logger.error(f"Erro ao ler arquivo de materiais: {e}")
            await query.edit_message_text(text=f"Erro ao processar materiais: {e}")

    async def _handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button clicks."""
        query = update.callback_query
        await query.answer() # type: ignore
        
        data = query.data

        # --- User Buttons ---
        if data == "btn_horarios":
            await self._show_horarios(query)
        elif data == "btn_cronogramas":
            await self._show_cronogramas(query)
        elif data == "btn_materiais":
            await self._show_materials(query)
        elif data == "btn_faq":
            await self._show_faq_content(query.message)
            await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        elif data == "btn_professor":
             await query.edit_message_text(
                 text="<b>Prof. Carlo Ralph De Musis</b>\n\n"
                      "Telegram: @carlodemusis\n"
                      "Telefone: (65) 9 9262-5221\n"
                      "E-mail: carlo.demusis@gmail.com",
                 parse_mode="HTML"
             ) # type: ignore
             await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        
        # --- Admin Buttons (Summary) ---
        elif data.startswith("btn_summary_"):
            days = int(data.split("_")[2])
            await self._generate_ai_summary(query, days)

    async def _cmd_admin_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Help for admin ingestion."""
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.") # type: ignore
            return
        
        await update.message.reply_text( # type: ignore
            "🔧 **Modo Admin - Ingestão**\n"
            "Para adicionar documentos à base de conhecimento, basta **enviar o arquivo (PDF, DOCX, CSV ou TXT)** aqui neste chat.\n"
            "Eu processarei automaticamente."
        )

    async def _cmd_admin_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show options for AI summary."""
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.") # type: ignore
            return
            
        keyboard = [
            [
                InlineKeyboardButton("Últimas 24h", callback_data="btn_summary_1"),
                InlineKeyboardButton("7 Dias", callback_data="btn_summary_7"),
                InlineKeyboardButton("30 Dias", callback_data="btn_summary_30"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📊 **Relatório de Interações**\nEscolha o período para análise:", reply_markup=reply_markup) # type: ignore

    async def _cmd_admin_insight(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Allow admin to query logs.
        Usage: /insight [days] [question]
        """
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.") # type: ignore
            return
            
        if not context.args:
            await update.message.reply_text("Uso: `/insight [dias] [pergunta]`\nEx: `/insight 7 Quais as dúvidas sobre provas?`") # type: ignore
            return

        try:
            # Parse args
            if context.args[0].isdigit():
                days = int(context.args[0])
                question = " ".join(context.args[1:])
            else:
                days = 7
                question = " ".join(context.args)
                
            if not question:
                 await update.message.reply_text("Por favor, digite sua pergunta.") # type: ignore
                 return
                 
            await update.message.reply_text(f"🔍 Analisando logs de {days} dias sobre: '{question}'...") # type: ignore
            
            # Get Logs
            logs_text = self.analytics.get_logs(days)
            if len(logs_text) < 10:
                await update.message.reply_text(f"ℹ️ {logs_text}") # type: ignore
                return
                
            # Construct Prompt
            prompt = (
                f"Analise o seguinte log de interações (Perguntas de usuários) dos últimos {days} dias:\n\n"
                f"{logs_text}\n\n"
                f"RESPONDA À SEGUINTE PERGUNTA DO ADMINISTRADOR:\n"
                f"Question: {question}\n\n"
                "Use apenas os dados fornecidos. Se não houver informação, diga que não encontrou."
            )
            
            # Call LLM
            provider = self.config_manager.get("ai_provider", "ollama")
            model = self.config_manager.get("ollama_model", "llama3:latest") if provider == "ollama" else self.config_manager.get("openrouter_model", "openai/gpt-3.5-turbo")
            
            response_text = ""
            if provider == "openrouter":
                from openrouter_client import OpenRouterAdapter
                key = self.config_manager.get("openrouter_key", "")
                adapter = OpenRouterAdapter(api_key=key)
                gen = adapter.generate_response(model, prompt, temperature=0.3, max_tokens=1000)
            else:
                 gen = self.ollama_adapter.generate_response(model, prompt, temperature=0.3, max_tokens=1000)
                 
            for chunk in gen:
                response_text += chunk
                
            await update.message.reply_text(f"🤖 **Insight IA**\n\n{response_text}", parse_mode="Markdown") # type: ignore
            
        except Exception as e:
            logger.error(f"Erro no insight: {e}")
            await update.message.reply_text("Erro ao processar insight.") # type: ignore


    async def _generate_ai_summary(self, query, days: int) -> None:
        """Generate AI Summary from logs."""
        await query.edit_message_text(text=f"🔄 Analisando logs dos últimos {days} dias... aguarde.")
        
        # 1. Get Logs
        logs_text = self.analytics.get_logs(days)
        if len(logs_text) < 10: # "Nenhum..." or empty
             await query.edit_message_text(text=f"ℹ️ {logs_text}")
             return

        # 2. Prompt LLM
        prompt = (
            f"Analise o seguinte log de interações (Perguntas de usuários) dos últimos {days} dias:\n\n"
            f"{logs_text}\n\n"
            "TAREFA: Crie um resumo executivo para o administrador.\n"
            "- Identifique os 3 tópicos mais frequentes.\n"
            "- Destaque reclamações ou dúvidas não respondidas (se houver).\n"
            "- Sugira melhorias na base de conhecimento.\n"
            "Responda em Português do Brasil, formato Markdown."
        )
        
        try:
            # Re-use generator logic (simplified call here for brevity, ideally refactor generate method)
            # We use the configured provider but force temperature 0.3 for analysis
            provider = self.config_manager.get("ai_provider", "ollama")
            model = self.config_manager.get("ollama_model", "llama3:latest") if provider == "ollama" else self.config_manager.get("openrouter_model", "openai/gpt-3.5-turbo")
            
            response_text = ""
            if provider == "openrouter":
                from openrouter_client import OpenRouterAdapter
                key = self.config_manager.get("openrouter_key", "")
                adapter = OpenRouterAdapter(api_key=key)
                gen = adapter.generate_response(model, prompt, temperature=0.3, max_tokens=1000)
            else:
                 gen = self.ollama_adapter.generate_response(model, prompt, temperature=0.3, max_tokens=1000)
                 
            for chunk in gen:
                response_text += chunk
                
            await query.edit_message_text(text=f"📊 **Relatório IA ({days} dias)**\n\n{response_text}", parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Erro no sumário: {e}")
            await query.edit_message_text(text="❌ Erro ao gerar resumo verificador logs do servidor.")

    def _is_admin(self, update: Update) -> bool:
        """Check if user is admin."""
        admin_id = self.config_manager.get("admin_id")
        if not admin_id:
            return False
        user_id = str(update.effective_user.id)
        return user_id == str(admin_id)

    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document uploads (Admin Only)."""
        if not self._is_admin(update):
            # Ignore or reply
            await update.message.reply_text("Eu não posso processar arquivos enviados por você.") # type: ignore
            return
        
        file = await update.message.document.get_file() # type: ignore
        file_name = update.message.document.file_name # type: ignore
        
        await update.message.reply_text(f"📥 Recebendo {file_name}...") # type: ignore
        
        # Save to temp
        temp_path = os.path.join(os.getcwd(), "temp_ingest")
        os.makedirs(temp_path, exist_ok=True)
        file_path = os.path.join(temp_path, file_name)
        
        await file.download_to_drive(file_path)
        
        # Ingest via subprocess worker
        try:
            await update.message.reply_text("⚙️ Processando...") # type: ignore
            
            result = await self._run_chroma_worker({
                "action": "ingest",
                "file_path": file_path
            })
            
            chunks = result.get('chunks_count', 0)
            await update.message.reply_text(f"✅ Sucesso! {chunks} fragmentos adicionados à base.") # type: ignore
        except Exception as e:
            import traceback
            logger.error(f"Erro na ingestão do arquivo: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            try:
                await update.message.reply_text(f"❌ Erro ao processar: {e}") # type: ignore
            except Exception:
                pass  # Prevent reply failure from propagating
        finally:
            # Cleanup
            if os.path.exists(file_path):
                os.remove(file_path)

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle incoming text messages.
        Performs RAG + Ollama Generation.
        """
        if not update.message or not update.message.text:
            return

        user_query = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Mensagem recebida: {user_query}")
        
        # Feature 3: Rate Limiting
        if not self._check_rate_limit(user_id):
            await update.message.reply_text(
                "⏳ Você atingiu o limite de mensagens por minuto. Aguarde um momento antes de enviar outra."
            )
            return
        
        # --- Handle Backslash Commands ---
        # If message starts with \ and isn't caught by CommandHandler (which expects /)
        if user_query.startswith('\\'):
            # Convert to forward slash and try to find a matching command
            parts = user_query[1:].split()
            if not parts:
                return # Just \ sent, ignore
            
            cmd_part = parts[0].lower()
            
            # Simple manual dispatch for known commands
            if cmd_part == "listar":
                return await self._cmd_list_documents(update, context)
            elif cmd_part == "remover":
                # Prepare context.args
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_delete_document(update, context)
            elif cmd_part in ["inicio", "start"]:
                return await self._cmd_start(update, context)
            elif cmd_part == "ajuda":
                return await self._cmd_ajuda(update, context)
            elif cmd_part == "meuid":
                return await self._cmd_my_id(update, context)
            elif cmd_part == "estatisticas":
                return await self._cmd_admin_summary(update, context)
            elif cmd_part == "ia":
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_list_models(update, context)
            elif cmd_part == "status":
                return await self._cmd_status(update, context)
            elif cmd_part == "aviso":
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_aviso(update, context)
            elif cmd_part == "prompt":
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_prompt(update, context)
            elif cmd_part == "conhecimento":
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_add_knowledge_text(update, context)
            elif cmd_part == "faq":
                return await self._cmd_faq(update, context)
            # If it's a backslash but not a command, we continue to RAG if appropriate
            elif any(cmd_part == name for name in ["insight", "bd", "limpar", "admin_summary"]):
                # Admin commands
                if cmd_part == "insight":
                    context.args = parts[1:] if len(parts) > 1 else []
                    return await self._cmd_admin_insight(update, context)
                elif cmd_part == "bd":
                    return await self._cmd_admin_help(update, context)
                elif cmd_part == "limpar":
                    return await self._cmd_clear_database(update, context)
                elif cmd_part == "admin_summary":
                    return await self._cmd_admin_summary(update, context)
        
        # Auto-show /start on first message of the day
        import datetime
        today_str = datetime.date.today().isoformat()
        if self._user_last_greeting.get(user_id) != today_str:
            self._user_last_greeting[user_id] = today_str
            await self._send_start_menu(update)
        
        # 1. Retrieve Context
        try:
            if update.effective_chat:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            rag_k = self.config_manager.get("rag_k", 8)
            result = await self._run_chroma_worker({
                "action": "query",
                "query": user_query,
                "k": rag_k
            })
            # result is a list of dicts with page_content
            context_text = "\n\n".join([doc["page_content"] for doc in result])
            
            if not context_text:
                logger.info("Nenhum contexto relevante encontrado na base.")
        except Exception as e:
            logger.error(f"Erro ao recuperar contexto: {e}")
            context_text = ""

        # 2. Construct Prompt
        # Prepare System Prompt with Date
        import datetime
        import locale
        
        try:
            locale.setlocale(locale.LC_TIME, 'pt_BR.utf8') # Try specific PT-BR
        except:
             try:
                 locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252') # Windows
             except:
                 pass # Fallback to default

        now = datetime.datetime.now()
        date_str = now.strftime("%A, %d de %B de %Y. Hora: %H:%M")
        
        base_system = self.config_manager.get("system_prompt", "Você é um assistente útil.")
        system_prompt = f"{base_system}\n\n[CONTEXTO TEMPORAL: Hoje é {date_str}]"
        
        # Feature 1: Include chat history
        history_text = self._get_history_text(user_id)
        history_block = ""
        if history_text:
            history_block = f"\nHistórico da conversa com este aluno:\n{history_text}\n"
        
        full_prompt = (
            f"Contexto recuperado:\n{context_text}\n"
            f"{history_block}\n"
            f"Pergunta do Usuário: {user_query}\n"
            f"Por favor, responda a pergunta do usuário usando o contexto fornecido."
        )

        # 3. Generate Response
        response_text = ""
        provider = self.config_manager.get("ai_provider", "ollama")
        
        try:
            temperature = self.config_manager.get("temperature", 0.7)
            max_tokens = int(self.config_manager.get("max_tokens", 2048))
            
            if provider == "openrouter":
                # Lazy Init or Re-init to get potential key change
                from openrouter_client import OpenRouterAdapter
                key = self.config_manager.get("openrouter_key", "")
                if not key:
                    await update.message.reply_text("Erro: API Key do OpenRouter não configurada.") # type: ignore
                    return
                
                adapter = OpenRouterAdapter(api_key=key)
                model = self.config_manager.get("openrouter_model", "openai/gpt-3.5-turbo")
                
                generator = adapter.generate_response(
                    model=model,
                    prompt=full_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                # Default Ollama
                model = self.config_manager.get("ollama_model", "llama3:latest")
                generator = self.ollama_adapter.generate_response(
                    model=model,
                    prompt=full_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            
            for chunk in generator:
                response_text += chunk
                
            # 4. Reply
            if response_text:
                # Clean markdown since we are sending as plain text
                response_text = self._clean_markdown(response_text)
                await update.message.reply_text(response_text) # type: ignore
                await update.message.reply_text("Selecione uma opção ou digite outra dúvida:", reply_markup=self._get_menu_keyboard()) # type: ignore
                
                # Feature 1: Save to chat history
                self._add_to_history(user_id, user_query, response_text)
            else:
                 await update.message.reply_text("Desculpe, não consegui gerar uma resposta.") # type: ignore
            
            # 5. Log Analysis
            user = update.effective_user
            full_name = f"{user.first_name} {user.last_name or ''}".strip()
            username = user.username or ""
            
            self.analytics.log_interaction(
                user_id=user_id,
                full_name=full_name,
                username=username,
                question=user_query,
                answer=response_text,
                provider=provider
            )

        except Exception as e:
            logger.error(f"Erro ao gerar resposta: {e}")
            await update.message.reply_text("Ocorreu um erro ao processar sua solicitação.") # type: ignore
            # Feature 5: Notify admin about critical errors
            await self._notify_admin(f"Erro ao gerar resposta para o usuário {user_id}:\n{str(e)}")
