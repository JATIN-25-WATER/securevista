"""
backend/services/telegram_service.py

Service for routing security alert notifications to 3 separate Telegram bots:
- Dashboard 1 / Operator 1 (Camera 1) -> TELEGRAM_BOT_1_TOKEN & TELEGRAM_CHAT_1_ID
- Dashboard 2 / Operator 2 (Camera 2) -> TELEGRAM_BOT_2_TOKEN & TELEGRAM_CHAT_2_ID
- Dashboard 3 / Operator 3 (Camera 3) -> TELEGRAM_BOT_3_TOKEN & TELEGRAM_CHAT_3_ID

All network calls are executed in a non-blocking threadpool to prevent any impact
on real-time camera detection, SQLite writes, or WebSocket UI streaming.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv

# Load .env file from project root if available
load_dotenv()

logger = logging.getLogger(__name__)

# Dedicated thread pool for non-blocking Telegram API requests
_telegram_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram_notify")


class TelegramNotifier:
    _instance = None

    def __init__(self):
        self._load_config()

    @classmethod
    def get_instance(cls) -> "TelegramNotifier":
        if cls._instance is None:
            cls._instance = TelegramNotifier()
        return cls._instance

    def _load_config(self):
        """Reload configuration from environment variables."""
        self.bot_configs = {
            1: {
                "name": "Dashboard 1 (Operator 1)",
                "token": os.getenv("TELEGRAM_BOT_1_TOKEN", "").strip(),
                "chat_id": os.getenv("TELEGRAM_CHAT_1_ID", "").strip(),
            },
            2: {
                "name": "Dashboard 2 (Operator 2)",
                "token": os.getenv("TELEGRAM_BOT_2_TOKEN", "").strip(),
                "chat_id": os.getenv("TELEGRAM_CHAT_2_ID", "").strip(),
            },
            3: {
                "name": "Dashboard 3 (Operator 3)",
                "token": os.getenv("TELEGRAM_BOT_3_TOKEN", "").strip(),
                "chat_id": os.getenv("TELEGRAM_CHAT_3_ID", "").strip(),
            },
        }

    def format_alert_message(self, alert_data: Dict[str, Any]) -> str:
        """Format existing alert object into a clean Telegram notification."""
        camera_id = alert_data.get("camera_id", 1)
        camera_name = alert_data.get("camera_name", f"Camera {camera_id}")
        raw_event = str(alert_data.get("event_type", "SECURITY ALERT")).upper().replace("_", " ")
        explanation = alert_data.get("explanation", "Security condition detected.")
        confidence = alert_data.get("confidence_score")
        conf_str = f"{int(confidence * 100)}%" if isinstance(confidence, (int, float)) else "N/A"
        impact = alert_data.get("impact_score", 0.8)
        severity = "CRITICAL" if impact >= 0.8 else "HIGH" if impact >= 0.5 else "MEDIUM"
        
        # Timestamp formatting
        ts_raw = alert_data.get("timestamp")
        time_str = datetime.utcnow().strftime("%H:%M:%S UTC")
        if ts_raw:
            try:
                dt = datetime.fromisoformat(ts_raw.replace("Z", ""))
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = str(ts_raw)

        msg = (
            f"🚨 *SECURITY ALERT*\n\n"
            f"📍 *Dashboard:* Dashboard {camera_id} (Operator {camera_id})\n"
            f"📹 *Camera:* {camera_name} (ID: {camera_id})\n"
            f"⚠️ *Event:* {raw_event}\n"
            f"🔴 *Severity:* {severity}\n"
            f"🎯 *Confidence:* {conf_str}\n"
            f"🕒 *Time:* `{time_str}`\n\n"
            f"ℹ️ *Details:* {explanation}"
        )
        return msg

    def _send_http_request(self, token: str, chat_id: str, message_text: str) -> Dict[str, Any]:
        """Synchronous HTTP call to Telegram Bot API (executed inside ThreadPool)."""
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "Markdown",
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    logger.info("Telegram message successfully sent to chat_id=%s", chat_id)
                    return {"status": "success", "response": response.json()}
                else:
                    err_msg = f"Telegram API HTTP {response.status_code}: {response.text}"
                    logger.error(err_msg)
                    return {"status": "error", "detail": err_msg}
        except Exception as exc:
            err_msg = f"Telegram network request failed: {exc}"
            logger.error(err_msg)
            return {"status": "error", "detail": err_msg}

    def send_alert_notification(self, alert_data: Dict[str, Any]):
        """
        Main non-blocking entry point for sending alert notifications to the
        bot corresponding to alert_data['camera_id'].
        """
        self._load_config()  # Ensure latest env vars are loaded
        camera_id = int(alert_data.get("camera_id", 1))
        
        # Route to Bot 1, 2, or 3 based on camera_id
        bot_cfg = self.bot_configs.get(camera_id, self.bot_configs[1])
        token = bot_cfg["token"]
        chat_id = bot_cfg["chat_id"]

        if not token or not chat_id:
            logger.warning(
                "Telegram notification skipped for Dashboard %d: "
                "TELEGRAM_BOT_%d_TOKEN or TELEGRAM_CHAT_%d_ID is missing.",
                camera_id, camera_id, camera_id
            )
            return

        message_text = self.format_alert_message(alert_data)
        # Dispatch to background threadpool to ensure non-blocking operation
        _telegram_executor.submit(self._send_http_request, token, chat_id, message_text)

    def send_test_notification(self, dashboard_id: int) -> Dict[str, Any]:
        """
        Manually trigger a test alert for Dashboard 1, 2, or 3.
        Returns immediate status information for debugging.
        """
        self._load_config()
        if dashboard_id not in (1, 2, 3):
            return {"status": "error", "detail": "dashboard_id must be 1, 2, or 3"}

        bot_cfg = self.bot_configs[dashboard_id]
        token = bot_cfg["token"]
        chat_id = bot_cfg["chat_id"]

        if not token:
            return {
                "status": "missing_config",
                "dashboard_id": dashboard_id,
                "detail": f"TELEGRAM_BOT_{dashboard_id}_TOKEN environment variable is not set.",
            }

        if not chat_id:
            return {
                "status": "missing_config",
                "dashboard_id": dashboard_id,
                "detail": f"TELEGRAM_CHAT_{dashboard_id}_ID environment variable is not set.",
            }

        test_alert = {
            "camera_id": dashboard_id,
            "camera_name": f"Camera {dashboard_id} (Webcam)",
            "event_type": "TEST_ALERT_TRIGGERED",
            "explanation": f"Manual test alert issued for Dashboard {dashboard_id} / Bot {dashboard_id}.",
            "confidence_score": 0.99,
            "impact_score": 0.9,
            "timestamp": datetime.utcnow().isoformat(),
        }

        message_text = self.format_alert_message(test_alert)
        result = self._send_http_request(token, chat_id, message_text)
        result["dashboard_id"] = dashboard_id
        result["bot_name"] = bot_cfg["name"]
        return result


def get_telegram_notifier() -> TelegramNotifier:
    return TelegramNotifier.get_instance()
