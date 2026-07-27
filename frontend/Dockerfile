# ============ 构建阶段 ============
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package.json ./
RUN npm install --registry=https://registry.npmmirror.com

# 构建
COPY . .
RUN npm run build

# ============ 生产阶段 ============
FROM nginx:1.27-alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
