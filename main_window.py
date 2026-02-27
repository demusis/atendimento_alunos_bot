import os
import asyncio
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
    QTextEdit, QPushButton, QLabel, QFileDialog, 
    QLineEdit, QFormLayout, QDoubleSpinBox, QSpinBox, QMessageBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QScrollArea, QGroupBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSlot, QTimer
from config_manager import ConfigurationManager
from log_observer import LogObserver
from async_worker import AsyncBridgeWorker
from telegram_controller import TelegramBotController
from ollama_client import OllamaAdapter

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador do Bot Telegram com IA")
        self.resize(900, 700)
        
        # Set Window Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if not os.path.exists(icon_path):
             icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
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
        
        # Tab 4: Menu Customization
        self.tab_menu = QWidget()
        
        # Need action_map for loading settings
        self.action_map = {
            "fixed_text": "Texto Fixo (Configurado aqui)",
            "text_file": "Ler de Arquivo Texto (Em arquivos/)",
            "file_upload": "Upload de Arquivos (Pelo prefixo)"
        }
        self.action_inv_map = {v: k for k, v in self.action_map.items()}

        self.init_menu_tab()
        self.tabs.addTab(self.tab_menu, "Menu Principal")
        
        # Initial Load after ALL tabs are ready
        self.load_settings_to_ui()
        self.toggle_provider_ui(self.input_provider.currentText())

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
        btn_select = QPushButton("Selecionar arquivos")
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
        btn_clear = QPushButton("Limpar Banco de Dados (RAG)")
        btn_clear.clicked.connect(self.clear_db)
        layout.addWidget(btn_clear)

        # Clear Interaction History
        btn_clear_history = QPushButton("🚨 Zerar Histórico de Conversas (Logs)")
        btn_clear_history.setStyleSheet("background-color: #ffaa00; color: black; font-weight: bold;")
        btn_clear_history.clicked.connect(self.clear_history_action)
        layout.addWidget(btn_clear_history)

        # Document List Table
        layout.addWidget(QLabel("<b>📄 Documentos na Base:</b>"))
        self.table_knowledge = QTableWidget(0, 3)
        self.table_knowledge.setHorizontalHeaderLabels(["Arquivo", "Download", "Ações"])
        self.table_knowledge.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_knowledge.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_knowledge.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table_knowledge, 1)
        
        btn_refresh_list = QPushButton("Atualizar Lista")
        btn_refresh_list.clicked.connect(self.refresh_knowledge_list)
        layout.addWidget(btn_refresh_list)

    def init_settings_tab(self):
        """Setup the Configuration tab."""
        # Initial list refresh
        QTimer.singleShot(1000, self.refresh_knowledge_list)
        
        layout = QFormLayout(self.tab_settings)
        
        # Provider Selection
        self.input_provider = QComboBox()
        self.input_provider.addItems(["Ollama", "OpenRouter"])
        self.input_provider.currentTextChanged.connect(self.toggle_provider_ui)
        
        self.input_telegram_token = QLineEdit()
        self.input_telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.input_embed_provider = QComboBox()
        self.input_embed_provider.addItems(["Ollama", "OpenRouter"])
        
        self.input_embed_model = QComboBox()
        self.input_embed_model.setEditable(True)
        
        self.input_admin_id = QLineEdit()
        self.input_admin_id.setPlaceholderText("IDs separados por vírgula (ex: 123456,789012)")
        
        # Log Verbosity
        self.input_log_verbosity = QComboBox()
        self.input_log_verbosity.addItems(["Baixo", "Médio", "Alto"])
        self.input_log_verbosity.setToolTip("Nível de detalhes nos logs (Baixo: apenas erros, Alto: tudo)")
        
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
        layout.addRow("Nível de Logs:", self.input_log_verbosity)
        
        self.lbl_ollama_url = QLabel("URL do Ollama:")
        self.lbl_or_key = QLabel("API Key OpenRouter:")
        
        layout.addRow(self.lbl_ollama_url, self.input_ollama_url)
        layout.addRow(self.lbl_or_key, self.input_openrouter_key)
        
        layout.addRow("Modelo (IA):", self.input_model_name)
        layout.addRow("Prompt do Sistema:", self.input_sys_prompt)
        layout.addRow("Provedor de Embedding:", self.input_embed_provider)
        layout.addRow("Modelo Embedding:", self.input_embed_model)
        layout.addRow("Temperatura:", self.input_temp)
        layout.addRow("Máx Tokens:", self.input_max_token)
        layout.addRow("Memória de Busca (K):", self.input_rag_k)
        layout.addRow("Histórico de Conversa:", self.input_chat_history)
        layout.addRow("Limite de Mensagens:", self.input_rate_limit)
        layout.addRow("Diretório ChromaDB:", chroma_widget)
        
        # Welcome Message
        self.input_welcome_msg = QTextEdit()
        self.input_welcome_msg.setMaximumHeight(100)
        self.input_welcome_msg.setToolTip("Mensagem enviada automaticamente na primeira interação de cada aluno novo. Use {nome} para inserir o nome do aluno.")
        layout.addRow("Mensagem de Boas-vindas:", self.input_welcome_msg)
        
        # Setup Autosave
        self.setup_autosave()
        
        # Status Label for Save
        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setStyleSheet("color: #00ff00; font-weight: bold;")
        layout.addRow("", self.lbl_save_status)
        
        self.btn_refresh_models = QPushButton("Buscar Modelos")
        self.btn_refresh_models.clicked.connect(self.refresh_models)
        layout.addRow(self.btn_refresh_models)
 
    def init_menu_tab(self):
        """Setup the Menu Customization tab."""
        layout = QVBoxLayout(self.tab_menu)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.menu_layout = QVBoxLayout(scroll_content)
        
        self.button_widgets = []
        
        
        for i in range(5):
            group = QGroupBox(f"Botão {i+1}")
            g_layout = QFormLayout()
            
            chk_enabled = QCheckBox("Habilitado")
            txt_label = QLineEdit()
            cmb_action = QComboBox()
            cmb_action.addItems(list(self.action_map.values()))
            
            txt_param = QTextEdit()
            txt_param.setMaximumHeight(60)
            
            g_layout.addRow(chk_enabled)
            g_layout.addRow("Texto do Botão:", txt_label)
            g_layout.addRow("Tipo de Ação:", cmb_action)
            g_layout.addRow("Parâmetro (Texto/Arquivo/Prefixo):", txt_param)
            
            group.setLayout(g_layout)
            self.menu_layout.addWidget(group)
            
            # Store widgets to access them later
            self.button_widgets.append({
                "enabled": chk_enabled,
                "text": txt_label,
                "action": cmb_action,
                "parameter": txt_param
            })
            
            # Connect signals
            chk_enabled.toggled.connect(self.trigger_autosave)
            txt_label.textChanged.connect(self.trigger_autosave)
            cmb_action.currentTextChanged.connect(self.trigger_autosave)
            txt_param.textChanged.connect(self.trigger_autosave)
            
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        layout.addWidget(QLabel("<i>* Alterações são salvas automaticamente após 1 segundo.</i>"))


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
        self.input_provider.currentTextChanged.connect(self.on_ai_provider_changed)
        self.input_embed_provider.currentTextChanged.connect(self.on_embed_provider_changed)
        
        self.input_telegram_token.textChanged.connect(self.trigger_autosave)
        self.input_admin_id.textChanged.connect(self.trigger_autosave)
        self.input_log_verbosity.currentTextChanged.connect(self.trigger_autosave)
        self.input_ollama_url.textChanged.connect(self.trigger_autosave)
        self.input_openrouter_key.textChanged.connect(self.trigger_autosave)
        self.input_model_name.currentTextChanged.connect(self.trigger_autosave)
        self.input_sys_prompt.textChanged.connect(self.trigger_autosave)
        self.input_embed_model.currentTextChanged.connect(self.trigger_autosave)
        self.input_temp.valueChanged.connect(self.trigger_autosave)
        self.input_max_token.valueChanged.connect(self.trigger_autosave)
        self.input_rag_k.valueChanged.connect(self.trigger_autosave)
        self.input_chat_history.valueChanged.connect(self.trigger_autosave)
        self.input_rate_limit.valueChanged.connect(self.trigger_autosave)
        self.input_chroma_dir.textChanged.connect(self.trigger_autosave)
        self.input_welcome_msg.textChanged.connect(self.trigger_autosave)

    def toggle_provider_ui(self, provider: str):
        """Show/Hide fields based on provider."""
        is_ollama = (provider == "Ollama")
        
        self.lbl_ollama_url.setVisible(is_ollama)
        self.input_ollama_url.setVisible(is_ollama)
        
        self.lbl_or_key.setVisible(not is_ollama)
        self.input_openrouter_key.setVisible(not is_ollama)
        
        if is_ollama:
            self.btn_refresh_models.setText("Buscar Modelos")
        else:
            self.btn_refresh_models.setText("Buscar Modelos")

    def on_ai_provider_changed(self, provider: str):
        """Handle AI provider swap by loading the correct model for that provider first."""
        self.toggle_provider_ui(provider)
        
        self.input_model_name.blockSignals(True)
        if provider.lower() == "ollama":
            model = self.config_manager.get("ollama_model", "llama3:latest")
        else:
            model = self.config_manager.get("openrouter_model", "openai/gpt-3.5-turbo")
        
        self.input_model_name.setCurrentText(model)
        self.input_model_name.blockSignals(False)
        self.trigger_autosave()

    def on_embed_provider_changed(self, provider: str):
        """Handle Embedding provider swap by loading the correct model for that provider first."""
        self.input_embed_model.blockSignals(True)
        if provider.lower() == "ollama":
            model = self.config_manager.get("ollama_embedding_model", "qwen3-embedding:latest")
        else:
            model = self.config_manager.get("openrouter_embedding_model", "openai/text-embedding-3-small")
        
        self.input_embed_model.setCurrentText(model)
        self.input_embed_model.blockSignals(False)
        self.trigger_autosave()

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
            "log_verbosity": self.input_log_verbosity.currentText().lower(),
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
        updates["embedding_provider"] = self.input_embed_provider.currentText().lower()
        
        embed_model = self.input_embed_model.currentText()
        if updates["embedding_provider"] == "openrouter":
            updates["openrouter_embedding_model"] = embed_model
        else:
            updates["ollama_embedding_model"] = embed_model
        
        updates["temperature"] = self.input_temp.value()
        updates["max_tokens"] = self.input_max_token.value()
        updates["rag_k"] = self.input_rag_k.value()
        updates["chat_history_size"] = self.input_chat_history.value()
        updates["rate_limit_per_minute"] = self.input_rate_limit.value()
        updates["chroma_dir"] = self.input_chroma_dir.text()
        updates["welcome_message"] = self.input_welcome_msg.toPlainText()
        
        # Collect Menu Buttons
        menu_btns = []
        for i, widgets in enumerate(self.button_widgets):
            btn_id = f"btn{i+1}"
            action_display = widgets["action"].currentText()
            action_key = self.action_inv_map.get(action_display, "fixed_text")
            
            menu_btns.append({
                "id": btn_id,
                "enabled": widgets["enabled"].isChecked(),
                "text": widgets["text"].text(),
                "action": action_key,
                "parameter": widgets["parameter"].toPlainText()
            })
        updates["menu_buttons"] = menu_btns

        self.config_manager.update_batch(updates)
        
        self.lbl_save_status.setText("Configuração Salva!")
        self.lbl_save_status.setStyleSheet("color: #00ff00;") # Green
        
        # Clear message after a while
        QTimer.singleShot(3000, lambda: self.lbl_save_status.setText(""))

    @pyqtSlot(str)
    def append_log(self, text: str):
        """Append text to the log widget and scroll to bottom."""
        self.text_logs.append(text)
        self.text_logs.ensureCursorVisible()
        # Also scroll to bottom
        scrollbar = self.text_logs.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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
            
            verbosity = data.get("log_verbosity", "médio").capitalize()
            self.input_log_verbosity.setCurrentText(verbosity)
            self.input_ollama_url.setText(data.get("ollama_url", "http://127.0.0.1:11434"))
            self.input_openrouter_key.setText(data.get("openrouter_key", ""))
            
            # Model logic: load based on provider
            if prov.lower() == "ollama":
                self.input_model_name.setCurrentText(data.get("ollama_model", "llama3:latest"))
            else:
                self.input_model_name.setCurrentText(data.get("openrouter_model", "openai/gpt-3.5-turbo"))

            self.input_sys_prompt.setText(data.get("system_prompt", ""))
            
            emb_prov = data.get("embedding_provider", "ollama").capitalize()
            self.input_embed_provider.setCurrentText(emb_prov)
            
            if emb_prov.lower() == "openrouter":
                self.input_embed_model.setCurrentText(data.get("openrouter_embedding_model", "openai/text-embedding-3-small"))
            else:
                self.input_embed_model.setCurrentText(data.get("ollama_embedding_model", "qwen3-embedding:latest"))

            self.input_temp.setValue(data.get("temperature", 0.7))
            self.input_max_token.setValue(data.get("max_tokens", 2048))
            self.input_rag_k.setValue(data.get("rag_k", 8))
            self.input_chat_history.setValue(data.get("chat_history_size", 5))
            self.input_rate_limit.setValue(data.get("rate_limit_per_minute", 10))
            self.input_chroma_dir.setText(data.get("chroma_dir", ""))
            self.input_welcome_msg.setText(data.get("welcome_message", ""))
            
            # --- Menu Buttons ---
            buttons_config = data.get("menu_buttons", [])
            for i, btn in enumerate(buttons_config):
                if i >= len(self.button_widgets): break
                widgets = self.button_widgets[i]
                
                widgets["enabled"].blockSignals(True)
                widgets["text"].blockSignals(True)
                widgets["action"].blockSignals(True)
                widgets["parameter"].blockSignals(True)
                
                try:
                    widgets["enabled"].setChecked(btn.get("enabled", True))
                    widgets["text"].setText(btn.get("text", ""))
                    
                    action_key = btn.get("action", "fixed_text")
                    action_display = self.action_map.get(action_key, self.action_map["fixed_text"])
                    widgets["action"].setCurrentText(action_display)
                    
                    widgets["parameter"].setText(btn.get("parameter", ""))
                finally:
                    widgets["enabled"].blockSignals(False)
                    widgets["text"].blockSignals(False)
                    widgets["action"].blockSignals(False)
                    widgets["parameter"].blockSignals(False)
        finally:
             self.input_provider.blockSignals(False)
             # ... unblock others ...

    def refresh_models(self):
        """Fetch models for both AI and Embedding providers."""
        ai_provider = self.input_provider.currentText()
        emb_provider = self.input_embed_provider.currentText()
        
        self.input_model_name.blockSignals(True)
        self.input_embed_model.blockSignals(True)
        
        curr_ai = self.input_model_name.currentText()
        curr_emb = self.input_embed_model.currentText()
        
        self.text_logs.append(f">> Buscando modelos (IA: {ai_provider}, Embeddings: {emb_provider})...")
        
        try:
            # Function to fetch models for a specific provider
            def fetch_for_provider(provider_name):
                if provider_name == "Ollama":
                    url = self.input_ollama_url.text()
                    adapter = OllamaAdapter(base_url=url)
                    return adapter.list_models()
                else: # OpenRouter
                    from openrouter_client import OpenRouterAdapter
                    key = self.input_openrouter_key.text()
                    if not key:
                        raise ValueError("API Key do OpenRouter ausente.")
                    adapter = OpenRouterAdapter(api_key=key)
                    return adapter.list_models()

            # Cache results to avoid double fetching if providers are the same
            cache = {}
            
            # 1. Fetch for AI
            if ai_provider not in cache:
                cache[ai_provider] = fetch_for_provider(ai_provider)
            
            self.input_model_name.clear()
            self.input_model_name.addItems(cache[ai_provider])
            self.input_model_name.setCurrentText(curr_ai)
            
            # 2. Fetch for Embedding
            if emb_provider not in cache:
                cache[emb_provider] = fetch_for_provider(emb_provider)
                
            self.input_embed_model.clear()
            self.input_embed_model.addItems(cache[emb_provider])
            self.input_embed_model.setCurrentText(curr_emb)
            
            msg = f"Modelos atualizados!\nIA ({ai_provider}): {len(cache[ai_provider])} modelos\nEmbedding ({emb_provider}): {len(cache[emb_provider])} modelos"
            QMessageBox.information(self, "Sucesso", msg)
            self.text_logs.append(">> Lista de modelos atualizada com sucesso.")
            
        except Exception as e:
             QMessageBox.critical(self, "Erro ao buscar modelos", f"Erro: {e}")
             self.append_log(f">> Falha ao buscar modelos: {e}")
        finally:
            self.input_model_name.blockSignals(False)
            self.input_embed_model.blockSignals(False)

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
        self.append_log(">> [SINAL] Operação iniciada: Aguardando conexão do Telegram...")

    def stop_bot(self):
        """Stop the bot."""
        if self.telegram_controller:
            self.async_worker.submit(self.telegram_controller.stop())
            self.telegram_controller = None
            
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.append_log(">> [SINAL] Operação encerrada: O Bot foi parado.")

    # --- Knowledge Base Logic ---

    def _browse_chroma_dir(self):
        """Open directory picker for ChromaDB storage."""
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Diretório ChromaDB")
        if dir_path:
            self.input_chroma_dir.setText(dir_path)

    def select_file(self):
        fnames, _ = QFileDialog.getOpenFileNames(self, "Abrir Arquivos", "", "Documentos (*.pdf *.txt *.csv *.md *.docx)")
        if fnames:
            self.selected_files = fnames
            if len(fnames) == 1:
                self.lbl_file.setText(os.path.basename(fnames[0]))
            else:
                self.lbl_file.setText(f"{len(fnames)} arquivos selecionados")
            self.btn_ingest.setEnabled(True)

    def ingest_file(self):
        """Run ingestion in background."""
        import logging
        logger = logging.getLogger(__name__)
        
        if not hasattr(self, 'selected_files') or not self.selected_files:
            fname = self.lbl_file.text()
            if not fname or fname == "Nenhum arquivo selecionado" or not os.path.exists(fname):
                logger.warning("Nenhum arquivo válido selecionado")
                self.text_logs.append(">> Nenhum arquivo válido selecionado para ingestão")
                return
            self.selected_files = [fname]
            
        fnames = self.selected_files
        logger.info(f"Ingestão solicitada para: {fnames}")
        
        self.btn_ingest.setEnabled(False)
        self.append_log(f">> [PROCESSO] Iniciando ingestão de {len(fnames)} arquivo(s)...")
        
        chroma_dir = self.input_chroma_dir.text() or self.config_manager.get("chroma_dir", "") or ""
        provider = self.input_embed_provider.currentText().lower()
        if provider == "openrouter":
            model_name = self.input_embed_model.currentText() or self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.input_embed_model.currentText() or self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        api_key = self.input_openrouter_key.text() or self.config_manager.get("openrouter_key", "")
        ollama_url = self.input_ollama_url.text() or self.config_manager.get("ollama_url", "http://127.0.0.1:11434")
            
        # Ensure file is in 'arquivos' folder for download availability
        import shutil
        base_dir = os.path.dirname(os.path.abspath(__file__))
        arquivos_path = os.path.join(base_dir, "arquivos")
        os.makedirs(arquivos_path, exist_ok=True)
        
        target_fnames = []
        for fname_path in fnames:
            if not os.path.exists(fname_path):
                continue
                
            filename = os.path.basename(fname_path)
            target_fname = os.path.join(arquivos_path, filename)
            
            # Copy to 'arquivos' if it's not already there
            if os.path.abspath(fname_path) != os.path.abspath(target_fname):
                try:
                    shutil.copy2(fname_path, target_fname)
                    target_fnames.append(target_fname)
                except Exception as e:
                    logger.error(f"Erro ao copiar arquivo para 'arquivos': {e}")
                    target_fnames.append(fname_path)
            else:
                target_fnames.append(fname_path)

        import json, subprocess
        worker_data = json.dumps({
            "action": "ingest",
            "file_paths": target_fnames,
            "chroma_dir": chroma_dir,
            "model_name": model_name,
            "embedding_provider": provider,
            "api_key": api_key,
            "ollama_url": ollama_url
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_ingest():
            """Run in subprocess to avoid PyQt6/SQLite DLL conflicts."""
            import sys
            
            # Use --worker flag if frozen (PyInstaller exe)
            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, "--worker"]
            else:
                cmd = [sys.executable, worker_script]
                
            result = subprocess.run(
                cmd,
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
        # Refresh list after a delay
        QTimer.singleShot(2000, self.refresh_knowledge_list)

    def clear_db(self):
        """Clear the vector database."""
        chroma_dir = self.input_chroma_dir.text() or self.config_manager.get("chroma_dir", "") or ""
        provider = self.input_embed_provider.currentText().lower()
        if provider == "openrouter":
            model_name = self.input_embed_model.currentText() or self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.input_embed_model.currentText() or self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        api_key = self.input_openrouter_key.text() or self.config_manager.get("openrouter_key", "")
        ollama_url = self.input_ollama_url.text() or self.config_manager.get("ollama_url", "http://127.0.0.1:11434")
        
        self.append_log(">> [PROCESSO] Iniciando Limpeza Profunda do Banco de Dados...")
        
        import json, subprocess
        worker_data = json.dumps({
            "action": "clear",
            "chroma_dir": chroma_dir,
            "model_name": model_name,
            "embedding_provider": provider,
            "api_key": api_key,
            "ollama_url": ollama_url
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_clear():
            import sys
            
            # Use --worker flag if frozen (PyInstaller exe)
            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, "--worker"]
            else:
                cmd = [sys.executable, worker_script]
                
            result = subprocess.run(
                cmd,
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
        self._monitor_future(future, lambda res: [self.append_log(f">> {res}"), self.refresh_knowledge_list()])

    def clear_history_action(self):
        """Confirm and clear interaction history."""
        reply = QMessageBox.question(
            self, "🚨 AVISO CRÍTICO", 
            "Você está prestes a apagar TODO o histórico de interações (logs) dos usuários.\n\n"
            "Isso zerará as estatísticas e os resumos de IA. Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            from analytics_manager import AnalyticsManager
            analytics = AnalyticsManager()
            if analytics.clear_history():
                 self.append_log(">> [SINAL] Histórico de interações apagado com sucesso.")
                 QMessageBox.information(self, "Sucesso", "O histórico de interações foi zerado.")
            else:
                 QMessageBox.warning(self, "Erro", "Não foi possível apagar o histórico.")

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
                    self.append_log(f">> Tarefa Falhou: {e}")
                    self.append_log(f">> Detalhes: {''.join(error_details[-3:])}")
                    self.btn_ingest.setEnabled(True)
        
        timer.timeout.connect(check)
        timer.start(500) # Check every 500ms

    def _on_ingest_complete(self, result):
        chunks = result.get('chunks_count', 0)
        filename = result.get('filename', 'arquivo')
        msg = f">> Sucesso: {chunks} fragmentos ingeridos de '{filename}'."
        self.append_log(msg)
        QMessageBox.information(self, "Ingestão Concluída", msg)
        self.btn_ingest.setEnabled(True)
        
        self.lbl_file.setText("Nenhum arquivo selecionado")
        if hasattr(self, 'selected_files'):
            self.selected_files = []
            self.btn_ingest.setEnabled(False)
            
        self.refresh_knowledge_list()

    def refresh_knowledge_list(self):
        """Fetch and display the list of documents in the vector store."""
        import json, subprocess
        
        # Pull latest settings
        provider = self.input_embed_provider.currentText().lower()
        if provider == "openrouter":
            model_name = self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        chroma_dir = self.config_manager.get("chroma_dir", "") or ""
        api_key = self.config_manager.get("openrouter_key", "")
        
        worker_data = json.dumps({
            "action": "list",
            "chroma_dir": chroma_dir,
            "model_name": model_name,
            "embedding_provider": provider,
            "api_key": api_key
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_list():
            import sys
            
            # Use --worker flag if frozen (PyInstaller exe)
            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, "--worker"]
            else:
                cmd = [sys.executable, worker_script]
                
            result = subprocess.run(
                cmd,
                input=worker_data,
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode != 0:
                return []
            output = result.stdout.strip()
            last_line = output.split('\n')[-1]
            data = json.loads(last_line)
            return data.get("result", [])
        
        async def do_list():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, sync_list)
        
        def update_table(file_list):
            self.table_knowledge.setRowCount(0)
            for filename in file_list:
                row = self.table_knowledge.rowCount()
                self.table_knowledge.insertRow(row)
                
                # Filename item
                self.table_knowledge.setItem(row, 0, QTableWidgetItem(filename))
                
                # Download button
                btn_dl = QPushButton("Baixar")
                btn_dl.setStyleSheet("background-color: #5555ff; color: white;")
                btn_dl.clicked.connect(lambda checked, f=filename: self.download_knowledge_file(f))
                self.table_knowledge.setCellWidget(row, 1, btn_dl)
                
                # Delete button
                btn_del = QPushButton("Excluir")
                btn_del.setStyleSheet("background-color: #ff5555; color: white;")
                btn_del.clicked.connect(lambda checked, f=filename: self.delete_knowledge_file(f))
                self.table_knowledge.setCellWidget(row, 2, btn_del)

        future = self.async_worker.submit(do_list())
        self._monitor_future(future, update_table)

    def delete_knowledge_file(self, filename):
        """Ask for confirmation and delete a specific document."""
        reply = QMessageBox.question(
            self, "Confirmar Exclusão", 
            f"Deseja realmente excluir '{filename}' da base de conhecimento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
            
        import json, subprocess
        
        provider = self.input_embed_provider.currentText().lower()
        if provider == "openrouter":
            model_name = self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        chroma_dir = self.config_manager.get("chroma_dir", "") or ""
        api_key = self.config_manager.get("openrouter_key", "")
        
        worker_data = json.dumps({
            "action": "delete",
            "filename": filename,
            "chroma_dir": chroma_dir,
            "model_name": model_name,
            "embedding_provider": provider,
            "api_key": api_key
        })
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        def sync_delete():
            import sys
            result = subprocess.run(
                [sys.executable, worker_script],
                input=worker_data,
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.returncode != 0:
                return {"ok": False, "error": "Process failed"}
            output = result.stdout.strip()
            last_line = output.split('\n')[-1]
            return json.loads(last_line)
            
        async def do_delete():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, sync_delete)
            
        def on_deleted(res):
            if res.get("ok"):
                self.append_log(f">> Arquivo '{filename}' excluído com sucesso.")
                self.refresh_knowledge_list()
            else:
                QMessageBox.warning(self, "Erro", f"Falha ao excluir: {res.get('error')}")

        future = self.async_worker.submit(do_delete())
        self._monitor_future(future, on_deleted)

    def download_knowledge_file(self, filename):
        """Allow user to save the original file to a new location."""
        import shutil
        source_path = os.path.join(os.getcwd(), "arquivos", filename)
        
        if not os.path.exists(source_path):
            QMessageBox.warning(self, "Não Encontrado", f"O arquivo original '{filename}' não foi encontrado na pasta 'arquivos'.")
            return
            
        target_path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo Como", filename)
        if target_path:
            try:
                shutil.copy2(source_path, target_path)
                QMessageBox.information(self, "Sucesso", f"Arquivo salvo com sucesso em:\n{target_path}")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao copiar arquivo: {e}")

