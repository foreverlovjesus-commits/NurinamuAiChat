import os
import sys
import asyncio
from dotenv import load_dotenv

# 프로젝트 루트 경로를 sys.path에 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from integrations.mcp_law_client import McpLawClient

async def main():
    # 환경 변수 로드
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    mcp_url = os.getenv("MCP_SERVER_URL")
    
    print(f"🔗 MCP 서버({mcp_url})에 연결 중...")
    mcp_client = McpLawClient(base_url=mcp_url)
    
    if not await mcp_client.is_healthy():
        print("❌ MCP 서버에 연결할 수 없습니다. MCP 서버가 실행 중인지 확인하세요.")
        return

    # 공식 법령 명칭 사용
    law_name = "부정청탁 및 금품등 수수의 금지에 관한 법률"
    print(f"🔍 '{law_name}' (청탁금지법) 전문 조회 중...")
    
    info_text = ""
    for tool in ["search_law", "search_laws", "chain_full_research"]:
        for param in ["query", "keyword", "lawName"]:
            res = await mcp_client.call_tool(tool, {param: law_name})
            res_str = str(res) if res else ""
            if res_str and "[MCP" not in res_str and "[결과 없음]" not in res_str and "INVALID" not in res_str and "Error" not in res_str and len(res_str.strip()) > 20:
                info_text = res_str
                break
        if info_text: break
            
    import re
    candidate_ids = []
    for pat in [r'(?:lawId|법령ID|ID)[\s"\':=]+(\d{4,8})', r'(?:일련번호|MST|mst|번호)[\s"\':=]+(\d{4,8})']:
        candidate_ids.extend(re.findall(pat, info_text, re.IGNORECASE))
    candidate_ids = list(dict.fromkeys(candidate_ids))
            
    law_text = ""
    for cid in candidate_ids:
        for param in ["lawId", "mst"]:
            fallback_text = await mcp_client.call_tool("get_law_text", {param: cid})
            fallback_text = str(fallback_text) if fallback_text else ""
            
            if fallback_text and "[INVALID" not in fallback_text and "Error" not in fallback_text and "데이터를 찾을 수 없습니다" not in fallback_text:
                if len(fallback_text) > 2000 and "제1조" in fallback_text:
                    law_text = fallback_text
                elif "목차" in fallback_text or "특정 조문" in fallback_text:
                    jos = re.findall(r'(제\d+조(?:의\d+)?)', fallback_text)
                    jos = list(dict.fromkeys(jos))
                    
                    if not jos:
                        jos = [f"제{i}조" for i in range(1, 151)]
                        
                    if jos:
                        print(f"  └─ 📑 목차 감지됨! 총 {len(jos)}개 조문 전문 추출 및 병합 시작...")
                        batch_res = None
                        for b_param in ["jos", "articles"]:
                            bres = await mcp_client.call_tool("get_batch_articles", {"lawId": cid, b_param: jos})
                            bres = str(bres) if bres else ""
                            if bres and "INVALID" not in bres and "Error" not in bres and "데이터를 찾을 수 없습니다" not in bres:
                                batch_res = bres
                                break
                        if batch_res and len(batch_res) > 200:
                            law_text = batch_res
                        else:
                            full_parts = []
                            empty_count = 0
                            for idx, jo in enumerate(jos):
                                jo_res = None
                                for jp in ["jo", "article"]:
                                    jres = await mcp_client.call_tool("get_law_text", {"lawId": cid, jp: jo})
                                    jres = str(jres) if jres else ""
                                    if jres and "INVALID" not in jres and "Error" not in jres and "데이터를 찾을 수 없습니다" not in jres:
                                        jo_res = jres
                                        break
                                if jo_res and len(jo_res.strip()) > 10:
                                    full_parts.append(jo_res)
                                    empty_count = 0
                                else:
                                    empty_count += 1
                                    if empty_count >= 5:
                                        break
                            if full_parts: law_text = "\n\n".join(full_parts)
                
                if law_text and "제1조" not in law_text:
                    law_text = ""
        if law_text: break
                        
    if not law_text or "데이터를 찾을 수 없습니다" in law_text or len(law_text.strip()) < 50:
        print(f"❌ 법제처 API에서 상세 법령 전문을 가져오지 못했습니다.\n(검색응답: {info_text[:80].replace(chr(10), ' ')}...)")
    else:
        # doc_archive/법령 폴더에 마크다운 파일로 저장
        save_path = os.path.join(BASE_DIR, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"), "법령", "청탁금지법_전문.md")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(f"# {law_name}\n\n")
            f.write(law_text)
            
        print(f"✅ 성공적으로 마크다운 파일로 저장되었습니다!\n💾 저장 위치: {save_path}")

    await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())