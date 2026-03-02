import asyncio
import os
import sys

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Log, TabbedContent, TabPane, Button, Static, Label, Input, Select, Switch, TextArea, DataTable
from textual.binding import Binding

from config_manager import ConfigurationManager
from telegram_controller import TelegramBotController

class BotTerminalUI(App):
    """Uma interface de terminal (TUI) para gerenciar o Bot do Telegram."""

    # Título da TUI
    TITLE = "Ollama Telegram Bot - Gerenciador TUI"
    
    # CSS para garantir um fundo legível e "limpo" num terminal, e estruturar painéis.
    CSS = """
    Screen {
        background: #0a0a0a;  /* Fundo preto profundo */
        color: #e0e0e0;       /* Texto cinza claro */
    }

    Header {
        background: #1a4a75;
        color: #ffffff;
        text-style: bold;
    }

    Footer {
        background: #1a1a1a;
        color: #888888;
    }

    TabPane {
        padding: 1;
        background: #0a0a0a;
    }
    
    .panel {
        border: solid #2b5b84;
        padding: 1;
        margin: 1 0;
        background: #121212;
    }

    Log {
        height: 1fr;
        border: double #2b5b84;
        background: #000000; 
        color: #00ff00;
    }

    .status-label {
        text-style: bold;
        margin-bottom: 1;
        padding: 1;
        background: #1a1a1a;
        border: tall #333333;
        color: #ffffff;
        width: 100%;
    }
    
    /* Estilização explícita de botões para evitar blocos cinzas sem texto */
    Button {
        margin: 1 1;
        width: auto;
        min-width: 16;
    }

    Button.-success {
        background: #2e7d32;
        color: white;
    }

    Button.-error {
        background: #c62828;
        color: white;
    }

    Button.-warning {
        background: #f57c00;
        color: white;
    }

    /* Garantir que botões bloqueados (running background) ainda mostrem o texto */
    Button:disabled {
        background: #333333;
        color: #777777;
    }

    #controls-container {
        height: auto;
        padding: 1;
        background: #121212;
        border-bottom: solid #2b5b84;
    }

    .panel-title {
        text-style: bold;
        color: #2b5b84;
        margin-top: 1;
    }

    .hidden-label {
        display: none;
    }

    /* Menu Principal CSS */
    #tab-menu {
        overflow-y: auto;
    }
    .menu-group {
        border: solid #2b5b84;
        margin-top: 1;
        margin-bottom: 1;
        background: #111111;
        padding: 1;
        height: auto;
    }
    .menu-label-bold {
        text-style: bold;
        color: #ffb74d;
    }
    .menu-row {
        height: auto;
    }
    Input, Select, TextArea, Switch {
        background: #2a2a2a;
        color: #f0f0f0;
        border: solid #555555;
        margin-bottom: 1;
    }
    Input:focus, Select:focus, TextArea:focus {
        border: solid #2196f3;
        background: #333333;
    }
    TextArea {
        height: 6;
    }
    #lbl-save-status {
        margin-top: 1;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair", show=True),
        Binding("ctrl+c", "quit", "Sair"),
    ]

    def __init__(self):
        super().__init__()
        self.telegram_controller = None
        self.bot_task = None
        self.log_file_path = "bot.log"
        self._tail_task = None
        self.config_manager = ConfigurationManager()

    def compose(self) -> ComposeResult:
        """Cria o layout da TUI."""
        yield Header()

        with Container():
            with TabbedContent():
                # Nova Aba 1: Painel Principal (Visão Geral)
                with TabPane("Painel Principal", id="tab-main"):
                    with Vertical(classes="panel"):
                        yield Static("📊 Status Geral do Assistente Acadêmico", classes="panel-title")
                        yield Label("Status: VERIFICANDO...", id="lbl-status-main", classes="status-label")
                        
                        with Horizontal(id="controls-container"):
                            yield Button("▶️ Iniciar Bot", id="btn-start", variant="success")
                            yield Button("⏹️ Parar Bot", id="btn-stop", variant="error", disabled=True)
                            yield Button("🔄 Reiniciar Serviço", id="btn-restart-svc", variant="warning", disabled=True)
                            
                        yield Static(
                            "🌐 IP Intranet: Oculto\n"
                            "🌍 IP Internet: Oculto\n"
                            "🔒 Tailscale: Oculto\n",
                            id="lbl-network-info", classes="panel"
                        )

                # Aba 2: Terminal de Logs
                with TabPane("Terminal de Logs", id="tab-controls"):
                    with Vertical():
                        yield Label("Status: VERIFICANDO...", id="lbl-status", classes="status-label hidden-label")
                        yield Static("📺 Console (bot.log):", classes="panel-title")
                        
                        # Painel de Log (ecoa em tempo real)
                        self.log_view = Log(id="log-view")
                        yield self.log_view

                # Aba 3: Menu Principal
                with TabPane("Menu Principal", id="tab-menu"):
                    with VerticalScroll():
                        yield Static("⚙️ Configuração dos Botões do Menu", classes="panel-title")
                        yield Button("💾 Salvar Alterações", id="btn-save-menu", variant="success")
                        yield Label("", id="lbl-save-status", classes="status-label")
                        
                        for i in range(5):
                            with Vertical(classes="menu-group"):
                                yield Label(f"Botão {i+1}", classes="menu-label-bold")
                                with Horizontal(classes="menu-row"):
                                    yield Label("Habilitado:")
                                    yield Switch(id=f"chk_enabled_{i}", value=True)
                                
                                yield Label("Texto do Botão:")
                                yield Input(id=f"txt_label_{i}", placeholder="Ex: Informações")
                                
                                yield Label("Tipo de Ação:")
                                yield Select(
                                    options=[
                                        ("Texto Fixo (Configurado aqui)", "fixed_text"),
                                        ("Ler de Arquivo Texto (Em arquivos/)", "text_file"),
                                        ("Upload de Arquivos (Pelo prefixo)", "file_upload")
                                    ],
                                    id=f"cmb_action_{i}"
                                )
                                
                                yield Label("Parâmetro (Texto/Arquivo/Prefixo):")
                                yield TextArea(id=f"txt_param_{i}")
                
                # Aba 4: Base de Conhecimento
                with TabPane("Base de Conhecimento", id="tab-kb"):
                    with VerticalScroll(classes="panel"):
                        yield Static("📚 Gerenciamento da Base de Conhecimento (RAG)", classes="panel-title")
                        
                        with Horizontal(classes="menu-row"):
                            curr_dir = os.path.abspath('.')
                            yield Input(id="kb_filepath", placeholder=f"{curr_dir}/")
                            yield Button("➕ Ingerir Arquivo", id="btn-ingest", variant="success")
                        
                        with Horizontal(classes="menu-row"):
                            yield Button("🔄 Atualizar Lista", id="btn-refresh-kb", variant="primary")
                            yield Button("🗑️ Limpar Banco RAG", id="btn-clear-db", variant="error")
                            yield Button("🚨 Zerar Histórico de Conversas", id="btn-clear-history", variant="warning")
                            yield Button("❌ Excluir Selecionado", id="btn-delete-file", variant="error", disabled=True)
                        
                        yield DataTable(id="table-kb", zebra_stripes=True)
                        
                with TabPane("Configuração", id="tab-settings"):
                    with VerticalScroll(classes="panel"):
                        yield Static("⚙️ Configurações Principais", classes="panel-title")
                        yield Button("💾 Salvar Configurações Gerais", id="btn-save-settings", variant="success")
                        yield Label("", id="lbl-save-settings-status", classes="status-label")
                        
                        yield Label("Provedor de IA:")
                        yield Select([("Ollama", "ollama"), ("OpenRouter", "openrouter")], id="cfg_ai_provider")
                        
                        yield Label("Token do Telegram:")
                        yield Input(id="cfg_telegram_token", password=True)
                        
                        yield Label("Admin ID (separado por vírgula):")
                        yield Input(id="cfg_admin_id")
                        
                        yield Label("Nível de Logs:")
                        yield Select([("Baixo", "baixo"), ("Médio", "médio"), ("Alto", "alto")], id="cfg_log_verbosity")
                        
                        yield Label("URL do Ollama:")
                        yield Input(id="cfg_ollama_url")
                        
                        yield Label("API Key OpenRouter (Opcional se usar Ollama):")
                        yield Input(id="cfg_openrouter_key", password=True)
                        
                        yield Label("Modelo (IA):")
                        yield Input(id="cfg_model_name")
                        
                        yield Label("Prompt do Sistema:")
                        yield TextArea(id="cfg_sys_prompt")
                        
                        yield Label("Provedor de Embedding:")
                        yield Select([("Ollama", "ollama"), ("OpenRouter", "openrouter")], id="cfg_embed_provider")
                        
                        yield Label("Modelo Embedding:")
                        yield Input(id="cfg_embed_model")
                        
                        yield Label("Temperatura (Ex: 0.7):")
                        yield Input(id="cfg_temperature")
                        
                        yield Label("Máx Tokens:")
                        yield Input(id="cfg_max_tokens")
                        
                        yield Label("Memória de Busca RAG (K):")
                        yield Input(id="cfg_rag_k")
                        
                        yield Label("Histórico de Conversa (0 para desativar):")
                        yield Input(id="cfg_chat_history")
                        
                        yield Label("Limite de Mensagens (Msg/min):")
                        yield Input(id="cfg_rate_limit")
                        
                        yield Label("Diretório ChromaDB (Vazio=Padrão):")
                        yield Input(id="cfg_chroma_dir")
                        
                        yield Label("Mensagem de Boas-vindas:")
                        yield TextArea(id="cfg_welcome_msg")

        yield Footer()

    def on_mount(self) -> None:
        """Chamado quando a aplicação é montada. Inicia a leitura do arquivo de log."""
        self.log_view.write_line("Iniciando monitoramento do log do bot...")
        self.stop_logging = False
        import threading
        threading.Thread(target=self.tail_logs, daemon=True).start()
        
        # Monitora a saúde do bot e verifica se ele está rodando de forma externa (start_rp4.sh / systemd)
        self.set_interval(2.0, self.check_external_status)
        
        # Busca IPs em background
        asyncio.create_task(self.fetch_network_info())
        
        # Inicia e configura a tabela
        table = self.query_one("#table-kb", DataTable)
        table.add_columns("Arquivo Salvo na Base Vetorial")
        
        # Carrega configurações na interface do menu e configurações gerais
        self.load_menu_settings()
        self.load_general_settings()
        
        # Atualiza a lista da Base
        self.refresh_knowledge_list()

    async def fetch_network_info(self) -> None:
        """Obtém os IPs assincronamente e atualiza o painel principal."""
        import socket
        import httpx
        
        local_ip = "N/A"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            pass
            
        public_ip = "Verificando..."
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.ipify.org", timeout=3.0)
                if resp.status_code == 200:
                    public_ip = resp.text.strip()
                else:
                    public_ip = "N/A"
        except:
            public_ip = "N/A"
            
        tailscale_ip = "N/A"
        try:
            proc = await asyncio.create_subprocess_shell(
                'tailscale ip -4', 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            if proc.returncode == 0:
                tailscale_ip = stdout.decode('utf-8').strip()
        except:
            pass

        info_text = (
            f"🌐 IP Intranet: {local_ip}\n"
            f"🌍 IP Internet: {public_ip}\n"
            f"🔒 Tailscale: {tailscale_ip}\n"
        )
        try:
            self.query_one("#lbl-network-info", Static).update(info_text)
        except:
            pass

    def check_external_status(self) -> None:
        """Verifica se há um lock PID externo criado pelo script start_rp4.sh e ajusta a interface."""
        lock_file = "/tmp/telegram-bot.pid"
        is_running_externally = False
        
        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r") as f:
                    pid = int(f.read().strip())
                # Checa se o processo existe no Unix (sinal 0 não mata, apenas checa permissão/presença)
                import signal
                os.kill(pid, 0)
                is_running_externally = True
            except (ValueError, OSError):
                pass
                
        # Se estiver rodando no TUI (internal), o sistema flui normalmente
        is_running_internally = self.bot_task and not self.bot_task.done()

        if is_running_externally:
            self.query_one("#lbl-status", Label).update("Status: [yellow]RODANDO EM BACKGROUND (start_rp4)[/yellow]")
            self.query_one("#lbl-status-main", Label).update("Status: [yellow]RODANDO EM BACKGROUND (start_rp4)[/yellow]")
            self.query_one("#btn-start", Button).disabled = True
            # Parar não funciona pelo TUI para kills externos a menos que usemos os.kill na thread principal. Melhor evitar para não quebrar a lógica do watchdog
            self.query_one("#btn-stop", Button).disabled = True
            self.query_one("#btn-stop", Button).tooltip = "O bot está sendo gerenciado pelo systemd / start_rp4.sh"
            self.query_one("#btn-restart-svc", Button).disabled = False
            
        elif is_running_internally:
            self.query_one("#lbl-status", Label).update("Status: [green]RODANDO[/green]")
            self.query_one("#lbl-status-main", Label).update("Status: [green]RODANDO[/green]")
            self.query_one("#btn-start", Button).disabled = True
            self.query_one("#btn-stop", Button).disabled = False
            self.query_one("#btn-stop", Button).tooltip = ""
            self.query_one("#btn-restart-svc", Button).disabled = True
            
        else:
            self.query_one("#lbl-status", Label).update("Status: [red]PARADO[/red]")
            self.query_one("#lbl-status-main", Label).update("Status: [red]PARADO[/red]")
            self.query_one("#btn-start", Button).disabled = False
            self.query_one("#btn-stop", Button).disabled = True
            self.query_one("#btn-stop", Button).tooltip = ""
            self.query_one("#btn-restart-svc", Button).disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Trata cliques nos botões."""
        btn_id = event.button.id
        
        if btn_id == "btn-start":
            self.start_bot()
        elif btn_id == "btn-stop":
            self.stop_bot()
        elif btn_id == "btn-restart-svc":
            self.restart_service()
        elif btn_id == "btn-save-menu":
            self.save_menu_settings()
        elif btn_id == "btn-save-settings":
            self.save_general_settings()
        elif btn_id == "btn-refresh-kb":
            self.refresh_knowledge_list()
        elif btn_id == "btn-ingest":
            self.ingest_file()
        elif btn_id == "btn-clear-db":
            self.clear_db()
        elif btn_id == "btn-clear-history":
            self.clear_history_action()
        elif btn_id == "btn-delete-file":
            self.delete_selected_file()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "table-kb":
            self.query_one("#btn-delete-file", Button).disabled = False

    def get_worker_base_data(self) -> dict:
        """Coleta dados base comuns para enviar pro ingest_worker."""
        provider = self.config_manager.get("embedding_provider", "ollama")
        if provider == "openrouter":
            model_name = self.config_manager.get("openrouter_embedding_model", "qwen/qwen3-embedding-8b")
        else:
            model_name = self.config_manager.get("ollama_embedding_model", "nomic-embed-text")
            
        return {
            "chroma_dir": self.config_manager.get("chroma_dir", ""),
            "model_name": model_name,
            "embedding_provider": provider,
            "api_key": self.config_manager.get("openrouter_key", ""),
            "ollama_url": self.config_manager.get("ollama_url", "http://127.0.0.1:11434")
        }

    async def run_worker_task(self, worker_data: dict, success_msg: str) -> None:
        """Executa um comando no ingest_worker de forma assíncrona."""
        import json
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, worker_script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            stdout, stderr = await proc.communicate(input=json.dumps(worker_data).encode('utf-8'))
            
            if proc.returncode != 0:
                self.log_view.write_line(f">>> Erro no worker: {stderr.decode('utf-8')}")
                return None
                
            last_line = stdout.decode('utf-8').strip().split('\n')[-1]
            data = json.loads(last_line)
            if not data.get("ok"):
                self.log_view.write_line(f">>> Ocorreu um erro na ação: {data.get('error')}")
                return None
            
            if success_msg: 
                self.log_view.write_line(f">>> {success_msg}")
            
            self.refresh_knowledge_list()
            return data.get("result")
        except Exception as e:
            self.log_view.write_line(f">>> Erro interno de execução: {e}")
            return None

    def ingest_file(self) -> None:
        filepath = self.query_one("#kb_filepath", Input).value.strip()
        if not filepath or not os.path.exists(filepath):
            self.log_view.write_line(">>> Erro: Arquivo especificado não encontrado.")
            return
            
        import shutil
        base_dir = os.path.dirname(os.path.abspath(__file__))
        arquivos_path = os.path.join(base_dir, "arquivos")
        os.makedirs(arquivos_path, exist_ok=True)
        filename = os.path.basename(filepath)
        target_fname = os.path.join(arquivos_path, filename)
        
        if os.path.abspath(filepath) != os.path.abspath(target_fname):
            try:
                shutil.copy2(filepath, target_fname)
            except Exception as e:
                self.log_view.write_line(f">>> Erro ao copiar arquivo: {e}")
                return
                
        self.log_view.write_line(f">>> Iniciando Ingestão de {filename}...")
        
        data = self.get_worker_base_data()
        data["action"] = "ingest"
        data["file_paths"] = [target_fname]
        asyncio.create_task(self.run_worker_task(data, f"Ingestão do arquivo '{filename}' concluída com sucesso!"))
        self.query_one("#kb_filepath", Input).value = ""

    def clear_db(self) -> None:
        self.log_view.write_line(">>> Limpando Banco RAG...")
        data = self.get_worker_base_data()
        data["action"] = "clear"
        asyncio.create_task(self.run_worker_task(data, "Banco de Dados Vetorial completamente limpo."))

    def delete_selected_file(self) -> None:
        table = self.query_one("#table-kb", DataTable)
        row_key = table.cursor_row
        if row_key is None or row_key < 0 or row_key >= table.row_count:
            return
            
        filename = table.get_row_at(row_key)[0]
        self.log_view.write_line(f">>> Excluindo {filename} do banco RAG...")
        data = self.get_worker_base_data()
        data["action"] = "delete"
        data["filename"] = filename
        
        self.query_one("#btn-delete-file", Button).disabled = True
        asyncio.create_task(self.run_worker_task(data, f"Arquivo '{filename}' deletado da Base."))

    def refresh_knowledge_list(self) -> None:
        async def fetch_list():
            data = self.get_worker_base_data()
            data["action"] = "list"
            import json
            worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_worker.py")
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, worker_script,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.path.dirname(os.path.abspath(__file__))
                )
                stdout, _ = await proc.communicate(input=json.dumps(data).encode('utf-8'))
                if proc.returncode == 0:
                    last_line = stdout.decode('utf-8').strip().split('\n')[-1]
                    res = json.loads(last_line)
                    if res.get("ok"):
                        files = res.get("result", [])
                        table = self.query_one("#table-kb", DataTable)
                        table.clear()
                        for f in files: table.add_row(f)
                        self.query_one("#btn-delete-file", Button).disabled = True
                        
            except Exception as e:
                self.log_view.write_line(f">>> Erro listando a base: {e}")
        
        asyncio.create_task(fetch_list())

    def clear_history_action(self) -> None:
        self.log_view.write_line(">>> Apagando Histórico de Logs Analítico...")
        from analytics_manager import AnalyticsManager
        import threading
        
        def run_clear():
            mgr = AnalyticsManager()
            if mgr.clear_history():
                 self.call_from_thread(self.log_view.write_line, ">>> Histórico de conversas apagado com sucesso do SQLite!")
            else:
                 self.call_from_thread(self.log_view.write_line, ">>> Falha ao zerar histórico.")
        
        threading.Thread(target=run_clear, daemon=True).start()

    def load_general_settings(self) -> None:
        """Carrega os dados de configuração gerais do config.json para os widgets da Aba Configuração."""
        d = self.config_manager.config_data
        try:
            prov = d.get("ai_provider", "ollama")
            if prov not in ["ollama", "openrouter"]: prov = "ollama"
            self.query_one("#cfg_ai_provider", Select).value = prov
            
            self.query_one("#cfg_telegram_token", Input).value = d.get("telegram_token", "")
            self.query_one("#cfg_admin_id", Input).value = str(d.get("admin_id", ""))
            
            verb = d.get("log_verbosity", "médio")
            if verb not in ["baixo", "médio", "alto"]: verb = "médio"
            self.query_one("#cfg_log_verbosity", Select).value = verb
            
            self.query_one("#cfg_ollama_url", Input).value = d.get("ollama_url", "http://127.0.0.1:11434")
            self.query_one("#cfg_openrouter_key", Input).value = d.get("openrouter_key", "")
            
            if prov == "ollama":
                model = d.get("ollama_model", "llama3:latest")
            else:
                model = d.get("openrouter_model", "openai/gpt-3.5-turbo")
            self.query_one("#cfg_model_name", Input).value = model
            
            self.query_one("#cfg_sys_prompt", TextArea).text = d.get("system_prompt", "")
            
            e_prov = d.get("embedding_provider", "ollama")
            if e_prov not in ["ollama", "openrouter"]: e_prov = "ollama"
            self.query_one("#cfg_embed_provider", Select).value = e_prov
            
            if e_prov == "openrouter":
                e_model = d.get("openrouter_embedding_model", "openai/text-embedding-3-small")
            else:
                e_model = d.get("ollama_embedding_model", "qwen3-embedding:latest")
            self.query_one("#cfg_embed_model", Input).value = e_model
            
            self.query_one("#cfg_temperature", Input).value = str(d.get("temperature", 0.7))
            self.query_one("#cfg_max_tokens", Input).value = str(d.get("max_tokens", 2048))
            self.query_one("#cfg_rag_k", Input).value = str(d.get("rag_k", 8))
            self.query_one("#cfg_chat_history", Input).value = str(d.get("chat_history_size", 5))
            self.query_one("#cfg_rate_limit", Input).value = str(d.get("rate_limit_per_minute", 10))
            self.query_one("#cfg_chroma_dir", Input).value = d.get("chroma_dir", "")
            self.query_one("#cfg_welcome_msg", TextArea).text = d.get("welcome_message", "")
        except Exception as e:
            self.log_view.write_line(f">>> Erro ao carregar configurações gerais na aba: {e}")

    def save_general_settings(self) -> None:
        """Salva a configuração da aba de Configuração pro config_manager."""
        updates = {}
        try:
            prov = self.query_one("#cfg_ai_provider", Select).value or "ollama"
            updates["ai_provider"] = prov
            updates["telegram_token"] = self.query_one("#cfg_telegram_token", Input).value
            updates["admin_id"] = self.query_one("#cfg_admin_id", Input).value
            updates["log_verbosity"] = self.query_one("#cfg_log_verbosity", Select).value or "médio"
            updates["ollama_url"] = self.query_one("#cfg_ollama_url", Input).value
            updates["openrouter_key"] = self.query_one("#cfg_openrouter_key", Input).value
            
            model = self.query_one("#cfg_model_name", Input).value
            if prov == "ollama":
                updates["ollama_model"] = model
            else:
                updates["openrouter_model"] = model
                
            updates["system_prompt"] = self.query_one("#cfg_sys_prompt", TextArea).text
            
            e_prov = self.query_one("#cfg_embed_provider", Select).value or "ollama"
            updates["embedding_provider"] = e_prov
            e_model = self.query_one("#cfg_embed_model", Input).value
            if e_prov == "openrouter":
                updates["openrouter_embedding_model"] = e_model
            else:
                updates["ollama_embedding_model"] = e_model
                
            # Safely cast numeric fields
            def float_val(val, default):
                try: return float(val)
                except: return default
            def int_val(val, default):
                try: return int(val)
                except: return default

            updates["temperature"] = float_val(self.query_one("#cfg_temperature", Input).value, 0.7)
            updates["max_tokens"] = int_val(self.query_one("#cfg_max_tokens", Input).value, 2048)
            updates["rag_k"] = int_val(self.query_one("#cfg_rag_k", Input).value, 8)
            updates["chat_history_size"] = int_val(self.query_one("#cfg_chat_history", Input).value, 5)
            updates["rate_limit_per_minute"] = int_val(self.query_one("#cfg_rate_limit", Input).value, 10)
            
            updates["chroma_dir"] = self.query_one("#cfg_chroma_dir", Input).value
            updates["welcome_message"] = self.query_one("#cfg_welcome_msg", TextArea).text
            
            self.config_manager.update_batch(updates)
            
            lbl = self.query_one("#lbl-save-settings-status", Label)
            lbl.update("[green]Configurações principais persistidas no sistema![/green]")
            self.set_timer(3.0, lambda: lbl.update(""))
            self.log_view.write_line(">>> Configurações gerais salvas no arquivo config.json.")
        except Exception as e:
            self.log_view.write_line(f">>> Erro ao salvar configurações gerais: {e}")

    def load_menu_settings(self) -> None:
        """Carrega os botões salvos na TUI."""
        buttons = self.config_manager.get("menu_buttons", [])
        for i in range(5):
            try:
                chk = self.query_one(f"#chk_enabled_{i}", Switch)
                txt_label = self.query_one(f"#txt_label_{i}", Input)
                cmb = self.query_one(f"#cmb_action_{i}", Select)
                txt_param = self.query_one(f"#txt_param_{i}", TextArea)
                
                if i < len(buttons):
                    btn = buttons[i]
                    chk.value = btn.get("enabled", True)
                    txt_label.value = btn.get("text", "")
                    cmb.value = btn.get("action", "fixed_text")
                    txt_param.text = btn.get("parameter", "")
                else:
                    chk.value = True
                    txt_label.value = ""
                    cmb.value = "fixed_text"
                    txt_param.text = ""
            except Exception as e:
                self.log_view.write_line(f">>> Erro interno ao carregar layout do botão {i}: {e}")

    def save_menu_settings(self) -> None:
        """Salva a configuração do menu persistindo no config.json."""
        menu_btns = []
        for i in range(5):
            try:
                chk = self.query_one(f"#chk_enabled_{i}", Switch).value
                txt_label = self.query_one(f"#txt_label_{i}", Input).value
                cmb = self.query_one(f"#cmb_action_{i}", Select).value
                txt_param = self.query_one(f"#txt_param_{i}", TextArea).text
                
                menu_btns.append({
                    "id": f"btn{i+1}",
                    "enabled": chk,
                    "text": txt_label,
                    "action": cmb or "fixed_text",
                    "parameter": txt_param
                })
            except Exception as e:
                self.log_view.write_line(f">>> Erro interno (leitura) botão {i}: {e}")
            
        self.config_manager.update_batch({"menu_buttons": menu_btns})
        try:
            lbl = self.query_one("#lbl-save-status", Label)
            lbl.update("[green]Configuração salva dinamicamente no sistema![/green]")
            self.set_timer(3.0, lambda: lbl.update(""))
        except: pass
        self.log_view.write_line(">>> Configurações de menu salvas no arquivo config.json.")

    def start_bot(self) -> None:
        """Inicia a execução do bot Telegram assincronamente."""
        if self.bot_task and not self.bot_task.done():
            self.log_view.write_line("O bot já está rodando internamente.")
            return

        # Verifica bloqueio externo antes de tentar iniciar
        if os.path.exists("/tmp/telegram-bot.pid"):
             self.log_view.write_line("Falha ao iniciar: Detectado PID lock file. Bot está sendo gerenciado em background.")
             return

        self.query_one("#lbl-status", Label).update("Status: [green]RODANDO[/green]")
        self.query_one("#btn-start", Button).disabled = True
        self.query_one("#btn-stop", Button).disabled = False
        
        self.telegram_controller = TelegramBotController()
        
        # Como o Textual internamente roda um self.loop (Event loop do asyncio),
        # podemos apenas criar uma task com a coroutine start() do bot.
        self.bot_task = asyncio.create_task(self.telegram_controller.start())
        self.log_view.write_line(">>> Comando de inicialização do Bot enviado.")

    def stop_bot(self) -> None:
        """Para o bot Telegram."""
        if not self.bot_task or self.bot_task.done():
            return
            
        self.log_view.write_line(">>> Comando de parada do Bot enviado.")
        
        if self.telegram_controller:
            # Chama a parada do controller de maneira assíncrona
            asyncio.create_task(self.telegram_controller.stop())
            
        self.query_one("#lbl-status", Label).update("Status: [red]PARADO[/red]")
        try:
            self.query_one("#lbl-status-main", Label).update("Status: [red]PARADO[/red]")
        except:
            pass
        self.query_one("#btn-start", Button).disabled = False
        self.query_one("#btn-stop", Button).disabled = True

    def restart_service(self) -> None:
        """Reinicia o serviço matando o processo filho, o que ativa o Watchdog silencioso do script."""
        self.log_view.write_line(">>> Enviando sinal de reinício para o processo em background...")
        try:
            async def run_restart():
                # Evita o "sudo systemctl" que pede senha nativamente arruinando a TUI.
                # Como o start_rp4.sh possui um Watchdog (restart count e sleep), 
                # ao fechar a instância Python, ele aciona o reboot automaticamente.
                proc = await asyncio.create_subprocess_shell(
                    'pkill -f "python3 main.py --cli" || pkill -f "python main.py --cli"',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                self.log_view.write_line(">>> Processo finalizado com sucesso. O Watchdog ligará o bot novamente em até 15 segundos...")
            
            asyncio.create_task(run_restart())
        except Exception as e:
             self.log_view.write_line(f">>> Erro interno ao chamar restart: {e}")

    def tail_logs(self):
        """Lê o arquivo de log do bot num loop independente (como 'tail -f') sem travar a interface."""
        log_file = self.log_file_path
        
        # Se o arquivo não existe, cria para evitar erros de leitura iniciais
        if not os.path.exists(log_file):
            open(log_file, 'a').close()
            
        try:
            import time
            with open(log_file, "r", encoding="utf-8") as f:
                # Pula para o final
                f.seek(0, 2)
                
                while not getattr(self, "stop_logging", False):
                    where = f.tell()
                    line = f.readline()
                    
                    if not line:
                        time.sleep(0.5)
                        f.seek(where) # Reset pointer since readline might have advanced without full line
                        continue
                        
                    # Agenda de forma segura para o EventLoop da Tela principal renderizar
                    self.call_from_thread(self.log_view.write_line, line.strip())
        except Exception as e:
            self.call_from_thread(self.log_view.write_line, f"Erro ao ler logs: {e}")

    async def action_quit(self) -> None:
        """Desliga limpo e fecha a TUI."""
        self.stop_logging = True
        self.log_view.write_line("Encerrando bot e terminal...")
        if self.telegram_controller and self.bot_task and not self.bot_task.done():
            await self.telegram_controller.stop()
            self.bot_task.cancel()
            
        self.exit()

if __name__ == "__main__":
    app = BotTerminalUI()
    app.run()
