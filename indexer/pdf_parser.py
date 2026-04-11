import pdfplumber
import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> str:
    """
    pdfplumber를 사용하여 PDF 파일에서 텍스트를 추출합니다.
    (공공기관 납품을 위해 AGPL 라이선스인 PyMuPDF 대체용)
    
    Args:
        file_path (str): PDF 파일의 로컬 경로
        
    Returns:
        str: 추출된 전체 텍스트
    """
    extracted_text = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                
                # 텍스트가 존재하는 경우에만 리스트에 추가 (이미지 통짜 페이지 대비)
                if text:
                    extracted_text.append(text)
                else:
                    logger.debug(f"페이지 {page_number}에서 추출된 텍스트가 없습니다. (이미지 위주 페이지일 수 있음)")
                    
        # 페이지별 텍스트를 줄바꿈으로 연결하여 반환
        return "\n\n".join(extracted_text)
        
    except Exception as e:
        logger.error(f"PDF 파일({file_path})을 읽는 중 오류가 발생했습니다: {e}")
        return ""