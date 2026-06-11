FROM golang:latest AS builder
WORKDIR /app
ADD . /app/
RUN go mod download
RUN go mod tidy

ENV CGO_ENABLED=0
RUN go build --ldflags '-extldflags "-static"' -o stx-oidc-client .

RUN go version > go.version.txt
RUN find /go -type f > go.dl.txt

FROM scratch

WORKDIR /app
COPY --from=builder /app ./

EXPOSE 5555
CMD ["./stx-oidc-client"]
