import logging
import asyncio
import os
import json
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
        
        # Watchdog: track uptime
        self._start_time = time.time()
        
        # Known users set (for first-time user detection)
        self._known_users: set = set(self.analytics.get_unique_users())
        
        # Feature 1: Per-user chat history
        self._chat_history: Dict[int, deque] = {}  # user_id -> deque of (question, answer)
        
        # Feature 3: Rate limiting
        self._user_message_times: Dict[int, list] = {}  # user_id -> list of timestamps
        
        # Feature: Scheduled Reminders
        self._reminders_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.json")
        self._reminders: List[Dict[str, Any]] = self._load_reminders()

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Strip markdown and simplify LaTeX math formatting for plain text display."""
        import re
        
        # 1. Strip Common Markdown
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*(.+?)\*', r'\1', text)       # *italic*
        text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)  # ### headers
        
        # 2. Handle LaTeX delimiters
        text = re.sub(r'\$\$(.*?)\$\$', r'\1', text, flags=re.DOTALL) # $$block$$
        text = re.sub(r'\$(.*?)\$', r'\1', text)                      # $inline$
        text = re.sub(r'\\\[(.*?)\\\]', r'\1', text, flags=re.DOTALL) # \[block\]
        text = re.sub(r'\\\((.*?)\\\)', r'\1', text)                  # \(inline\)
        
        # 3. Simplify common LaTeX math commands
        replacements = [
            (r'\\text\{(.+?)\}', r'\1'),            # \text{...} -> ...
            (r'\\frac\{(.+?)\}\{(.+?)\}', r'(\1/\2)'), # \frac{a}{b} -> (a/b)
            (r'\\times', 'x'),
            (r'\\cdot', '·'),
            (r'\\div', '/'),
            (r'\\pm', '+/-'),
            (r'\\approx', '≈'),
            (r'\\leq', '<='),
            (r'\\geq', '>='),
            (r'\\neq', '!='),
            (r'\\infty', '∞'),
            (r'\\rightarrow', '→'),
            (r'\\pi', 'π'),
            (r'\\sqrt\{(.+?)\}', r'sqrt(\1)'),
            (r'\\hat\{(.+?)\}', r'\1'),
            (r'\\bar\{(.+?)\}', r'\1'),
            (r'\\Delta', 'Δ'),
            (r'\\alpha', 'α'),
            (r'\\beta', 'β'),
            (r'\\theta', 'θ'),
            (r'\\{', '{'),
            (r'\\}', '}'),
            (r'\\_', '_'),
            (r'\\ ', ' '),
        ]
        
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text)
            
        # 4. Final cleanup of any remaining backslashes before common chars
        text = re.sub(r'\\([_#$!%&])', r'\1', text)
        
        return text.strip()

    async def _run_chroma_worker(self, action_data: Dict[str, Any]) -> Any:
        """
        Run a ChromaDB operation in a subprocess to avoid SQLite DLL conflicts with PyQt6.
        """
        import json, subprocess, sys
        
        # Load latest settings
        provider = self.config_manager.get("embedding_provider", "ollama")
        if provider == "openrouter":
            model_name = self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        action_data["chroma_dir"] = self.config_manager.get("chroma_dir") or ""
        action_data["model_name"] = model_name
        action_data["embedding_provider"] = provider
        action_data["api_key"] = self.config_manager.get("openrouter_key", "")
        action_data["ollama_url"] = self.config_manager.get("ollama_url", "http://127.0.0.1:11434")
        
        worker_data = json.dumps(action_data)
        
        loop = asyncio.get_running_loop()
        
        def _run():
            # Determine worker command
            if getattr(sys, 'frozen', False):
                # We are in a bundle (exe)
                cmd = [sys.executable, "--worker"]
            else:
                # We are running from source
                cmd = [sys.executable, self._worker_script]

            try:
                result = subprocess.run(
                    cmd,
                    input=worker_data,
                    capture_output=True, text=True,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    timeout=180 # 180 seconds timeout for any DB operation
                )
            except subprocess.TimeoutExpired:
                 logger.error(f"ChromaDB worker timed out after 180s (Action: {action_data.get('action')})")
                 raise RuntimeError("Base de dados demorou muito para responder")
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
        self.application.add_handler(CommandHandler("embedding", self._cmd_embedding))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("aviso", self._cmd_aviso))
        self.application.add_handler(CommandHandler("prompt", self._cmd_prompt))
        self.application.add_handler(CommandHandler("conhecimento", self._cmd_add_knowledge_text))
        self.application.add_handler(CommandHandler("meuid", self._cmd_my_id))
        self.application.add_handler(CommandHandler("estatisticas", self._cmd_admin_summary))
        self.application.add_handler(CommandHandler("lembrete", self._cmd_add_reminder))
        # Admin System Management
        self.application.add_handler(CommandHandler("reiniciar_bot", self._cmd_restart_bot))
        self.application.add_handler(CommandHandler("logs", self._cmd_verbosity))
        self.application.add_handler(CommandHandler("limpar_historico", self._cmd_clear_history))
        self.application.add_handler(CommandHandler("monitor_cpu", self._cmd_monitor_cpu))
        self.application.add_handler(CommandHandler("speedtest", self._cmd_speedtest))
        self.application.add_handler(CommandHandler("ping_ia", self._cmd_ping_ia))
        self.application.add_handler(CommandHandler("atualizar", self._cmd_update))
        self.application.add_handler(CommandHandler("saude", self._cmd_saude))
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
        
        # Load Scheduled Jobs
        self._setup_reminder_jobs()
        
        await self.application.start()
        await self.application.updater.start_polling() # type: ignore
        
        # Notify admin if this is a restart after /atualizar
        await self._check_update_restart()
        
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
                "🛠️ <b>Painel de Controle do Administrador</b>\n\n"
                
                "🧠 <b>IA & Conhecimento:</b>\n"
                "• /ia <code>[modelo]</code> - Lista ou troca modelo de chat\n"
                "• /embedding <code>[modelo]</code> - Lista/Troca modelo de busca\n"
                "• /conhecimento <code>[texto]</code> - Ingestão direta de texto\n"
                "• /listar - Lista e permite ⬇️ baixar arquivos da base\n"
                "• /remover <code>[nome]</code> - Remove arquivo da base\n"
                "• /limpar - Reseta totalmente o banco de dados\n"
                "• /prompt <code>[texto]</code> - Vê/Edita instruções da IA\n"
                "• /bd - Guia rápido para ingestão de arquivos\n\n"
                
                "📢 <b>Comunicação & Avisos:</b>\n"
                "• /aviso <code>[texto]</code> - Mensagem para TODOS os alunos\n"
                "• /lembrete <code>DD/MM HH:MM Mensagem</code> - Agendar envio\n"
                "• /faq - Mostra as perguntas frequentes atuais\n\n"
                
                "🖥️ <b>Sistema & Hardware:</b>\n"
                "• /status - Relatório completo de saúde e hardware\n"
                "• /monitor_cpu - Uso de CPU e processos ativos\n"
                "• /speedtest - Teste de internet no servidor\n"
                "• /logs <code>[baixo|médio|alto]</code> - Nível de detalhes\n"
                "• /limpar_historico - Zera os logs de interações\n"
                "• /ping_ia - Latência (Ollama vs OpenRouter)\n"
                "• /atualizar - Git Pull + Update dependencies\n"
                "• /reiniciar_bot - Reinicia o processo do bot\n"
                "• /saude - Verifica se o bot está vivo (uptime)\n\n"
                
                "📊 <b>Análise & Identidade:</b>\n"
                "• /estatisticas - Dashboard de uso geral\n"
                "• /admin_summary - Resumo por IA das últimas interações\n"
                "• /insight <code>[qtd] [pergunta]</code> - Análise de tendências\n"
                "• /meuid - Ver seu ID do Telegram\n\n"
                
                "🧭 <b>Geral:</b>\n"
                "• /inicio - Retorna ao menu principal\n"
                "• /ajuda - Exibe este guia detalhado"
            )
        else:
            msg = (
                "🎓 <b>Central de Ajuda - Aluno</b>\n\n"
                "Olá! Você pode interagir comigo usando os botões do menu ou os comandos abaixo:\n\n"
                "• /inicio - Abre o menu principal interativo\n"
                "• /ajuda - Mostra esta lista de ajuda\n"
                "• /meuid - Informa seu número de identificação\n\n"
                "💡 <b>Dica:</b> Você pode enviar sua dúvida diretamente por texto (ou até documentos/fotos se o professor permitir) e eu tentarei responder usando o material de aula!"
            )
            
        await update.message.reply_text(msg, parse_mode="HTML")
        if not is_admin: # For students, usually nice to remind of the menu
            await update.message.reply_text("Como posso te ajudar agora?", reply_markup=self._get_menu_keyboard())

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
                    keyboard = []
                    # Files that actually exist in 'arquivos' for download
                    arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
                    local_files = os.listdir(arquivos_dir) if os.path.exists(arquivos_dir) else []
                    
                    for f in result:
                        # Check if file exists in 'arquivos' folder
                        file_exists = f in local_files
                        
                        row = []
                        if file_exists:
                            # Callback data limit is 64 bytes. Filenames usually fit.
                            # We use btn_dl_ prefix (7 chars).
                            if len(f.encode('utf-8')) <= 55:
                                row.append(InlineKeyboardButton(f"⬇️ {f}", callback_data=f"btn_dl_{f}"))
                            else:
                                # Truncate gracefully if name is too long for callback_data
                                short_name = f[:50]
                                row.append(InlineKeyboardButton(f"⬇️ {f[:30]}...", callback_data=f"btn_dl_{short_name}"))
                        else:
                            row.append(InlineKeyboardButton(f"📄 {f} (Remoto/Indisponível)", callback_data="ignore"))
                        
                        keyboard.append(row)
                    
                    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
                    await status_msg.edit_text(
                        f"<b>📚 Base de Conhecimento ({len(result)} arquivos):</b>\n\n"
                        "Clique em um arquivo abaixo para baixar o documento original.",
                        reply_markup=reply_markup,
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

    async def _cmd_embedding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /embedding command - list or switch Embedding models."""
        if not update.message:
            return
            
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado. Apenas administradores podem gerenciar modelos de Embedding.")
            return
            
        provider = self.config_manager.get("embedding_provider", "ollama")
        current_model = self.config_manager.get(f"{provider}_embedding_model", "Sem modelo configurado")
        
        # Scenario 1: List Models
        if not context.args:
            status_msg = await update.message.reply_text(f"🔎 Consultando modelos de Embedding no {provider.capitalize()}...")
            try:
                if provider == "ollama":
                    models = self.ollama_adapter.list_models()
                else:
                    from openrouter_client import OpenRouterAdapter
                    key = self.config_manager.get("openrouter_key", "")
                    adapter = OpenRouterAdapter(api_key=key)
                    models = adapter.list_models()
                    
                if not models:
                    await status_msg.edit_text(f"Nenhum modelo encontrado no {provider.capitalize()}.\n\nModelo atual: <code>{current_model}</code>", parse_mode="HTML")
                    return
                
                import html
                models_list = "\n".join([f"- {html.escape(m)}" for m in models])
                await status_msg.edit_text(
                    f"🧠 <b>Modelos de Embedding ({provider.capitalize()}):</b>\n\n{models_list}\n\n"
                    f"<b>Modelo atual:</b> <code>{html.escape(current_model)}</code>\n\n"
                    "Para trocar, use: <code>/embedding [nome_do_modelo]</code>\n"
                    "<i>⚠️ Nota: Mudar o modelo de embedding exige limpar e re-ingerir a base.</i>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Erro ao listar modelos de embedding: {e}")
                await status_msg.edit_text(f"Erro ao consultar modelos.\n\nModelo atual: <code>{current_model}</code>", parse_mode="HTML")
            return

        # Scenario 2: Switch Model
        import html
        new_model = context.args[0]
        status_msg = await update.message.reply_text(f"⚙️ Trocando modelo de embedding para: <code>{html.escape(new_model)}</code>...", parse_mode="HTML")
        
        try:
            # Save based on current provider
            conf_key = f"{provider}_embedding_model"
            self.config_manager.set(conf_key, new_model)
            
            await status_msg.edit_text(
                f"✅ Sucesso! O modelo de embedding foi alterado para: <code>{html.escape(new_model)}</code>\n\n"
                "<b>IMPORTANTE:</b> Como as dimensões dos vetores podem ter mudado, você <u>DEVE</u> limpar a base de dados (/limpar) "
                "e reenviar os documentos para que a busca continue funcionando.", 
                parse_mode="HTML"
            )
            logger.info(f"Modelo de Embedding ({provider}) alterado para: {new_model}")
            
        except Exception as e:
            logger.error(f"Erro ao trocar modelo de embedding: {e}")
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
        """Handle the /status command with parallel execution for speed."""
        if not update.message: return
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.")
            return

        status_msg = await update.message.reply_text("⏳ Coletando informações do sistema em tempo real...")
        
        async def get_ollama_info():
            import time
            try:
                start_time = time.time()
                # Run list_models in a thread to not block event loop
                loop = asyncio.get_running_loop()
                models = await loop.run_in_executor(None, self.ollama_adapter.list_models)
                latency = (time.time() - start_time) * 1000
                return ("✅ Online" if models else "❌ Offline", f"{latency:.0f}ms")
            except:
                return ("❌ Offline", "N/A")

        async def get_sys_metrics():
            import platform
            hostname = platform.node()
            try:
                import psutil
                mem = psutil.virtual_memory()
                mem_info = f"{mem.percent}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)"
                disk = psutil.disk_usage('/')
                disk_info = f"{disk.percent}% ({disk.free // (1024**3)}GB de {disk.total // (1024**3)}GB)"
                return hostname, mem_info, disk_info
            except:
                return hostname, "N/A", "N/A"

        try:
            # Execute database and system tasks in parallel
            db_task = self._run_chroma_worker({"action": "stats"})
            ollama_task = get_ollama_info()
            metrics_task = get_sys_metrics()
            
            db_stats, (ollama_status, ollama_lat), (hostname, mem_info, disk_info) = await asyncio.gather(
                db_task, ollama_task, metrics_task
            )

            current_model = self.config_manager.get("ollama_model", "N/A")
            provider = self.config_manager.get("ai_provider", "ollama")
            emb_provider = self.config_manager.get("embedding_provider", "ollama")
            
            import html
            report = (
                "📊 <b>Status do Sistema</b>\n\n"
                f"🖥️ <b>Host:</b> <code>{html.escape(hostname)}</code>\n"
                f"📈 <b>RAM:</b> <code>{mem_info}</code>\n"
                f"💽 <b>Disco:</b> <code>{disk_info}</code>\n\n"
                f"🤖 <b>AI Chat:</b> <code>{provider.upper()}</code> ({html.escape(str(current_model))})\n"
                f"🧬 <b>Embeddings:</b> <code>{emb_provider.upper()}</code>\n"
                f"📡 <b>Ollama:</b> {ollama_status} ({ollama_lat})\n\n"
                "📂 <b>Base de Conhecimento:</b>\n"
                f"- Arquivos: <code>{db_stats.get('file_count', 0)}</code>\n"
                f"- Fragmentos: <code>{db_stats.get('chunk_count', 0)}</code>\n\n"
                "<i>Nota: Para teste de internet, use /speedtest separadamente.</i>"
            )
            await status_msg.edit_text(report, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erro no status: {e}")
            await status_msg.edit_text(f"❌ Erro ao obter status: {e}")

    async def _cmd_restart_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/reiniciar_bot - Restart the bot process."""
        import os, sys
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _cmd_verbosity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/logs [baixo|médio|alto] - Switch logging levels."""
        if not update.message or not self._is_admin(update): return
        
        if not context.args:
            current = self.config_manager.get("log_verbosity", "médio")
            await update.message.reply_text(
                f"📝 <b>Configuração de Logs</b>\n\n"
                f"Nível atual: <code>{current}</code>\n\n"
                f"Opções:\n"
                f"• <code>/logs baixo</code> (Apenas erros importantes)\n"
                f"• <code>/logs médio</code> (Padrão: info e ações)\n"
                f"• <code>/logs alto</code> (Debug completo / depuração)\n\n"
                f"<i>Nota: Alterar o nível reiniciará o bot para aplicar as novas regras.</i>",
                parse_mode="HTML"
            )
            return

        level = context.args[0].lower()
        if level not in ["baixo", "médio", "alto"]:
            await update.message.reply_text("❌ Nível inválido. Use: baixo, médio ou alto.")
            return

        self.config_manager.set("log_verbosity", level)
        await update.message.reply_text(f"✅ Nível de logs alterado para <b>{level}</b>. Reiniciando...", parse_mode="HTML")
        
        # Restart to apply logging changes (logging configuration is done at startup)
        import os, sys
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _cmd_clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/limpar_historico - Delete all interaction logs."""
        if not update.message or not self._is_admin(update): return
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sim, Limpar Tudo", callback_data="btn_confirm_clear_history"),
                InlineKeyboardButton("❌ Cancelar", callback_data="btn_cancel_clear_history")
            ]
        ])
        await update.message.reply_text(
            "⚠️ <b>AVISO CRÍTICO</b>\n\n"
            "Você está prestes a apagar <b>TODO o histórico de interações</b> dos usuários. "
            "Isso zerará as estatísticas e os resumos de IA.\n\n"
            "Deseja continuar?",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    async def _cmd_monitor_cpu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/monitor_cpu - Show CPU usage and top processes."""
        if not update.message: return
        if not self._is_admin(update): return
        import psutil
        cpu_usage = psutil.cpu_percent(interval=1)
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                procs.append(p.info)
            except: pass
        procs = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:5]
        
        import html
        plist = "\n".join([f"<code>{p['pid']}</code>: {html.escape(str(p['name']))} ({p['cpu_percent']}%)" for p in procs])
        await update.message.reply_text(f"📊 <b>Uso de CPU:</b> {cpu_usage}%\n\n<b>Top Processos:</b>\n{plist}", parse_mode="HTML")

    async def _cmd_speedtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/speedtest - Perform internet speed test."""
        if not update.message: return
        if not self._is_admin(update): return
        status_msg = await update.message.reply_text("🌐 Iniciando Speedtest... Isso pode levar 30 segundos.")
        try:
            import speedtest
            st = speedtest.Speedtest()
            st.get_best_server()
            download = st.download() / 1_000_000
            upload = st.upload() / 1_000_000
            ping = st.results.ping
            await status_msg.edit_text(
                f"🚀 <b>Resultado Speedtest:</b>\n\n"
                f"⬇️ Download: <code>{download:.2f} Mbps</code>\n"
                f"⬆️ Upload: <code>{upload:.2f} Mbps</code>\n"
                f"🏓 Ping: <code>{ping:.1f} ms</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Erro no Speedtest: {e}")

    async def _cmd_ping_ia(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/ping_ia - Check latency to AI providers."""
        if not update.message: return
        if not self._is_admin(update): return
        import time, httpx
        report = "🏓 <b>Latência da IA:</b>\n\n"
        
        # Ollama
        ollama_url = self.config_manager.get("ollama_url", "http://127.0.0.1:11434")
        try:
            start_time = time.time()
            async with httpx.AsyncClient() as client:
                await client.get(f"{ollama_url}/api/tags", timeout=5)
            lat = (time.time() - start_time) * 1000
            report += f"🏠 <b>Ollama (Local):</b> <code>{lat:.0f}ms</code>\n"
        except:
            report += "🏠 <b>Ollama (Local):</b> ❌ Timeout/Erro\n"
            
        # OpenRouter
        try:
            start_time = time.time()
            async with httpx.AsyncClient() as client:
                await client.get("https://openrouter.ai/api/v1/models", timeout=5)
            lat = (time.time() - start_time) * 1000
            report += f"☁️ <b>OpenRouter (Cloud):</b> <code>{lat:.0f}ms</code>\n"
        except:
            report += "☁️ <b>OpenRouter (Cloud):</b> ❌ Timeout/Erro\n"
            
        await update.message.reply_text(report, parse_mode="HTML")

    async def _cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/atualizar - Git pull and restart."""
        if not update.message: return
        if not self._is_admin(update): return
        status_msg = await update.message.reply_text("🔄 Iniciando atualização via Git...")
        import subprocess, sys, os
        try:
            # 1. Stash local changes to avoid conflicts
            subprocess.run(["git", "stash"], capture_output=True, text=True)
            
            # 2. Git Pull
            res = subprocess.run(["git", "pull"], capture_output=True, text=True)
            if res.returncode != 0:
                subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
                await status_msg.edit_text(f"❌ Erro no Git Pull:\n<code>{res.stderr}</code>", parse_mode="HTML")
                return
            
            # 3. Restore stashed local changes (if any)
            subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
            
            # 2. Pip Install
            await status_msg.edit_text("📦 Git atualizado. Verificando dependências...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            
            await status_msg.edit_text("✅ Tudo pronto! Reiniciando processo...")
            await asyncio.sleep(2)
            
            # Create flag file so the bot knows to notify admin after restart
            flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".update_restart")
            with open(flag_path, 'w') as f:
                f.write(res.stdout.strip())
            
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await status_msg.edit_text(f"❌ Erro na atualização: {e}")

    async def _check_update_restart(self) -> None:
        """Check if the bot was restarted after /atualizar and notify admin."""
        flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".update_restart")
        if not os.path.exists(flag_path):
            return
        
        try:
            with open(flag_path, 'r') as f:
                git_output = f.read().strip()
            os.remove(flag_path)
            
            admin_ids_raw = self.config_manager.get("admin_id", "")
            if not admin_ids_raw:
                return
            
            msg = (
                "✅ <b>Atualização concluída com sucesso!</b>\n\n"
                f"<b>Git Pull:</b>\n<code>{git_output or 'Already up to date.'}</code>\n\n"
                "O bot foi reiniciado e está operando normalmente."
            )
            
            for admin_id in str(admin_ids_raw).split(","):
                admin_id = admin_id.strip()
                if admin_id:
                    try:
                        await self.application.bot.send_message(
                            chat_id=int(admin_id), text=msg, parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Não foi possível notificar admin {admin_id}: {e}")
        except Exception as e:
            logger.error(f"Erro ao verificar flag de atualização: {e}")

    async def _cmd_saude(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/saude - Health check with uptime."""
        if not update.message: return
        if not self._is_admin(update): return
        
        uptime_seconds = int(time.time() - self._start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        if days > 0:
            uptime_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = f"{minutes}m"
        
        known_count = len(self._known_users)
        
        await update.message.reply_text(
            "💚 <b>Bot Operacional</b>\n\n"
            f"⏱️ <b>Uptime:</b> <code>{uptime_str}</code>\n"
            f"👥 <b>Usuários conhecidos:</b> <code>{known_count}</code>\n"
            f"📡 <b>Polling:</b> ✅ Ativo\n"
            f"🤖 <b>Provedor IA:</b> <code>{self.config_manager.get('ai_provider', 'N/A')}</code>\n\n"
            "<i>Se você recebeu esta mensagem, o bot está vivo e respondendo.</i>",
            parse_mode="HTML"
        )

    # --- Reminder System ---

    def _load_reminders(self) -> List[Dict[str, Any]]:
        if os.path.exists(self._reminders_file):
            try:
                with open(self._reminders_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return []
        return []

    def _save_reminders(self):
        with open(self._reminders_file, 'w', encoding='utf-8') as f:
            json.dump(self._reminders, f, ensure_ascii=False, indent=4)

    def _setup_reminder_jobs(self):
        """Register all pending reminders to the Telegram JobQueue."""
        if not self.application or not self.application.job_queue: return
        
        now = time.time()
        for rem in self._reminders[:]:
            if rem['timestamp'] > now:
                self.application.job_queue.run_once(
                    self._execute_reminder, 
                    when=rem['timestamp'] - now,
                    data=rem,
                    name=rem['id']
                )
            else:
                # Remove expired
                self._reminders.remove(rem)
        self._save_reminders()

    async def _execute_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Triggered by JobQueue to send the broadcast."""
        job = context.job
        if not job or not job.data: return
        rem = job.data
        
        # Send broadcast
        user_ids = self.analytics.get_unique_users()
        success = 0
        for uid in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=int(uid), 
                    text=f"⏰ <b>Lembrete Agendado:</b>\n\n{rem['message']}",
                    parse_mode="HTML"
                )
                success += 1
            except: pass
            await asyncio.sleep(0.05)
            
        logger.info(f"Lembrete '{rem['id']}' enviado para {success} usuários.")
        
        # Remove from list
        self._reminders = [r for r in self._reminders if r['id'] != rem['id']]
        self._save_reminders()

    async def _cmd_add_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/lembrete DD/MM HH:MM Mensagem ou /lembrete DD/MM/AAAA HH:MM Mensagem"""
        if not update.message or not self._is_admin(update): return
        
        args = context.args
        if not args or len(args) < 3:
            await update.message.reply_text(
                "📝 <b>Uso do Lembrete:</b>\n\n"
                "<code>/lembrete DD/MM HH:MM Sua Mensagem</code>\n"
                "Ex: <code>/lembrete 25/02 19:00 Prova de Algoritmos</code>",
                parse_mode="HTML"
            )
            return

        date_str = args[0]
        time_str = args[1]
        message = " ".join(args[2:])
        
        import datetime
        now = datetime.datetime.now()
        
        try:
            # Parse Date logic
            if len(date_str.split('/')) == 2:
                # DD/MM - assumes current year
                target_dt = datetime.datetime.strptime(f"{date_str}/{now.year} {time_str}", "%d/%m/%Y %H:%M")
            else:
                # DD/MM/YYYY
                target_dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            
            target_ts = target_dt.timestamp()
            
            if target_ts <= now.timestamp():
                await update.message.reply_text("❌ Erro: A data/hora deve estar no futuro.")
                return
                
            rem_id = f"rem_{int(target_ts)}"
            new_rem = {
                "id": rem_id,
                "timestamp": target_ts,
                "date_human": target_dt.strftime("%d/%m/%Y %H:%M"),
                "message": message
            }
            
            # Save and schedule
            self._reminders.append(new_rem)
            self._save_reminders()
            
            if self.application and self.application.job_queue:
                self.application.job_queue.run_once(
                    self._execute_reminder,
                    when=target_ts - now.timestamp(),
                    data=new_rem,
                    name=rem_id
                )
            
            await update.message.reply_text(
                f"✅ <b>Lembrete Agendado!</b>\n\n"
                f"📅 Data: <code>{new_rem['date_human']}</code>\n"
                f"💬 Mensagem: <i>{message}</i>",
                parse_mode="HTML"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Formato de data inválido. Use <code>DD/MM HH:MM</code>.", parse_mode="HTML")

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
                    await context.bot.send_message(chat_id=int(u_id), text=text_to_send, parse_mode="HTML")
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
            logger.info("System Prompt alterado pelo admin.")
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
            
            # Save permanently to 'arquivos' for later download support
            base_dir = os.path.dirname(os.path.abspath(__file__))
            target_path = os.path.join(base_dir, "arquivos")
            os.makedirs(target_path, exist_ok=True)
            file_path = os.path.join(target_path, file_name)
            
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
            
        except Exception as e:
            logger.error(f"Erro no /conhecimento: {e}")
            await status_msg.edit_text(f"❌ Erro ao injetar texto: {e}")

    async def _cmd_my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /meuid command."""
        if not update.message:
            return
        await update.message.reply_text(f"Seu ID do Telegram é: <code>{update.effective_user.id}</code>", parse_mode="HTML")

    def _get_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Return the standard menu keyboard built from config."""
        buttons_config = self.config_manager.get("menu_buttons", [])
        
        keyboard = []
        current_row = []
        
        for btn in buttons_config:
            if not btn.get("enabled", True):
                continue
                
            current_row.append(InlineKeyboardButton(btn["text"], callback_data=f"dyn_{btn['id']}"))
            
            # Max 2 buttons per row for better UX on mobile
            if len(current_row) >= 2:
                keyboard.append(current_row)
                current_row = []
        
        if current_row:
            keyboard.append(current_row)
            
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
        """Send an error notification to all admins via Telegram."""
        admin_ids_raw = self.config_manager.get("admin_id", "")
        if not admin_ids_raw or not self.application:
            return
        admin_list = [aid.strip() for aid in str(admin_ids_raw).split(",") if aid.strip()]
        for aid in admin_list:
            try:
                await self.application.bot.send_message(
                    chat_id=int(aid),
                    text=f"⚠️ ALERTA DO BOT:\n\n{message}"
                )
            except Exception as e:
                logger.error(f"Falha ao notificar admin {aid}: {e}")

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
        if not query:
            return
            
        # Answer immediately to avoid "Query is too old" timeout (Telegram limit is 10s)
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Could not answer callback query: {e}")
            
        data = query.data

        # --- Dynamic Buttons ---
        if data.startswith("dyn_"):
            btn_id = data[4:]
            buttons_config = self.config_manager.get("menu_buttons", [])
            btn_data = next((b for b in buttons_config if b["id"] == btn_id), None)
            
            if btn_data:
                await self._execute_button_action(query, btn_data)
                return
        elif data == "btn_prof_old":
             await query.edit_message_text(
                 text="<b>Prof. Carlo Ralph De Musis</b>\n\n"
                      "Telegram: @carlodemusis\n"
                      "Telefone: (65) 9 9262-5221\n"
                      "E-mail: carlo.demusis@gmail.com",
                 parse_mode="HTML"
             ) # type: ignore
             await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
        
        elif data == "btn_confirm_clear_history":
            if self.analytics.clear_history():
                await query.edit_message_text("✅ <b>Histórico de interações apagado com sucesso.</b>", parse_mode="HTML")
                logger.info("Histórico de interações limpo pelo administrador.")
            else:
                await query.edit_message_text("❌ Falha ao limpar o histórico.")
                
        elif data == "btn_cancel_clear_history":
            await query.edit_message_text("❌ Ação cancelada pelo administrador.")

        # --- Admin Buttons (Summary) ---
        elif data.startswith("btn_summary_"):
            count = int(data.split("_")[2])
            await self._generate_ai_summary(query, count)
            
        elif data.startswith("btn_dl_"):
            filename = data[7:]
            await self._download_document_file(query, filename)

    async def _execute_button_action(self, query, btn_data: Dict[str, Any]) -> None:
        """Execute the action defined for a dynamic button."""
        action = btn_data.get("action")
        param = btn_data.get("parameter", "")
        btn_text = btn_data.get("text", "Opção")

        if action == "fixed_text":
            try:
                await query.edit_message_text(text=param, parse_mode="HTML")
            except Exception:
                await query.edit_message_text(text=param)
            await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())

        elif action == "text_file":
            await query.edit_message_text(text=f"Buscando informações sobre {btn_text.lower()}...")
            try:
                arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
                file_path = os.path.join(arquivos_dir, param)
                
                if not os.path.exists(file_path):
                    await query.edit_message_text(
                        text=f"Erro: Arquivo <code>{param}</code> não encontrado.",
                        parse_mode="HTML"
                    )
                    return

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                if not content.strip():
                    await query.edit_message_text(text=f"O arquivo {param} está vazio.")
                    return

                await query.edit_message_text(
                    text=f"<b>{btn_text}</b>\n\n{content}",
                    parse_mode="HTML"
                )
                await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
            except Exception as e:
                logger.error(f"Erro ao ler arquivo {param}: {e}")
                await query.edit_message_text(text=f"Erro ao processar {btn_text.lower()}: {e}")

        elif action == "file_upload":
            await query.edit_message_text(text=f"Buscando arquivos de {btn_text.lower()}...")
            try:
                arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
                if not os.path.exists(arquivos_dir):
                    await query.edit_message_text(text="Pasta de arquivos não encontrada.")
                    return
                
                # Parameter should be the prefix, e.g., 'horario'
                files = [f for f in os.listdir(arquivos_dir) if f.lower().startswith(param.lower())]
                
                if not files:
                    await query.edit_message_text(text=f"Nenhum arquivo de {btn_text.lower()} disponível.")
                    return

                await query.edit_message_text(text=f"Encontrei {len(files)} arquivo(s). Enviando...")
                
                for filename in files:
                    file_path = os.path.join(arquivos_dir, filename)
                    with open(file_path, 'rb') as f:
                        await query.message.reply_document(
                            document=f,
                            filename=filename,
                            caption=f"📄 {filename}"
                        )
                
                await query.message.reply_text("Selecione outra opção ou digite sua dúvida:", reply_markup=self._get_menu_keyboard())
            except Exception as e:
                logger.error(f"Erro ao buscar arquivos prefixo {param}: {e}")
                await query.edit_message_text(text=f"Erro ao processar {btn_text.lower()}: {e}")

    async def _download_document_file(self, query, filename: str) -> None:
        """Send a document file to the user."""
        try:
            arquivos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
            file_path = os.path.join(arquivos_dir, filename)
            
            if not os.path.exists(file_path):
                # Check for truncated filename in callback_data
                potential_files = os.listdir(arquivos_dir)
                match = next((f for f in potential_files if f.startswith(filename)), None)
                if match:
                    file_path = os.path.join(arquivos_dir, match)
                    filename = match
                else:
                    await query.message.reply_text(f"❌ O arquivo original <code>{filename}</code> não foi encontrado no servidor.", parse_mode="HTML")
                    return

            with open(file_path, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📄 {filename} (Download Solicitado)"
                )
        except Exception as e:
            logger.error(f"Erro ao baixar arquivo {filename}: {e}")
            await query.message.reply_text(f"❌ Erro ao baixar arquivo: {e}")

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
                InlineKeyboardButton("Últimas 10", callback_data="btn_summary_10"),
                InlineKeyboardButton("Últimas 50", callback_data="btn_summary_50"),
                InlineKeyboardButton("Últimas 100", callback_data="btn_summary_100"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📊 **Relatório de Interações**\nEscolha a quantidade de mensagens recentes para análise:", reply_markup=reply_markup) # type: ignore

    async def _cmd_admin_insight(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Allow admin to query logs.
        Usage: /insight [days] [question]
        """
        if not self._is_admin(update):
            await update.message.reply_text("⛔ Acesso negado.") # type: ignore
            return
            
        if not context.args:
            await update.message.reply_text("Uso: `/insight [quantidade] [pergunta]`\nEx: `/insight 50 Quais as dúvidas sobre provas?`") # type: ignore
            return

        try:
            # Parse args
            if context.args[0].isdigit():
                count = int(context.args[0])
                question = " ".join(context.args[1:])
            else:
                count = 50
                question = " ".join(context.args)
                
            if not question:
                 await update.message.reply_text("Por favor, digite sua pergunta.") # type: ignore
                 return
                 
            await update.message.reply_text(f"🔍 Analisando as últimas {count} interações sobre: '{question}'...") # type: ignore
            
            # Get Logs
            logs_text = self.analytics.get_logs_by_count(count)
            if len(logs_text) < 10:
                await update.message.reply_text(f"ℹ️ {logs_text}") # type: ignore
                return
                
            # Construct Prompt
            prompt = (
                f"Analise o seguinte log das últimas {count} interações:\n\n"
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


    async def _generate_ai_summary(self, query, count: int) -> None:
        """Generate AI Summary from last 'count' interactions."""
        await query.edit_message_text(text=f"🔄 Analisando as últimas {count} interações... aguarde.")
        
        # 1. Get Logs
        logs_text = self.analytics.get_logs_by_count(count)
        if len(logs_text) < 10: # "Nenhum..." or empty
             await query.edit_message_text(text=f"ℹ️ {logs_text}")
             return

        # 2. Prompt LLM
        prompt = (
            f"Analise o seguinte log das últimas {count} interações:\n\n"
            f"{logs_text}\n\n"
            "FAÇA UM RESUMO EXECUTIVO (MÁXIMO 200 PALAVRAS) DESTACANDO:\n"
            "1. Principais dúvidas ou problemas relatados.\n"
            "2. Sugestão de melhoria ou FAQ baseada nessas dúvidas.\n"
            "Formate em Markdown legível."
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
            
            if not response_text:
                await query.edit_message_text(text="⚠️ A IA não retornou um resumo para os logs analisados.")
                return

            try:
                await query.edit_message_text(text=f"📊 **Relatório IA ({count} interações)**\n\n{response_text}", parse_mode="Markdown")
            except Exception as markdown_err:
                logger.warning(f"Failed to send summary with Markdown, falling back to plain text: {markdown_err}")
                await query.edit_message_text(text=f"📊 Relatório IA ({count} interações)\n\n{response_text}")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Erro no sumário IA: {e}\n{error_details}")
            await query.edit_message_text(text="❌ Erro ao gerar o resumo dos logs do servidor. Por favor, tente novamente mais tarde.")

    def _is_admin(self, update: Update) -> bool:
        """Check if user is admin. Supports multiple IDs separated by comma."""
        admin_ids_raw = self.config_manager.get("admin_id", "")
        if not admin_ids_raw:
            return False
        user_id = str(update.effective_user.id)
        admin_list = [aid.strip() for aid in str(admin_ids_raw).split(",") if aid.strip()]
        return user_id in admin_list

    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document uploads (Admin Only)."""
        if not self._is_admin(update):
            # Ignore or reply
            await update.message.reply_text("Eu não posso processar arquivos enviados por você.") # type: ignore
            return
        
        file = await update.message.document.get_file() # type: ignore
        file_name = update.message.document.file_name # type: ignore
        
        await update.message.reply_text(f"📥 Recebendo {file_name}...") # type: ignore
        
        # Save permanently to 'arquivos' for later download support
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(base_dir, "arquivos")
        os.makedirs(target_path, exist_ok=True)
        file_path = os.path.join(target_path, file_name)
        
        await file.download_to_drive(file_path)
        
        # Ingest via subprocess worker
        try:
            await update.message.reply_text("⚙️ Processando e Indexando...") # type: ignore
            
            result = await self._run_chroma_worker({
                "action": "ingest",
                "file_path": file_path
            })
            
            chunks = result.get('chunks_count', 0)
            await update.message.reply_text(f"✅ Sucesso! {chunks} fragmentos adicionados.\nO arquivo agora está disponível para baixar no menu /listar.") # type: ignore
        except Exception as e:
            import traceback
            logger.error(f"Erro na ingestão do arquivo: {type(e).__name}: {e}")
            logger.error(traceback.format_exc())
            try:
                await update.message.reply_text(f"❌ Erro ao processar: {e}") # type: ignore
            except Exception:
                pass  # Prevent reply failure from propagating
        # No cleanup (remove) here, we want to keep it in 'arquivos'

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
                "⏳ <b>Aviso de Frequência de Mensagens</b>\n\n"
                "Prezado aluno, para garantir a estabilidade do sistema e o atendimento equânime a todos os usuários, "
                "há um limite de interações por minuto. Por favor, aguarde um momento antes de formular sua próxima dúvida.\n\n"
                "Recomendamos que suas perguntas sejam objetivas e contenham o contexto necessário para uma resposta completa.",
                parse_mode="HTML"
            )
            # Send menu buttons even on rate limit
            await update.message.reply_text(
                "Enquanto aguarda, utilize o menu abaixo para navegar pelas informações disponíveis:",
                reply_markup=self._get_menu_keyboard()
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
            elif cmd_part == "embedding":
                context.args = parts[1:] if len(parts) > 1 else []
                return await self._cmd_embedding(update, context)
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
                elif cmd_part == "reiniciar_bot":
                    return await self._cmd_restart_bot(update, context)
                elif cmd_part == "monitor_cpu":
                    return await self._cmd_monitor_cpu(update, context)
                elif cmd_part == "speedtest":
                    return await self._cmd_speedtest(update, context)
                elif cmd_part == "ping_ia":
                    return await self._cmd_ping_ia(update, context)
                elif cmd_part == "atualizar":
                    return await self._cmd_update(update, context)
                elif cmd_part == "lembrete":
                    context.args = parts[1:] if len(parts) > 1 else []
                    return await self._cmd_add_reminder(update, context)
        
        # Welcome message for first-time users
        if user_id not in self._known_users:
            self._known_users.add(user_id)
            user_name = update.effective_user.first_name or "Aluno(a)"
            
            welcome_text = self.config_manager.get("welcome_message", "")
            if welcome_text:
                # Support {nome} placeholder
                welcome_text = welcome_text.replace("{nome}", user_name)
                await update.message.reply_text(
                    f"👋 <b>Olá, {user_name}! Seja bem-vindo(a)!</b>\n\n"
                    f"{welcome_text}",
                    parse_mode="HTML",
                    reply_markup=self._get_menu_keyboard()
                )
        
        # Auto-show /start on first message of the day
        import datetime
        today_str = datetime.date.today().isoformat()
        if self._user_last_greeting.get(user_id) != today_str:
            self._user_last_greeting[user_id] = today_str
            # Skip start menu if already sent welcome above
            if user_id in self._known_users:
                await self._send_start_menu(update)
        
        # 1. Retrieve Context
        try:
            if update.effective_chat:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            emb_provider = self.config_manager.get("embedding_provider", "ollama")
            
            # Guard against model name contamination
            if emb_provider == "openrouter":
                model_name = self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
            else:
                model_name = self.config_manager.get("ollama_embedding_model", "qwen3-embedding:latest")

            logger.info(f"Conectando ao provedor de Embeddings ({emb_provider}) - Modelo: {model_name}...")
            
            rag_k = self.config_manager.get("rag_k", 8)
            result = await self._run_chroma_worker({
                "action": "query",
                "query": user_query,
                "k": rag_k,
                "model_name": model_name, # Overwrite with correct name for safety
                "embedding_provider": emb_provider
            })
            
            logger.info(f"Conexão com Embeddings ({emb_provider}) bem-sucedida! {len(result)} trechos recuperados.")
            
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
                
                # Safety: If it's Ollama but looks like an OpenRouter model name (has a slash), strip the prefix
                if "/" in model:
                    old_model = model
                    model = model.split("/")[-1]
                    logger.warning(f"Nome do modelo Ollama parecia inválido ('{old_model}'). Corrigido para '{model}'")

                logger.info(f"Iniciando geração com Ollama (Modelo: {model})...")
                generator = self.ollama_adapter.generate_response(
                    model=model,
                    prompt=full_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            
            chunk_count = 0
            for chunk in generator:
                if chunk_count == 0:
                     logger.info("Primeiro fragmento recebido da IA.")
                response_text += chunk
                chunk_count += 1
            
            logger.info(f"Geração concluída. Total de fragmentos: {chunk_count}. Tamanho: {len(response_text)} caracteres.")
                
            # 4. Reply
            if response_text:
                # Clean markdown since we are sending as plain text
                response_text = self._clean_markdown(response_text)
                
                # Split long messages (Telegram limit is 4096 chars)
                MAX_LEN = 4000
                if len(response_text) > MAX_LEN:
                    parts = [response_text[i:i+MAX_LEN] for i in range(0, len(response_text), MAX_LEN)]
                    for part in parts:
                        await update.message.reply_text(part) # type: ignore
                else:
                    await update.message.reply_text(response_text) # type: ignore
                
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
        
        # ALWAYS show menu buttons at the end, regardless of success or failure
        try:
            await update.message.reply_text("Selecione uma opção ou digite outra dúvida:", reply_markup=self._get_menu_keyboard()) # type: ignore
        except Exception:
            pass  # Last-resort: don't let button sending crash the handler
