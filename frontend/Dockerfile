# ─── Frontend (Next.js) Dockerfile ───
FROM node:20-alpine AS base

# 1. 의존성 설치
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 2. 소스 코드 빌드
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED 1
RUN npm run build

# 3. 배포용 최적화 스테이지 (Standalone)
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Standalone 빌드 결과물 복사 (권장 최적화 방식)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT 3000
# 서버 주소 (배포 환경에 맞게 백엔드 API 주소 설정)
ENV NEXT_PUBLIC_API_BASE_URL http://localhost:8000

CMD ["node", "server.js"]
