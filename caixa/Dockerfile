FROM nginx:alpine
ENV FRONTEND_PORT=3000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY public/ /usr/share/nginx/html/
