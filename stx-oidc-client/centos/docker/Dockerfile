FROM golang:latest
WORKDIR /app
ADD . /app/
RUN go get -d -v ./...
RUN go build -o stx-oidc-client .

EXPOSE 5555
CMD ["./stx-oidc-client"]
