# Repository Map

Purpose:
Provide a quick structural overview so AI tools can understand the project.

Core Areas:

auth/
Authentication logic.

rag/
Main RAG pipeline.

retriever/
Vector search.

indexer/
Document ingestion.

server/
Backend API layer.

web/
Frontend UI.

monitoring/
Logging and metrics.

Data Flow:

PDF Upload
→ indexer
→ embeddings
→ vector index
→ retriever
→ rag context
→ server
→ user response