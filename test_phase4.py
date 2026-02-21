import asyncio
from unittest.mock import MagicMock, AsyncMock
from telegram_controller import TelegramBotController

async def test_telegram_controller_mock():
    print("--- Testing TelegramBotController (Mocked) ---")
    
    # Instantiate Controller
    controller = TelegramBotController()
    
    # Mock Dependencies to avoid real IO/Tokens
    controller.config_manager = MagicMock()
    controller.config_manager.get.side_effect = lambda key, default=None: {
        "telegram_token": "FAKE_TOKEN",
        "ollama_model": "llama3:latest",
        "system_prompt": "You are a bot.",
        "temperature": 0.7,
        "max_tokens": 100,
        "ollama_url": "http://127.0.0.1:11434"
    }.get(key, default)
    
    controller.ollama_adapter = MagicMock()
    # Mock generator for response
    controller.ollama_adapter.generate_response.return_value = ["Hello ", "from ", "mocked ", "Ollama!"]
    
    controller.rag_repository = MagicMock()
    # Mock context retrieval
    mock_doc = MagicMock()
    mock_doc.page_content = "This is a mocked context."
    controller.rag_repository.query_context.return_value = [mock_doc]
    
    # Simulate Message Handling Logic directly
    # (Checking the private method _handle_message logic without needing full Application/Updater loop)
    
    # Mock Update and Context
    update = MagicMock()
    update.message.text = "Hello Bot"
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 12345
    
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    
    print("Simulating incoming message: 'Hello Bot'")
    await controller._handle_message(update, context)
    
    # Verifications
    print("\nVerifying interactions:")
    
    # 1. Check RAG call
    controller.rag_repository.query_context.assert_called_with("Hello Bot", n_results=4)
    print("✅ RAG Repository queried.")
    
    # 2. Check Ollama call
    # We can check if generate_response was called.
    args, kwargs = controller.ollama_adapter.generate_response.call_args
    print(f"✅ Ollama Adapter called with model: {kwargs.get('model')}")
    assert "mocked context" in kwargs.get('prompt', ''), "Context missing in prompt"
    
    # 3. Check Reply
    update.message.reply_text.assert_called_once()
    args_reply, _ = update.message.reply_text.call_args
    print(f"✅ Bot replied with: '{args_reply[0]}'")
    
    print("\nTelegram Controller Test Complete.\n")

if __name__ == "__main__":
    asyncio.run(test_telegram_controller_mock())
