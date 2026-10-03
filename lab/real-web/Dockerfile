# Real host: a genuine nginx web server (HANDOVER §7.1, Module 1).
FROM nginx:1.24-alpine

RUN printf '<!doctype html><html><head><title>web-front-01</title></head>' \
    > /usr/share/nginx/html/index.html \
 && printf '<body><h1>web-front-01</h1><p>It works.</p></body></html>' \
    >> /usr/share/nginx/html/index.html

EXPOSE 80
# nginx:alpine's default CMD already runs nginx in the foreground.
