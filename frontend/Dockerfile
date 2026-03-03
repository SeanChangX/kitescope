FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ENV VITE_API_URL=/api
ARG VITE_PREVIEW_INTERVAL_MS
ARG VITE_PREVIEW_STAGGER_MS
ENV VITE_PREVIEW_INTERVAL_MS=$VITE_PREVIEW_INTERVAL_MS
ENV VITE_PREVIEW_STAGGER_MS=$VITE_PREVIEW_STAGGER_MS
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
