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

    def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        """
        Get embeddings for a list of texts using OpenRouter.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/demusis/atendimento_alunos_bot",
        }
        
        payload = {
            "model": model,
            "input": texts
        }
        
        response = requests.post(f"{self.base_url}/embeddings", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        
        data = response.json()
        return [item["embedding"] for item in data["data"]]

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
            with requests.post(url, headers=headers, json=payload, stream=True, timeout=(5, 60)) as response:
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
        Fetch available models from OpenRouter API.
        
        Returns
        -------
        list[str]
            Sorted list of model IDs (e.g., "openai/gpt-4o").
        """
        url = f"{self.base_url}/models"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            models = []
            for model in data.get("data", []):
                model_id = model.get("id", "")
                if model_id:
                    models.append(model_id)
            
            if models:
                return sorted(models)
        except Exception as e:
            print(f"Erro ao buscar modelos do OpenRouter: {e}")
        
        # Fallback: curated list if API fails
        return [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3-haiku",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-flash-1.5",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-8b-instruct",
            "mistralai/mistral-7b-instruct",
            "deepseek/deepseek-chat",
        ]

    def get_balance(self) -> dict:
        """
        Fetch balance and usage statistics from OpenRouter API.
        
        Returns
        -------
        dict
            Dictionary containing credits and usage data.
        """
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        result = {
            "total_credits": 0.0,
            "total_usage": 0.0,
            "balance": 0.0,
            "usage_daily": 0.0,
            "usage_weekly": 0.0,
            "usage_monthly": 0.0
        }
        
        try:
            # Get credits
            cred_resp = requests.get(f"{self.base_url}/credits", headers=headers, timeout=10)
            if cred_resp.ok:
                cred_data = cred_resp.json().get("data", {})
                result["total_credits"] = cred_data.get("total_credits", 0.0)
            
            # Get key usage stats
            key_resp = requests.get(f"{self.base_url}/auth/key", headers=headers, timeout=10)
            if key_resp.ok:
                key_data = key_resp.json().get("data", {})
                result["total_usage"] = key_data.get("usage", 0.0)
                result["usage_daily"] = key_data.get("usage_daily", 0.0)
                result["usage_weekly"] = key_data.get("usage_weekly", 0.0)
                result["usage_monthly"] = key_data.get("usage_monthly", 0.0)
            else:
                if cred_resp.ok:
                    result["total_usage"] = cred_data.get("total_usage", 0.0)

            result["balance"] = max(0.0, result["total_credits"] - result["total_usage"])
        except Exception as e:
            print(f"Erro ao buscar saldo do OpenRouter: {e}")
            
        return result

