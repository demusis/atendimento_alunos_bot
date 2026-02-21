import re
import requests
import json
from typing import Dict, Any, Generator, Optional

class OllamaAdapter:
    """
    Adapter class to interact with partylocal Ollama instance.
    Handles HTTP requests to the Ollama API for text generation.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        """
        Initialize the Ollama adapter.

        Parameters
        ----------
        base_url : str, optional
            Base URL of the Ollama API, by default "http://127.0.0.1:11434"
        """
        self.base_url = base_url.rstrip('/')

    def generate_response(
        self, 
        model: str, 
        prompt: str, 
        system_prompt: str = "", 
        temperature: float = 0.7, 
        max_tokens: int = 2048
    ) -> Generator[str, None, None]:
        """
        Generate a response from the Ollama model.
        Uses the /api/generate endpoint with streaming.

        Parameters
        ----------
        model : str
            Name of the model to use (e.g., "llama3").
        prompt : str
            The user, or context-augmented, prompt.
        system_prompt : str, optional
            System instructions for behavior definition.
        temperature : float, optional
            Sampling temperature, by default 0.7.
        max_tokens : int, optional
            Maximum number of tokens to predict, by default 2048.

        Yields
        ------
        str
            Chunks of the generated text.

        Raises
        ------
        ConnectionError
            If the Ollama service is unreachable.
        RuntimeError
            If the API returns an error.
        """
        url = f"{self.base_url}/api/generate"
        
        # Disable Qwen3 "thinking" mode to speed up responses
        if "qwen3" in model.lower():
            prompt = prompt + " /no_think"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        try:
            with requests.post(url, json=payload, stream=True) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        body = json.loads(line)
                        if "error" in body:
                            raise RuntimeError(f"Ollama API Error: {body['error']}")
                        
                        if not body.get("done", False):
                            chunk = body.get("response", "")
                            # Strip <think>...</think> tags from Qwen3 responses
                            chunk = re.sub(r'<think>.*?</think>', '', chunk, flags=re.DOTALL)
                            if chunk:
                                yield chunk
                            
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Could not connect to Ollama at {self.base_url}. Is it running?")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request failed: {e}")

    def list_models(self) -> list[str]:
        """
        List available models on the local Ollama instance.

        Returns
        -------
        list[str]
            List of model names.
        """
        url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            print(f"Error fetching models: {e}")
            return []
