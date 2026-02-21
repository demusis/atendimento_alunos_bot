import os
from ollama_client import OllamaAdapter
from rag_repository import VectorStoreRepository

def test_ollama():
    print("--- Testing OllamaAdapter ---")
    client = OllamaAdapter()
    try:
        print("Models available:", client.list_models())
        print("Generating response for 'Say Hello':")
        for chunk in client.generate_response("llama3:latest", "Say Hello", max_tokens=10):
            print(chunk, end="", flush=True)
        print("\nOllama Test Complete.\n")
    except Exception as e:
        print(f"Ollama Test Failed: {e}\n")

def test_rag():
    print("--- Testing VectorStoreRepository ---")
    # Using llama3:latest for embeddings as nomic-embed-text is not available
    print("Initializing RAG with llama3:latest...")
    repo = VectorStoreRepository(model_name="llama3:latest") 
    
    # Create dummy file
    test_file = "test_doc.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("This is a critical test document about Quantum Physics.")
    
    # Ingest
    print(f"Ingesting {test_file}...")
    res = repo.ingest_file(os.path.abspath(test_file))
    print(res)
    
    # Query
    print("Querying 'Quantum'...")
    docs = repo.query_context("Quantum")
    for doc in docs:
        print(f"Found: {doc.page_content}")
    
    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)
    print("RAG Test Complete.\n")

if __name__ == "__main__":
    # Note: Ensure ollama is running and 'nomic-embed-text' is pulled for RAG test to work fully
    # otherwise it will fail gracefully or show error.
    test_ollama()
    test_rag()
