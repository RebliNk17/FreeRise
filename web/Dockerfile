FROM oven/bun:1.4.4
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# next.config.ts resolves the /api rewrite at build time, so API_URL must be known here.
ARG API_URL=http://localhost:8000
ENV API_URL=$API_URL NEXT_TELEMETRY_DISABLED=1 TZ=Asia/Jerusalem
RUN bun run build
CMD ["sh", "-c", "exec bun run start -H 0.0.0.0 -p ${PORT:-3000}"]
