import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="autopatch-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["AUTOPATCH_DATA_DIR"] = str(_root)
os.environ["GEMINI_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-jwt-secret-for-pytest-only"
