FROM golang:latest
WORKDIR /app
ADD . /app/
RUN go mod download
RUN go build -o stx-oidc-client .

EXPOSE 5555
CMD ["./stx-oidc-client"]
