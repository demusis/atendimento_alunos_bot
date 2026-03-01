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
        background: #f0f0f0;  /* Fundo "branquicento" / cinza bem claro */
        color: #111111;       /* Texto escuro padrão */
    }

    Header {
        background: #2b5b84;
        color: white;
    }

    Footer {
        background: #e0e0e0;
        color: #333333;
    }

    TabPane {
        padding: 1;
        background: #ffffff;
    }
    
    .panel {
        border: solid #aaaaaa;
        padding: 1;
        margin: 1 0;
        background: #ffffff;
    }

    Log {
        height: 1fr;
        border: solid #2b5b84;
        background: #1e1e1e; /* Painel do log continua com cara de terminal (escuro) para facilitar leitura das cores de log (opcionalmente) */
        color: lime;
    }

    .status-label {
        text-style: bold;
        margin-bottom: 1;
        padding: 1;
        background: #eeeeee;
        border: solid #cccccc;
    }
    
    Button {
        margin: 1 1;
    }

    #controls-container {
        height: auto;
        padding: 1;
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
                # Aba 1: Controle e Logs (Equivalente à aba 'Terminal e Controle' da GUI)
                with TabPane("Controle & Logs", id="tab-controls"):
                    with Vertical():
                        # Painel de Botões de Controle
                        with Horizontal(id="controls-container"):
                            yield Button("▶️ Iniciar Bot", id="btn-start", variant="success")
                            yield Button("⏹️ Parar Bot", id="btn-stop", variant="error", disabled=True)
                            yield Label("Status: PARADO", id="lbl-status", classes="status-label")
                        
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
            self.query_one("#btn-start", Button).disabled = True
            # Parar não funciona pelo TUI para kills externos a menos que usemos os.kill na thread principal. Melhor evitar para não quebrar a lógica do watchdog
            self.query_one("#btn-stop", Button).disabled = True
            self.query_one("#btn-stop", Button).tooltip = "O bot está sendo gerenciado pelo systemd / start_rp4.sh"
            
        elif is_running_internally:
            self.query_one("#lbl-status", Label).update("Status: [green]RODANDO[/green]")
            self.query_one("#btn-start", Button).disabled = True
            self.query_one("#btn-stop", Button).disabled = False
            self.query_one("#btn-stop", Button).tooltip = ""
            
        else:
            self.query_one("#lbl-status", Label).update("Status: [red]PARADO[/red]")
            self.query_one("#btn-start", Button).disabled = False
            self.query_one("#btn-stop", Button).disabled = True
            self.query_one("#btn-stop", Button).tooltip = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Trata cliques nos botões."""
        btn_id = event.button.id
        
        if btn_id == "btn-start":
            self.start_bot()
        elif btn_id == "btn-stop":
            self.stop_bot()

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
        self.query_one("#btn-start", Button).disabled = False
        self.query_one("#btn-stop", Button).disabled = True

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
