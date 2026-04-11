# RAG Architecture

System Pipeline:

User Question
→ API Server
→ Retriever
→ Context Builder
→ LLM
→ Response

Processing Flow:

PDF Upload
→ Text Extraction
→ Chunking
→ Embedding Generation
→ Vector Index
→ Retrieval
→ Prompt Assembly
→ LLM Response

Key Components:

rag/
Core pipeline logic.

retriever/
Vector search.

indexer/
Document ingestion and embedding.

server/
API services.

web/
Frontend interface.