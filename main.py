import sys
import os
import threading
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    level=logging.INFO
)

def run_webhook():
    import uvicorn
    from src.webhook_server import app
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

def run_bot():
    from src.bot import main
    main()

if __name__ == "__main__":
    t = threading.Thread(target=run_webhook, daemon=True)
    t.start()
    run_bot()
