import sys
import os
import multiprocessing

# Handle worker mode for PyInstaller frozen app early to avoid heavy imports
if "--worker" in sys.argv:
    import ingest_worker
    ingest_worker.main()
    sys.exit(0)

# Essential for Windows exes using multiprocessing anywhere in the stack
if __name__ == '__main__':
    multiprocessing.freeze_support()

import logging
import argparse
import asyncio
from telegram_controller import TelegramBotController

# Configure logging levels based on verbosity
from config_manager import ConfigurationManager
config_manager = ConfigurationManager()
verbosity = config_manager.get("log_verbosity", "médio").lower()

if verbosity == "baixo":
    # Low: Only show warnings/errors for most things
    root_level = logging.WARNING
    httpx_level = logging.ERROR
    telegram_level = logging.ERROR
elif verbosity == "alto":
    # High: Full debug everywhere
    root_level = logging.DEBUG
    httpx_level = logging.DEBUG
    telegram_level = logging.DEBUG
else:
    # Médio (Default): Standard Info
    root_level = logging.INFO
    httpx_level = logging.INFO
    telegram_level = logging.INFO

logging.basicConfig(
    level=root_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)

# Apply specific levels to heavy modules
logging.getLogger("httpx").setLevel(httpx_level)
logging.getLogger("telegram").setLevel(telegram_level)
logging.getLogger("telegram.ext").setLevel(telegram_level)

async def run_cli():
    """Run the bot in CLI mode."""
    controller = TelegramBotController()
    print("\n" + "="*50)
    print("   🌐 TELEGRAM BOT - MODO CLI ATIVO")
    print("   Pressione CTRL+C para encerrar com segurança")
    print("="*50 + "\n")
    
    try:
        await controller.start()
    except asyncio.CancelledError:
        print("\nSinal de encerramento recebido...")
        await controller.stop()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        await controller.stop()
    finally:
        print("Bot finalizado com sucesso.")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AI Telegram Bot Manager")
    parser.add_argument("--cli", action="store_true", help="Rodar em modo texto (sem interface gráfica)")
    args, unknown = parser.parse_known_args()

    # Explicit CLI Mode
    if args.cli:
        try:
            asyncio.run(run_cli())
        except KeyboardInterrupt:
            pass
        return

    # GUI Mode (Attempt)
    try:
        # Check if we have a display available (on Linux/Raspberry)
        if sys.platform != "win32" and "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
             raise RuntimeError("Nenhum monitor (X11/Wayland Display) detectado.")

        from PyQt6.QtWidgets import QApplication
        from main_window import MainWindow
        
        app = QApplication(sys.argv)
        app.setApplicationName("AI Telegram Bot Manager")
        app.setApplicationVersion("1.0.0")
        app.setStyle("Fusion")

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
        
    except Exception as e:
        print("\n⚠️  Aviso: Não foi possível iniciar a interface gráfica.")
        print(f"Erro: {e}")
        print("-" * 50)
        print("Acionando MODO CLI automaticamente...")
        print("-" * 50)
        
        try:
            asyncio.run(run_cli())
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
