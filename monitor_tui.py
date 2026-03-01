import asyncio
import os
import sys

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Log, TabbedContent, TabPane, Button, Static, Label
from textual.binding import Binding

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
        width: 20;
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
        border: none;
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

                # Aba 2: Outros (Placeholder para Settings, Conhecimento, etc que existirem na GUI)
                with TabPane("Base de Conhecimento", id="tab-kb"):
                    with Vertical(classes="panel"):
                        yield Static(
                            "🚧 Funcionalidades de Ingestão de Base de Conhecimento via TUI\n"
                            "poderão ser injetadas aqui através de Inputs Textual ou Botões acionando \n"
                            "o script 'ingest_worker.py' da mesma forma que a GUI."
                        )
                        yield Button("🔄 Atualizar Lista de Arquivos (Em breve)", disabled=True)
                        
                with TabPane("Configuração", id="tab-settings"):
                    with Vertical(classes="panel"):
                         yield Static(
                            "🚧 As configurações principais devem ser alteradas \n"
                            "diretamente no arquivo config.json ou via GUI PyQt6 por enquanto.\n"
                        )

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
        """Reinicia o serviço systemd do bot em background no Raspberry Pi."""
        self.log_view.write_line(">>> Enviando comando de restart para o systemd (telegram-bot.service)...")
        try:
            async def run_restart():
                proc = await asyncio.create_subprocess_shell(
                    'sudo systemctl restart telegram-bot.service',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    self.log_view.write_line(">>> Serviço reiniciado com sucesso via CLI! Acompanhe o log.")
                else:
                    self.log_view.write_line(f">>> Falha ao reiniciar serviço: {stderr.decode('utf-8')}")
            
            asyncio.create_task(run_restart())
        except Exception as e:
             self.log_view.write_line(f">>> Erro interno ao chamar systemctl: {e}")

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
