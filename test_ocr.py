import sys
import os

try:
    import easyocr
except ImportError:
    print("❌ EasyOCR 패키지가 설치되지 않았거나 현재 설치 중입니다.")
    print("터미널의 pip 설치가 완료된 후 다시 시도해주세요.")
    sys.exit(1)

def test_extract_text(image_path):
    if not os.path.exists(image_path):
        print(f"❌ 파일을 찾을 수 없습니다: {image_path}")
        return

    print("=========================================")
    print(f"⏳ [{image_path}] 이미지 분석 중...")
    print("=========================================")
    
    # 모델 로딩 (최초 1회만 느리고 다음부터는 빠릅니다)
    reader = easyocr.Reader(['ko', 'en'])
    
    # 텍스트 추출 (결과는 리스트 형태로 반환됨)
    result = reader.readtext(image_path, detail=0)
    
    print("\n✅ [추출된 텍스트 결과]")
    print("-----------------------------------------")
    
    if not result:
        print("(추출된 텍스트가 없습니다. 이미지가 너무 흐리거나 글자가 없습니다.)")
    else:
        # 추출된 문장들을 보기 좋게 줄바꿈하여 출력
        extracted_text = "\n".join(result)
        print(extracted_text)
        
    print("-----------------------------------------")

if __name__ == "__main__":
    # 사용자가 스크립트 실행 시 이미지 경로를 안 넣었을 경우 안내
    if len(sys.argv) < 2:
        print("사용법: python test_ocr.py [이미지경로.png]")
        print("예시: python test_ocr.py sample.png")
    else:
        test_extract_text(sys.argv[1])
