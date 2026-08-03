import os
import re
import streamlit as st
from google import genai
from google.genai.errors import APIError
from fpdf import FPDF, XPos, YPos

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
        self.in_exponent = False
        
    def _apply_style(self):
        style = "B" if self.bold else ""
        size = self.base_size * self.size_mult
        try:
            self.pdf.set_font(self.font_name, style, size)
        except:
            self.pdf.set_font("helvetica", style, size)

    def _write_at(self, x, y, text):
    """Escreve texto em coordenada absoluta, retorna o X final."""
    if not text: return x
    self._apply_style()
    if self.pdf.font_family.lower() == "helvetica":
        text = text.encode('latin-1', 'replace').decode('latin-1')
    self.pdf.set_xy(x, y)
    self.pdf.write(self.line_height, text)
    return self.pdf.get_x()

def draw_fraction(self, num_text, den_text):
    if self.in_exponent:
        self.x = self._write_at(self.x, self.y, f"({num_text}/{den_text})")
        return
    
    old_mult = self.size_mult
    self.size_mult *= 0.85
    self._apply_style()
    
    w_num = self.pdf.get_string_width(num_text)
    w_den = self.pdf.get_string_width(den_text)
    w_frac = max(w_num, w_den) + 4
    half = self.line_height * 0.55
    
    # Numerador acima da linha base
    self._write_at(self.x + (w_frac - w_num) / 2, self.y - half, num_text)
    
    # Linha separadora exatamente na linha base
    self.pdf.set_draw_color(44, 62, 80)
    self.pdf.set_line_width(0.2)
    self.pdf.line(self.x, self.y + self.line_height / 2,
                  self.x + w_frac, self.y + self.line_height / 2)
    
    # Denominador abaixo da linha base
    self._write_at(self.x + (w_frac - w_den) / 2, self.y + half, den_text)
    
    # Avança o cursor X
    self.x += w_frac + 1
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
                
                old_mult, old_exp = self.size_mult, self.in_exponent
                self.size_mult *= 0.7
                self.in_exponent = True
                
                # Salva a posição atual para retornar após o expoente
                x_before_exp, y_before_exp = self.pdf.get_x(), self.pdf.get_y()
                
                # Move o cursor para cima para o expoente
                self.pdf.set_y(y_before_exp - 2.5)
                self.render_span(content)
                
                # Retorna o cursor para a linha base, mantendo o X avançado
                self.pdf.set_xy(self.pdf.get_x(), y_before_exp)
                
                self.size_mult, self.in_exponent = old_mult, old_exp
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
            
            match_raiz = re.match(r'(?:raiz|\d*√)\((.*?)\)', text[i:])
            if match_raiz:
                full_match = match_raiz.group(0)
                content = match_raiz.group(1)
                prefix = full_match.split('(')[0]
                
                x_start_radical, y_start_radical = self.pdf.get_x(), self.pdf.get_y()
                
                # Renderiza o índice da raiz se houver (ex: 3√)
                if '√' in prefix and prefix != 'raiz':
                    index_val = prefix.replace('√', '')
                    old_mult = self.size_mult
                    self.size_mult *= 0.7 # Tamanho menor para o índice
                    
                    # Move o cursor para cima para o índice
                    self.pdf.set_y(y_start_radical - 1.5)
                    self._write(index_val)
                    self.pdf.set_y(y_start_radical) # Volta para a linha base
                    
                    self.size_mult = old_mult
                    self._apply_style()
                    
                # Renderiza o símbolo da raiz
                self._write('√')
                
                # Salva a posição X após o símbolo da raiz para desenhar o vínculo
                x_after_radical_symbol = self.pdf.get_x()
                
                # Renderiza o conteúdo da raiz
                self.render_span(content)
                
                # Desenha o vínculo (linha horizontal) sobre o conteúdo
                self.pdf.set_draw_color(44, 62, 80)
                self.pdf.set_line_width(0.2)
                # A linha deve começar onde o símbolo da raiz termina e ir até o final do conteúdo
                # Ajuste fino para alinhar com o topo do texto
                line_y = y_start_radical + self.line_height / 2 - 1.5 
                self.pdf.line(x_after_radical_symbol, line_y, self.pdf.get_x(), line_y)
                
                i += len(full_match)
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
            
            # Salva a posição X e Y atual antes de qualquer alteração
            x_before_bullet = self.pdf.get_x()
            y_before_bullet = self.pdf.get_y()

            # Define a posição para o bullet (com indentação)
            self.pdf.set_x(self.pdf.l_margin + 5)
            self._write(bullet + " ")
            
            # Salva a posição X após o bullet para o conteúdo
            x_after_bullet = self.pdf.get_x()
            
            # Restaura o Y para a linha original antes de renderizar o conteúdo
            self.pdf.set_y(y_before_bullet)

            # Usa multi_cell para o conteúdo da lista, com recuo
            # O multi_cell precisa do X inicial e Y inicial para calcular o fluxo
            self.pdf.multi_cell(
                w=self.pdf.epw - x_after_bullet + self.pdf.l_margin,
                h=self.line_height,
                text=content,
                border=0,
                align='L',
                fill=False,
                new_x=XPos.LEFT, 
                new_y=YPos.NEXT
            )
            
        else:
            self.render_span(text)
            self.pdf.ln(self.line_height + 2)

# --- UTILITÁRIOS ───────────────────────────────────────────────────────────────
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
    texto = texto.replace('<=>', '⟺').replace('=>', '⇒').replace('>=' , '≥').replace('<=' , '≤').replace('!=' , '≠')
    texto = re.sub(r'(?<=[0-9a-zA-Z\)])\s*\*\s*(?=[0-9a-zA-Z\(])', ' · ', texto)
    texto = re.sub(r'(?<![*])\*([^*\n]+?)\*(?![*])', r'\1', texto)
    texto = re.sub(r'\`', '', texto)
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
        self.cell(0, 10, "PLANO DE AULA E MATERIAL DIDÁTICO", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(fonte, "B", 9)
        self.set_text_color(41, 128, 185)
        self.cell(0, 5, f"{self.disciplina.upper()} | {self.ano} | Assunto: {self.assunto}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
            pdf.cell(pdf.epw, 8, f"  {s[2:]}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(3)
        elif s.startswith('## '):
            pdf.ln(3)
            pdf.set_font(fonte, "B", 10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(0, 7, f"{s[3:]}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
    try:
        response = client.models.generate_content(model='gemini-flash-latest', contents=prompt, config=genai.types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7))
        return response.text
    except APIError as e:
        if e.status_code == 503:
            st.error("O modelo Gemini está com alta demanda no momento. Por favor, tente novamente em alguns segundos.")
        else:
            st.error(f"Ocorreu um erro na API do Gemini: {e}")
        return None

# --- Interface ---
st.title("📚 Gerador de Aulas")
st.markdown('<div class="author-card"><div class="author-name">Prof. Me. Eric Souza da Silva</div><div class="author-desc">Perspectiva PHC e Hegemoniana.</div></div>', unsafe_allow_html=True)

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
            client = get_client(api_key)
            with st.spinner("🧠 Gerando com Gemini Flash..."):
                st.session_state.md = gerar(client, disc, ano, ass, bncc)
        except Exception as e:
            st.error(f"Ocorreu um erro: {e}")

if st.session_state.md:
    st.subheader("Material Gerado (Pré-visualização)")
    st.markdown(st.session_state.md)

    st.subheader("Gerar PDF")
    if st.button("⬇️ Baixar PDF"):
        try:
            pdf_output = compilar_pdf(st.session_state.md, disc, ano, ass)
            st.download_button(
                label="Clique para baixar o PDF",
                data=pdf_output,
                file_name=f"aula_{ass.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

st.markdown('<div class="footer">Desenvolvido por Prof. Me. Eric Souza da Silva · PHC & Perspectiva Hegeliana</div>', unsafe_allow_html=True)
