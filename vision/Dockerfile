# Python 3.11 for tflite-runtime wheel (Edge TPU delegate); 3.12 has no official wheel

###############################################################################
# Stage 1: Build libusb 1.0.26 WITHOUT udev support.
# Inside Docker containers udev is not running; the stock libusb relies on it
# for USB device lifecycle events and will intermittently fail with
# LIBUSB_TRANSFER_NO_DEVICE (error 5) during bulk transfers.
# Frigate NVR uses the same approach:
#   https://github.com/blakeblackshear/frigate/blob/dev/docker/main/Dockerfile
###############################################################################
FROM python:3.11-slim AS libusb-no-udev
ARG LIBUSB_VERSION=v1.0.26
ARG LIBUSB_SHA256=4175f942e74f3c34b71d01b107d33e713f9ff47563f49bcc6e8b2534f414dd54
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential automake libtool pkg-config wget unzip \
    && rm -rf /var/lib/apt/lists/*
RUN wget -q "https://github.com/libusb/libusb/archive/${LIBUSB_VERSION}.zip" -O /tmp/libusb.zip \
    && echo "${LIBUSB_SHA256}  /tmp/libusb.zip" | sha256sum -c - \
    && cd /tmp && unzip libusb.zip \
    && cd "libusb-${LIBUSB_VERSION#v}" \
    && ./bootstrap.sh \
    && ./configure --disable-udev --enable-shared --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install

###############################################################################
# Stage 2: Vision runtime
###############################################################################
FROM python:3.11-slim
ARG LIBEDGETPU_VERSION=16.0TF2.17.1-1
ARG LIBEDGETPU_SHA256=23f33972026fbba37f52283b0314cf30f815aeebd254f20bf843bbad72b06f4d
ARG TFLITE_RUNTIME_VERSION=2.17.1
ARG TFLITE_RUNTIME_SHA256=5983bc00bc47d86a6a39f258ad07b69bd4d9fd61703535b10347c13f6901eb05

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Overlay custom libusb (no-udev).  Only copy the .so files -- the build stage
# shares the same base image and /usr/local/lib/ also contains Python itself.
COPY --from=libusb-no-udev /usr/local/lib/libusb-1.0.so* /usr/local/lib/

# Coral Edge TPU runtime -- feranick's fork compiled against TF 2.17.1.
# The official Google libedgetpu from coral-edgetpu-stable (RuntimeVersion 14, TF 2.5 era)
# is INCOMPATIBLE with tflite_runtime >= 2.12: the delegate loads but silently fails to
# handle custom ops at invoke() time.  See https://github.com/google-coral/edgetpu/issues/812
# Using libedgetpu1-max (same as Frigate) for full Edge TPU clock speed.
# python:3.11-slim is now based on Debian trixie; use matching deb.
# dpkg -x extracts files without running maintainer scripts (avoids EULA prompt
# that fails in Docker where no debconf frontend is available).
RUN curl -sSL -o /tmp/libedgetpu.deb \
         "https://github.com/feranick/libedgetpu/releases/download/${LIBEDGETPU_VERSION}/libedgetpu1-max_16.0tf2.17.1-1.trixie_amd64.deb" \
    && echo "${LIBEDGETPU_SHA256}  /tmp/libedgetpu.deb" | sha256sum -c - \
    && dpkg -x /tmp/libedgetpu.deb / \
    && rm /tmp/libedgetpu.deb

# Ensure the no-udev libusb is found before the system one
RUN ldconfig

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# tflite_runtime with Edge TPU support: feranick wheel for amd64 (v2.17.1; v2.18.0 has no linux_x86_64 wheel), PyPI for other arches
RUN arch=$(dpkg --print-architecture 2>/dev/null || echo ""); \
    if [ "$arch" = "amd64" ]; then \
      curl -fsSLo /tmp/tflite_runtime.whl "https://github.com/feranick/TFlite-builds/releases/download/v${TFLITE_RUNTIME_VERSION}/tflite_runtime-${TFLITE_RUNTIME_VERSION}-cp311-cp311-linux_x86_64.whl" \
      && echo "${TFLITE_RUNTIME_SHA256}  /tmp/tflite_runtime.whl" | sha256sum -c - \
      && pip install --no-cache-dir /tmp/tflite_runtime.whl \
      && rm /tmp/tflite_runtime.whl; \
    else \
      pip install --no-cache-dir "tflite-runtime==2.18.0"; \
    fi
COPY . .
RUN mkdir -p /app/data /app/models

ENV PYTHONUNBUFFERED=1
# Force the no-udev libusb for every process (libedgetpu, probe subprocess, etc.).
# Without this, the system libusb (pulled as transitive dep by ffmpeg/curl) in
# /usr/lib/x86_64-linux-gnu/ takes precedence and crashes with USB error 5.
ENV LD_PRELOAD=/usr/local/lib/libusb-1.0.so.0
# Suppress noisy TFLite / GLOG native logs (same as Frigate).
ENV TF_CPP_MIN_LOG_LEVEL=3
ENV GLOG_minloglevel=2

EXPOSE 9000
ENV PYTHONPATH=/app
CMD ["python", "main.py"]
