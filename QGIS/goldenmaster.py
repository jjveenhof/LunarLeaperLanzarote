import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Code/
import goldenmaster as gm

DATA_DIR = Path(__file__).resolve().parents[2] / "Data" / "GNSS" / "Cleaned"

GM_DIR = Path(__file__).resolve().parent / "_goldenmaster"
SOURCES = [("geojson", DATA_DIR, "GPR_*.geojson")]

if __name__ == "__main__":
    sys.exit(gm.main(GM_DIR, SOURCES, "the QGIS session"))
