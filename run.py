import threading
import time
import webbrowser
import os

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

import httpx
import uvicorn


def start_server():
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=False, log_level="info")


def wait_for_health(url: str, timeout_seconds: int = 30) -> bool:
    start_time = time.time()
    with httpx.Client(timeout=2.0) as client:
        while time.time() - start_time < timeout_seconds:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


if __name__ == "__main__":
    # Hint if API key missing
    if not os.getenv("GEMINI_API_KEY"):
        print("Warning: GEMINI_API_KEY is not set. Create a .env file or set the env var.")

    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    ready = wait_for_health("http://127.0.0.1:8002/health", timeout_seconds=60)
    if ready:
        webbrowser.open("http://127.0.0.1:8002/")
        print("ChefGPT is ready at http://127.0.0.1:8002/")
    else:
        print("Server did not become ready in time. Visit http://127.0.0.1:8002/ manually.")

    # Keep main thread alive while server thread runs
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")

