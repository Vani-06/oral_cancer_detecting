# Static frontend served by nginx. Build from the repository root:
#   docker build -f deploy/web.Dockerfile --build-arg VITE_API_BASE_URL=https://api.example -t oralsentinel-web .
FROM node:22-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} VITE_USE_MOCKS=false
RUN test -n "$VITE_API_BASE_URL" && npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
