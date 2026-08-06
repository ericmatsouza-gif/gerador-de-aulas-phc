# FUNCIONA
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
CODECOGS_URL = "https://latex.codecogs.com/png.image?"


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
    Insere PNG LaTeX preservando a linha de base ou forçando quebra em fórmulas de bloco (display).
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
            h = min(h_px * px_to_mm, 12.0)
            w = h * (w_px / h_px)

            # Força a quebra de linha e vai para a margem esquerda antes do bloco
            pdf.ln(6.5)
            pdf.set_x(pdf.l_margin)

            x_centro = pdf.l_margin + (pdf.epw - w) / 2
            pdf.image(tmp_path, x=x_centro, y=pdf.get_y(), h=h, w=w)

            # Avança a altura da imagem + espaçamento e reseta o X
            pdf.set_y(pdf.get_y() + h + 3)
            pdf.set_x(pdf.l_margin)
        else:
            # Salva o Y original da linha antes de inserir a imagem inline
            y_base = pdf.get_y()

            # Espaçamento de guarda antes da imagem
            pdf.set_x(pdf.get_x() + 0.8)

            h = min(h_px * px_to_mm, 4.0)
            w = h * (w_px / h_px)

            # Se a imagem extrapolar a margem direita, faz quebra de linha
            if pdf.get_x() + w > pdf.w - pdf.r_margin:
                pdf.ln(6.5)
                pdf.set_x(pdf.l_margin)
                y_base = pdf.get_y()

            # Posiciona verticalmente para alinhar com o centro do texto
            y_img = y_base + (6.5 - h) / 2
            x_img = pdf.get_x()

            pdf.image(tmp_path, x=x_img, y=y_img, h=h, w=w)

            # Restaura exatamente a coordenada Y original da linha de texto
            pdf.set_xy(x_img + w + 1.2, y_base)
    finally:
        os.unlink(tmp_path)


# ── TOKENIZADOR ───────────────────────────────────────────────────────────────
def tokenizar_linha(texto: str) -> list[dict]:
    """
    Divide uma linha em tokens (texto, display $$, inline $).
    """
    tokens = []
    i = 0
    buf = ""
    n = len(texto)

    while i < n:

        # ── Display $$...$$ ──────────────────────────────────────────────────
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

        # ── Inline $...$ ─────────────────────────────────────────────────────
        if texto[i] == "$":
            precedido = i > 0 and (texto[i - 1].isalpha() or texto[i - 1].isdigit())
            seguido_valido = (i + 1 < n) and texto[i + 1] not in (" ", "\t", "")

            if not precedido and seguido_valido:
                j = i + 1
                fechamento = -1
                while j < n:
                    if texto[j] == "$":
                        prec_ok = texto[j - 1] != " "
                        segu = texto[j + 1] if j + 1 < n else ""
                        segu_ok = segu == "" or not segu.isalnum()
                        if prec_ok and segu_ok:
                            fechamento = j
                            break
                    j += 1

                if fechamento != -1:
                    if buf:
                        tokens.append({"tipo": "texto", "conteudo": buf})
                        buf = ""
                    tokens.append({"tipo": "inline", "conteudo": texto[i + 1:fechamento]})
                    i = fechamento + 1
                    continue

        buf += texto[i]
        i += 1

    if buf:
        tokens.append({"tipo": "texto", "conteudo": buf})

    return tokens


# ── RENDERER DE TEXTO ─────────────────────────────────────────────────────────
class TextRenderer:
    """Renderiza texto puro tratando **negrito** e *itálico*, removendo marcadores e sanitizando caracteres."""

    def __init__(self, pdf: FPDF, font_name: str = "DejaVu", base_size: float = 10):
        self.pdf = pdf
        self.font_name = font_name
        self.base_size = base_size
        self.lh = 6.5

    def _set(self, style: str = ""):
        try:
            self.pdf.set_font(self.font_name, style, self.base_size)
        except Exception:
            self.pdf.set_font("helvetica", style, self.base_size)

    def _encode(self, t: str) -> str:
        # Substitui travessões longos (—) e médios (–) por hífen simples (-)
        t = t.replace("—", "-").replace("–", "-")

        if self.pdf.font_family.lower() == "helvetica":
            return t.encode("latin-1", "replace").decode("latin-1")
        return t

    def write_span(self, text: str):
        partes = re.split(r'(\*\*|\*)', text)
        bold = False
        italic = False

        for p in partes:
            if p == "**":
                bold = not bold
                continue
            elif p == "*":
                italic = not italic
                continue

            if not p:
                continue

            style = ""
            if bold: style += "B"
            if italic: style += "I"

            self._set(style)
            limpo = p.replace("*", "")
            if limpo:
                self.pdf.write(self.lh, self._encode(limpo))

        self._set("")


# ── RENDERIZAÇÃO DE TOKENS ────────────────────────────────────────────────────
def _renderizar_tokens(pdf: FPDF, renderer: TextRenderer, texto: str):
    """Processa tokens de uma linha intercalando texto e imagens LaTeX."""
    tokens = tokenizar_linha(texto)
    for tok in tokens:
        if tok["tipo"] == "texto":
            renderer.write_span(tok["conteudo"])
        elif tok["tipo"] in ("inline", "display"):
            is_display = tok["tipo"] == "display"
            png = latex_para_png(tok["conteudo"])
            if png:
                inserir_imagem_latex(pdf, png, is_display)
            else:
                renderer.write_span(tok["conteudo"])


# ── CLASSE PDF ────────────────────────────────────────────────────────────────
class PDFMaterial(FPDF):
    def __init__(self, disciplina: str, ano_escolar: str, assunto: str):
        super().__init__()
        self.disciplina = disciplina
        self.ano_escolar = ano_escolar
        self.assunto = assunto
        if FONT_DIR:
            self.add_font("DejaVu", style="", fname=os.path.join(FONT_DIR, "DejaVuSans.ttf"))
            self.add_font("DejaVu", style="B", fname=os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
            self.add_font("DejaVu", style="I", fname=os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf"))

    def header(self):
        # Renderiza o cabeçalho APENAS na primeira página
        if self.page_no() == 1:
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
        self.cell(0, 10, f"Página {self.page_no()}/{'{nb}'}", align="R")


# ── COMPILADOR PDF ────────────────────────────────────────────────────────────
def compilar_pdf(texto_md: str, disciplina: str,
                 ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    fonte = "DejaVu" if FONT_DIR else "helvetica"
    renderer = TextRenderer(pdf, font_name=fonte, base_size=10)
    W = pdf.epw

    def set_fonte(bold=False, size=10):
        try:
            pdf.set_font(fonte, "B" if bold else "", size)
        except Exception:
            pdf.set_font("helvetica", "B" if bold else "", size)

    for linha_raw in texto_md.split("\n"):
        linha = linha_raw.rstrip()
        s = linha.strip()

        if not s:
            pdf.ln(3)
            continue

        # H1
        if s.startswith("# "):
            # Força a quebra de página se for o Gabarito
            if "GABARITO COMENTADO" in s.upper():
                pdf.add_page()
            else:
                pdf.ln(4)

            pdf.set_fill_color(41, 128, 185)
            set_fonte(bold=True, size=11)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(W, 8, f"  {s[2:]}", fill=True,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(44, 62, 80)
            pdf.ln(3)
            continue

        # H2
        if s.startswith("## "):
            pdf.ln(3)
            set_fonte(bold=True, size=10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(W, 7, s[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(41, 128, 185)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
            continue

        # H3/H4
        if re.match(r'^#{3,4}\s+', s):
            conteudo = re.sub(r'^#{3,4}\s+', '', s)
            pdf.ln(2)
            set_fonte(bold=True, size=10)
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

        # Lista: -, *, •, 1., a)
        match_list = re.match(r'^(\s*)([-•]|\d+\.|\w\))\s+', linha)
        if match_list:
            bullet = match_list.group(2)
            indent = len(match_list.group(1)) * 2 + 5
            conteudo = linha[len(match_list.group(0)):]
            pdf.set_x(pdf.l_margin + indent - 3)
            set_fonte(bold=False, size=10)
            pdf.set_text_color(44, 62, 80)
            pdf.write(renderer.lh, bullet + " ")
            _renderizar_tokens(pdf, renderer, conteudo)
            pdf.ln(renderer.lh + 1)
            continue

        # Linha normal
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(44, 62, 80)
        set_fonte(bold=False, size=10)
        _renderizar_tokens(pdf, renderer, s)
        pdf.ln(renderer.lh + 1)

    return bytes(pdf.output())
# ── GEMINI ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def gerar_conteudo_phc(client, disciplina: str, ano_escolar: str,
                       assunto: str, nivel_dificuldade: str = "Intermediário",
                       codigo_bncc: str = "") -> str:
    
    bncc_str = f"com referência à BNCC: {codigo_bncc}" if codigo_bncc else ""
    
    prompt = f"""Você é um professor de {disciplina} do {ano_escolar} seguindo a Pedagogia Histórico-Crítica (PHC).

Gere um plano de aula completo sobre "{assunto}" {bncc_str}.

NÍVEL DE DIFICULDADE DO MATERIAL: {nivel_dificuldade.upper()}
- Ajuste a profundidade dos conceitos, a complexidade dos problemas e a linguagem pedagógica para o nível {nivel_dificuldade}.
- Se {nivel_dificuldade} == Prefeitura Municipal de Casimiro de Abreu: o nível é abaixo do básico.

Estrutura obrigatória (use exatamente estes cabeçalhos):
# 1. Prática Social
# 2. Fixação
# 3. Leitura Crítica
# 4. Gabarito

REGRAS RIGOROSAS DE FORMATAÇÃO (PROIBIÇÕES E OBRIGAÇÕES):
- NUNCA deixe explicito, a palavra 'autogoverno', 'pedagogia histórico-crítica' e 'escola pública'
- NUNCA use blocos de código (triplas crases ```) para formatar texto, exemplos ou matemática.
- NUNCA escreva notação matemática solta no texto como 3^0, 3^1, x^2. Use SEMPRE a notação LaTeX embutida: $3^0$, $3^1$, $x^2$.
- Para exibições em listas ou passos organizados, use listas comuns do Markdown (com traço "-") e insira as variáveis/expressões em LaTeX. Exemplo:
  - Instante $t = 0$: 1 pessoa original ($3^0$)
  - Instante $t = 1$: 3 novas pessoas ($3^1$)
- Use LaTeX ($...$) para QUALQUER variável, expressão, fórmula, igualdade ou notação de potência/radiciação no texto (ex: $t = 0$, $x$, $A = l^2$).
- Expressões matemáticas em destaque (fórmulas, equações em bloco próprio): $$expressão$$ — exemplo: $$M = C \\cdot (1+i)^t$$
- Use notação LaTeX padrão: \\frac{{num}}{{den}}, \\sqrt{{x}}, \\sqrt[3]{{x}}, x^{{2}}, \\cdot, \\pm, \\leq, \\geq
- NUNCA coloque números isolados ou texto simples dentro de $ (escreva "3 voltas", "4 lados" normalmente como texto).
- NÃO use $ para indicar moeda (escreva "reais", "R$" com espaço após o símbolo, ou "BRL").
- Negrito para termos importantes: **termo**.
- Texto corrido em português fora dos delimitadores matemáticos.
"""
    config = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite", contents=prompt, config=config
    )
    return response.text


# ── INTERFACE ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")
    st.caption("""Licenciado em Matemática (UERJ), Mestre em Matemática pelo PROFMAT/UERJ e especialista em Tecnologias Digitais Aplicadas ao Ensino (IFRJ).

Professor de Matemática da Prefeitura de Macaé (Matrícula nº 48.836) e da Prefeitura de Casimiro de Abreu (Matrícula nº 15.035).

Atua em Educação Matemática, Tecnologias Digitais no Ensino, História da Educação Matemática, Políticas Públicas, Educação Ambiental e Esquemas Colaborativos na Educação.""")
    
    st.divider()
    
    st.markdown("### 📞 Contato & Suporte")
    st.markdown("📧 **E-mail:** [ericmatsouza@gmail.com](mailto:ericmatsouza@gmail.com)")
    st.markdown("💬 **WhatsApp:** [(21) 97048-1891](https://wa.me/5521970481891)")
    
    # A gracinha sobre o PIX no WhatsApp 😉
    st.info(
        "💡 **Dica do Prof:** O número do WhatsApp também funciona como **Chave PIX**! "
        "Se o gerador te economizou horas de planejamento, o café virtual é sempre bem-vindo! ☕😉"
    )

st.title("Gerador de Aulas")
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

col_disc, col_ano, col_dif = st.columns(3)
with col_disc:
    disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática")
with col_ano:
    ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 9º ano")
with col_dif:
    nivel_dificuldade = st.selectbox(
        "Nível de Dificuldade",
        options=["Prefeitura Municipal de Casimiro de Abreu", "Básico", "Intermediário", "Avançado"]
    )

assunto = st.text_input("Assunto", placeholder="Ex: Potenciação")
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
                st.session_state.conteudo_md = gerar_conteudo_phc(
                    client,
                    disciplina,
                    ano_escolar,
                    assunto,
                    nivel_dificuldade,
                    codigo_bncc,
                )
                st.session_state.ultima_disciplina = disciplina
                st.session_state.ultimo_ano = ano_escolar
                st.session_state.ultimo_assunto = assunto
            st.success("✅ Material gerado com sucesso!")
        except APIError as e:
            erro_msg = str(e).lower()
            if "429" in erro_msg or "resource_exhausted" in erro_msg:
                st.error("⏳ Limite de requisições atingido (Cota Gratuita). Por favor, aguarde alguns minutos antes de tentar novamente.")
            elif "503" in erro_msg or "unavailable" in erro_msg:
                st.error("⚠️ Servidor ocupado no momento. Tente novamente em alguns segundos.")
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
