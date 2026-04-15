# NuriNamu 프로덕션 배포 계획 (GCP + Supabase)

본 문서는 NuriNamu AI Chat 시스템을 **Google Cloud Platform (GCP)**의 **Cloud Run** 컨테이너 환경에 배포하고, 데이터베이스를 **Supabase**의 서버리스 PostgreSQL로 구성하기 위한 최신 가이드입니다.

---

## 1. 아키텍처 개요 (Architecture Overview)

기존 VM 단위 배포(All-in-One)에서 벗어나, 상용 서비스 수준의 무중단 확장이 가능한 서버리스 클라우드 아키텍처로 분리합니다.

*   **프론트엔드/백엔드 컨테이너**: GCP Cloud Run (min_instances=1, max=10, mem=4Gi, cpu=2)
*   **로드밸런서 (네트워크/보안)**: Google Cloud HTTP(S) 로드밸런서 + Managed SSL (자동 HTTPS 강제) 및 Cloud Armor (WAF 기능 제공)
*   **시스템 시크릿 관리**: GCP Secret Manager (`MASTER_KEY`, API 키 등 격리)
*   **도커 이미지 저장소**: GCP Artifact Registry (asia-northeast3)
*   **데이터베이스 (지식 저장소)**: Supabase (PostgreSQL + `pgvector` 임베딩 저장용)
*   **AI 모델 (LLM)**: 운영 비용 절감 및 빠른 응답 속도를 위해 상용 API (Google Gemini 2.5 Flash Lite) 사용. 

---

## 2. 1단계: Supabase (데이터베이스) 설정 가이드

가장 먼저 구축해야 하는 핵심 인프라입니다. NuriNamu의 백터 문서 정보가 저장됩니다.

1.  **프로젝트 생성**: Supabase 사이트에 로그인 후 새 프로젝트를 생성합니다. (지역: 서울 `ap-northeast-2` 권장)
2.  **데이터베이스 비밀번호 설정**: 영문+숫자+특수문자 조합의 강력한 비밀번호를 생성하고 **반드시 메모장에 복사**해 둡니다. (이후 재생성이 까다로움)
3.  **pgvector 확장 프로그램 활성화**:
    *   Supabase 대시보드 -> 왼쪽 메뉴 `SQL Editor` 클릭
    *   아래 명령어를 복사 후 실행(Run)합니다.
    ```sql
    CREATE EXTENSION IF NOT EXISTS vector;
    ```
4.  **Connection String (연결 문자열) 확보**: 
    *   `Project Settings` -> `Database` -> `Connection String` -> `URI` 선택
    *   `postgresql://postgres.아이디:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres` 형태의 주소를 잘 보관합니다.

> [!CAUTION]
> 생성된 DB 연결 문자열에는 관리자 `포트(5432)`와 커넥션 풀러 `포트(6543)`가 있습니다. Cloud Run에서 짧고 빈번한 API 연결을 할 때는 **커넥션 풀러 포트(6543)**를 사용하는 것을 강력히 권장합니다.

---

## 3. 2단계: GCP 서버리스 및 보안 인프라 세팅

Cloud Run은 컨테이너 구동 기반이므로 VM 인스턴스가 필요하지 않습니다.

1.  **Secret Manager 세팅**:
    *   `MASTER_KEY`, `GOOGLE_API_KEY`, `DATABASE_URL` 등 민감한 정보는 소스코드 내부 `.env`에서 제거하세요.
    *   GCP "Secret Manager" 콘솔에서 위 변수들을 등록합니다. (예: `nurinamu-db-url`)
2.  **Artifact Registry 생성**:
    *   도커 이미지가 푸시될 저장소를 만듭니다. (지역: `asia-northeast3` 서울)
3.  **Cloud Load Balancing + SSL 인증서 자동 구성**:
    *   Cloud Run 서비스를 외부에 HTTP (비보안)로 직접 노출하는 것은 공공기관 납품 기준 위반입니다.
    *   반드시 "서버리스 NEG"를 생성해 Google Cloud Load Balancer 에 연결하고 위임받은 도메인에 대한 Google Managed SSL 인증서를 부여하십시오. 

---

## 4. 3단계: 배포용 환경 변수 주입 방식 설정

Cloud Run은 배포 시점에 환경 변수와 시크릿을 지정합니다. `gcloud run deploy` 명령 또는 GitHub Actions 배포 스크립트를 통해 다음 항목들을 주입합니다.

```bash
# 보안 정보: Secret Manager 매핑 --set-secrets 파라미터 사용
--set-secrets=DATABASE_URL=nurinamu-db-url:latest
--set-secrets=GOOGLE_API_KEY=nurinamu-google-api:latest

# 일반 환경 정보: --set-env-vars 파라미터 사용
--set-env-vars="APP_ENV=production"
--set-env-vars="NEXT_PUBLIC_API_BASE_URL=https://api.nurinamu.go.kr"
--set-env-vars="ALLOWED_ORIGINS=https://www.nurinamu.go.kr"
--set-env-vars="GLOBAL_LLM_PROVIDER=gemini"
--set-env-vars="GEMINI_MODEL=gemini-2.5-flash-lite"
```

---

## 5. 4단계: 실제 배포 및 무중단 업데이트 런칭 (CI/CD)

Cloud Run은 GitHub Actions (`.github/workflows/cd.yml`) 연동을 통해 커밋 푸시마다 무중단 (Rolling Update) 배포가 되도록 구성되어 있습니다.

### 1) GitHub Repo 비밀 변수 (Secrets) 등록
레포지토리의 `Settings > Secrets and variables > Actions` 에 다음을 추가합니다.
- `GCP_CREDENTIALS_PROD`: GCP 서비스 계정의 JSON 키 파일
- `DOCKER_USERNAME`: GCP Artifact Registry 호스트 주소 (예: `asia-northeast3-docker.pkg.dev/my-project/nurinamu-repo`)

### 2) 배포 가동
소스코드를 `main` 브랜치에 `push` 또는 PR Merge하면 GitHub Actions가 자동으로 Cloud Build와 Cloud Run을 갱신합니다.

> [!TIP]
> 롤백(상태 되돌리기)이 필요한 경우 CLI에서 리비전을 롤백할 수 있습니다:
> `gcloud run services update-traffic nurinamu-api-prod --to-revisions=OLD_REVSION=100`

---

## 향후 마이그레이션 과제 사전 확인

도메인(https)이 붙고 Artifact Registry + Secret Manager 구조로 세팅하면 **완벽한 2026년 상용 스탠다드 프로덕션 런칭**에 성공하실 수 있습니다. 혹시 이 단계들 중 "GCP 인프라 IAM 권한 세팅법" 측면에서 조작하시다가 막히는 부분이 있으시다면 바로 말씀해주십시오. 제가 즉시 문제를 격리해 드리겠습니다.
