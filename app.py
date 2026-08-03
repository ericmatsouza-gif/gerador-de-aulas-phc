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


# ── CODECOGS: RENDERIZAÇÃO DE LaTeX → PNG ─────────────────────────────────────
CODECOGS_URL = "https://latex.codecogs.com/png.image?"

def latex_para_png(expr: str, dpi: int = 150) -> bytes | None:
    """
    Baixa da Codecogs a imagem PNG de uma expressão LaTeX.
    Retorna os bytes da imagem ou None em caso de falha.
    """
    # Codecogs espera a expressão URL-encoded com fundo branco
    params = f"\\dpi{{{dpi}}}\\bg{{white}}{expr}"
    try:
        resp = requests.get(CODECOGS_URL + requests.utils.quote(params), timeout=8)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def inserir_imagem_latex(pdf: FPDF, png_bytes: bytes, fonte: str,
                          base_size: float, is_display: bool):
    """
    Insere a imagem PNG de uma expressão LaTeX no PDF.
    - display ($$...$$): centralizada em linha própria
    - inline ($...$): inline com o texto, alinhada pela base
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name

    try:
        # Altura alvo em mm proporcional ao tamanho da fonte
        # 1 pt ≈ 0.353 mm; usamos 1.8x para dar margem visual
        h_alvo = base_size * 0.353 * 1.8

        if is_display:
            # Bloco centralizado — nova linha antes e depois
            pdf.ln(3)
            pdf.image(tmp_path, x=None, y=None, h=h_alvo * 1.4)
            pdf.ln(3)
        else:
            # Inline — insere na posição atual do cursor
            # Calcula a largura proporcional a partir dos bytes
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(png_bytes)) as img:
                w_px, h_px = img.size
            ratio = w_px / h_px
            w_alvo = h_alvo * ratio

            # Verifica se cabe na linha; se não, quebra
            if pdf.get_x() + w_alvo > pdf.w - pdf.r_margin:
                pdf.ln(h_alvo + 1)
                pdf.set_x(pdf.l_margin)

            pdf.image(tmp_path, x=pdf.get_x(), y=pdf.get_y(), h=h_alvo, w=w_alvo)
            pdf.set_x(pdf.get_x() + w_alvo + 0.5)
    finally:
        os.unlink(tmp_path)


# ── TOKENIZADOR DE LINHA COM LaTeX ────────────────────────────────────────────
def tokenizar_linha(texto: str) -> list[dict]:
    """
    Divide uma linha em tokens do tipo:
      {"tipo": "texto", "conteudo": "..."}
      {"tipo": "display", "conteudo": "expr latex"}   — de $$...$$
      {"tipo": "inline",  "conteudo": "expr latex"}   — de $...$
    """
    tokens = []
    i = 0
    buf = ""

    while i < len(texto):
        # Display math $$...$$
        if texto.startswith("$$", i):
            if buf:
                tokens.append({"tipo": "texto", "conteudo": buf})
                buf = ""
            j = texto.find("$$", i + 2)
            if j != -1:
                tokens.append({"tipo": "display", "conteudo": texto[i + 2:j]})
                i = j + 2
            else:
                buf += texto[i]
                i += 1
            continue

        # Inline math $...$
        if texto[i] == "$":
            if buf:
                tokens.append({"tipo": "texto", "conteudo": buf})
                buf = ""
            j = texto.find("$", i + 1)
            if j != -1:
                tokens.append({"tipo": "inline", "conteudo": texto[i + 1:j]})
                i = j + 1
            else:
                buf += texto[i]
                i += 1
            continue

        buf += texto[i]
        i += 1

    if buf:
        tokens.append({"tipo": "texto", "conteudo": buf})

    return tokens


# ── RENDERER DE TEXTO SIMPLES (sem matemática) ────────────────────────────────
class TextRenderer:
    """
    Renderizador de texto puro com suporte a **negrito**.
    A matemática é tratada separadamente via Codecogs.
    """

    def __init__(self, pdf: FPDF, font_name: str = "DejaVu", base_size: float = 10):
        self.pdf       = pdf
        self.font_name = font_name
        self.base_size = base_size
        self.lh        = 6.5   # line height em mm

    def _set(self, bold: bool = False, size_mult: float = 1.0):
        style = "B" if bold else ""
        size  = self.base_size * size_mult
        try:
            self.pdf.set_font(self.font_name, style, size)
        except Exception:
            self.pdf.set_font("helvetica", style, size)

    def _encode(self, t: str) -> str:
        if self.pdf.font_family.lower() == "helvetica":
            return t.encode("latin-1", "replace").decode("latin-1")
        return t

    def write_span(self, text: str):
        """Escreve texto com suporte a **negrito** inline."""
        parts = re.split(r'(\*\*)', text)
        bold = False
        for part in parts:
            if part == "**":
                bold = not bold
                continue
            if not part:
                continue
            self._set(bold)
            self.pdf.write(self.lh, self._encode(part))

    def write_line(self, text: str):
        """Escreve uma linha completa e avança para a próxima."""
        if not text.strip():
            self.pdf.ln(self.lh * 0.5)
            return
        self._set()
        self.pdf.set_x(self.pdf.l_margin)
        self.write_span(text)
        self.pdf.ln(self.lh + 1)


# ── COMPILADOR PDF PRINCIPAL ──────────────────────────────────────────────────
class PDFMaterial(FPDF):
    def __init__(self, disciplina: str, ano_escolar: str, assunto: str):
        super().__init__()
        self.disciplina  = disciplina
        self.ano_escolar = ano_escolar
        self.assunto     = assunto
        if FONT_DIR:
            self.add_font("DejaVu", style="",  fname=os.path.join(FONT_DIR, "DejaVuSans.ttf"))
            self.add_font("DejaVu", style="B", fname=os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))

    def header(self):
        fonte = "DejaVu" if FONT_DIR else "helvetica"
        self.set_font(fonte, "B", 12)
        self.set_text_color(26, 42, 58)
        self.cell(0, 10, "PLANO DE AULA E MATERIAL DIDÁTICO",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(fonte, "B", 9)
        self.set_text_color(41, 128, 185)
        self.cell(0, 5,
                  f"{self.disciplina.upper()} | {self.ano_escolar} | Assunto: {self.assunto}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        fonte = "DejaVu" if FONT_DIR else "helvetica"
        self.set_font(fonte, "", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="R")


def compilar_pdf(texto_md: str, disciplina: str,
                  ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    fonte     = "DejaVu" if FONT_DIR else "helvetica"
    renderer  = TextRenderer(pdf, font_name=fonte, base_size=10)
    W         = pdf.epw

    for linha_raw in texto_md.split("\n"):
        linha = linha_raw.rstrip()
        s     = linha.strip()

        # Linha vazia
        if not s:
            pdf.ln(3)
            continue

        # Cabeçalho # H1
        if s.startswith("# "):
            pdf.ln(4)
            pdf.set_fill_color(41, 128, 185)
            try:
                pdf.set_font(fonte, "B", 11)
            except Exception:
                pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(W, 8, f"  {s[2:]}", fill=True,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(3)
            continue

        # Cabeçalho ## H2
        if s.startswith("## "):
            pdf.ln(3)
            try:
                pdf.set_font(fonte, "B", 10.5)
            except Exception:
                pdf.set_font("helvetica", "B", 10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(W, 7, s[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(41, 128, 185)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
            continue

        # Cabeçalho ### H3/H4
        if re.match(r'^#{3,4}\s+', s):
            conteudo = re.sub(r'^#{3,4}\s+', '', s)
            pdf.ln(2)
            try:
                pdf.set_font(fonte, "B", 10)
            except Exception:
                pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(W, 6, conteudo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            continue

        # Separador ---
        if re.match(r'^-{3,}$', s):
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
            continue

        # Item de lista: -, *, •, 1., a)
        match_list = re.match(r'^(\s*)([-*•]|\d+\.|\w\))\s+', linha)
        if match_list:
            bullet  = match_list.group(2)
            indent  = len(match_list.group(1)) * 2 + 5
            conteudo = linha[len(match_list.group(0)):]
            pdf.set_x(pdf.l_margin + indent - 3)
            try:
                pdf.set_font(fonte, "", 10)
            except Exception:
                pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(44, 62, 80)
            pdf.write(renderer.lh, bullet + " ")
            _renderizar_tokens(pdf, fonte, renderer, conteudo, 10)
            pdf.ln(renderer.lh + 1)
            continue

        # Linha normal com possível LaTeX inline/display
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(44, 62, 80)
        _renderizar_tokens(pdf, fonte, renderer, s, 10)
        pdf.ln(renderer.lh + 1)

    return bytes(pdf.output())


def _renderizar_tokens(pdf: FPDF, fonte: str, renderer: TextRenderer,
                        texto: str, base_size: float):
    """
    Processa tokens de uma linha, intercalando texto normal e imagens LaTeX.
    """
    tokens = tokenizar_linha(texto)

    for tok in tokens:
        if tok["tipo"] == "texto":
            renderer.write_span(tok["conteudo"])

        elif tok["tipo"] in ("inline", "display"):
            is_display = tok["tipo"] == "display"
            png = latex_para_png(tok["conteudo"], dpi=150)
            if png:
                inserir_imagem_latex(pdf, png, fonte, base_size, is_display)
            else:
                # Fallback: escreve a expressão como texto se a API falhar
                renderer.write_span(f"[{tok['conteudo']}]")


# ── CLIENTE GEMINI ────────────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def gerar_conteudo_phc(client, disciplina: str, ano_escolar: str,
                        assunto: str, codigo_bncc: str = "") -> str:
    prompt = f"""Você é um professor de {disciplina} do {ano_escolar} seguindo a Pedagogia Histórico-Crítica (PHC).

Gere um plano de aula completo sobre "{assunto}" {"com referência à BNCC: " + codigo_bncc if codigo_bncc else ""}.

Estrutura obrigatória:
# 1. Prática Social
# 2. Fixação
# 3. Leitura Crítica
# 4. Gabarito

REGRAS DE FORMATAÇÃO:
- Use $...$ para expressões matemáticas inline. Exemplo: A área é $A = l^2$.
- Use $$...$$ para expressões em destaque. Exemplo: $$x = \\frac{{-b \\pm \\sqrt{{b^2 - 4ac}}}}{{2a}}$$
- Use LaTeX padrão dentro dos delimitadores $ e $$.
- Frações: \\frac{{num}}{{den}}
- Raízes: \\sqrt{{x}}, \\sqrt[3]{{x}}
- Potências: x^{{2}}, x^{{n}}
- NÃO use blocos de código, NÃO use ```math, NÃO use \\[ \\].
- Texto normal em português, sem LaTeX fora dos delimitadores.
"""
    config   = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=prompt, config=config
    )
    return response.text


# ── INTERFACE STREAMLIT ───────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")
    st.caption("Licenciado em Matemática (UERJ), Mestre pelo PROFMAT/UERJ.")

st.title("📚 Gerador de Aulas")
st.markdown(
    '<div class="author-card">'
    '<div class="author-name">Prof. Me. Eric Souza da Silva</div>'
    '<div class="author-desc">Perspectiva PHC e Hegemonia Gramsciana.</div>'
    '</div>',
    unsafe_allow_html=True,
)

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.text_input("🔑 Chave API Gemini:", type="password")

col_disc, col_ano = st.columns(2)
with col_disc:
    disciplina  = st.text_input("Disciplina", placeholder="Ex: Matemática")
with col_ano:
    ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 9º ano")

assunto     = st.text_input("Assunto", placeholder="Ex: Potenciação")
codigo_bncc = st.text_input("🎯 BNCC (opcional)")

for chave in ("conteudo_md", "ultima_disciplina", "ultimo_ano", "ultimo_assunto"):
    if chave not in st.session_state:
        st.session_state[chave] = None if chave == "conteudo_md" else ""

if st.button("✨ Gerar Material Didático"):
    if not api_key or not disciplina or not ano_escolar or not assunto:
        st.warning("Preencha todos os campos obrigatórios.")
    else:
        try:
            with st.spinner("🧠 Elaborando material (Gemini Flash)..."):
                client = get_gemini_client(api_key)
                st.session_state.conteudo_md      = gerar_conteudo_phc(
                    client, disciplina, ano_escolar, assunto, codigo_bncc
                )
                st.session_state.ultima_disciplina = disciplina
                st.session_state.ultimo_ano        = ano_escolar
                st.session_state.ultimo_assunto    = assunto
            st.success("✅ Material gerado com sucesso!")
        except APIError as e:
            if "503" in str(e) or "unavailable" in str(e).lower():
                st.error("⚠️ Servidor ocupado. Tente novamente em alguns segundos.")
            else:
                st.error(f"❌ Erro na API Gemini: {e}")
        except Exception as e:
            st.error(f"❌ Erro inesperado: {e}")

if st.session_state.conteudo_md:
    st.divider()
    with st.expander("📄 Visualizar texto gerado", expanded=True):
        st.markdown(st.session_state.conteudo_md)
    st.divider()

    if st.button("🖨️ Gerar PDF"):
        with st.spinner("⚙️ Renderizando expressões matemáticas via Codecogs..."):
            try:
                pdf_bytes = compilar_pdf(
                    st.session_state.conteudo_md,
                    st.session_state.ultima_disciplina,
                    st.session_state.ultimo_ano,
                    st.session_state.ultimo_assunto,
                )
                st.download_button(
                    label="⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"Aula_{st.session_state.ultimo_assunto.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"❌ Erro ao gerar PDF: {e}")

st.markdown(
    '<div class="footer">© Prof. Eric Souza da Silva</div>',
    unsafe_allow_html=True,
)
