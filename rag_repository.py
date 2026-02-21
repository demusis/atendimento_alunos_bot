import os
import sys

# SQLite patch for Linux (needed for ChromaDB on some Raspberry Pi versions)
if sys.platform == "linux":
    try:
        import pysqlite3 as sqlite3
        sys.modules["sqlite3"] = sqlite3
    except ImportError:
        pass

import shutil
from typing import List, Optional, Dict, Any
from langchain_community.document_loaders import PyPDFLoader, CSVLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

class OpenRouterEmbeddings(Embeddings):
    """
    Custom Embeddings class for OpenRouter.
    """
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key
        from openrouter_client import OpenRouterAdapter
        self.adapter = OpenRouterAdapter(api_key=api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.adapter.get_embeddings(self.model, texts)

    def embed_query(self, text: str) -> List[float]:
        return self.adapter.get_embeddings(self.model, [text])[0]

class VectorStoreRepository:
    """
    Repository for managing document ingestion and vector retrieval.
    """

    def __init__(
        self, 
        persist_directory: str = None, 
        model_name: str = "nomic-embed-text",
        provider: str = "ollama",
        api_key: str = "",
        base_url: str = "http://127.0.0.1:11434"
    ) -> None:
        """
        Initialize the VectorStoreRepository.

        Parameters
        ----------
        persist_directory : str, optional
            Path to persist the ChromaDB database.
        model_name : str, optional
            Name of the embedding model to use.
        provider : str, optional
            Embedding provider ("ollama" or "openrouter").
        api_key : str, optional
            OpenRouter API Key if provider is "openrouter".
        base_url : str, optional
            Base URL for Ollama API.
        """
        if persist_directory is None:
            appdata = os.path.join(os.path.expanduser("~"), ".atendimento_bot")
            persist_directory = os.path.join(appdata, "chroma_db")
            os.makedirs(persist_directory, exist_ok=True)
        
        self.persist_directory = persist_directory
        
        if provider == "openrouter":
            self.embedding_function = OpenRouterEmbeddings(model=model_name, api_key=api_key)
        else:
            self.embedding_function = OllamaEmbeddings(model=model_name, base_url=base_url)
            
        self.vector_store: Optional[Chroma] = None
        
        # Initialize/Load DB
        self._load_db()

    def _load_db(self) -> None:
        """
        Initialize the Chroma vector store.
        """
        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_function
        )

    def ingest_file(self, file_path: str, chunk_size: int = 2000, chunk_overlap: int = 400) -> Dict[str, Any]:
        """
        Ingest a file into the vector store.
        Supports PDF, CSV, and TXT files.

        Parameters
        ----------
        file_path : str
            Absolute path to the file.
        chunk_size : int, optional
            Size of text chunks, by default 1000.
        chunk_overlap : int, optional
            Overlap between chunks, by default 200.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing 'status', 'chunks_count', and 'filename'.
        
        Raises
        ------
        FileNotFoundError
            If file not found.
        ValueError
            If file type is unsupported.
        RuntimeError
            If ingestion process fails.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        loader = None
        
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif ext == ".csv":
                loader = CSVLoader(file_path)
            elif ext == ".docx":
                loader = Docx2txtLoader(file_path)
            elif ext in (".txt", ".md"):
                loader = TextLoader(file_path, encoding='utf-8')
            else:
                raise ValueError(f"Tipo de arquivo não suportado: '{ext}'")

            # Load
            documents = loader.load()
            
            # Split
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, 
                chunk_overlap=chunk_overlap
            )
            splits = text_splitter.split_documents(documents)
            
            # Add to Vector Store
            if self.vector_store:
                self.vector_store.add_documents(documents=splits)
                return {
                    "status": "success",
                    "chunks_count": len(splits),
                    "filename": os.path.basename(file_path)
                }
            else:
                raise RuntimeError("Vector Store não inicializado.")
                
        except Exception as e:
            raise RuntimeError(f"Erro na ingestão do arquivo: {str(e)}") from e

    def query_context(self, query_text: str, n_results: int = 4) -> List[Document]:
        """
        Retrieve relevant documents for a given query.

        Parameters
        ----------
        query_text : str
            The query string.
        n_results : int, optional
            Number of results to return, by default 4.

        Returns
        -------
        List[Document]
            List of retrieved LangChain Documents.
        """
        if not self.vector_store:
            return []
            
        return self.vector_store.similarity_search(query_text, k=n_results)

    def clear_database(self) -> str:
        """
        Clear the vector database by deleting the persistence directory.
        This is necessary when switching between models with different dimensions.
        
        Returns
        -------
        str
            Status message.
        """
        try:
            if os.path.exists(self.persist_directory):
                # We need to close the connection if possible, but Chroma doesn't 
                # expose an explicit close() easily in this wrapper.
                # shutil.rmtree is the most effective way to RESET the dimension.
                shutil.rmtree(self.persist_directory)
                os.makedirs(self.persist_directory, exist_ok=True)
                # Re-load an empty DB
                self._load_db()
                return "Banco de dados resetado completamente (inclusive dimensões)."
            return "Diretório não encontrado."
        except Exception as e:
            return f"Erro ao limpar: {str(e)}"

    def list_documents(self) -> List[str]:
        """
        List unique source filenames currently in the database.
        
        Returns
        -------
        List[str]
            List of unique filenames.
        """
        if not self.vector_store:
            return []
            
        try:
            data = self.vector_store.get()
            metadatas = data.get('metadatas', [])
            
            unique_sources = set()
            for meta in metadatas:
                if meta and 'original_filename' in meta:
                    unique_sources.add(meta['original_filename'])
                elif meta and 'source' in meta:
                    # Fallback to basename of source path
                    unique_sources.add(os.path.basename(str(meta['source'])))
            
            return sorted(list(unique_sources))
        except Exception as e:
            print(f"Error listing documents: {e}")
            return []
    def delete_document(self, filename: str) -> Dict[str, Any]:
        """
        Delete a document and all its chunks from the vector store.
        
        Parameters
        ----------
        filename : str
            The name of the file to delete (basename).
            
        Returns
        -------
        Dict[str, Any]
            Status and count of deleted items.
        """
        if not self.vector_store:
            return {"ok": False, "error": "Vector Store não inicializado."}
            
        try:
            data = self.vector_store.get()
            ids = data.get('ids', [])
            metadatas = data.get('metadatas', [])
            
            ids_to_delete = []
            for i, meta in enumerate(metadatas):
                if not meta:
                    continue
                
                # Check original_filename or source
                source_file = meta.get('original_filename') or os.path.basename(str(meta.get('source', '')))
                if source_file == filename:
                    ids_to_delete.append(ids[i])
            
            if ids_to_delete:
                self.vector_store.delete(ids=ids_to_delete)
                return {
                    "ok": True, 
                    "deleted_count": len(ids_to_delete),
                    "filename": filename
                }
            else:
                return {
                    "ok": False, 
                    "error": f"Arquivo '{filename}' não encontrado na base."
                }
        except Exception as e:
            print(f"Error deleting document {filename}: {e}")
            return {"ok": False, "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary with 'file_count' and 'chunk_count'.
        """
        if not self.vector_store:
            return {"file_count": 0, "chunk_count": 0}
            
        try:
            data = self.vector_store.get()
            ids = data.get('ids', [])
            metadatas = data.get('metadatas', [])
            
            unique_files = set()
            for meta in metadatas:
                if not meta:
                    continue
                source = meta.get('original_filename') or os.path.basename(str(meta.get('source', '')))
                if source:
                    unique_files.add(source)
            
            return {
                "file_count": len(unique_files),
                "chunk_count": len(ids)
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {"file_count": 0, "chunk_count": 0, "error": str(e)}
