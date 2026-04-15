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

# NEXT_PUBLIC_* 변수는 빌드 타임에 번들로 인라이닝됨.
# 배포 시 반드시 --build-arg NEXT_PUBLIC_API_BASE_URL=https://... 로 주입할 것.
# 기본값은 로컬 개발 편의용이며 운영 빌드에서 절대 사용 금지.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

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
# NEXT_PUBLIC_API_BASE_URL은 builder 스테이지에서 번들에 이미 인라이닝되었으므로
# runner 스테이지에서 ENV로 다시 설정해도 클라이언트 JS에는 반영되지 않음.
# (서버 사이드 런타임 참조용으로만 필요한 경우 --build-arg 또는 docker run -e 사용)

CMD ["node", "server.js"]
