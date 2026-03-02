import json
import os
import threading
from typing import Any, Dict, Optional

class ConfigurationManager:
    """
    Singleton class to manage application configuration.
    Handles reading and writing settings to a JSON file.
    """
    _instance: Optional['ConfigurationManager'] = None
    _lock: threading.Lock = threading.Lock()
    _base_dir: str = os.path.dirname(os.path.abspath(__file__))
    _config_file: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    def __new__(cls) -> 'ConfigurationManager':
        """
        Create a new instance of ConfigurationManager if one does not exist.
        Thread-safe singleton implementation.

        Returns
        -------
        ConfigurationManager
            The singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ConfigurationManager, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """
        Initialize the configuration manager.
        Loads existing config or creates default config if file is missing.
        """
        self._config_data: Dict[str, Any] = {}
        if not os.path.exists(self._config_file):
            self._create_default_config()
        else:
            self._load_config()
            # Migration: ensure all default keys exist in loaded config
            self._migrate_config()

    def _create_default_config(self) -> None:
        """
        Create the default configuration file with initial values.
        """
        self._config_data = self._get_defaults()
        self._save_config()

    def _get_defaults(self) -> Dict[str, Any]:
        """
        Return the full dictionary of default configuration values.
        """
        return {
            "ai_provider": "ollama", # ollama or openrouter
            "telegram_token": "",
            "admin_id": "", # Telegram ID of the admin
            "ollama_model": "llama3:latest",
            "openrouter_key": "",
            "openrouter_model": "openai/gpt-3.5-turbo",
            "system_prompt": (
                "Você é um assistente virtual dedicado ao atendimento de alunos. "
                "Forneça orientações sobre horários, disciplinas e material didático. "
                "Seja sempre cortês e solícito. RESPONDA APENAS com base no contexto fornecido. "
                "Se a informação não estiver disponível, informe que não sabe."
            ),
            "temperature": 0.7,
            "max_tokens": 2048,
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_embedding_model": "nomic-embed-text",
            "rag_k": 8,
            "embedding_provider": "ollama", # ollama or openrouter
            "openrouter_embedding_model": "qwen/qwen3-embedding-8b",
            "chat_history_size": 5,
            "rate_limit_per_minute": 10,
            "chroma_dir": "db_atendimento",
            "log_verbosity": "médio",
            "welcome_message": (
                "Sou o assistente virtual do Professor e estou aqui para ajudá-lo(a) "
                "com dúvidas sobre as disciplinas, horários, materiais e muito mais.\n\n"
                "💡 Como me usar:\n"
                "• Envie sua dúvida diretamente por texto\n"
                "• Use os botões do menu abaixo para acesso rápido\n"
                "• Digite /ajuda para ver todos os comandos\n\n"
                "Vamos lá! Como posso ajudá-lo(a)?"
            ),
            "menu_buttons": [
                {"id": "btn1", "enabled": True, "text": "Horário", "action": "file_upload", "parameter": "horario"},
                {"id": "btn2", "enabled": True, "text": "Cronograma", "action": "file_upload", "parameter": "cronograma"},
                {"id": "btn3", "enabled": True, "text": "Materiais", "action": "text_file", "parameter": "materiais.txt"},
                {"id": "btn4", "enabled": True, "text": "FAQ", "action": "text_file", "parameter": "faq.txt"},
                {"id": "btn5", "enabled": True, "text": "Falar com o Professor", "action": "fixed_text", "parameter": "Prof. Carlo Ralph De Musis\n\nTelegram: @carlodemusis\nTelefone: (65) 9 9262-5221\nE-mail: carlo.demusis@gmail.com"}
            ]
        }

    def _migrate_config(self) -> None:
        """
        Ensure all default keys exist in the loaded config.
        Adds missing keys with default values without overwriting existing ones.
        """
        defaults = self._get_defaults()
        updated = False
        for key, value in defaults.items():
            if key not in self._config_data:
                self._config_data[key] = value
                updated = True
        if updated:
            self._save_config()


    def _load_config(self) -> None:
        """
        Load configuration from the JSON file.
        """
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                self._config_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading config: {e}")
            # Fallback to defaults if load fails
            self._create_default_config()

    def _save_config(self) -> None:
        """
        Save current configuration to the JSON file.
        """
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Parameters
        ----------
        key : str
            The configuration key to retrieve.
        default : Any, optional
            The default value to return if key is not found.

        Returns
        -------
        Any
            The configuration value.
        """
        return self._config_data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value and save to file.

        Parameters
        ----------
        key : str
            The configuration key to set.
        value : Any
            The value to store.
        """
        self._config_data[key] = value
        self._save_config()

    def update_batch(self, updates: Dict[str, Any]) -> None:
        """
        Update multiple configuration values and save once.

        Parameters
        ----------
        updates : Dict[str, Any]
            Dictionary of key-value pairs to update.
        """
        self._config_data.update(updates)
        self._save_config()

    @property
    def config_data(self) -> Dict[str, Any]:
        """
        Get a copy of the entire configuration dictionary.

        Returns
        -------
        Dict[str, Any]
            The configuration dictionary.
        """
        return self._config_data.copy()
