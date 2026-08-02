import os
import re
import streamlit as st
from google import genai
from google.genai.errors import APIError
from fpdf import FPDF
from google.genai import types

# --- CONFIGURAÇÃO DA PÁGINA ---
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

# ── RENDERIZADOR ROBUSTO (PHCRenderer) ─────────────────────────────────────────
class PHCRenderer:
    def __init__(self, pdf, font_name="DejaVu", base_size=10):
        self.pdf = pdf
        self.font_name = font_name
        self.base_size = base_size
        self.line_height = 6.0
        self.bold = False
        self.size_mult = 1.0
        self.y_offset = 0
        self.in_exponent = False
        
    def _apply_style(self):
        style = "B" if self.bold else ""
        size = self.base_size * self.size_mult
        try:
            self.pdf.set_font(self.font_name, style, size)
        except:
            self.pdf.set_font("helvetica", style, size)

    def _safe_write(self, text):
        if not text: return
        if self.pdf.font_family.lower() == "helvetica":
            text = text.encode('latin-1', 'replace').decode('latin-1')
        if self.y_offset != 0:
            x, y = self.pdf.get_x(), self.pdf.get_y()
            self.pdf.set_y(y + self.y_offset)
            self.pdf.write(self.line_height, text)
            self.pdf.set_xy(self.pdf.get_x(), y)
        else:
            self.pdf.write(self.line_height, text)

    def draw_fraction(self, num_text, den_text):
        if self.in_exponent:
            self._safe_write(f"({num_text}/{den_text})")
            return
        x0, y0 = self.pdf.get_x(), self.pdf.get_y()
        old_mult = self.size_mult
        self.size_mult *= 0.85
        self._apply_style()
        w_num = self.pdf.get_string_width(num_text)
        w_den = self.pdf.get_string_width(den_text)
        w_frac = max(w_num, w_den) + 2
        h_cell = self.line_height * 0.7
        self.pdf.set_xy(x0 + (w_frac - w_num)/2, y0 - h_cell/2 - 0.5)
        self.pdf.write(h_cell, num_text)
        self.pdf.set_draw_color(44, 62, 80)
        self.pdf.set_line_width(0.2)
        self.pdf.line(x0, y0 + self.line_height/2, x0 + w_frac, y0 + self.line_height/2)
        self.pdf.set_xy(x0 + (w_frac - w_den)/2, y0 + h_cell/2 + 0.5)
        self.pdf.write(h_cell, den_text)
        self.pdf.set_xy(x0 + w_frac + 1, y0)
        self.size_mult = old_mult
        self._apply_style()

    def render_span(self, text):
        i = 0
        while i < len(text):
            if text.startswith("**", i):
                self.bold = not self.bold
                i += 2
                continue
            if text[i] == "^":
                i += 1
                content = ""
                if i < len(text) and text[i] == "(":
                    i += 1
                    balance = 1
                    start = i
                    while i < len(text) and balance > 0:
                        if text[i] == "(": balance += 1
                        elif text[i] == ")": balance -= 1
                        if balance > 0: i += 1
                    content = text[start:i]
                    i += 1
                else:
                    start = i
                    while i < len(text) and (text[i].isalnum() or text[i] in "+-"):
                        i += 1
                    content = text[start:i]
                old_mult, old_y, old_exp = self.size_mult, self.y_offset, self.in_exponent
                self.size_mult *= 0.7
                self.y_offset -= 2.5
                self.in_exponent = True
                self.render_span(content)
                self.size_mult, self.y_offset, self.in_exponent = old_mult, old_y, old_exp
                continue
            if text[i] == "(":
                balance, j, slash_pos = 1, i + 1, -1
                while j < len(text) and balance > 0:
                    if text[j] == "(": balance += 1
                    elif text[j] == ")": balance -= 1
                    elif text[j] == "/" and balance == 1: slash_pos = j
                    if balance > 0: j += 1
                if slash_pos != -1:
                    num, den = text[i+1:slash_pos].strip(), text[slash_pos+1:j].strip()
                    self.draw_fraction(num, den)
                    i = j + 1
                    continue
            match_raiz = re.match(r'(?:raiz|\d*√)\(', text[i:])
            if match_raiz:
                prefix = match_raiz.group(0)[:-1]
                i += len(match_raiz.group(0))
                balance, start = 1, i
                while i < len(text) and balance > 0:
                    if text[i] == "(": balance += 1
                    elif text[i] == ")": balance -= 1
                    if balance > 0: i += 1
                content, i = text[start:i], i + 1
                y_root = self.pdf.get_y()
                self._safe_write("√" if not prefix or prefix == "raiz" else prefix)
                x_start = self.pdf.get_x()
                self.render_span(content)
                self.pdf.set_draw_color(44, 62, 80)
                self.pdf.set_line_width(0.2)
                self.pdf.line(x_start, y_root + 0.8, self.pdf.get_x(), y_root + 0.8)
                continue
            self._safe_write(text[i])
            i += 1

    def render_line(self, text):
        if not text.strip():
            self.pdf.ln(self.line_height)
            return
        match_list = re.match(r'^(\s*)([-*•]|\d+\.)\s+', text)
        if match_list:
            bullet = match_list.group(2)
            indent = len(match_list.group(1)) * 2 + 5
            text = text[len(match_list.group(0)):]
            self.pdf.set_x(self.pdf.l_margin + indent - 5)
            self._safe_write(bullet + " ")
            self.pdf.set_x(self.pdf.l_margin + indent)
        else:
            self.pdf.set_x(self.pdf.l_margin)
        self.render_span(text)
        self.pdf.ln(self.line_height + 2)

# ── LOCALIZAÇÃO DE FONTES ─────────────────────────────────────────────────────
def _localizar_fontes_dejavu() -> str:
    paths = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "/usr/local/share/fonts/"]
    for p in paths:
        if os.path.isfile(os.path.join(p, "DejaVuSans.ttf")): return p
    return ""

FONT_DIR = _localizar_fontes_dejavu()

# ── SANITIZAÇÃO ───────────────────────────────────────────────────────────────
def sanitizar(texto: str) -> str:
    if not texto: return ""
    texto = texto.replace("—", "--").replace("–", "-").replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'").replace("•", "-")
    texto = re.sub(r'(\d{4,})\1', r'\1', texto)
    texto = re.sub(r'([A-Za-z0-9=×+/\-^√()]{6,})\1', r'\1', texto)
    texto = re.sub(r'\$+', '', texto)
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'\1√(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}',             r'raiz(\1)',     texto)
    texto = re.sub(r'\\text\{([^}]+)\}',             r'\1',           texto)
    texto = re.sub(r'\\(cdot|times)',   ' · ', texto)
    texto = re.sub(r'\\div\b',          ' / ',  texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)
    mapa_simb = {'\\approx': '≈', '\\neq': '≠', '\\le': '≤', '\\leq': '≤', '\\ge': '≥', '\\geq': '≥', '\\pm': '±', '\\infty': '∞', '\\rightarrow': '→', '\\Rightarrow': '⇒', '\\pi': 'π', '\\alpha': 'α', '\\beta': 'β', '\\Delta': 'Δ'}
    for k, v in mapa_simb.items(): texto = texto.replace(k, v)
    texto = texto.replace('<=>', '⟺').replace('=>', '⇒').replace('>=', '≥').replace('<=', '≤').replace('!=', '≠')
    texto = re.sub(r'(?<=[0-9a-zA-Z\)])\s*\*\s*(?=[0-9a-zA-Z\(])', ' · ', texto)
    texto = re.sub(r'^-{3,}$', '', texto.strip()) if re.match(r'^-{3,}$', texto.strip()) else texto
    texto = re.sub(r'(?<![*])\*([^*\n]+?)\*(?![*])', r'\1', texto)
    texto = texto.replace('`', '')
    return texto

# ── CLASSE PDF ─────────────────────────────────────────────────────────────────
class PDFMaterial(FPDF):
    def __init__(self, disciplina: str, ano_escolar: str, assunto: str):
        super().__init__()
        self.disciplina, self.ano_escolar, self.assunto = disciplina, ano_escolar, assunto
        if FONT_DIR:
            self.add_font("DejaVu",  style="",  fname=os.path.join(FONT_DIR, "DejaVuSans.ttf"))
            self.add_font("DejaVu",  style="B", fname=os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))

    def header(self):
        fonte = "DejaVu" if FONT_DIR else "helvetica"
        self.set_font(fonte, "B", 12)
        self.set_text_color(26, 42, 58)
        self.cell(0, 10, "PLANO DE AULA E MATERIAL DIDÁTICO", align="C", ln=1)
        self.set_font(fonte, "B", 9)
        self.set_text_color(41, 128, 185)
        subtitulo = f"{self.disciplina.upper()} | {self.ano_escolar} | Assunto: {self.assunto}"
        self.cell(0, 5, subtitulo, align="C", ln=1)
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

# ── COMPILADOR PDF ─────────────────────────────────────────────────────────────
def compilar_pdf(texto_md: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    fonte = "DejaVu" if FONT_DIR else "helvetica"
    renderer = PHCRenderer(pdf, font_name=fonte, base_size=10)
    W = pdf.epw
    for linha_raw in texto_md.split('\n'):
        linha = sanitizar(linha_raw.rstrip())
        s = linha.strip()
        if not s:
            pdf.ln(3)
            continue
        if s.startswith('# '):
            pdf.ln(4)
            pdf.set_fill_color(41, 128, 185)
            pdf.set_font(fonte, "B", 11)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(W, 8, f"  {s[2:]}", fill=True, ln=1)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(3)
        elif s.startswith('## '):
            pdf.ln(3)
            pdf.set_font(fonte, "B", 10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(W, 7, s[3:], ln=1)
            pdf.set_draw_color(41, 128, 185)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
        elif re.match(r'^#{3,4}\s+', s):
            pdf.ln(2)
            renderer.render_line(re.sub(r'^#{3,4}\s+', '**', s) + '**')
        else:
            renderer.render_line(linha)
    return pdf.output(dest='S')

# ── LOGICA DE GERAÇÃO E UI ────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)

def gerar_conteudo_phc(client, disciplina, ano_escolar, assunto, codigo_bncc=""):
    prompt = f"Professor PHC. Matéria: {disciplina}, {ano_escolar}. Assunto: {assunto}. BNCC: {codigo_bncc}. Estrutura: # 1. Prática Social, # 2. Fixação, # 3. Leitura Crítica, # 4. Gabarito. Use (a/b) para frações e ^(exp) para potências."
    config = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    # USO OBRIGATÓRIO DO MODELO FLASH LATEST
    response = client.models.generate_content(model='gemini-flash-latest', contents=prompt, config=config)
    return response.text

# --- Interface Streamlit ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")
    st.caption("Licenciado em Matemática (UERJ), Mestre pelo PROFMAT/UERJ.")

st.title("📚 Gerador de Aulas")
st.markdown('<div class="author-card"><div class="author-name">Prof. Me. Eric Souza da Silva</div><div class="author-desc">Perspectiva PHC e Hegemonia Gramsciana.</div></div>', unsafe_allow_html=True)

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key: api_key = st.text_input("🔑 Chave API Gemini:", type="password")

col_disc, col_ano = st.columns(2)
with col_disc: disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática")
with col_ano: ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 9º ano")
assunto = st.text_input("Assunto", placeholder="Ex: Potenciação")
codigo_bncc = st.text_input("🎯 BNCC (opcional)")

for chave in ("conteudo_md", "ultima_disciplina", "ultimo_ano", "ultimo_assunto"):
    if chave not in st.session_state: st.session_state[chave] = None if chave == "conteudo_md" else ""

if st.button("✨ Gerar Material Didático"):
    if not api_key or not disciplina or not ano_escolar or not assunto: st.warning("Preencha os campos.")
    else:
        try:
            with st.spinner("🧠 Elaborando material (Gemini Flash)..."):
                client = get_gemini_client(api_key)
                st.session_state.conteudo_md = gerar_conteudo_phc(client, disciplina, ano_escolar, assunto, codigo_bncc)
                st.session_state.ultima_disciplina, st.session_state.ultimo_ano, st.session_state.ultimo_assunto = disciplina, ano_escolar, assunto
            st.success("✅ Gerado!")
        except APIError as e:
            if "503" in str(e) or "unavailable" in str(e).lower():
                st.error("⚠️ O servidor do Google está com alta demanda no momento (Erro 503). Por favor, aguarde alguns segundos e tente clicar no botão novamente.")
            else:
                st.error(f"❌ Erro na API Gemini: {e}")
        except Exception as e: st.error(f"❌ Erro inesperado: {e}")

if st.session_state.conteudo_md:
    st.divider()
    with st.expander("📄 Visualizar texto", expanded=True): st.markdown(st.session_state.conteudo_md)
    st.divider()
    col_pdf, col_md = st.columns(2)
    with col_pdf:
        try:
            pdf_bytes = compilar_pdf(st.session_state.conteudo_md, st.session_state.ultima_disciplina, st.session_state.ultimo_ano, st.session_state.ultimo_assunto)
            st.download_button("🖨️ Baixar PDF", data=pdf_bytes, file_name=f"Aula_{st.session_state.ultima_disciplina}.pdf", mime="application/pdf")
        except Exception as e: st.error(f"❌ Erro no PDF: {e}")
    with col_md:
        st.download_button("⬇️ Baixar Markdown", data=st.session_state.conteudo_md.encode("utf-8"), file_name=f"Aula_{st.session_state.ultima_disciplina}.md", mime="text/markdown")

st.markdown('<div class="footer">© Prof. Eric Souza da Silva</div>', unsafe_allow_html=True)
