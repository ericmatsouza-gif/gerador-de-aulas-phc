import os
import re
import streamlit as st
from google import genai
from google.genai.errors import APIError
from fpdf import FPDF
from google.genai import types
from renderer_phc import PHCRenderer

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
.contact-badge {
    display: inline-block; background-color: #eef7fc; color: #2980b9;
    padding: 4px 10px; border-radius: 12px; font-size: 0.85rem;
    font-weight: 600; margin-right: 8px; margin-top: 5px; text-decoration: none;
}
.contact-badge-wa { background-color: #e8f8ef; color: #27ae60; }
.footer {
    margin-top: 50px; padding-top: 20px; border-top: 1px solid #e0e0e0;
    text-align: center; font-size: 0.85rem; color: #7f8c8d;
}
</style>
""", unsafe_allow_html=True)

# ── LOCALIZAÇÃO DE FONTES ─────────────────────────────────────────────────────
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

# ── SANITIZAÇÃO MELHORADA ─────────────────────────────────────────────────────
def sanitizar(texto: str) -> str:
    if not texto: return ""
    
    # 1. Remove duplicatas geradas por falhas do LLM (ex: 200200 toneladas)
    # Tenta encontrar números repetidos colados
    texto = re.sub(r'(\d+)\1', r'\1', texto)
    
    # 2. Remove repetições de expressões matemáticas coladas
    # Ex: P=P0×2tP=P0​×2t
    texto = re.sub(r'([A-Za-z0-9=×+/\-^√()]+)\1', r'\1', texto)

    # 3. Normaliza caracteres Unicode problemáticos
    # Substitui travessão longo por hífen longo ou normal se a fonte falhar
    # Mas com DejaVu o travessão deve funcionar. Se falhar, o renderizador PHC trata.
    
    # 4. Remove cifrões LaTeX
    texto = re.sub(r'\$+', '', texto)
    
    # 5. Comandos LaTeX estruturais
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'\1√(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}',             r'raiz(\1)',     texto)
    texto = re.sub(r'\\text\{([^}]+)\}',             r'\1',           texto)
    texto = re.sub(r'\\(cdot|times)',   ' · ', texto)
    texto = re.sub(r'\\div\b',          ' / ',  texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)
    
    # 6. Potências: Converte chaves para parênteses
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)
    
    # 7. Símbolos matemáticos Unicode
    mapa_simb = {
        '\\approx': '≈', '\\neq': '≠', '\\le': '≤', '\\leq': '≤',
        '\\ge': '≥', '\\geq': '≥', '\\pm': '±', '\\infty': '∞',
        '\\rightarrow': '→', '\\Rightarrow': '⇒',
        '\\pi': 'π', '\\alpha': 'α', '\\beta': 'β', '\\Delta': 'Δ',
    }
    for k, v in mapa_simb.items(): texto = texto.replace(k, v)
    
    # 8. Operadores relacionais
    texto = texto.replace('<=>', '⟺').replace('=>', '⇒').replace('>=', '≥').replace('<=', '≤').replace('!=', '≠')
    
    # 9. Multiplicação
    texto = re.sub(r'(?<=[0-9a-zA-Z\)])\s*\*\s*(?=[0-9a-zA-Z\(])', ' · ', texto)
    
    # 10. Markdown básico
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
        else:
            # Se não encontrar DejaVu, tenta carregar fontes do sistema que suportem Unicode
            # Fallback para helvetica (mas avisando no log)
            print("AVISO: Fontes DejaVu não encontradas. Usando Helvetica.")

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
            pdf.set_font(fonte, "B", 10)
            pdf.set_text_color(41, 128, 185)
            # Renderiza o título H3 com o PHCRenderer para suportar matemática se houver
            renderer.render_line(re.sub(r'^#{3,4}\s+', '**', s) + '**')
        else:
            renderer.render_line(linha)
            
    return pdf.output(dest='S')

# ── LOGICA DE UI (STREAMLIT) ──────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)

def gerar_conteudo_phc(client, disciplina, ano_escolar, assunto, codigo_bncc=""):
    prompt = f"""
    Você é um Professor de Matemática e Pedagogo especializado na Pedagogia Histórico-Crítica (PHC).
    Elabore um material didático para {disciplina}, {ano_escolar}, sobre: {assunto}.
    {"Habilidade BNCC: " + codigo_bncc if codigo_bncc else ""}

    ESTRUTURA:
    # 1. PRÁTICA SOCIAL E GÊNESE HISTÓRICA DO CONTEÚDO
    # 2. EXERCÍCIOS DE FIXAÇÃO E DOMÍNIO CONCEITUAL
    # 3. DESAFIOS DE LEITURA CRÍTICA E CONTRA-HEGEMONIA
    # 4. GABARITO COMENTADO E PEDAGÓGICO

    REGRAS CRÍTICAS:
    - NÃO repita termos ou números colados (ex: 200200).
    - Use notação (a / b) para frações.
    - Use ^(exp) para potências.
    - Use raiz(exp) para raízes.
    - Foco em rigor técnico e consciência crítica.
    """
    config = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt, config=config)
    return response.text

# --- Interface Principal ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")
    st.caption("Licenciado em Matemática (UERJ), Mestre pelo PROFMAT/UERJ.")
    st.divider()
    st.info("💡 Materiais baseados na PHC.")

st.title("📚 Gerador de Aulas")
st.markdown("""
<div class="author-card">
  <div class="author-name">Desenvolvido por Prof. Me. Eric Souza da Silva</div>
  <div class="author-desc">Plataforma pedagógica sob a perspectiva da PHC e Hegemonia Gramsciana.</div>
</div>
""", unsafe_allow_html=True)

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.text_input("🔑 Chave API Gemini:", type="password")

col_disc, col_ano = st.columns(2)
with col_disc: disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática")
with col_ano: ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 9º ano")
assunto = st.text_input("Assunto", placeholder="Ex: Potenciação")
codigo_bncc = st.text_input("🎯 BNCC (opcional)")

for chave in ("conteudo_md", "ultima_disciplina", "ultimo_ano", "ultimo_assunto"):
    if chave not in st.session_state: st.session_state[chave] = None if chave == "conteudo_md" else ""

if st.button("✨ Gerar Material Didático"):
    if not api_key or not disciplina or not ano_escolar or not assunto:
        st.warning("Preencha todos os campos.")
    else:
        try:
            with st.spinner("🧠 Gerando conteúdo..."):
                client = get_gemini_client(api_key)
                st.session_state.conteudo_md = gerar_conteudo_phc(client, disciplina, ano_escolar, assunto, codigo_bncc)
                st.session_state.ultima_disciplina, st.session_state.ultimo_ano, st.session_state.ultimo_assunto = disciplina, ano_escolar, assunto
            st.success("✅ Gerado!")
        except Exception as e: st.error(f"❌ Erro: {e}")

if st.session_state.conteudo_md:
    st.divider()
    with st.expander("📄 Visualizar texto completo", expanded=True):
        st.markdown(st.session_state.conteudo_md)
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
