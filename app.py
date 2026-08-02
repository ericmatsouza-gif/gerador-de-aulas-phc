import os
import re
import streamlit as st
from google import genai
from google.genai.errors import APIError
from fpdf import FPDF
import matplotlib

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

# ── FONTES DejaVu (TTF Unicode) ───────────────────────────────────────────────
def _localizar_fontes_dejavu() -> str:
    sistema = "/usr/share/fonts/truetype/dejavu"
    if os.path.isfile(os.path.join(sistema, "DejaVuSans.ttf")):
        return sistema + "/"
    mpl_dir = os.path.join(
        os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"
    )
    if os.path.isfile(os.path.join(mpl_dir, "DejaVuSans.ttf")):
        return mpl_dir + "/"
    raise FileNotFoundError(
        "Fontes DejaVu não encontradas. Instale fonts-dejavu-core ou matplotlib."
    )

FONT_DIR = _localizar_fontes_dejavu()


# ── CACHE DO CLIENTE GEMINI ────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


# ── LIMPEZA E FORMATAÇÃO MATEMÁTICA PARA PDF ───────────────────────────────────
def sanitizar(texto: str) -> str:
    """
    Remove resíduos de LaTeX, cifrões e formata a matemática de forma 
    100% limpa e compatível com as fontes DejaVu do FPDF.
    """
    if not texto:
        return ""

    # 1. Remove qualquer cifrão de LaTeX
    texto = texto.replace('$', '')

    # 2. Limpa comandos e tags LaTeX comuns que causam ruído
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'(\1-ésima raiz de \2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', texto)
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)

    # 3. Mapeamento de sobrescritos comuns para potências elegantes
    sobrescritos = {
        '^0': '⁰', '^1': '¹', '^2': '²', '^3': '³', '^4': '⁴',
        '^5': '⁵', '^6': '⁶', '^7': '⁷', '^8': '⁸', '^9': '⁹',
        '^n': 'ⁿ', '^m': 'ᵐ', '^k': 'ᵏ', '^x': 'ˣ', '^t': 'ᵗ',
        '^(m+n)': 'ᵐ⁺ⁿ', '^(m-n)': 'ᵐ⁻ⁿ', '^(m.n)': 'ᵐ·ⁿ', '^(m·n)': 'ᵐ·ⁿ'
    }
    for orig, sub in sobrescritos.items():
        texto = texto.replace(orig, sub)

    # 4. Ajustes finos em símbolos
    texto = texto.replace('\\cdot', '.').replace('*', '.')
    texto = texto.replace('`', '')
    
    # 5. Remove espaços múltiplos e parênteses desnecessários resultantes
    texto = re.sub(r'\s+', ' ', texto)

    return texto


# ── CLASSE PDF ─────────────────────────────────────────────────────────────────
class PDFMaterial(FPDF):
    def __init__(self, disciplina: str, ano_escolar: str, assunto: str):
        super().__init__()
        self.disciplina  = disciplina
        self.ano_escolar = ano_escolar
        self.assunto     = assunto
        self.add_font("DejaVu",  style="",  fname=FONT_DIR + "DejaVuSans.ttf")
        self.add_font("DejaVu",  style="B", fname=FONT_DIR + "DejaVuSans-Bold.ttf")
        self.add_font("DejaVuI", style="",  fname=FONT_DIR + "DejaVuSerif-Italic.ttf")

    def header(self):
        self.set_font("DejaVu", "B", 12)
        self.set_text_color(26, 42, 58)
        self.cell(0, 6, "PLANO DE AULA E MATERIAL DIDÁTICO", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("DejaVu", "B", 8.5)
        self.set_text_color(41, 128, 185)
        subtitulo = f"{self.disciplina.upper()} | {self.ano_escolar} | Assunto: {self.assunto}"
        self.cell(0, 5, subtitulo, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(44, 62, 80)

    def footer(self):
        self.set_y(-14)
        self.set_font("DejaVuI", "", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, "Elaborado por Prof. Me. Eric Souza | PHC", align="L")
        self.set_font("DejaVu", "", 8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="R")


# ── ESCREVER PARÁGRAFO COM NEGRITO INLINE ──────────────────────────────────────
def escrever_texto_formatado(pdf: FPDF, texto: str, recuo_x: float = 0):
    pdf.set_x(pdf.l_margin + recuo_x)
    partes = re.split(r'(\*\*.*?\*\*)', texto)
    
    for parte in partes:
        if not parte:
            continue
        if parte.startswith('**') and parte.endswith('**'):
            conteudo = parte[2:-2]
            pdf.set_font("DejaVu", "B", 10)
        else:
            conteudo = parte
            pdf.set_font("DejaVu", "", 10)
        
        pdf.write(5.5, conteudo)
    pdf.ln(6)


# ── COMPILADOR PDF ─────────────────────────────────────────────────────────────
def compilar_pdf(texto_md: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    W = pdf.epw

    for linha_raw in texto_md.split('\n'):
        linha = sanitizar(linha_raw.rstrip())
        s = linha.strip()

        if not s:
            pdf.ln(2)
            continue

        # H1 ─ Seção Principal
        if re.match(r'^# ', s):
            texto_h = re.sub(r'^# ', '', s)
            pdf.ln(3)
            pdf.set_fill_color(41, 128, 185)
            pdf.set_font("DejaVu", "B", 11)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(W, 7.5, f"  {texto_h}", fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(44, 62, 80)
            pdf.ln(2.5)

        # H2 ─ Subseção
        elif re.match(r'^## ', s):
            texto_h = re.sub(r'^## ', '', s)
            pdf.ln(2.5)
            pdf.set_font("DejaVu", "B", 10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(W, 6, texto_h, new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(41, 128, 185)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.set_text_color(44, 62, 80)
            pdf.ln(2)

        # H3 / H4 ─ Sub-subseção
        elif re.match(r'^#{3,4}\s+', s):
            texto_h = re.sub(r'^#{3,4}\s+', '', s)
            pdf.ln(1.5)
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(41, 128, 185)
            pdf.multi_cell(W, 5.5, texto_h)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(1)

        # Items de Lista (- ou * ou números)
        elif re.match(r'^[-*]\s+', s):
            texto_item = re.sub(r'^[-*]\s+', '', s)
            pdf.set_x(pdf.l_margin + 3)
            pdf.set_font("DejaVu", "", 10)
            pdf.write(5.5, "• ")
            escrever_texto_formatado(pdf, texto_item, recuo_x=7)

        # Parágrafos comuns
        else:
            escrever_texto_formatado(pdf, s, recuo_x=0)

    return bytes(pdf.output())


# ── GERAÇÃO DE CONTEÚDO VIA GEMINI ────────────────────────────────────────────
# ── GERAÇÃO DE CONTEÚDO VIA GEMINI COM FALLBACK AUTOMÁTICO ────────────────────
def gerar_conteudo_phc(client: genai.Client, disciplina: str,
                       ano_escolar: str, assunto: str,
                       codigo_bncc: str = "") -> str:
    bloco_bncc = ""
    if codigo_bncc.strip():
        bloco_bncc = f"""
    ALINHAMENTO CURRICULAR OBRIGATÓRIO:
    - Alinhe este material à habilidade BNCC: **{codigo_bncc.strip().upper()}**.
    - Cite o código e sua descrição na abertura da Seção 1.
    - Todos os exercícios devem desenvolver especificamente essa habilidade.
    """

    prompt = f"""
    Você é um professor especialista em Didática sob o referencial da
    PEDAGOGIA HISTÓRICO-CRÍTICA e da TEORIA GRAMSCIANA DA HEGEMONIA.

    Elabore um material de aula completo e profundo para:
    - Disciplina: {disciplina}
    - Ano/Série: {ano_escolar}
    - Conteúdo/Assunto: {assunto}
    {bloco_bncc}

    ORIENTAÇÃO PEDAGÓGICO-POLÍTICA OBRIGATÓRIA:
    1. O conhecimento científico/escolar deve ser tratado como um saber sistematizado, produzido
       historicamente pela humanidade para responder a necessidades concretas de sobrevivência,
       trabalho e organização social.
    2. A propriedade dos conceitos deve ser apresentada como ferramenta de LEITURA CRÍTICA DA
       REALIDADE, capacitando os sujeitos (especialmente das classes populares) para o AUTOGOVERNO,
       a interpretação da sociedade e a tomada de decisão autônoma.
    3. Rompa com a dualidade do ensino: entregue RIGOR TÉCNICO-CIENTÍFICO unido à CONSCIÊNCIA CRÍTICA.

    Siga ESTRITAMENTE a estrutura abaixo:

    # 1. PRÁTICA SOCIAL E GÊNESE HISTÓRICA DO CONTEÚDO
    - Apresente a origem social e a necessidade histórica deste conceito.
    - Aponte a relevância para o mundo contemporâneo (trabalho, economia, política, cidadania).
    - Definição rigorosa, formal e conceitual, com propriedades e leis.

    # 2. EXERCÍCIOS DE FIXAÇÃO E DOMÍNIO CONCEITUAL
    - Questões de aplicação rigorosa dos conceitos e fórmulas.

    # 3. DESAFIOS DE LEITURA CRÍTICA E CONTRA-HEGEMONIA
    - Questões contextualizadas em dados reais ou plausíveis da sociedade.
    - Exija interpretação, argumentação e decisão crítica com base no conhecimento.

    # 4. GABARITO COMENTADO E PEDAGÓGICO
    - Resolução passo a passo com justificativa técnica e reflexão pedagógica.

    REGRAS DE FORMATAÇÃO E NOTAÇÃO MATEMÁTICA DIDÁTICA (MUITO IMPORTANTE):
    - É STRICTLY PROIBIDO usar código LaTeX (NÃO use $, $$, \\frac, \\sqrt, \\cdot, \\ge, etc).
    - É PROIBIDO usar notação de programação como a^n ou raiz_n(a).
    - As equações devem ser escritas de forma textual e limpa para alunos do Ensino Fundamental:
      * Potências: use a², a³, aⁿ, aᵐ⁺ⁿ, aᵐ⁻ⁿ, 2⁶.
      * Radicais: use √144 = 12, √x, ³√27 = 3, raiz n-ésima de a, raiz cúbica de x.
      * Multiplicação: use o ponto simples (.) ou x. Exemplo: a . b
      * Divisão: use / ou ÷. Exemplo: a / b
    - Use ## para subseções dentro de cada seção principal.
    - Use **negrito** para termos técnicos e enunciados.
    - NÃO inclua saudações. Comece direto no título '# 1. PRÁTICA SOCIAL E GÊNESE HISTÓRICA DO CONTEÚDO'.
    """

    # Lista de modelos ordenada por prioridade (incluindo gemini-flash-latest)
    modelos = [
        'gemini-flash-latest',
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-2.5-pro'
    ]
    
    ultimo_erro = None
    for modelo in modelos:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt,
            )
            return response.text
        except APIError as e:
            msg_erro = str(e).upper()
            # Captura erros de cota (429/quota), indisponibilidade (503/unavailable) e modelo inexistente (404/not_found)
            if any(codigo in msg_erro for codigo in ["503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "QUOTA"]):
                ultimo_erro = e
                continue  # Pula para o próximo modelo da lista
            raise e
            
    if ultimo_erro:
        raise ultimo_erro
# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")
    st.caption(
        "Licenciado em Matemática (UERJ), Mestre em Matemática pelo PROFMAT/UERJ. "
        "Professor de Matemática das redes de Macaé e Casimiro de Abreu."
    )
    st.divider()
    st.subheader("📬 Contato & Suporte")
    st.markdown("💬 **WhatsApp:** [(21) 97048-1891](https://wa.me/5521970481891)")
    st.markdown("✉️ **E-mail:** [ericmatsouza@gmail.com](mailto:ericmatsouza@gmail.com)")
    st.divider()
    st.info("💡 Materiais didáticos fundamentados na Pedagogia Histórico-Crítica e Hegemonia Gramsciana.")

# ── INTERFACE PRINCIPAL ────────────────────────────────────────────────────────
st.title("📚 Gerador de Aulas")

st.markdown("""
<div class="author-card">
  <div class="author-name">👨‍🏫 Desenvolvido por Prof. Me. Eric Souza da Silva</div>
  <div class="author-desc">Plataforma pedagógica para elaboração de materiais didáticos multidisciplinares sob
  a perspectiva da <b>Pedagogia Histórico-Crítica</b> e <b>Hegemonia Gramsciana</b>.</div>
  <div>
    <a href="https://wa.me/5521970481891" target="_blank" class="contact-badge contact-badge-wa">📱 (21) 97048-1891</a>
    <a href="mailto:ericmatsouza@gmail.com" class="contact-badge">✉️ ericmatsouza@gmail.com</a>
  </div>
</div>
""", unsafe_allow_html=True)

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.text_input("🔑 Informe sua chave da API do Gemini para começar:", type="password")

col_disc, col_ano = st.columns(2)
with col_disc:
    disciplina  = st.text_input("Disciplina / Componente Curricular",
                                placeholder="Ex: Matemática, História, Física...")
with col_ano:
    ano_escolar = st.text_input("Ano / Série",
                                placeholder="Ex: 8º ano, 1º ano do EM...")

assunto = st.text_input("Assunto / Conteúdo Específico",
                        placeholder="Ex: Potenciação e Radiciação, Revolução Industrial...")

codigo_bncc = st.text_input(
    "🎯 Código de Habilidade BNCC (opcional)",
    placeholder="Ex: EF07MA01, EF09CI08...",
    help="Quando preenchido, o material será alinhado a esta habilidade da BNCC."
)

for chave in ("conteudo_md", "ultima_disciplina", "ultimo_ano", "ultimo_assunto"):
    if chave not in st.session_state:
        st.session_state[chave] = None if chave == "conteudo_md" else ""

# ── BOTÃO DE GERAÇÃO ───────────────────────────────────────────────────────────
if st.button("✨ Gerar Material Didático"):
    if not api_key:
        st.error("Por favor, informe a chave da API do Gemini para continuar.")
    elif not disciplina or not ano_escolar or not assunto:
        st.warning("Preencha a Disciplina, Ano/Série e o Assunto antes de gerar.")
    else:
        try:
            with st.spinner("🧠 Elaborando o plano de aula crítico via Gemini..."):
                client      = get_gemini_client(api_key)
                conteudo_md = gerar_conteudo_phc(client, disciplina, ano_escolar,
                                                 assunto, codigo_bncc)

            st.session_state.conteudo_md       = conteudo_md
            st.session_state.ultima_disciplina = disciplina
            st.session_state.ultimo_ano        = ano_escolar
            st.session_state.ultimo_assunto    = assunto
            st.success("✅ Conteúdo gerado! Revise o texto abaixo antes de compilar o PDF.")

        except APIError as e:
            erro = str(e).lower()
            if "quota" in erro or "429" in erro or "rate" in erro:
                st.error("⚠️ Limite de requisições atingido (quota). Aguarde alguns minutos e tente novamente.")
            elif "401" in erro or "403" in erro or "api_key" in erro or "authentication" in erro:
                st.error("🔑 Chave de API inválida ou sem permissão. Verifique sua GEMINI_API_KEY.")
            else:
                st.error(f"❌ Erro de comunicação com a API Gemini: {e}")
        except (ConnectionError, TimeoutError) as e:
            st.error(f"🌐 Erro de rede: não foi possível conectar ao servidor do Gemini. ({e})")
        except Exception as e:
            st.error(f"❌ Erro inesperado ao contatar a API: {e}")

# ── PREVIEW + EXPORTAÇÕES ─────────────────────────────────────────────────────
if st.session_state.conteudo_md:
    disc = st.session_state.ultima_disciplina
    ano  = st.session_state.ultimo_ano
    ass  = st.session_state.ultimo_assunto
    md   = st.session_state.conteudo_md

    st.divider()
    st.subheader("👀 Preview do Conteúdo Gerado")
    st.caption("Revise o texto abaixo. Quando estiver satisfeito, exporte nas opções abaixo.")

    with st.expander("📄 Visualizar texto completo", expanded=True):
        st.markdown(md)

    st.divider()
    st.subheader("📥 Exportar Material")
    col_pdf, col_md = st.columns(2)

    with col_pdf:
        try:
            pdf_bytes = compilar_pdf(md, disc, ano, ass)
            st.download_button(
                label="🖨️ Baixar PDF Pronto",
                data=pdf_bytes,
                file_name=f"Aula_{disc}_{ass.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"❌ Erro na compilação do PDF: {e}")

    with col_md:
        st.download_button(
            label="⬇️ Baixar Markdown (.md)",
            data=md.encode("utf-8"),
            file_name=f"Aula_{disc}_{ass.replace(' ', '_')}.md",
            mime="text/markdown"
        )
        st.caption("Edite no Obsidian, Notion, Typora ou qualquer editor Markdown.")

# ── RODAPÉ ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  © Desenvolvido por <b>Prof. Mestre Eric Souza da Silva</b><br>
  Dúvidas ou suporte?
  <a href="https://wa.me/5521970481891" target="_blank">WhatsApp</a> ou
  <a href="mailto:ericmatsouza@gmail.com">E-mail</a>.
</div>
""", unsafe_allow_html=True)
