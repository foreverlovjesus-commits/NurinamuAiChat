#!/bin/bash
# ─────────────────────────────────────────────────────────────
# NuriNamu — Gemini API 방화벽 점검 스크립트
# 대상 환경: RHEL 7.8 / CentOS 7 (bash 4+, curl, openssl, dig)
# 용도: 공공기관 서버에서 Gemini API 접속 가능 여부를 단계별로 진단
#
# 사용법:
#   bash scripts/check_gemini_network.sh
#   또는
#   chmod +x scripts/check_gemini_network.sh && ./scripts/check_gemini_network.sh
#
# 종료 코드:
#   0: 모든 점검 통과 (API 호출 가능)
#   1: 하나 이상의 점검 실패 (보안팀 협의 필요)
# ─────────────────────────────────────────────────────────────

set +e

# ── 색상 코드 (터미널 지원 시) ──
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' YELLOW='' BLUE='' BOLD='' RESET=''
fi

# ── 점검 대상 호스트 ──
HOSTS="generativelanguage.googleapis.com oauth2.googleapis.com www.googleapis.com pki.goog"
PRIMARY_HOST="generativelanguage.googleapis.com"

# ── 결과 집계 ──
FAIL_COUNT=0
WARN_COUNT=0
PASS_COUNT=0

pass() { echo -e "  ${GREEN}[OK]${RESET} $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "  ${RED}[FAIL]${RESET} $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn() { echo -e "  ${YELLOW}[WARN]${RESET} $1"; WARN_COUNT=$((WARN_COUNT + 1)); }
info() { echo -e "  ${BLUE}[INFO]${RESET} $1"; }

section() {
    echo ""
    echo -e "${BOLD}═══ $1 ═══${RESET}"
}

# ─────────────────────────────────────────────────────────────
# [0] 사전 도구 확인
# ─────────────────────────────────────────────────────────────
section "[0] 사전 도구 확인"

MISSING_TOOLS=""
for tool in curl dig openssl timeout; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        MISSING_TOOLS="$MISSING_TOOLS $tool"
    fi
done

if [ -n "$MISSING_TOOLS" ]; then
    fail "누락된 도구:$MISSING_TOOLS"
    info "설치: sudo yum install -y curl bind-utils openssl"
    echo ""
    echo -e "${RED}점검 중단: 필수 도구가 없습니다.${RESET}"
    exit 1
else
    pass "필수 도구 (curl, dig, openssl, timeout) 모두 설치됨"
fi

# ─────────────────────────────────────────────────────────────
# [1] DNS 해석
# ─────────────────────────────────────────────────────────────
section "[1] DNS 해석 점검"

DNS_FAIL=0
for h in $HOSTS; do
    ip=$(dig +short +time=3 +tries=1 "$h" 2>/dev/null | grep -E '^[0-9]+\.' | head -1)
    if [ -n "$ip" ]; then
        pass "$h → $ip"
    else
        fail "$h → 해석 실패"
        DNS_FAIL=$((DNS_FAIL + 1))
    fi
done

if [ $DNS_FAIL -gt 0 ]; then
    info "대응: /etc/resolv.conf 확인 또는 내부 DNS에 Google 도메인 등록 요청"
    info "    현재 DNS: $(grep '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"

    # 공용 DNS로 우회 테스트
    echo ""
    info "공용 DNS(8.8.8.8)로 우회 테스트:"
    PUBLIC_DNS_IP=$(dig @8.8.8.8 +short +time=3 +tries=1 "$PRIMARY_HOST" 2>/dev/null | grep -E '^[0-9]+\.' | head -1)
    if [ -n "$PUBLIC_DNS_IP" ]; then
        warn "공용 DNS로는 해석됨 ($PUBLIC_DNS_IP) → 내부 DNS에만 막혀 있음"
    else
        fail "공용 DNS도 해석 실패 → DNS 53번 포트 자체가 차단됨"
    fi
fi

# ─────────────────────────────────────────────────────────────
# [2] TCP 443 도달성
# ─────────────────────────────────────────────────────────────
section "[2] TCP 443 도달성 점검"

TCP_FAIL=0
for h in $HOSTS; do
    if timeout 5 bash -c "echo > /dev/tcp/$h/443" 2>/dev/null; then
        pass "$h:443 연결 성공"
    else
        fail "$h:443 차단됨"
        TCP_FAIL=$((TCP_FAIL + 1))
    fi
done

if [ $TCP_FAIL -gt 0 ]; then
    info "대응: 아웃바운드 방화벽에 위 도메인:443 허용 요청 필요"
    info "    도메인 기반 화이트리스트로 요청할 것 (IP는 Anycast로 수시 변경됨)"
fi

# ─────────────────────────────────────────────────────────────
# [3] TLS 핸드셰이크 + 인증서 체인
# ─────────────────────────────────────────────────────────────
section "[3] TLS 인증서 체인 검증"

CERT_OUTPUT=$(echo | timeout 10 openssl s_client \
    -connect ${PRIMARY_HOST}:443 \
    -servername ${PRIMARY_HOST} 2>/dev/null \
    | openssl x509 -noout -issuer -subject 2>/dev/null)

if [ -z "$CERT_OUTPUT" ]; then
    fail "TLS 핸드셰이크 실패 — TCP 연결이 되어도 TLS 레이어에서 차단"
    info "대응: TLS Inspection 장비가 TLS 1.2+ 를 지원하지 않거나 완전 차단 중"
else
    echo "$CERT_OUTPUT" | sed 's/^/    /'
    echo ""

    if echo "$CERT_OUTPUT" | grep -qi "Google Trust Services"; then
        pass "직접 연결 — Google Trust Services 인증서 확인됨 (TLS Inspection 없음)"
    elif echo "$CERT_OUTPUT" | grep -qiE "(proxy|inspect|firewall|국가정보자원|NIA|gateway)"; then
        warn "TLS Inspection 감지됨 — 내부 CA가 인증서를 재발급 중"
        info "대응 (옵션 A - 권장): 보안팀에 해당 도메인을 SSL Inspection 예외로 추가 요청"
        info "대응 (옵션 B): 내부 CA 인증서를 /etc/pki/ca-trust/source/anchors/ 에 설치 후 update-ca-trust"
    else
        warn "알 수 없는 CA가 인증서를 발급함 — 위 Issuer를 보안팀에 확인 요청"
    fi
fi

# ─────────────────────────────────────────────────────────────
# [4] HTTPS 접속 테스트 (인증 없이)
# ─────────────────────────────────────────────────────────────
section "[4] HTTPS 접속 테스트"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 10 \
    "https://${PRIMARY_HOST}/v1beta/models" 2>/dev/null)

case "$HTTP_CODE" in
    401|403)
        pass "HTTP $HTTP_CODE — 네트워크 정상 (인증만 필요한 상태)"
        ;;
    200)
        pass "HTTP 200 — 정상 응답"
        ;;
    000)
        fail "HTTP 000 — 연결 자체가 안 됨 (타임아웃/SSL 에러/프록시 문제)"
        echo ""
        info "상세 진단:"
        curl -v --max-time 10 "https://${PRIMARY_HOST}/v1beta/models" 2>&1 \
            | grep -E '^\*|curl:' | head -10 | sed 's/^/    /'
        ;;
    *)
        warn "HTTP $HTTP_CODE — 예상과 다른 응답 코드"
        ;;
esac

# ─────────────────────────────────────────────────────────────
# [5] 프록시 환경변수 점검
# ─────────────────────────────────────────────────────────────
section "[5] 프록시 환경 점검"

PROXY_VARS=$(env | grep -iE '^(http_proxy|https_proxy|no_proxy|all_proxy)=' || true)
if [ -n "$PROXY_VARS" ]; then
    info "환경변수에 프록시 설정됨:"
    echo "$PROXY_VARS" | sed 's/^/    /'
else
    info "환경변수 프록시 설정 없음"
fi

# 시스템 전역 프록시
if [ -f /etc/environment ]; then
    SYSTEM_PROXY=$(grep -iE 'proxy' /etc/environment 2>/dev/null || true)
    if [ -n "$SYSTEM_PROXY" ]; then
        info "/etc/environment 프록시 설정:"
        echo "$SYSTEM_PROXY" | sed 's/^/    /'
    fi
fi

# yum 프록시
if [ -f /etc/yum.conf ]; then
    YUM_PROXY=$(grep -i '^proxy' /etc/yum.conf 2>/dev/null || true)
    if [ -n "$YUM_PROXY" ]; then
        info "yum 프록시 (네트워크 정책 참고):"
        echo "$YUM_PROXY" | sed 's/^/    /'
    fi
fi

# ─────────────────────────────────────────────────────────────
# [6] 로컬 방화벽 / SELinux
# ─────────────────────────────────────────────────────────────
section "[6] 로컬 방화벽 / SELinux"

# firewalld
if command -v firewall-cmd >/dev/null 2>&1; then
    FW_STATE=$(sudo -n firewall-cmd --state 2>/dev/null || firewall-cmd --state 2>/dev/null)
    if [ "$FW_STATE" = "running" ]; then
        info "firewalld: running"
        info "    활성 영역: $(sudo -n firewall-cmd --get-active-zones 2>/dev/null | head -1 || echo 'N/A (sudo 필요)')"
    else
        info "firewalld: ${FW_STATE:-not running}"
    fi
else
    info "firewalld: 미설치"
fi

# iptables OUTPUT 정책 (sudo 필요)
if command -v iptables >/dev/null 2>&1; then
    OUTPUT_POLICY=$(sudo -n iptables -L OUTPUT -n 2>/dev/null | head -1 || echo "")
    if [ -n "$OUTPUT_POLICY" ]; then
        info "iptables OUTPUT: $OUTPUT_POLICY"
        DROP_RULES=$(sudo -n iptables -L OUTPUT -n 2>/dev/null | grep -cE '^DROP|^REJECT' || echo 0)
        if [ "$DROP_RULES" -gt 0 ]; then
            warn "OUTPUT 체인에 DROP/REJECT 규칙 $DROP_RULES 개 존재 — 외부 연결 차단 가능성"
        fi
    else
        info "iptables: sudo 권한 없음 (점검 스킵)"
    fi
fi

# SELinux
if command -v getenforce >/dev/null 2>&1; then
    SELINUX_STATE=$(getenforce 2>/dev/null)
    info "SELinux: $SELINUX_STATE"
    if [ "$SELINUX_STATE" = "Enforcing" ]; then
        # 최근 1시간 내 denied 로그
        DENIED=$(sudo -n grep -c "denied" /var/log/audit/audit.log 2>/dev/null || echo 0)
        if [ "$DENIED" != "0" ] && [ "$DENIED" != "" ]; then
            warn "audit.log에 denied 항목 $DENIED 건 — 네트워크 관련이면 httpd_can_network_connect 확인"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────
# [7] 실제 Gemini API 호출 테스트 (API Key 있을 때만)
# ─────────────────────────────────────────────────────────────
section "[7] 실제 Gemini API 호출 테스트"

# .env 로드
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
GOOGLE_API_KEY=""

if [ -f "$ENV_FILE" ]; then
    # GOOGLE_API_KEY 추출 (따옴표 제거)
    GOOGLE_API_KEY=$(grep -E '^GOOGLE_API_KEY=' "$ENV_FILE" 2>/dev/null \
        | tail -1 \
        | sed -E "s/^GOOGLE_API_KEY=['\"]?([^'\"]*)['\"]?$/\1/")
fi

if [ -z "$GOOGLE_API_KEY" ]; then
    info ".env 에서 GOOGLE_API_KEY 를 찾지 못함 — 실제 호출 스킵"
    info "대응: 수동 테스트 시 GOOGLE_API_KEY=xxx bash $0"
else
    MODEL="gemini-2.5-flash-lite"
    API_URL="https://${PRIMARY_HOST}/v1beta/models/${MODEL}:generateContent?key=${GOOGLE_API_KEY}"

    RESPONSE=$(curl -s --max-time 30 -w "\n__HTTP_CODE__%{http_code}" \
        -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d '{"contents":[{"parts":[{"text":"핑 테스트"}]}]}' 2>&1)

    API_HTTP_CODE=$(echo "$RESPONSE" | grep -oE '__HTTP_CODE__[0-9]+$' | sed 's/__HTTP_CODE__//')
    API_BODY=$(echo "$RESPONSE" | sed 's/__HTTP_CODE__[0-9]*$//')

    case "$API_HTTP_CODE" in
        200)
            pass "Gemini API 호출 성공 (HTTP 200)"
            SNIPPET=$(echo "$API_BODY" | grep -oE '"text":\s*"[^"]*"' | head -1 | cut -c1-80)
            [ -n "$SNIPPET" ] && info "응답 일부: $SNIPPET..."
            ;;
        400)
            warn "HTTP 400 — API Key 형식 오류"
            ;;
        403)
            warn "HTTP 403 — API Key 권한 거부 (IP 제한 또는 키 만료)"
            info "대응: Google Cloud Console에서 API Key 제한 사항 확인"
            ;;
        429)
            warn "HTTP 429 — 쿼터 초과 (하지만 네트워크는 정상)"
            ;;
        000|"")
            fail "연결 실패 — 네트워크/TLS 레이어 문제"
            ;;
        *)
            warn "HTTP $API_HTTP_CODE — 예상 외 응답"
            echo "$API_BODY" | head -5 | sed 's/^/    /'
            ;;
    esac
fi

# ─────────────────────────────────────────────────────────────
# 최종 결과 요약
# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══ 최종 결과 ═══${RESET}"
echo -e "  ${GREEN}통과:${RESET} $PASS_COUNT"
echo -e "  ${YELLOW}경고:${RESET} $WARN_COUNT"
echo -e "  ${RED}실패:${RESET} $FAIL_COUNT"
echo ""

if [ $FAIL_COUNT -eq 0 ] && [ $WARN_COUNT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✅ 전체 점검 통과 — Gemini API 사용 가능${RESET}"
    exit 0
elif [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${YELLOW}${BOLD}⚠  실패는 없으나 경고가 있습니다 — 경고 항목 검토 후 운영 반영 권장${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}❌ 실패 항목이 있습니다 — 보안팀/네트워크팀 협의 필요${RESET}"
    echo ""
    echo "제출용 요약:"
    echo "  - 점검 일시: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  - 서버: $(hostname) ($(hostname -I 2>/dev/null | awk '{print $1}'))"
    echo "  - 요청 허용 도메인: $HOSTS"
    echo "  - 요청 포트: 443/TCP (HTTPS)"
    echo "  - 비고: 도메인 기반 화이트리스트 필수 (IP 기반 불가 — Google Anycast)"
    exit 1
fi