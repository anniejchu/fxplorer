from pathlib import Path
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = REPO_ROOT / "_outputs"
OUTPUT_DIR_AFX = OUTPUT_DIR
UPLOADS_DIR = REPO_ROOT / "uploads"
TMP_CONFIG_DIR = REPO_ROOT / "tmp_configs"

ASSETS_DIR = REPO_ROOT / "assets"
PRETRAINED_DIR = REPO_ROOT / "pretrained"
AFX_REP_DIR = PRETRAINED_DIR / "afx-rep"
AFX_REP_CKPT = AFX_REP_DIR / "afx-rep.ckpt"
AFX_REP_CONFIG = AFX_REP_DIR / "config.yaml"
AFX_REP_BASE_URL = "https://huggingface.co/csteinmetz1/afx-rep/resolve/main/"


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
