#!/usr/bin/env bash
#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

set -ex

IMAGE=$1
IMAGE_TAG=$2
WORKDIR=$(pwd)

# Build using a custom multi-stage Dockerfile
# Stage 1: build binary using official golang image
# Stage 2: copy binary to distroless runtime image
DOCKER_CTX="${WORKDIR}/../oauth2-proxy-docker-ctx"
mkdir -p "${DOCKER_CTX}"
cp -r "${WORKDIR}"/* "${DOCKER_CTX}/" 2>/dev/null || true

DOCKERFILE="${DOCKER_CTX}/Dockerfile.stx"
PROXY_PKG="github.com/oauth2-proxy/oauth2-proxy/v7"
BUILDER_WD="/go/src/github.com/oauth2-proxy/oauth2-proxy"
VERSION="v7.15.2"

{
    echo "FROM golang:1.25-bookworm AS builder"
    echo "WORKDIR ${BUILDER_WD}"
    echo "COPY go.mod go.sum ./"
    echo "RUN go mod download"
    echo "COPY . ."
    echo "ENV CGO_ENABLED=0"
    echo "RUN go build \\"
    echo "    -ldflags=\"-X ${PROXY_PKG}/pkg/version.VERSION=${VERSION}\" \\"
    echo "    -o oauth2-proxy ${PROXY_PKG}"
    echo "FROM gcr.io/distroless/static:nonroot"
    echo "COPY --from=builder ${BUILDER_WD}/oauth2-proxy \\"
    echo "    /bin/oauth2-proxy"
    echo "ENTRYPOINT [\"/bin/oauth2-proxy\"]"
} > "${DOCKERFILE}"

docker build \
    -t "${IMAGE_TAG}" \
    -f "${DOCKERFILE}" \
    "${DOCKER_CTX}"
echo "Docker image ${IMAGE_TAG} built successfully"

