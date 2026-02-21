import requests
import json
from typing import Generator

class OpenRouterAdapter:
    """
    Adapter class to interact with OpenRouter API.
    """

    def __init__(self, api_key: str) -> None:
        """
        Initialize the OpenRouter adapter.

        Parameters
        ----------
        api_key : str
            The OpenRouter API Key.
        """
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"

    def generate_response(
        self, 
        model: str, 
        prompt: str, 
        system_prompt: str = "", 
        temperature: float = 0.7, 
        max_tokens: int = 2048
    ) -> Generator[str, None, None]:
        """
        Generate a response from OpenRouter using OpenAI-compatible API.

        Parameters
        ----------
        model : str
            Name of the model (e.g., "openai/gpt-3.5-turbo").
        prompt : str
            The user prompt.
        system_prompt : str, optional
            System instructions.
        temperature : float, optional
            Sampling temperature.
        max_tokens : int, optional
            Max tokens.

        Yields
        ------
        str
            Chunks of generated text.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/demusis/atendimento_alunos_bot",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            with requests.post(url, headers=headers, json=payload, stream=True) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data_str = line_str[6:] # Strip "data: "
                            
                            if data_str.strip() == "[DONE]":
                                break
                                
                            try:
                                body = json.loads(data_str)
                                choices = body.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                pass
                                
        except Exception as e:
            raise RuntimeError(f"OpenRouter API Error: {e}")

    def list_models(self) -> list[str]:
        """
        List models from OpenRouter is complex (requires GET /models).
        For simplicity, we return a popular subset or implement fetch.
        """
        # Minimal implementation relying on manual entry or simple fetch
        return ["openai/gpt-3.5-turbo", "anthropic/claude-3-haiku", "google/gemini-flash-1.5"]
