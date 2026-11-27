FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -o /erp-server ./cmd/erp-server

FROM alpine:3.20
RUN adduser -D -u 10001 erpuser && mkdir -p /data && chown -R erpuser:erpuser /data
USER erpuser
COPY --from=builder /erp-server /erp-server
EXPOSE 8080
ENTRYPOINT ["/erp-server"]
