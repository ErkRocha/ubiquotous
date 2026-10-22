FROM rust:1-slim-bookworm AS build

WORKDIR /src

# Compila as dependências numa camada separada (cache entre builds)
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release && rm -rf src

COPY src ./src
RUN touch src/main.rs && cargo build --release

FROM debian:bookworm-slim

COPY --from=build /src/target/release/api-rust /api

EXPOSE 8000
CMD ["/api"]
