import sys
import os
import asyncio
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
    QTextEdit, QPushButton, QLabel, QFileDialog, QProgressBar, 
    QLineEdit, QFormLayout, QDoubleSpinBox, QSpinBox, QMessageBox,
    QComboBox
)
from PyQt6.QtCore import pyqtSlot, Qt, QTimer
from config_manager import ConfigurationManager
from log_observer import LogObserver
from async_worker import AsyncBridgeWorker
from telegram_controller import TelegramBotController
from rag_repository import VectorStoreRepository
from ollama_client import OllamaAdapter

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador do Bot Telegram com IA")
        self.resize(900, 700)
        
        # Dependencies
        self.config_manager = ConfigurationManager()
        self.log_observer = LogObserver()
        
        # Worker Thread
        self.async_worker = AsyncBridgeWorker()
        self.async_worker.start()
        
        # Controller (lazy init to allow config updates first, 
        # but we need it for start/stop. We init here but start later)
        self.telegram_controller = None

        # UI Setup
        self.init_ui()
        
        # Connect Log Observer
        self.log_observer.log_signal.connect(self.append_log)

    def closeEvent(self, event):
        """Handle execution shutdown cleanly."""
        if self.telegram_controller:
            # We can't easily wait for async stop here in closeEvent without 
            # blocking UI or sophisticated handling. 
            # Ideally we signal stop to worker.
            pass
        self.async_worker.stop()
        event.accept()

    def init_ui(self):
        """Initialize the UI components."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab 1: Terminal & Control
        self.tab_terminal = QWidget()
        self.init_terminal_tab()
        self.tabs.addTab(self.tab_terminal, "Terminal e Controle")
        
        # Tab 2: Knowledge Base
        self.tab_knowledge = QWidget()
        self.init_knowledge_tab()
        self.tabs.addTab(self.tab_knowledge, "Base de Conhecimento")
        
        # Tab 3: settings
        self.tab_settings = QWidget()
        self.init_settings_tab()
        self.tabs.addTab(self.tab_settings, "Configuração")

    def init_terminal_tab(self):
        """Setup the Terminal tab."""
        layout = QVBoxLayout(self.tab_terminal)
        
        # Controls
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Iniciar Bot")
        self.btn_start.clicked.connect(self.start_bot)
        self.btn_stop = QPushButton("Parar Bot")
        self.btn_stop.clicked.connect(self.stop_bot)
        self.btn_stop.setEnabled(False)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_layout)
        
        # Terminal Output
        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        self.text_logs.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.text_logs)

    def init_knowledge_tab(self):
        """Setup the Knowledge Base tab."""
        layout = QVBoxLayout(self.tab_knowledge)
        
        # File Selection
        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("Nenhum arquivo selecionado")
        btn_select = QPushButton("Selecionar Arquivo")
        btn_select.clicked.connect(self.select_file)
        
        file_layout.addWidget(btn_select)
        file_layout.addWidget(self.lbl_file)
        layout.addLayout(file_layout)
        
        # Ingest Action
        self.btn_ingest = QPushButton("Ingerir na Base Vetorial")
        self.btn_ingest.clicked.connect(self.ingest_file)
        self.btn_ingest.setEnabled(False)
        layout.addWidget(self.btn_ingest)
        
        # Clear DB Action
        btn_clear = QPushButton("Limpar Banco de Dados")
        btn_clear.clicked.connect(self.clear_db)
        layout.addWidget(btn_clear)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        layout.addStretch()

    def init_settings_tab(self):
        """Setup the Configuration tab."""
        layout = QFormLayout(self.tab_settings)
        
        # Provider Selection
        self.input_provider = QComboBox()
        self.input_provider.addItems(["Ollama", "OpenRouter"])
        self.input_provider.currentTextChanged.connect(self.toggle_provider_ui)
        
        self.input_telegram_token = QLineEdit()
        self.input_telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.input_admin_id = QLineEdit()
        self.input_admin_id.setPlaceholderText("IDs separados por vírgula (ex: 123456,789012)")
        
        # Ollama Widgets
        self.input_ollama_url = QLineEdit()
        
        # OpenRouter Widgets
        self.input_openrouter_key = QLineEdit()
        self.input_openrouter_key.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.input_model_name = QComboBox() # Shared or Separate? Shared for simplicity, just text.
        self.input_model_name.setEditable(True)
        
        self.input_sys_prompt = QTextEdit()
        self.input_sys_prompt.setMaximumHeight(100)
        
        self.input_temp = QDoubleSpinBox()
        self.input_temp.setRange(0.0, 1.0)
        self.input_temp.setSingleStep(0.1)
        
        self.input_max_token = QSpinBox()
        self.input_max_token.setRange(100, 32000)
        
        self.input_rag_k = QSpinBox()
        self.input_rag_k.setRange(1, 50)
        self.input_rag_k.setSuffix(" trechos")
        
        self.input_chat_history = QSpinBox()
        self.input_chat_history.setRange(0, 20)
        self.input_chat_history.setSuffix(" mensagens")
        self.input_chat_history.setToolTip("Quantas mensagens anteriores o bot lembra por aluno (0 = desativado)")
        
        self.input_rate_limit = QSpinBox()
        self.input_rate_limit.setRange(1, 60)
        self.input_rate_limit.setSuffix(" msg/min")
        self.input_rate_limit.setToolTip("Máximo de mensagens por minuto por usuário")
        
        # ChromaDB Directory
        chroma_layout = QHBoxLayout()
        chroma_layout.setContentsMargins(0, 0, 0, 0)
        self.input_chroma_dir = QLineEdit()
        self.input_chroma_dir.setPlaceholderText("Padrão: ~/.atendimento_bot/chroma_db")
        self.btn_browse_chroma = QPushButton("Procurar...")
        self.btn_browse_chroma.clicked.connect(self._browse_chroma_dir)
        chroma_layout.addWidget(self.input_chroma_dir)
        chroma_layout.addWidget(self.btn_browse_chroma)
        chroma_widget = QWidget()
        chroma_widget.setLayout(chroma_layout)
        
        layout.addRow("Provedor de IA:", self.input_provider)
        layout.addRow("Token do Telegram:", self.input_telegram_token)
        layout.addRow("Admin ID:", self.input_admin_id)
        
        self.lbl_ollama_url = QLabel("URL do Ollama:")
        self.lbl_or_key = QLabel("API Key OpenRouter:")
        
        layout.addRow(self.lbl_ollama_url, self.input_ollama_url)
        layout.addRow(self.lbl_or_key, self.input_openrouter_key)
        
        layout.addRow("Modelo (Nome):", self.input_model_name)
        layout.addRow("Prompt do Sistema:", self.input_sys_prompt)
        layout.addRow("Temperatura:", self.input_temp)
        layout.addRow("Máx Tokens:", self.input_max_token)
        layout.addRow("Memória de Busca (K):", self.input_rag_k)
        layout.addRow("Histórico de Conversa:", self.input_chat_history)
        layout.addRow("Limite de Mensagens:", self.input_rate_limit)
        layout.addRow("Diretório ChromaDB:", chroma_widget)
        
        # Setup Autosave
        self.setup_autosave()
        
        # Status Label for Save
        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setStyleSheet("color: #00ff00; font-weight: bold;")
        layout.addRow("", self.lbl_save_status)
        
        self.btn_refresh_models = QPushButton("Atualizar Modelos")
        self.btn_refresh_models.clicked.connect(self.refresh_models)
        layout.addRow(self.btn_refresh_models)
        
        # Initial Load
        self.load_settings_to_ui()
        self.toggle_provider_ui(self.input_provider.currentText())


    # --- Logic ---

    def setup_autosave(self):
        """Connect widgets to autosave logic."""
        from PyQt6.QtCore import QTimer
        
        # Debounce timer
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000) # 1 second delay
        self._save_timer.timeout.connect(self.persist_settings)
        
        # Connect signals
        self.input_provider.currentTextChanged.connect(self.trigger_autosave)
        self.input_telegram_token.textChanged.connect(self.trigger_autosave)
        self.input_admin_id.textChanged.connect(self.trigger_autosave)
        self.input_ollama_url.textChanged.connect(self.trigger_autosave)
        self.input_openrouter_key.textChanged.connect(self.trigger_autosave)
        self.input_model_name.currentTextChanged.connect(self.trigger_autosave)
        self.input_sys_prompt.textChanged.connect(self.trigger_autosave)
        self.input_temp.valueChanged.connect(self.trigger_autosave)
        self.input_max_token.valueChanged.connect(self.trigger_autosave)
        self.input_rag_k.valueChanged.connect(self.trigger_autosave)
        self.input_chat_history.valueChanged.connect(self.trigger_autosave)
        self.input_rate_limit.valueChanged.connect(self.trigger_autosave)
        self.input_chroma_dir.textChanged.connect(self.trigger_autosave)

    def toggle_provider_ui(self, provider: str):
        """Show/Hide fields based on provider."""
        is_ollama = (provider == "Ollama")
        
        self.lbl_ollama_url.setVisible(is_ollama)
        self.input_ollama_url.setVisible(is_ollama)
        
        self.lbl_or_key.setVisible(not is_ollama)
        self.input_openrouter_key.setVisible(not is_ollama)
        
        if is_ollama:
            self.btn_refresh_models.setText("Atualizar Modelos (Ollama)")
        else:
            self.btn_refresh_models.setText("Listar Modelos Comuns (OpenRouter)")

    @pyqtSlot()
    def trigger_autosave(self):
        """Reset timer for autosave."""
        self.lbl_save_status.setText("Salvando...")
        self.lbl_save_status.setStyleSheet("color: #ffff00;") # Yellow
        self._save_timer.start()

    @pyqtSlot()
    def persist_settings(self):
        """Save all UI values to ConfigManager using batch update."""
        provider = self.input_provider.currentText().lower() # ollama or openrouter
        
        updates = {
            "ai_provider": provider,
            "telegram_token": self.input_telegram_token.text(),
            "admin_id": self.input_admin_id.text(),
            "ollama_url": self.input_ollama_url.text(),
            "openrouter_key": self.input_openrouter_key.text(),
            # For simplicity, we save the current model combo text to the specific key based on provider
            # But better is to just save both if we tracked them, OR just save to 'ollama_model'/'openrouter_model'
            # Let's map current model text to the right key
        }
        
        if provider == "ollama":
            updates["ollama_model"] = self.input_model_name.currentText()
        else:
            updates["openrouter_model"] = self.input_model_name.currentText()

        updates["system_prompt"] = self.input_sys_prompt.toPlainText()
        updates["temperature"] = self.input_temp.value()
        updates["max_tokens"] = self.input_max_token.value()
        updates["rag_k"] = self.input_rag_k.value()
        updates["chat_history_size"] = self.input_chat_history.value()
        updates["rate_limit_per_minute"] = self.input_rate_limit.value()
        updates["chroma_dir"] = self.input_chroma_dir.text()

        self.config_manager.update_batch(updates)
        
        self.lbl_save_status.setText("Configuração Salva!")
        self.lbl_save_status.setStyleSheet("color: #00ff00;") # Green
        
        # Clear message after a while
        QTimer.singleShot(3000, lambda: self.lbl_save_status.setText(""))

    @pyqtSlot(str)
    def append_log(self, text: str):
        """Append text to the log widget."""
        self.text_logs.append(text)

    def load_settings_to_ui(self):
        """Load values from ConfigManager to UI fields."""
        data = self.config_manager.config_data
        
        # Block signals
        self.input_provider.blockSignals(True)
        # ... block others ...
        
        try:
            # Provider
            prov = data.get("ai_provider", "ollama").capitalize()
            if prov not in ["Ollama", "Openrouter"]: prov = "Ollama"
            self.input_provider.setCurrentText(prov)

            self.input_telegram_token.setText(data.get("telegram_token", ""))
            self.input_admin_id.setText(str(data.get("admin_id", "")))
            self.input_ollama_url.setText(data.get("ollama_url", "http://127.0.0.1:11434"))
            self.input_openrouter_key.setText(data.get("openrouter_key", ""))
            
            # Model logic: load based on provider
            if prov.lower() == "ollama":
                self.input_model_name.setCurrentText(data.get("ollama_model", "llama3:latest"))
            else:
                self.input_model_name.setCurrentText(data.get("openrouter_model", "openai/gpt-3.5-turbo"))

            self.input_sys_prompt.setText(data.get("system_prompt", ""))
            self.input_temp.setValue(data.get("temperature", 0.7))
            self.input_max_token.setValue(data.get("max_tokens", 2048))
            self.input_rag_k.setValue(data.get("rag_k", 8))
            self.input_chat_history.setValue(data.get("chat_history_size", 5))
            self.input_rate_limit.setValue(data.get("rate_limit_per_minute", 10))
            self.input_chroma_dir.setText(data.get("chroma_dir", ""))
        finally:
             self.input_provider.blockSignals(False)
             # ... unblock others ...

    def refresh_models(self):
        """Fetch models."""
        provider = self.input_provider.currentText()
        
        self.input_model_name.blockSignals(True)
        current = self.input_model_name.currentText()
        self.input_model_name.clear()
        
        try:
            if provider == "Ollama":
                url = self.input_ollama_url.text()
                adapter = OllamaAdapter(base_url=url)
                models = adapter.list_models()
                self.input_model_name.addItems(models)
                QMessageBox.information(self, "Ollama", f"Modelos encontrados: {len(models)}")
            else:
                # OpenRouter List
                from openrouter_client import OpenRouterAdapter
                # We assume key is present
                key = self.input_openrouter_key.text()
                if not key:
                    QMessageBox.warning(self, "Aviso", "Insira a API Key do OpenRouter.")
                    return
                adapter = OpenRouterAdapter(api_key=key)
                models = adapter.list_models()
                self.input_model_name.addItems(models)
                QMessageBox.information(self, "OpenRouter", f"Modelos comuns listados.")
                
            self.input_model_name.setCurrentText(current)
        except Exception as e:
             QMessageBox.critical(self, "Erro", f"Erro: {e}")
        finally:
            self.input_model_name.blockSignals(False)

    # --- Bot Logic ---
    
    def start_bot(self):
        """Instantiate controller and start it in worker."""
        if self.telegram_controller:
            return 
            
        self.telegram_controller = TelegramBotController()
        
        # Submit the start coroutine to the worker
        # We don't await here because it blocks. The start() method runs forever.
        # We need to ensure start() is async and run it.
        
        def run_bot_task():
             # This runs in the worker thread
             asyncio.run_coroutine_threadsafe(self.telegram_controller.start(), self.async_worker.loop)

        # But wait, self.telegram_controller.start() is a coroutine. 
        # We can just submit it.
        self.async_worker.submit(self.telegram_controller.start())
        
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.text_logs.append(">> Sinal de Início do Bot Enviado.")

    def stop_bot(self):
        """Stop the bot."""
        if self.telegram_controller:
            self.async_worker.submit(self.telegram_controller.stop())
            self.telegram_controller = None
            
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.text_logs.append(">> Sinal de Parada do Bot Enviado.")

    # --- Knowledge Base Logic ---

    def _browse_chroma_dir(self):
        """Open directory picker for ChromaDB storage."""
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Diretório ChromaDB")
        if dir_path:
            self.input_chroma_dir.setText(dir_path)

    def select_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Abrir Arquivo", "", "Documentos (*.pdf *.txt *.csv *.md)")
        if fname:
            self.lbl_file.setText(fname)
            self.btn_ingest.setEnabled(True)

    def ingest_file(self):
        """Run ingestion in background."""
        import logging
        logger = logging.getLogger(__name__)
        
        fname = self.lbl_file.text()
        logger.info(f"Ingestão solicitada para: '{fname}'")
        
        if not fname or not os.path.exists(fname):
            logger.warning(f"Arquivo não encontrado ou não selecionado: '{fname}'")
            self.text_logs.append(f">> Arquivo não encontrado: '{fname}'")
            return
            
        self.progress_bar.setValue(10)
        self.btn_ingest.setEnabled(False)
        self.text_logs.append(f">> Iniciando ingestão de {fname}...")
        
        chroma_dir = self.config_manager.get("chroma_dir", "") or ""
        model_name = self.config_manager.get("embedding_model", "nomic-embed-text")
        
        import json, subprocess
        worker_data = json.dumps({
            "action": "ingest",
            "file_path": fname,
            "chroma_dir": chroma_dir,
            "model_name": model_name
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_ingest():
            """Run in subprocess to avoid PyQt6/SQLite DLL conflicts."""
            import sys
            result = subprocess.run(
                [sys.executable, worker_script],
                input=worker_data,
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Processo encerrado inesperadamente"
                raise RuntimeError(f"Falha na ingestão (exit {result.returncode}): {error_msg}")
            output = result.stdout.strip()
            if not output:
                raise RuntimeError("Processo de ingestão não retornou dados")
            # Parse JSON from last line (skip any warnings)
            last_line = output.split('\n')[-1]
            data = json.loads(last_line)
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "Erro desconhecido"))
            return data["result"]
        
        async def do_ingest():
            logger.info("do_ingest: Iniciando subprocess...")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, sync_ingest)
            logger.info(f"do_ingest: Concluído! Resultado: {result}")
            return result
            
        future = self.async_worker.submit(do_ingest())
        
        # Poll for completion
        self._monitor_future(future, self._on_ingest_complete)

    def clear_db(self):
        """Clear the vector database."""
        chroma_dir = self.config_manager.get("chroma_dir", "") or ""
        model_name = self.config_manager.get("embedding_model", "nomic-embed-text")
        
        import json, subprocess
        worker_data = json.dumps({
            "action": "clear",
            "chroma_dir": chroma_dir,
            "model_name": model_name
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_clear():
            import sys
            result = subprocess.run(
                [sys.executable, worker_script],
                input=worker_data,
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Processo encerrado inesperadamente"
                raise RuntimeError(f"Falha ao limpar DB (exit {result.returncode}): {error_msg}")
            output = result.stdout.strip()
            last_line = output.split('\n')[-1]
            data = json.loads(last_line)
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "Erro desconhecido"))
            return data["result"]
        
        async def do_clear():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, sync_clear)
        
        future = self.async_worker.submit(do_clear())
        self._monitor_future(future, lambda res: self.text_logs.append(f">> {res}"))

    def _monitor_future(self, future, callback):
        """Helper to check future completion."""
        from PyQt6.QtCore import QTimer
        timer = QTimer(self)
        
        def check():
            if future.done():
                timer.stop()
                try:
                    res = future.result()
                    callback(res)
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exception(type(e), e, e.__traceback__)
                    self.text_logs.append(f">> Tarefa Falhou: {e}")
                    self.text_logs.append(f">> Detalhes: {''.join(error_details[-3:])}")
                    self.progress_bar.setValue(0)
                    self.btn_ingest.setEnabled(True)
        
        timer.timeout.connect(check)
        timer.start(500) # Check every 500ms

    def _on_ingest_complete(self, result):
        self.progress_bar.setValue(100)
        chunks = result.get('chunks_count', 0)
        filename = result.get('filename', 'arquivo')
        msg = f">> Sucesso: {chunks} fragmentos ingeridos de '{filename}'."
        self.text_logs.append(msg)
        QMessageBox.information(self, "Ingestão Concluída", msg)
        self.btn_ingest.setEnabled(True)

