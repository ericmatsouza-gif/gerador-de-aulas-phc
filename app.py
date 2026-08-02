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
.stButton>button { width: 100%; background-color: #2980b9; color: white; font-weight: bold; height: 3.2em; border-radius: 8px; border: none; font-size: 16px; }
.stButton>button:hover { background-color: #1f6391; color: white; }
.author-card { background-color: #f8f9fa; border-left: 4px solid #2980b9; padding: 15px; border-radius: 6px; margin-bottom: 25px; }
.author-name { font-size: 1.1rem; font-weight: bold; color: #1a2a3a; margin-bottom: 4px; }
.author-desc { font-size: 0.9rem; color: #555; margin-bottom: 10px; }
.footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; font-size: 0.85rem; color: #7f8c8d; }
</style>
""", unsafe_allow_html=True)

# ── RENDERIZADOR ESTÁVEL ──────────────────────────────────────────────────────
class PHCRenderer:
    def __init__(self, pdf, font_name="DejaVu", base_size=10):
        self.pdf = pdf
        self.font_name = font_name
        self.base_size = base_size
        self.line_height = 7.0
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

    def _write(self, text):
        if not text: return
        self._apply_style()
        if self.pdf.font_family.lower() == "helvetica":
            text = text.encode('latin-1', 'replace').decode('latin-1')
        
        if self.y_offset != 0:
            # Deslocamento vertical relativo simples
            self.pdf.y += self.y_offset
            self.pdf.write(self.line_height, text)
            self.pdf.y -= self.y_offset
        else:
            self.pdf.write(self.line_height, text)

    def draw_fraction(self, num, den):
        if self.in_exponent:
            self._write(f"({num}/{den})")
            return
        
        x, y = self.pdf.get_x(), self.pdf.get_y()
        old_mult = self.size_mult
        self.size_mult *= 0.8
        self._apply_style()
        
        w_num = self.pdf.get_string_width(num)
        w_den = self.pdf.get_string_width(den)
        w = max(w_num, w_den) + 2
        
        # Numerador (acima)
        self.pdf.set_xy(x + (w - w_num)/2, y - 1.5)
        self.pdf.write(self.line_height, num)
        
        # Linha da fração
        self.pdf.set_draw_color(44, 62, 80)
        self.pdf.set_line_width(0.2)
        self.pdf.line(x, y + self.line_height/2 + 0.5, x + w, y + self.line_height/2 + 0.5)
        
        # Denominador (abaixo)
        self.pdf.set_xy(x + (w - w_den)/2, y + 2.5)
        self.pdf.write(self.line_height, den)
        
        # Retorna o cursor para a linha base após a fração
        self.pdf.set_xy(x + w + 1, y)
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
                    balance, start = 1, i
                    while i < len(text) and balance > 0:
                        if text[i] == "(": balance += 1
                        elif text[i] == ")": balance -= 1
                        if balance > 0: i += 1
                    content, i = text[start:i], i + 1
                else:
                    start = i
                    while i < len(text) and (text[i].isalnum() or text[i] in "+-"): i += 1
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
                self._write("√" if not prefix or prefix == "raiz" else prefix)
                x_start = self.pdf.get_x()
                self.render_span(content)
                self.pdf.line(x_start, y_root + 0.8, self.pdf.get_x(), y_root + 0.8)
                continue
            
            self._write(text[i])
            i += 1

    def render_line(self, text):
        if not text.strip():
            self.pdf.ln(self.line_height)
            return
        
        # Detecta marcadores de lista a), 1., - etc
        match_list = re.match(r'^(\s*)([-*•]|\d+\.|\w\))\s+', text)
        if match_list:
            bullet = match_list.group(2)
            content = text[len(match_list.group(0)):]
            x_start = self.pdf.get_x()
            self._write(bullet + " ")
            # Garante que o conteúdo comece após o bullet sem resetar X para a margem
            self.render_span(content)
        else:
            self.render_span(text)
        self.pdf.ln(self.line_height + 2)

# ── UTILITÁRIOS ───────────────────────────────────────────────────────────────
def _localizar_fontes_dejavu() -> str:
    paths = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "/usr/local/share/fonts/"]
    for p in paths:
        if os.path.isfile(os.path.join(p, "DejaVuSans.ttf")): return p
    return ""

FONT_DIR = _localizar_fontes_dejavu()

def sanitizar(texto: str) -> str:
    if not texto: return ""
    texto = texto.replace("—", "--").replace("–", "-").replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'").replace("•", "-")
    # Remove repetições de números ou expressões longas (falha comum de LLMs)
    texto = re.sub(r'(\d{5,})\1', r'\1', texto)
    texto = re.sub(r'([A-Za-z0-9=×+/\-^√()]{10,})\1', r'\1', texto)
    texto = re.sub(r'\$+', '', texto)
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'\1√(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}',             r'raiz(\1)',     texto)
    texto = re.sub(r'\\(cdot|times)',   ' · ', texto)
    texto = re.sub(r'\\div\b',          ' / ',  texto)
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)
    mapa_simb = {'\\approx': '≈', '\\neq': '≠', '\\le': '≤', '\\leq': '≤', '\\ge': '≥', '\\geq': '≥', '\\pm': '±', '\\infty': '∞', '\\pi': 'π', '\\Delta': 'Δ'}
    for k, v in mapa_simb.items(): texto = texto.replace(k, v)
    texto = texto.replace('<=>', '⟺').replace('=>', '⇒').replace('>=', '≥').replace('<=', '≤').replace('!=', '≠')
    texto = re.sub(r'(?<=[0-9a-zA-Z\)])\s*\*\s*(?=[0-9a-zA-Z\(])', ' · ', texto)
    texto = re.sub(r'(?<![*])\*([^*\n]+?)\*(?![*])', r'\1', texto)
    texto = texto.replace('`', '')
    return texto

# ── PDF E STREAMLIT ───────────────────────────────────────────────────────────
class PDFMaterial(FPDF):
    def __init__(self, disciplina, ano, assunto):
        super().__init__()
        self.disciplina, self.ano, self.assunto = disciplina, ano, assunto
        if FONT_DIR:
            self.add_font("DejaVu", "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
            self.add_font("DejaVu", "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))

    def header(self):
        fonte = "DejaVu" if FONT_DIR else "helvetica"
        self.set_font(fonte, "B", 12)
        self.set_text_color(26, 42, 58)
        self.cell(0, 10, "PLANO DE AULA E MATERIAL DIDÁTICO", align="C", ln=1)
        self.set_font(fonte, "B", 9)
        self.set_text_color(41, 128, 185)
        self.cell(0, 5, f"{self.disciplina.upper()} | {self.ano} | Assunto: {self.assunto}", align="C", ln=1)
        self.ln(2)
        self.set_draw_color(41, 128, 185)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="R")

def compilar_pdf(texto_md, disciplina, ano, assunto):
    pdf = PDFMaterial(disciplina, ano, assunto)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(True, 20)
    pdf.add_page()
    fonte = "DejaVu" if FONT_DIR else "helvetica"
    renderer = PHCRenderer(pdf, fonte, 10)
    
    for linha in texto_md.split('\n'):
        s = sanitizar(linha.strip())
        if not s: pdf.ln(3); continue
        
        if s.startswith('# '):
            pdf.ln(4)
            pdf.set_fill_color(41, 128, 185)
            pdf.set_font(fonte, "B", 11)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(pdf.epw, 8, f"  {s[2:]}", fill=True, ln=1)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(3)
        elif s.startswith('## '):
            pdf.ln(3)
            pdf.set_font(fonte, "B", 10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(0, 7, s[3:], ln=1)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
        elif re.match(r'^Quest[ãa]o\s+\d+', s):
            pdf.ln(2)
            renderer.render_line("**" + s + "**")
        else:
            renderer.render_line(linha)
    return bytes(pdf.output())

@st.cache_resource
def get_client(key): return genai.Client(api_key=key)

def gerar(client, disc, ano, ass, bncc):
    prompt = f"Professor PHC. Disciplina: {disc}, {ano}. Assunto: {ass}. BNCC: {bncc}. Estrutura: # 1. Prática Social, # 2. Fixação, # 3. Leitura Crítica, # 4. Gabarito. Use (a/b) para frações e ^(exp) para potências. Não use LaTeX."
    response = client.models.generate_content(model='gemini-flash-latest', contents=prompt, config=types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7))
    return response.text

# --- Interface ---
st.title("📚 Gerador de Aulas")
st.markdown('<div class="author-card"><div class="author-name">Prof. Me. Eric Souza da Silva</div><div class="author-desc">Perspectiva PHC e Hegemonia Gramsciana.</div></div>', unsafe_allow_html=True)

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key: api_key = st.text_input("🔑 Chave API Gemini:", type="password")

c1, c2 = st.columns(2)
with c1: disc = st.text_input("Disciplina", "Matemática")
with c2: ano = st.text_input("Ano / Série", "8º ano")
ass = st.text_input("Assunto", "Radiciação e Potenciação")
bncc = st.text_input("🎯 BNCC (opcional)")

if "md" not in st.session_state: st.session_state.md = None

if st.button("✨ Gerar Material Didático"):
    if not api_key: st.warning("Insira a chave API.")
    else:
        try:
            with st.spinner("🧠 Gerando com Gemini Flash..."):
                st.session_state.md = gerar(get_client(api_key), disc, ano, ass, bncc)
            st.success("✅ Gerado!")
        except Exception as e:
            if "503" in str(e): st.error("Servidor ocupado. Tente novamente em instantes.")
            else: st.error(f"Erro: {e}")

if st.session_state.md:
    st.divider()
    with st.expander("📄 Visualizar texto"): st.markdown(st.session_state.md)
    col1, col2 = st.columns(2)
    with col1:
        try:
            pdf = compilar_pdf(st.session_state.md, disc, ano, ass)
            st.download_button("🖨️ Baixar PDF", pdf, f"Aula_{disc}.pdf", "application/pdf")
        except Exception as e: st.error(f"Erro no PDF: {e}")
    with col2:
        st.download_button("⬇️ Baixar Markdown", st.session_state.md.encode(), f"Aula_{disc}.md", "text/markdown")

st.markdown('<div class="footer">© Prof. Eric Souza da Silva</div>', unsafe_allow_html=True)
