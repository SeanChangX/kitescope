#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="kitescope-edgetpu-compiler:latest"
SCRIPT_NAME="$(basename "$0")"
COLOR_RESET=$'\033[0m'
COLOR_DIM=$'\033[2m'
COLOR_BLUE=$'\033[34m'
COLOR_CYAN=$'\033[36m'
COLOR_GREEN=$'\033[32m'
COLOR_YELLOW=$'\033[33m'
COLOR_RED=$'\033[31m'

print_line() {
  printf '%s\n' "============================================================"
}

print_banner() {
  print_line
  printf '%b\n' "${COLOR_CYAN}  Coral Edge TPU Compiler Helper${COLOR_RESET}"
  printf '%b\n' "${COLOR_DIM}  Build once with Docker, compile any int8 TFLite model${COLOR_RESET}"
  print_line
}

print_step() {
  printf '%b\n' "${COLOR_BLUE}[STEP]${COLOR_RESET} $1"
}

print_info() {
  printf '%b\n' "${COLOR_CYAN}[INFO]${COLOR_RESET} $1"
}

print_warn() {
  printf '%b\n' "${COLOR_YELLOW}[WARN]${COLOR_RESET} $1"
}

print_error() {
  printf '%b\n' "${COLOR_RED}[ERROR]${COLOR_RESET} $1" >&2
}

print_success() {
  printf '%b\n' "${COLOR_GREEN}[DONE]${COLOR_RESET} $1"
}

confirm() {
  local prompt="$1"
  local reply
  read -r -p "$prompt [y/N]: " reply || true
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

usage() {
  print_banner
  echo "Usage:"
  echo "  $SCRIPT_NAME /absolute/or/relative/path/to/model_int8.tflite"
  echo
  echo "Example:"
  echo "  $SCRIPT_NAME ./train3_kite_int8.tflite"
  exit 1
}

if [[ $# -ne 1 ]]; then
  usage
fi

print_banner

if ! command -v docker >/dev/null 2>&1; then
  print_error "docker is required but was not found in PATH."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  print_error "python3 is required but was not found in PATH."
  exit 1
fi

INPUT_PATH="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")"

if [[ ! -f "$INPUT_PATH" ]]; then
  print_error "input model not found: $INPUT_PATH"
  exit 1
fi

if [[ "${INPUT_PATH##*.}" != "tflite" ]]; then
  print_error "input file must be a .tflite model."
  exit 1
fi

MODEL_DIR="$(dirname "$INPUT_PATH")"
MODEL_FILE="$(basename "$INPUT_PATH")"
OUTPUT_FILE="${MODEL_FILE%.tflite}_edgetpu.tflite"

print_info "Input model : $INPUT_PATH"
print_info "Output model: $MODEL_DIR/$OUTPUT_FILE"
echo

# Build a reusable compiler image on first use so later runs are fast.
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  print_warn "Compiler image not found locally: $IMAGE_NAME"
  if ! confirm "Build the Docker image now?"; then
    print_error "aborted by user."
    exit 1
  fi

  print_step "Building reusable compiler image"
  BUILD_DIR="$(mktemp -d)"
  trap 'rm -rf "$BUILD_DIR"' EXIT
  cat > "$BUILD_DIR/Dockerfile" <<'EOF'
FROM ubuntu:22.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/coral-edgetpu.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/coral-edgetpu.gpg] https://packages.cloud.google.com/apt coral-edgetpu-stable main" > /etc/apt/sources.list.d/coral-edgetpu.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends edgetpu-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
EOF
  docker build -t "$IMAGE_NAME" "$BUILD_DIR"
  print_success "Docker image is ready."
else
  print_step "Using existing compiler image"
  print_info "$IMAGE_NAME"
fi

echo
print_step "Compiling model with Edge TPU compiler"
docker run --rm \
  -v "$MODEL_DIR:/work" \
  "$IMAGE_NAME" \
  edgetpu_compiler "/work/$MODEL_FILE"

echo
print_line
print_success "Compilation finished."
print_info "Compiled model: $MODEL_DIR/$OUTPUT_FILE"
print_info "Compiler log : $MODEL_DIR/${MODEL_FILE%.tflite}_edgetpu.log"
print_line
