import os
import re
import io
import requests
import tempfile
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError
from fpdf import FPDF, XPos, YPos

# ── CONFIGURAÇÃO DA PÁGINA ────────────────────────────────────────────────────
st.set_page_config(page_title="Gerador de Aulas", page_icon="📚", layout="centered")

st.markdown("""
<style>
.stButton>button {
    width: 100%; background-color: #2980b9; color: white;
    font-weight: bold; height: 3.2em; border-radius: 8px;
    border: none; font-size: 16px;
}
.stButton>button:hover { background-color: #1f6391; color: white; }
.author-card {
    background-color: #f8f9fa; border-left: 4px solid #2980b9;
    padding: 15px; border-radius: 6px; margin-bottom: 25px;
}
.author-name { font-size: 1.1rem; font-weight: bold; color: #1a2a3a; margin-bottom: 4px; }
.author-desc { font-size: 0.9rem; color: #555; margin-bottom: 10px; }
.footer {
    margin-top: 50px; padding-top: 20px; border-top: 1px solid #e0e0e0;
    text-align: center; font-size: 0.85rem; color: #7f8c8d;
}
</style>
""", unsafe_allow_html=True)


# ── LOCALIZAÇÃO DE FONTES DejaVu ──────────────────────────────────────────────
def _localizar_fontes_dejavu() -> str:
    paths = [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/dejavu/",
        "/usr/local/share/fonts/",
    ]
    for p in paths:
        if os.path.isfile(os.path.join(p, "DejaVuSans.ttf")):
            return p
    return ""

FONT_DIR = _localizar_fontes_dejavu()


# ── CODECOGS: LaTeX → PNG ─────────────────────────────────────────────────────
CODECOGS_URL = "[https://latex.codecogs.com/png.image](https://latex.codecogs.com/png.image)?"

def latex_para_png(expr: str, dpi: int = 110) -> bytes | None:
    """Baixa PNG da expressão LaTeX via Codecogs com DPI ajustado para fonte 10pt."""
    params = f"\\dpi{{{dpi}}}\\bg{{white}}{expr}"
    try:
        resp = requests.get(CODECOGS_URL + requests.utils.quote(params), timeout=8)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def inserir_imagem_latex(pdf: FPDF, png_bytes: bytes, is_display: bool):
    """
    Insere PNG LaTeX preservando proporção de fonte constante mesmo para frações/expressões altas.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name

    try:
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(png_bytes)) as img:
            w_px, h_px = img.size

        px_to_mm = 0.22  # Conversão para DPI 110

        if is_display:
            # Em bloco (display), permite altura até 12mm
            h = min(h_px * px_to_mm, 12.0)
            w = h * (w_px / h_px)
            
            pdf.ln(6.5)
            pdf.set_x(pdf.l_margin)
            
            x_centro = pdf.l_margin + (pdf.epw - w) / 2
            pdf.image(tmp_path, x=x_centro, y=pdf.get_y(), h=h, w=w)
            
            pdf.set_y(pdf.get_y() + h + 3)
            pdf.set_x(pdf.l_margin)
        else:
            # Em linha (inline): calcula largura natural para manter o tamanho do texto/fonte uniforme
            w_calculado = w_px * px_to_mm
            h_calculado = h_px * px_to_mm

            # Se a imagem for muito alta (ex: frações), permite até 6.5mm em vez de travar em 4.0mm
            h = min(h_calculado, 6.5)
            w = w_calculado * (h / h_calculado)

            y_base = pdf.get_y()
            pdf.set
