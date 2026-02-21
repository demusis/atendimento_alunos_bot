"""
Subprocess worker for ChromaDB operations.
Runs in a separate process to avoid DLL conflicts with PyQt6's SQLite.
"""
import sys
import json
import os
import traceback


def main():
    try:
        # Read JSON from stdin to avoid Windows shell escaping issues
        data = json.loads(sys.stdin.read())
        action = data["action"]
        chroma_dir = data.get("chroma_dir") or None
        model_name = data.get("model_name", "nomic-embed-text")
        provider = data.get("embedding_provider", "ollama")
        api_key = data.get("api_key", "")

        # Import here, inside the clean subprocess
        from rag_repository import VectorStoreRepository

        repo = VectorStoreRepository(
            persist_directory=chroma_dir, 
            model_name=model_name,
            provider=provider,
            api_key=api_key
        )

        if action == "ingest":
            file_path = data["file_path"]
            result = repo.ingest_file(file_path)
            print(json.dumps({"ok": True, "result": result}))

        elif action == "clear":
            result = repo.clear_database()
            print(json.dumps({"ok": True, "result": result}))

        elif action == "query":
            query_text = data["query"]
            k = data.get("k", 4)
            results = repo.query_context(query_text, n_results=k)
            # Convert Document objects to dicts
            docs = [{"page_content": d.page_content, "metadata": d.metadata} for d in results]
            print(json.dumps({"ok": True, "result": docs}))

        elif action == "list":
            result = repo.list_documents()
            print(json.dumps({"ok": True, "result": result}))

        elif action == "delete":
            filename = data["filename"]
            result = repo.delete_document(filename)
            # Result is already a dict with ok: True/False
            print(json.dumps(result))

        elif action == "stats":
            result = repo.get_stats()
            print(json.dumps({"ok": True, "result": result}))

        else:
            print(json.dumps({"ok": False, "error": f"Unknown action: {action}"}))

    except Exception as e:
        tb = traceback.format_exc()
        print(json.dumps({"ok": False, "error": str(e), "traceback": tb}))


if __name__ == "__main__":
    main()
