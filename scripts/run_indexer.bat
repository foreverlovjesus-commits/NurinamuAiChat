@echo off
:: 1. 한글 인코딩 설정 (UTF-8 모드)
chcp 65001 > nul

:: 2. 프로젝트 경로로 이동
cd /d "C:\NuriNamuAiChat"

:: 3. 가상환경 활성화
call venv\Scripts\activate

:: 4. 현재 시간 기록 및 인덱서 실행
echo [%date% %time%] === 지식베이스 자동 업데이트 시작 === >> logs\schedule.log
python indexer\rag_indexer.py >> logs\schedule.log 2>&1
echo [%date% %time%] === 업데이트 완료 === >> logs\schedule.log
echo. >> logs\schedule.log

:: 5. 완료 후 터미널 창 자동 닫기
exit
