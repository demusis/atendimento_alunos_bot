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
        ollama_url = data.get("ollama_url", "http://127.0.0.1:11434")

        if action == "clear":
            import shutil
            if chroma_dir and os.path.exists(chroma_dir):
                shutil.rmtree(chroma_dir)
                os.makedirs(chroma_dir, exist_ok=True)
                print(json.dumps({"ok": True, "result": "Banco de dados resetado completamente (inclusive dimensões)."}))
            else:
                print(json.dumps({"ok": True, "result": "Diretório não encontrado, nada para limpar."}))
            return

        # Import here, inside the clean subprocess
        from rag_repository import VectorStoreRepository
        
        repo = VectorStoreRepository(
            persist_directory=chroma_dir, 
            model_name=model_name,
            provider=provider,
            api_key=api_key,
            base_url=ollama_url
        )

        if action == "ingest":
            file_paths = data.get("file_paths")
            if file_paths is None:
                file_paths = [data.get("file_path")]
            
            results = []
            errors = []
            for fp in file_paths:
                if not fp:
                    continue
                try:
                    res = repo.ingest_file(fp)
                    results.append(res)
                except Exception as e:
                    errors.append(f"{os.path.basename(fp)}: {str(e)}")
            
            if not results and errors:
                print(json.dumps({"ok": False, "error": " | ".join(errors)}))
                return
                
            total_chunks = sum(r.get("chunks_count", 0) for r in results)
            
            if len(results) == 1:
                filename_display = results[0].get("filename", "")
            else:
                filename_display = f"{len(results)} arquivos"
                
            if errors:
                filename_display += f" (com Falhas em {len(errors)})"
                
            print(json.dumps({
                "ok": True, 
                "result": {
                    "chunks_count": total_chunks,
                    "filename": filename_display
                }
            }))

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
            if result.get("ok"):
                print(json.dumps({"ok": True, "result": result}))
            else:
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
