# FUNCIONA - v2 com abas: Aula + Exercícios
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

/* ===== BOTÕES ===== */
.stButton>button {
    width: 100%;
    background-color: #2980b9;
    color: white;
    font-weight: bold;
    height: 3.2em;
    border-radius: 8px;
    border: none;
    font-size: 16px;
}

.stButton>button:hover {
    background-color: #1f6391;
    color: white;
}


/* ===== CARD DO AUTOR ===== */
.author-card {
    background-color: #f8f9fa;
    border-left: 4px solid #2980b9;
    padding: 15px;
    border-radius: 6px;
    margin-bottom: 25px;
}

.author-name {
    font-size: 1.1rem;
    font-weight: bold;
    color: #1a2a3a;
    margin-bottom: 4px;
}

.author-desc {
    font-size: 0.9rem;
    color: #555;
    margin-bottom: 10px;
}


/* ===== RODAPÉ ===== */
.footer {
    margin-top: 50px;
    padding-top: 20px;
    border-top: 1px solid #e0e0e0;
    text-align: center;
    font-size: 0.85rem;
    color: #7f8c8d;
}


/* ===== LARGURA DA SIDEBAR ===== */
section[data-testid="stSidebar"] {
    min-width: 320px !important;
    max-width: 320px !important;
}

/* ===== ESPAÇO NO TOPO DA SIDEBAR ===== */
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem;
}

/* ===== NOME DO AUTOR ===== */
.author-name-sidebar {
    margin-top: -0.8rem;
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
    params = f"\\dpi{{{dpi}}}\\bg{{white}}{expr}"
    try:
        resp = requests.get(CODECOGS_URL + requests.utils.quote(params), timeout=8)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def inserir_imagem_latex(pdf: FPDF, png_bytes: bytes, is_display: bool):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name

    try:
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(png_bytes)) as img:
            w_px, h_px = img.size

        px_to_mm = 0.22

        if is_display:
            h = min(h_px * px_to_mm, 12.0)
            w = h * (w_px / h_px)
            pdf.ln(6.5)
            pdf.set_x(pdf.l_margin)
            x_centro = pdf.l_margin + (pdf.epw - w) / 2
            pdf.image(tmp_path, x=x_centro, y=pdf.get_y(), h=h, w=w)
            pdf.set_y(pdf.get_y() + h + 3)
            pdf.set_x(pdf.l_margin)
        else:
            y_base = pdf.get_y()
            pdf.set_x(pdf.get_x() + 0.8)
            h = min(h_px * px_to_mm, 4.0)
            w = h * (w_px / h_px)
            if pdf.get_x() + w > pdf.w - pdf.r_margin:
                pdf.ln(6.5)
                pdf.set_x(pdf.l_margin)
                y_base = pdf.get_y()
            y_img = y_base + (6.5 - h) / 2
            x_img = pdf.get_x()
            pdf.image(tmp_path, x=x_img, y=y_img, h=h, w=w)
            pdf.set_xy(x_img + w + 1.2, y_base)
    finally:
        os.unlink(tmp_path)


# ── TOKENIZADOR ───────────────────────────────────────────────────────────────
def tokenizar_linha(texto: str) -> list[dict]:
    tokens = []
    i = 0
    buf = ""
    n = len(texto)

    while i < n:
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


# ── CLASSE PDF BASE ───────────────────────────────────────────────────────────
class PDFBase(FPDF):
    def __init__(self, titulo_cabecalho: str, subtitulo_cabecalho: str):
        super().__init__()
        self._titulo_cab = titulo_cabecalho
        self._subtitulo_cab = subtitulo_cabecalho
        if FONT_DIR:
            self.add_font("DejaVu", style="", fname=os.path.join(FONT_DIR, "DejaVuSans.ttf"))
            self.add_font("DejaVu", style="B", fname=os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
            self.add_font("DejaVu", style="I", fname=os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf"))

    def header(self):
        if self.page_no() == 1:
            fonte = "DejaVu" if FONT_DIR else "helvetica"
            self.set_font(fonte, "B", 12)
            self.set_text_color(26, 42, 58)
            self.cell(0, 10, self._titulo_cab,
                      align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font(fonte, "B", 9)
            self.set_text_color(41, 128, 185)
            self.cell(0, 5, self._subtitulo_cab,
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


# ── COMPILADOR PDF GENÉRICO ───────────────────────────────────────────────────
def _compilar_pdf_generico(texto_md: str, titulo_cab: str, subtitulo_cab: str,
                            marcador_nova_pagina: str = "GABARITO") -> bytes:
    pdf = PDFBase(titulo_cab, subtitulo_cab)
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

        if s.startswith("# "):
            if marcador_nova_pagina and marcador_nova_pagina.upper() in s.upper():
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

        if s.startswith("## "):
            pdf.ln(3)
            set_fonte(bold=True, size=10.5)
            pdf.set_text_color(26, 42, 58)
            pdf.cell(W, 7, s[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(41, 128, 185)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
            continue

        if re.match(r'^#{3,4}\s+', s):
            conteudo = re.sub(r'^#{3,4}\s+', '', s)
            pdf.ln(2)
            set_fonte(bold=True, size=10)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(W, 6, conteudo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            continue

        if re.match(r'^-{3,}$', s):
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
            continue

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

        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(44, 62, 80)
        set_fonte(bold=False, size=10)
        _renderizar_tokens(pdf, renderer, s)
        pdf.ln(renderer.lh + 1)

    return bytes(pdf.output())


def compilar_pdf(texto_md: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    titulo = "PLANO DE AULA E MATERIAL DIDÁTICO"
    subtitulo = f"{disciplina.upper()} | {ano_escolar} | Assunto: {assunto}"
    return _compilar_pdf_generico(texto_md, titulo, subtitulo, marcador_nova_pagina="GABARITO COMENTADO")


def compilar_pdf_exercicios(texto_md: str, disciplina: str,
                             ano_escolar: str, assunto: str) -> bytes:
    """PDF apenas com os exercícios (sem gabarito)."""
    titulo = "LISTA DE EXERCÍCIOS"
    subtitulo = f"{disciplina.upper()} | {ano_escolar} | Assunto: {assunto}"
    # Remove tudo a partir do marcador de gabarito
    separador = re.split(r'(?mi)^#{1,2}\s+.*GABARITO.*$', texto_md)
    conteudo = separador[0].strip()
    return _compilar_pdf_generico(conteudo, titulo, subtitulo, marcador_nova_pagina="")


def compilar_pdf_gabarito(texto_md: str, disciplina: str,
                           ano_escolar: str, assunto: str) -> bytes:
    """PDF apenas com o gabarito comentado."""
    titulo = "GABARITO COMENTADO"
    subtitulo = f"{disciplina.upper()} | {ano_escolar} | Assunto: {assunto}"
    # Extrai apenas a seção de gabarito
    match = re.search(r'(?mi)^#{1,2}\s+.*GABARITO.*$', texto_md)
    if match:
        conteudo = texto_md[match.start():].strip()
    else:
        conteudo = texto_md
    return _compilar_pdf_generico(conteudo, titulo, subtitulo, marcador_nova_pagina="")


# ── GEMINI ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _tratar_erro_api(e: Exception):
    erro_str = str(e)
    if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
        st.warning(
            "⏳ **Cota de requisições atingida!**\n\n"
            "O serviço gratuito do Gemini atingiu o limite temporário por minuto (RPM). "
            "Aguarde cerca de 10 a 15 segundos e tente novamente."
        )
    elif "503" in erro_str or "unavailable" in erro_str.lower():
        st.error("⚠️ O servidor do Gemini está temporariamente ocupado. Tente novamente em instantes.")
    else:
        st.error(f"❌ Erro: {e}")


REGRAS_FORMATACAO = """
REGRAS RIGOROSAS DE FORMATAÇÃO (PROIBIÇÕES E OBRIGAÇÕES):
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

ORIENTACAO_PHC = """
ORIENTAÇÃO PEDAGÓGICO-POLÍTICA OBRIGATÓRIA:
1. O conhecimento científico/escolar deve ser tratado como um saber sistematizado, produzido
   historicamente pela humanidade para responder a necessidades concretas de sobrevivência,
   trabalho e organização social.
2. A propriedade dos conceitos deve ser apresentada como ferramenta de LEITURA CRÍTICA DA
   REALIDADE, capacitando os sujeitos (especialmente das classes populares) para o AUTOGOVERNO,
   a interpretação da sociedade e a tomada de decisão autônoma.
3. Rompa com a dualidade do ensino: entregue RIGOR TÉCNICO-CIENTÍFICO unido à CONSCIÊNCIA CRÍTICA.
4. NUNCA deixe explicito, a palavra 'autogoverno', 'pedagogia histórico-crítica' e 'escola pública'.
"""


def gerar_conteudo_phc(client, disciplina: str, ano_escolar: str,
                        assunto: str, nivel_dificuldade: str = "Intermediário",
                        codigo_bncc: str = "") -> str:
    prompt = f"""
    Você é um professor especialista em Didática sob o referencial da
    PEDAGOGIA HISTÓRICO-CRÍTICA e da TEORIA GRAMSCIANA DA HEGEMONIA.

    Elabore um material de aula completo e profundo para:
    - Disciplina: {disciplina}
    - Ano/Série: {ano_escolar}
    - Conteúdo/Assunto: {assunto}
    {f"- BNCC: {codigo_bncc}" if codigo_bncc else ""}
    - Nível de dificuldade: {nivel_dificuldade}
        - Ajuste a profundidade dos conceitos, a complexidade dos problemas e a linguagem pedagógica para o nível {nivel_dificuldade}.
        - Se {nivel_dificuldade} == 'Prefeitura Municipal de Casimiro de Abreu': o nível é abaixo do básico, contexto de escola pública do interior do RJ, salas lotadas, estudantes com dificuldades e contexto familiar delicado.

    {ORIENTACAO_PHC}

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

    {REGRAS_FORMATACAO}
    """
    config = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    response = client.models.generate_content(
        model="gemini-flash-latest", contents=prompt, config=config
    )
    return response.text


def gerar_exercicios_phc(client, disciplina: str, ano_escolar: str, assunto: str,
                          nivel_dificuldade: str, quantidade: int,
                          tipos: list[str], codigo_bncc: str = "") -> str:
    """Gera lista de exercícios + gabarito comentado em uma única chamada."""

    # Monta a instrução de tipos
    mapa_tipos = {
        "Dissertativos / resolução passo a passo": "dissertativos (resolução passo a passo)",
        "Múltipla escolha": "múltipla escolha (4 alternativas, A a D)",
        "Verdadeiro ou Falso": "verdadeiro ou falso (com justificativa obrigatória)",
    }
    tipos_str = ", ".join(mapa_tipos[t] for t in tipos if t in mapa_tipos)
    if not tipos_str:
        tipos_str = "variados"

    prompt = f"""
    Você é um professor especialista em Didática sob o referencial da
    PEDAGOGIA HISTÓRICO-CRÍTICA e da TEORIA GRAMSCIANA DA HEGEMONIA.

    Elabore uma lista de exercícios para:
    - Disciplina: {disciplina}
    - Ano/Série: {ano_escolar}
    - Conteúdo/Assunto: {assunto}
    {f"- BNCC: {codigo_bncc}" if codigo_bncc else ""}
    - Nível de dificuldade: {nivel_dificuldade}
        - Se {nivel_dificuldade} == 'Prefeitura Municipal de Casimiro de Abreu': nível abaixo do básico, contexto de escola pública do interior do RJ, salas lotadas, estudantes com dificuldades e contexto familiar delicado.

    QUANTIDADE TOTAL: {quantidade} exercícios.
    TIPOS DE EXERCÍCIOS A USAR: {tipos_str}.
    - Distribua os {quantidade} exercícios entre os tipos solicitados de forma equilibrada.
    - Para múltipla escolha: apresente as alternativas A), B), C), D) em linhas separadas.
    - Para verdadeiro ou falso: apresente a afirmação e deixe espaço para o aluno responder.
    - Para dissertativos: enuncie claramente o problema, com dados e o que se pede.

    {ORIENTACAO_PHC}

    PERSPECTIVA DOS EXERCÍCIOS:
    - Pelo menos 90% dos exercícios devem contextualizar o conteúdo em situações reais da vida
      das classes populares (trabalho, salário, consumo, saúde, território, política, ambiente 
      e questionamento reais contra o capitalismo).
    - Os demais podem ser de fixação direta do conteúdo, mas sempre com rigor conceitual.
    - Em nenhum exercício o conhecimento deve parecer neutro ou descolado da realidade social.

    Siga ESTRITAMENTE a estrutura abaixo:

    # LISTA DE EXERCÍCIOS
    ## {disciplina} | {ano_escolar} | {assunto}REGRAS RIGOROSAS DE FORMATAÇÃO (PROIBIÇÕES E OBRIGAÇÕES):
- NUNCA use blocos de código (triplas crases ```) para formatar texto, exemplos ou matemática.
- NUNCA escreva notação matemática solta no texto como 3^0, 3^1, x^2. Use SEMPRE a notação LaTeX embutida: $3^0$, $3^1$, $x^2$.
- Para exibições em listas ou passos organizados, use listas comuns do Markdown (com traço "-") e insira as variáveis/expressões em LaTeX.
- Use LaTeX ($...$) para QUALQUER variável, expressão, fórmula, igualdade ou notação de potência/radiciação no texto.
- Expressões matemáticas em destaque (fórmulas, equações em bloco próprio): $$expressão$$
- Use notação LaTeX padrão: \\frac{num}{den}, \\sqrt{x}, \\sqrt[3]{x}, x^{2}, \\cdot, \\pm, \\leq, \\geq
- NUNCA coloque números isolados ou texto simples dentro de $ (escreva "3 voltas", "4 lados" normalmente como texto).
- NÃO use $ para indicar moeda (escreva "reais", "R$" com espaço após o símbolo, ou "BRL").
- Negrito para termos importantes: **termo**.
- Texto corrido em português fora dos delimitadores matemáticos.

    [Enumere os exercícios de 1 a {quantidade}. Use "**Exercício N.**" como marcador de cada questão.]

    # GABARITO COMENTADO
    [Para cada exercício, apresente:]
    **Exercício N.**
    - **Resposta:** [resposta objetiva]
    - **Resolução:** [passo a passo técnico com LaTeX onde necessário]
    - **Comentário pedagógico PHC:** [reflexão sobre o conhecimento como ferramenta crítica,
      conectando a resolução à realidade social dos estudantes]

    {REGRAS_FORMATACAO}
    """
    config = types.GenerateContentConfig(max_output_tokens=8192, temperature=0.7)
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite", contents=prompt, config=config
    )
    return response.text


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Sobre o Autor")
    st.markdown(
    '<div class="author-name-sidebar"><strong>Prof. Me. Eric Souza da Silva</strong></div>',
    unsafe_allow_html=True
)

    st.markdown(
        """
        <div style="
            text-align: justify;
            font-size: 0.8rem;
            line-height: 1.5;
            color: rgba(250, 250, 250, 0.65);
        ">
        Licenciado em Matemática (UERJ), Mestre em Matemática pelo PROFMAT/UERJ e especialista em Tecnologias Digitais Aplicadas ao Ensino (IFRJ). <br><br>
        Professor de Matemática da Prefeitura de Macaé (Matrícula nº 48.836) e da Prefeitura de Casimiro de Abreu (Matrícula nº 15.035).<br><br>
        Atua em Educação Matemática, Tecnologias Digitais no Ensino, História da Educação Matemática, Políticas Públicas, Educação Ambiental e Esquemas Colaborativos na Educação.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    st.markdown("### 📞 Contato & Suporte")
    st.markdown("📧 **E-mail:** [ericmatsouza@gmail.com](mailto:ericmatsouza@gmail.com)")
    st.markdown("💬 **WhatsApp:** [(21) 97048-1891](https://wa.me/5521970481891)")

    st.info(
        "💡 **Dica do Prof:** O número do WhatsApp também funciona como **Chave PIX**! "
        "Se o gerador te economizou horas de planejamento, o café virtual é sempre bem-vindo! ☕😉"
    )

st.title("📚 Gerador de Aulas PHC")

st.markdown("**Prof. Me. Eric Souza da Silva**")

st.markdown(
    """
    <div style="
        background-color: rgba(128, 128, 128, 0.12);
        padding: 15px;
        border-radius: 10px;
        text-align: justify;
        line-height: 1.6;
        margin-top: 10px;
        margin-bottom: 15px;
    ">
    O material será elaborado com base na <strong>Pedagogia Histórico-Crítica (PHC)</strong> e no conceito gramsciano de <strong>hegemonia</strong>, articulando o conhecimento escolar à realidade histórica e social dos estudantes. As atividades buscarão superar a simples memorização, promovendo a problematização, a reflexão e a análise crítica dos conteúdos. Dessa forma, o estudante será incentivado a compreender o conhecimento como construção histórica e instrumento para interpretar e transformar a realidade.
    </div>
    """,
    unsafe_allow_html=True,
)

# ── API KEY ───────────────────────────────────────────────────────────────────
api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.text_input("🔑 Chave API Gemini:", type="password")

# ── SESSION STATE ─────────────────────────────────────────────────────────────
for chave, padrao in [
    ("conteudo_md", None),
    ("ultima_disciplina", ""),
    ("ultimo_ano", ""),
    ("ultimo_assunto", ""),
    ("ultimo_nivel", ""),
    ("exercicios_md", None),
    ("ex_disciplina", ""),
    ("ex_ano", ""),
    ("ex_assunto", ""),
    ("ex_nivel", ""),
]:
    if chave not in st.session_state:
        st.session_state[chave] = padrao

# ── ABAS ─────────────────────────────────────────────────────────────────────
aba_aula, aba_exercicios = st.tabs(["📖 Plano de Aula", "✏️ Lista de Exercícios"])


# ════════════════════════════════════════════════════════════════════════════════
# ABA 1: PLANO DE AULA (código original intacto)
# ════════════════════════════════════════════════════════════════════════════════
with aba_aula:
    col_disc, col_ano = st.columns(2)
    with col_disc:
        disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática", key="aula_disc")
    with col_ano:
        ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 9º ano", key="aula_ano")

    assunto = st.text_input("Assunto", placeholder="Ex: Potenciação", key="aula_assunto")
    codigo_bncc = st.text_input("🎯 BNCC (opcional)", key="aula_bncc")
    nivel_dificuldade = st.selectbox(
        "Nível de Dificuldade",
        ["Básico", "Intermediário", "Avançado", "Prefeitura Municipal de Casimiro de Abreu"],
        key="aula_nivel",
    )

    if st.button("✨ Gerar Material Didático", key="btn_gerar_aula"):
        if not api_key or not disciplina or not ano_escolar or not assunto:
            st.warning("Preencha todos os campos obrigatórios.")
        else:
            try:
                with st.spinner("🧠 Elaborando material (Gemini Flash)..."):
                    client = get_gemini_client(api_key)
                    st.session_state.conteudo_md = gerar_conteudo_phc(
                        client=client,
                        disciplina=disciplina,
                        ano_escolar=ano_escolar,
                        assunto=assunto,
                        nivel_dificuldade=nivel_dificuldade,
                        codigo_bncc=codigo_bncc,
                    )
                st.session_state.ultima_disciplina = disciplina
                st.session_state.ultimo_ano = ano_escolar
                st.session_state.ultimo_assunto = assunto
                st.session_state.ultimo_nivel = nivel_dificuldade
                st.success("✅ Material gerado com sucesso!")
            except (APIError, Exception) as e:
                _tratar_erro_api(e)

    if st.session_state.conteudo_md:
        st.divider()
        with st.expander("📄 Visualizar texto gerado", expanded=True):
            st.markdown(st.session_state.conteudo_md)
        st.divider()

        if st.button("🖨️ Gerar PDF", key="btn_pdf_aula"):
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
                        key="dl_pdf_aula",
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar PDF: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# ABA 2: LISTA DE EXERCÍCIOS
# ════════════════════════════════════════════════════════════════════════════════
with aba_exercicios:
    st.markdown("#### Configure a lista de exercícios")

    col_disc2, col_ano2 = st.columns(2)
    with col_disc2:
        ex_disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática", key="ex_disc")
    with col_ano2:
        ex_ano = st.text_input("Ano / Série", placeholder="Ex: 9º ano", key="ex_ano_field")

    ex_assunto = st.text_input("Assunto", placeholder="Ex: Potenciação", key="ex_assunto_field")
    ex_bncc = st.text_input("🎯 BNCC (opcional)", key="ex_bncc")

    ex_nivel = st.selectbox(
        "Nível de Dificuldade",
        ["Básico", "Intermediário", "Avançado", "Prefeitura Municipal de Casimiro de Abreu"],
        key="ex_nivel_field",
    )

    ex_quantidade = st.slider(
        "Quantidade de exercícios",
        min_value=5,
        max_value=20,
        value=10,
        step=1,
        key="ex_quantidade",
    )

    ex_tipos = st.multiselect(
        "Tipos de exercício",
        options=[
            "Dissertativos / resolução passo a passo",
            "Múltipla escolha",
            "Verdadeiro ou Falso",
        ],
        default=["Dissertativos / resolução passo a passo", "Múltipla escolha"],
        key="ex_tipos",
    )

    if st.button("✨ Gerar Lista de Exercícios", key="btn_gerar_ex"):
        if not api_key or not ex_disciplina or not ex_ano or not ex_assunto:
            st.warning("Preencha todos os campos obrigatórios.")
        elif not ex_tipos:
            st.warning("Selecione ao menos um tipo de exercício.")
        else:
            try:
                with st.spinner(f"🧠 Gerando {ex_quantidade} exercícios (Gemini Flash)..."):
                    client = get_gemini_client(api_key)
                    st.session_state.exercicios_md = gerar_exercicios_phc(
                        client=client,
                        disciplina=ex_disciplina,
                        ano_escolar=ex_ano,
                        assunto=ex_assunto,
                        nivel_dificuldade=ex_nivel,
                        quantidade=ex_quantidade,
                        tipos=ex_tipos,
                        codigo_bncc=ex_bncc,
                    )
                st.session_state.ex_disciplina = ex_disciplina
                st.session_state.ex_ano = ex_ano
                st.session_state.ex_assunto = ex_assunto
                st.session_state.ex_nivel = ex_nivel
                st.success("✅ Lista gerada com sucesso!")
            except (APIError, Exception) as e:
                _tratar_erro_api(e)

    if st.session_state.exercicios_md:
        st.divider()
        with st.expander("📄 Visualizar exercícios gerados", expanded=True):
            st.markdown(st.session_state.exercicios_md)
        st.divider()

        st.markdown("##### Gerar PDFs")
        col_pdf1, col_pdf2 = st.columns(2)

        with col_pdf1:
            if st.button("🖨️ PDF Exercícios (aluno)", key="btn_pdf_ex"):
                with st.spinner("⚙️ Renderizando PDF de exercícios..."):
                    try:
                        pdf_ex = compilar_pdf_exercicios(
                            st.session_state.exercicios_md,
                            st.session_state.ex_disciplina,
                            st.session_state.ex_ano,
                            st.session_state.ex_assunto,
                        )
                        st.download_button(
                            label="⬇️ Baixar Exercícios (PDF)",
                            data=pdf_ex,
                            file_name=f"Exercicios_{st.session_state.ex_assunto.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key="dl_pdf_ex",
                        )
                    except Exception as e:
                        st.error(f"❌ Erro ao gerar PDF: {e}")

        with col_pdf2:
            if st.button("🖨️ PDF Gabarito (professor)", key="btn_pdf_gab"):
                with st.spinner("⚙️ Renderizando PDF do gabarito..."):
                    try:
                        pdf_gab = compilar_pdf_gabarito(
                            st.session_state.exercicios_md,
                            st.session_state.ex_disciplina,
                            st.session_state.ex_ano,
                            st.session_state.ex_assunto,
                        )
                        st.download_button(
                            label="⬇️ Baixar Gabarito (PDF)",
                            data=pdf_gab,
                            file_name=f"Gabarito_{st.session_state.ex_assunto.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key="dl_pdf_gab",
                        )
                    except Exception as e:
                        st.error(f"❌ Erro ao gerar PDF: {e}")

st.markdown(
    '<div class="footer">© Prof. Eric Souza da Silva</div>',
    unsafe_allow_html=True,
)
