from __future__ import annotations
from pathlib import Path
import pickle


class Dumpable:
    def dump(self, fout: Path) -> None:
        with open(fout, "wb") as f:
            pickle.dump(self, f)
