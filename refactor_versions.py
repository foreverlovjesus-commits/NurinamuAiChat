import os
import glob

workspace = r"c:\NuriNamuAiChat"

# 1. Rename Target Files
renames = [
    (r"rag\rag_engine_v3.py", r"rag\rag_engine.py"),
    (r"retriever\advanced_retriever_v2.py", r"retriever\advanced_retriever.py"),
    (r"indexer\rag_indexer_v4.py", r"indexer\rag_indexer.py")
]

for old, new in renames:
    old_path = os.path.join(workspace, old)
    new_path = os.path.join(workspace, new)
    if os.path.exists(old_path):
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(old_path, new_path)
        print(f"Renamed: {old} -> {new}")
    else:
        print(f"Skip rename: {old} not found")

# 2. Text Replacements
replacements = {
    "rag_engine_v3": "rag_engine",
    "advanced_retriever_v2": "advanced_retriever",
    "rag_indexer_v4": "rag_indexer"
}

targets = [
    r"server\api_server.py",
    r"server\api_server_cloud.py",
    r"retriever\factory.py",
    r"retriever\advanced_retriever.py",
    r"rag\rag_engine.py",
    r"indexer\rag_indexer.py",
    r"scripts\run_indexer.bat",
    r"scripts\start.sh",
    r"pyproject.toml",
    r".env.example",
    r"docs\MCP_연계_로드맵.md",
    r"docs\운영_매뉴얼.md",
    r"지능형_챗봇_구축_보고서_최종.md",
    r"CLAUDE.md",
    r"start_all.bat",
    r"start_cloud.bat",
    r"start_local.bat",
    r"docker-compose.yml",
    r"Dockerfile"
]

for t in targets:
    file_path = os.path.join(workspace, t)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        modified = content
        for k, v in replacements.items():
            modified = modified.replace(k, v)
            
        if modified != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified)
            print(f"Updated contents: {t}")

print("Refactoring complete.")
