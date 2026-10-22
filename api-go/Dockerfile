FROM golang:1.24-alpine AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY *.go ./
RUN CGO_ENABLED=0 go build -o /api .

FROM alpine:3.21

COPY --from=build /api /api

EXPOSE 8000
CMD ["/api"]
