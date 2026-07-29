FROM otel/opentelemetry-collector-contrib:0.132.0 AS collector

FROM alpine:3.22.1

RUN apk add --no-cache wget \
    && addgroup -S -g 10001 otel \
    && adduser -S -D -H -u 10001 -G otel otel

COPY --from=collector --chown=otel:otel /otelcol-contrib /otelcol-contrib

USER 10001:10001
ENTRYPOINT ["/otelcol-contrib"]
