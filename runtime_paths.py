"""Per-user writable paths, independent of installation location."""
import os,sys
from pathlib import Path
def data_home():
    root=Path(__file__).resolve().parent
    default=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'ManjuStudio' if getattr(sys,'frozen',False) else root/'data'
    return Path(os.environ.get('MANJU_DATA',default)).resolve()
def output_home():
    return Path.home()/'Videos'/'漫剧工坊' if getattr(sys,'frozen',False) else Path(__file__).resolve().parent/'output'
