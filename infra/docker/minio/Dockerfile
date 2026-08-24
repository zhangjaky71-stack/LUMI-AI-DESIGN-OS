FROM golang:1.24-bookworm AS builder

ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
ENV CGO_ENABLED=0

RUN mkdir -p /out && GOBIN=/out go install "github.com/minio/minio@${MINIO_RELEASE}"

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -S -g 10001 minio \
    && adduser -S -D -H -u 10001 -G minio minio \
    && mkdir -p /data \
    && chown minio:minio /data
COPY --from=builder /out/minio /usr/local/bin/minio

EXPOSE 9000 9001
VOLUME ["/data"]
USER minio
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
