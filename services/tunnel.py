import re
import shutil
import subprocess
import threading

URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.(?:ngrok[a-z.-]*\.app|trycloudflare\.com)")


class TunnelManager:
    def __init__(self):
        self._proc = None
        self._url = None
        self._provider = None
        self._error = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict:
        with self._lock:
            proc = self._proc
            running = proc is not None and proc.poll() is None
            return {
                "running": running,
                "provider": self._provider,
                "url": self._url,
                "error": self._error,
            }

    def start(self, provider: str, token: str | None = None) -> dict:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"running": True, "provider": self._provider, "url": self._url, "error": None}

        provider = provider.lower()
        if provider == "ngrok":
            exe = shutil.which("ngrok")
            if not exe:
                return {"running": False, "provider": provider, "url": None, "error": "ngrok не найден в PATH"}
            if token:
                subprocess.run([exe, "config", "add-authtoken", token], capture_output=True, timeout=30)
            proc = subprocess.Popen(
                [exe, "http", "8010", "--log", "stdout"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        elif provider == "cloudflared":
            exe = shutil.which("cloudflared")
            if not exe:
                return {"running": False, "provider": provider, "url": None, "error": "cloudflared не найден в PATH"}
            proc = subprocess.Popen(
                [exe, "tunnel", "--url", "http://localhost:8010", "--no-autoupdate"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        else:
            return {"running": False, "provider": provider, "url": None, "error": "Неизвестный провайдер: " + provider}

        with self._lock:
            self._proc = proc
            self._provider = provider
            self._url = None
            self._error = None

        threading.Thread(target=self._reader, args=(proc,), daemon=True).start()
        return {"running": True, "provider": provider, "url": None, "error": None}

    def _reader(self, proc):
        for line in proc.stdout:
            m = URL_RE.search(line)
            if m:
                with self._lock:
                    self._url = m.group(0)
            if self._url is None and ("error" in line.lower() or "failed" in line.lower()):
                with self._lock:
                    if self._error is None:
                        self._error = line.strip()[:300]

    def stop(self) -> dict:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._url = None
            self._provider = None
            self._error = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        return {"running": False, "provider": None, "url": None, "error": None}


tunnel = TunnelManager()