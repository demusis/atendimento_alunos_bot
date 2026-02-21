import sys
import logging
import argparse
import asyncio
from telegram_controller import TelegramBotController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress verbose httpx logs to avoid exposing tokens in the UI
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)

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

    # CLI Mode
    if args.cli:
        try:
            asyncio.run(run_cli())
        except KeyboardInterrupt:
            # Already handled in run_cli, but catch here to prevent traceback on Windows
            pass
        return

    # GUI Mode (Default)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from main_window import MainWindow
        
        app = QApplication(sys.argv)
        app.setApplicationName("AI Telegram Bot Manager")
        app.setApplicationVersion("1.0.0")
        app.setStyle("Fusion")

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"Critical Error during startup: {e}")
        # If QApplication is alive, try to show message box
        if 'PyQt6' in sys.modules:
             try:
                 from PyQt6.QtWidgets import QApplication, QMessageBox
                 if QApplication.instance():
                     QMessageBox.critical(None, "Critical Error", f"Application failed to start:\n{e}")
             except:
                 pass

if __name__ == "__main__":
    main()
