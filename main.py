from pathlib import Path
import runpy


if __name__ == "__main__":
    script_path = Path(__file__).with_name("\u7ea2\u70e7box.py")
    runpy.run_path(str(script_path), run_name="__main__")
