import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import uvicorn
from src.webhook_server import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
