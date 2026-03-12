<p align="right"><a href="README.zh-TW.md">繁體中文</a></p>

<div align="center">

# KiteScope

**Real-time kite monitoring: when2fly, where2fly.**

[![GitHub stars](https://img.shields.io/github/stars/SeanChangX/KiteScope)](https://github.com/SeanChangX/KiteScope) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Web](https://img.shields.io/badge/Web-kitescope.labxcloud.com-purple.svg)](https://kitescope.labxcloud.com)

<img src="docs/images/KiteScope_title.png" alt="KiteScope logo" width="200" style="display: block; margin: 0.5em auto;">

<table>
<tr>
<td width="50%" align="center"><img src="docs/images/Dashboard.png" alt="Dashboard" width="100%"><br><strong>Dashboard</strong><br>Stream cards, live count, suggest a source</td>
<td width="50%" align="center"><img src="docs/images/Notifications.png" alt="Notifications" width="100%"><br><strong>Notifications</strong><br>Subscriptions per source, threshold, channel</td>
</tr>
<tr>
<td width="50%" align="center"><img src="docs/images/AdminDashboard.png" alt="Admin Dashboard" width="100%"><br><strong>Admin — Dashboard</strong><br>Pending sources, broadcast</td>
<td width="50%" align="center"><img src="docs/images/AdminSources.png" alt="Admin Sources" width="100%"><br><strong>Admin — Sources</strong><br>Source list, manage streams</td>
</tr>
</table>

<br>

<div align="center">

[**Features**](#features) &#8226;
[**Getting Started**](#getting-started) &#8226;
[**Stream sources**](#stream-sources) &#8226;
[**Detection model**](#detection-model) &#8226;
[**Notifications**](#notifications) &#8226;
[**Development**](#development)

</div>

</div>

---

## Features

Every time you want to fly, you check the weather and wind, drive to the beach—and the wind’s gone. If someone’s already flying, you know it’s flyable. KiteScope watches live video from various streaming platforms, detects how many kites are in the frame, and when the count hits your threshold, notifies you via LINE or Telegram.

<p align="right">— Made by SCX, a robotics nerd who loves stunt kites.</p>

---

## Getting started

### Prerequisites

- Docker and Docker Compose
- (Optional) LINE Channel and/or Telegram Bot for login and notifications

### Run with Docker

1. Clone and enter the repo:
   ```bash
   git clone https://github.com/SeanChangX/KiteScope.git
   cd KiteScope
   ```

2. Copy the example env file and edit if needed:
   ```bash
   cp env.example .env
   ```

3. Start all services:
   ```bash
   docker compose up -d
   ```

4. **Set the admin password first.** Open **http://localhost:3000/admin**. If no admin exists yet, the app shows a setup form: choose a username and password and submit. Then log in with those credentials. All other use (sources, bots, users) depends on having an admin account.

5. Use the app:
   - **http://localhost:3000** — Dashboard (streams and counts), suggest a source, link to History and Notifications.
   - **http://localhost:3000/login** — Sign in with LINE or Telegram.
   - **http://localhost:3000/notifications** — Manage your alert subscriptions (after login).

---

## System architecture

```
[ Browser ] ---- [ Frontend ] ---- [ Backend ]
                     |                  |
                     |   Auth, DB, notification worker
                     |
[ go2rtc ] ---- [ Vision: ingest + detect ] ---- counts + frames
```

Docker runs four services: **frontend** (port 3000), **backend**, **vision**, and **go2rtc**. Data is stored in a single SQLite volume; the detection model is in a separate volume or uploaded via the admin UI.

---

## Stream sources

Sources are added by an admin (or approved from user suggestions). You provide a URL and optional location (for weather in notifications). The system detects the type from the URL.

| Type | Description |
|------|-------------|
| **HTTP snapshot** | A single image URL (JPEG/PNG). |
| **MJPEG** | MJPEG stream URL. |
| **RTSP** | `rtsp://` URL. |
| **go2rtc** | Stream added in go2rtc (container on port 1984). Use the go2rtc snapshot or stream URL. |
| **YouTube Live** | `youtube.com` / `youtu.be` live URLs. Servers may be rate-limited by YouTube. |

Credentials stay on the backend and are not exposed to the frontend.

---

## Detection model

The vision service needs a detection model to report kite counts. Without a model, counts stay at 0.

- **CPU path (default)**: upload an **ONNX** model where **class 0 is kite** (e.g. YOLOv8 trained on a kite dataset and exported to ONNX).  
- **Coral Edge TPU (optional)**: upload a **TFLite model compiled for Edge TPU** (INT8, via `edgetpu_compiler`). When a `.tflite` model is selected and a Coral TPU is available, inference runs on the TPU.

In the admin UI go to **Settings → Model settings**: upload the model file (.onnx for CPU, .tflite for Coral) or place it in the vision model volume and select it there. Confidence and other options can be set in the same page.

### Coral Edge TPU (optional)

KiteScope can offload detection to a Google Coral Edge TPU:

- **Model**: use a YOLO-style TFLite model compiled for Edge TPU where **class 0 is kite**.
- **Docker mapping** (USB Coral example, vision service):
  - Uncomment in `docker-compose.yml` / `docker-compose.dev.yml`:
    - `- /dev/bus/usb:/dev/bus/usb`
- **Environment**:
  - `DETECT_DEVICE=auto` (default): use Coral when detected, otherwise CPU.
  - `DETECT_DEVICE=cpu`: force CPU ONNX backend.
  - `DETECT_DEVICE=edgetpu`: force Coral (falls back to CPU if no TPU).
- **PyCoral**:
  - Install in the vision image or environment:
    ```bash
    pip install pycoral
    ```
  - If `pycoral` is not installed, the vision service automatically falls back to CPU (ONNX) even if a TPU is present.

To confirm which backend is used, open **Admin → Dashboard** and check the **System status** card: it shows whether the detector is running on **CPU (ONNX)** or **Coral Edge TPU**, and whether a TPU was detected.

---

## Notifications

Users subscribe per source: threshold, optional release threshold (hysteresis), channel (LINE or Telegram), and cooldown. When the smoothed count reaches the threshold and stays above until the release level, one notification is sent (count, weather for the source location, and a snapshot on Telegram). LINE and Telegram credentials are configured in **Admin → Settings → Bot settings**. Admins can also send a one-off broadcast to all or selected users from the admin dashboard.

---

## Development

Use the dev Compose file for local work with hot reload:

```bash
docker compose -f docker-compose.dev.yml up
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Vision | http://localhost:9000 |
| go2rtc | http://localhost:1984 |

The frontend dev server proxies `/api` to the backend. For LINE or Telegram login locally, expose the app via a tunnel (e.g. ngrok or cloudflared) and set the callback/domain to that URL.

---

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT) - see the [LICENSE](LICENSE) file for details.

____
