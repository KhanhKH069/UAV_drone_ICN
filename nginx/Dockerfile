FROM nginx:alpine
RUN apk add --no-cache openssl
RUN mkdir -p /etc/nginx/ssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx-selfsigned.key \
    -out /etc/nginx/ssl/nginx-selfsigned.crt \
    -subj "/C=VN/ST=Hanoi/L=Hanoi/O=Paraline/OU=Drone/CN=localhost"
COPY nginx.conf /etc/nginx/nginx.conf
