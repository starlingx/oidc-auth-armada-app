FROM golang:latest as builder
WORKDIR /app
ADD . /app/
RUN go mod download

ENV CGO_ENABLED=0
RUN go build --ldflags '-extldflags "-static"' -o stx-oidc-client .

RUN go version > go.version.txt
RUN find /go -type f > go.dl.txt

FROM scratch

WORKDIR /app
COPY --from=builder /app ./

EXPOSE 5555
CMD ["./stx-oidc-client"]
