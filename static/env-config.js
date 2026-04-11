// 🌐 상용 배포 환경설정 파일
// 본 파일은 빌드 과정 없이 Nginx/Apache 등 웹 서버에 배포 시 바로 수정할 수 있습니다.

window.ENV = {
  // 백엔드 API 서버 주소 
  // (개발 시 http://localhost:8000, 상용 리버스 프록시 시 '' 또는 실제 도메인 입력)
  API_BASE: "http://localhost:8000"
};
