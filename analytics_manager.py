import json
import os
import hashlib
from datetime import datetime


class AnalyticsManager:
    """
    Manages logging of user interactions for analytics.
    Anonymizes user IDs using SHA-256.
    """
    def __init__(self, log_file: str = "history.jsonl"):
        # If the path is relative, make it absolute based on the script's location
        if not os.path.isabs(log_file):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.log_file = os.path.join(base_dir, log_file)
        else:
            self.log_file = log_file

    def _anonymize_user(self, user_id: int) -> str:
        """Hash user ID for privacy."""
        return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]

    def log_interaction(self, user_id: int, question: str, answer: str, provider: str, full_name: str = "Unknown", username: str = ""):
        """
        Log a Q&A interaction with full user details.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "full_name": full_name,
            "username": username,
            "question_length": len(question),
            "answer_length": len(answer),
            "provider": provider,
            "question": question, 
            "answer": answer
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to log interaction: {e}")
    
    def get_logs(self, days: int) -> str:
        """
        Retrieve logs from the last `days`.
        Returns a formatted string for the LLM.
        """
        if not os.path.exists(self.log_file):
            return "Nenhum histórico encontrado."
            
        relevant_logs = []
        now = datetime.now()
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if (now - ts).days <= days:
                            # Format for LLM reading (detailed)
                            user_str = f"{entry.get('full_name', 'User')} (@{entry.get('username', '')})"
                            relevant_logs.append(f"- [{entry['timestamp'][:16]}] [{user_str}] Q: {entry.get('question', '')}")
                    except:
                        continue
            
            # Limit to last 200 relevant entries to avoid context window issues
            relevant_logs = relevant_logs[-200:]
            
            return "\n".join(relevant_logs) if relevant_logs else "Nenhuma interação no período."
        except Exception as e:
            return f"Erro ao ler logs: {e}"

    def get_logs_by_count(self, count: int) -> str:
        """
        Retrieve the last `count` log entries.
        Returns a formatted string for the LLM.
        """
        if not os.path.exists(self.log_file):
            return "Nenhum histórico encontrado."
            
        logs = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                # Read all lines but we'll take the last N
                for line in f:
                    try:
                        entry = json.loads(line)
                        user_str = f"{entry.get('full_name', 'User')} (@{entry.get('username', '')})"
                        logs.append(f"- [{entry['timestamp'][:16]}] [{user_str}] Q: {entry.get('question', '')}")
                    except:
                        continue
            
            # Take the last 'count' logs
            relevant_logs = logs[-count:] if count > 0 else logs[-50:]
            
            return "\n".join(relevant_logs) if relevant_logs else "Nenhuma interação encontrada."
        except Exception as e:
            return f"Erro ao ler logs: {e}"

    def clear_history(self) -> bool:
        """
        Clear the entire interaction history file.
        Returns True if successful.
        """
        try:
            if os.path.exists(self.log_file):
                os.remove(self.log_file)
            # Re-create empty file
            with open(self.log_file, "w", encoding="utf-8") as f:
                pass
            return True
        except Exception as e:
            print(f"Erro ao limpar histórico: {e}")
            return False

    def get_unique_users(self) -> list[int]:
        """
        Get a list of all unique Telegram user IDs from the history.
        """
        if not os.path.exists(self.log_file):
            return []
            
        unique_users = set()
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        u_id = entry.get("user_id")
                        if u_id:
                            unique_users.add(int(u_id))
                    except:
                        continue
            return list(unique_users)
        except Exception as e:
            print(f"Error getting unique users: {e}")
            return []
