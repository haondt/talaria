FROM python:3.13.2-alpine

WORKDIR /app

RUN apk add \
    git \
    skopeo


RUN addgroup -S talaria && adduser -S talaria -G talaria

COPY --chown=talaria:talaria requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=talaria:talaria app /app/app

USER talaria
ENTRYPOINT ["python", "-m", "app"]

