"""Direct local launcher using the same saved selection as the sidebar."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import runtime_paths,xiaovmiao

try:
    result=xiaovmiao.Manager(runtime_paths.data_home(),ROOT).open()
    print(result['message'])
except Exception as error:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0,str(error),'小v喵启动提示',16)
    raise SystemExit(1)
