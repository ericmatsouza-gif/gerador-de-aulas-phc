import os
import re
import streamlit as st
from google import genai
from fpdf import FPDF
from google.genai.errors import APIError

# --- CONFIGURAÇÃO DA PÁGINA WEB ---
st.set_page_config(
    page_title="Gerador de Aulas",
    page_icon="📚",
    layout="centered"
)

# Estilização CSS customizada
st.markdown("""
    <style>
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
    .contact-badge {
        display: inline-block;
        background-color: #eef7fc;
        color: #2980b9;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 8px;
        margin-top: 5px;
        text-decoration: none;
    }
    .contact-badge-wa {
        background-color: #e8f8ef;
        color: #27ae60;
    }
    .footer {
        margin-top: 50px;
        padding-top: 20px;
        border-top: 1px solid #e0e0e0;
        text-align: center;
        font-size: 0.85rem;
        color: #7f8c8d;
    }
    </style>
""", unsafe_allow_html=True)


# --- CLASSE PARA GERAÇÃO DO PDF ---
class PDFMaterial(FPDF):
    def __init__(self, disciplina, ano_escolar, assunto):
        super().__init__()
        self.disciplina = disciplina
        self.ano_escolar = ano_escolar
        self.assunto = assunto

    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(26, 42, 58)
        self.cell(0, 7, 'PLANO DE AULA E MATERIAL DIDÁTICO', align='C', new_x="LMARGIN", new_y="NEXT")
        
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(41, 128, 185)
        subtitulo = f"{self.disciplina.upper()} | {self.ano_escolar} | Assunto: {self.assunto}"
        self.cell(0, 6, subtitulo, align='C', new_x="LMARGIN", new_y="NEXT")
        
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.8)
        self.line(15, self.get_y() + 2, 195, self.get_y() + 2)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, 'Elaborado por Prof. Me. Eric Souza | PHC', align='L')
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', align='R')


def sanitizar_texto_latin1(texto: str) -> str:
    """
    Remove sintaxe LaTeX, limpa marcações Markdown e garante que 
    todo o texto utilize apenas caracteres totalmente suportados
    pela fonte Helvetica (Latin-1/ISO-8859-1) do FPDF.
    """
    if not texto:
        return ""
    
    # 1. Remove qualquer cifrão de LaTeX ($ ou \$)
    texto = re.sub(r'\\?\$', '', texto)
    
    # 2. Converte notações LaTeX brutas para texto plano limpo
    texto = texto.replace('^{\\wedge}', '^').replace('^{\\circ}', '°').replace('\\^', '^')
    texto = texto.replace('\\_', '_')
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^}]+)\]\{([^}]+)\}', r'raiz_\1(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}', r'raiz(\1)', texto)
    texto = re.sub(r'\\cdot', ' * ', texto)
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)  # Remove outros comandos \comando
    
    # 3. Trata potências para notação limpa e segura em Latin-1
    # Mantém apenas os expoentes suportados pelo Latin-1 (2 e 3)
    texto = texto.replace('^2', '²').replace('^3', '³')
    
    # Para expoentes genéricos entre parênteses ou variáveis, usa a notação ^
    # Exemplo: a^(n) -> a^n, 2^(10) -> 2^10
    texto = re.sub(r'\^\(([^)]+)\)', r'^\1', texto)
    
    # 4. Substituição de símbolos por representações textuais seguras
    texto = texto.replace('sqrt', 'raiz').replace('√', 'raiz')
    texto = texto.replace('·', '*').replace('×', '*')
    
    # 5. Limpa marcações Markdown restantes
    texto = texto.replace('**', '').replace('`', '')
    
    # 6. Mapeamento estrito de caracteres especiais para Latin-1
    substituicoes = {
        '•': '-', '—': '-', '–': '-',
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '≤': '<=', '≥': '>=', '≠': '!=', '≈': '~'
    }
    for orig, dest in substituicoes.items():
        texto = texto.replace(orig, dest)
        
    # Garante a conversão sem substituir caracteres por '?'
    return texto.encode('latin-1', 'replace').decode('latin-1').replace('?', '')


def gerar_pdf_fpdf(texto_md: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    
    largura_util = pdf.epw 
    linhas = texto_md.split('\n')
    
    for linha in linhas:
        linha_str = linha.strip()
        if not linha_str:
            pdf.ln(3)
            continue
            
        # Aplica a limpeza e sanitização para FPDF
        texto_limpo = sanitizar_texto_latin1(linha_str)
        if not texto_limpo:
            continue
            
        # Títulos (#, ##, ###)
        if linha_str.startswith('#'):
            texto_titulo = re.sub(r'^#+\s*', '', texto_limpo)
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(26, 42, 58)
            pdf.ln(3)
            pdf.multi_cell(largura_util, 6, texto_titulo)
            pdf.ln(1)
            
        # Tópicos (- ou *)
        elif linha_str.startswith('- ') or linha_str.startswith('* '):
            texto_item = re.sub(r'^[-*]\s*', '', texto_limpo)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(largura_util, 5, f"- {texto_item}")
            
        # Parágrafos comuns
        else:
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(largura_util, 5, texto_limpo)
            pdf.ln(1)
            
    return bytes(pdf.output())


def gerar_conteudo_phc(api_key: str, disciplina: str, ano_escolar: str, assunto: str) -> str:
    client = genai.Client(api_key=api_key)

    prompt = f"""
    Você é um professor especialista em Didática de todas as disciplinas sob o referencial da 
    PEDAGOGIA HISTÓRICO-CRÍTICA e da TEORIA GRAMSCIANA DA HEGEMONIA.

    Elabore um material de aula completo e profundo para:
    - Disciplina: {disciplina}
    - Ano/Série: {ano_escolar}
    - Conteúdo/Assunto: {assunto}

    ORIENTAÇÃO PEDAGÓGICO-POLÍTICA OBRIGATÓRIA:
    1. O conhecimento científico/escolar deve ser tratado como um saber sistematizado, produzido historicamente 
       pela humanidade para responder a necessidades concretas de sobrevivência, trabalho e organização social.
    2. A propriedade dos conceitos deve ser apresentada como ferramenta de LEITURA CRÍTICA DA REALIDADE, 
       capacitando os sujeitos (especialmente das classes populares) para o AUTOGOVERNO, a interpretação da sociedade, 
       o questionamento de discursos hegemonicos e a tomada de decisão autônoma.
    3. Rompa com a dualidade do ensino (formação técnico-instrumental vs. humanista elitista): entregue o RIGOR TÉCNICO-CIENTÍFICO 
       unido à CONSCIÊNCIA CRÍTICA.

    Siga ESTRITAMENTE a estrutura abaixo:

    1. PRÁTICA SOCIAL E GÊNESE HISTÓRICA DO CONTEÚDO
    - Apresente a origem social e a necessidade histórica que fez a humanidade inventar/sistematizar este conceito.
    - Aponte a relevância deste saber para a compreensão do mundo contemporâneo (trabalho, economia, política, cidadania).
    - Definição rigorosa, formal e conceitual do conteúdo, suas propriedades, conceitos-chave ou leis.

    2. EXERCÍCIOS DE FIXAÇÃO E DOMÍNIO CONCEITUAL
    - Questões de aplicação rigorosa dos conceitos, fórmulas, leis ou análises (garantindo a socialização do saber erudito).

    3. DESAFIOS DE LEITURA CRÍTICA E CONTRA-HEGEMONIA
    - Questões contextualizadas em dados reais ou plausíveis da sociedade (relações sociais, mundo do trabalho, cidadania, contradições históricas/científicas).
    - Exija que o estudante não apenas resolva/responda, mas interprete, argumente ou tome uma decisão crítica com base no conhecimento sistematizado.

    4. GABARITO COMENTADO E PEDAGÓGICO
    - Resolução passo a passo com justificativa técnica e reflexão pedagógica.

    REGRAS RÍGIDAS DE FORMATAÇÃO E ESCRITA MATEMÁTICA:
    - É PROIBIDO O USO DE QUALQUER CIFRÃO ($ ou $$).
    - É PROIBIDO O USO DE COMANDOS LATEX (como \\frac, \\sqrt, \\cdot, \\wedge).
    - Escreva equações e expressões usando notação de teclado simples:
      * Use a^n para potências em geral (Exemplo: 2^10, a^n, (1,10)^t). Para ao quadrado/cubo pode usar ² e ³.
      * Use 'raiz(x)' ou 'raiz_n(x)' para radiciação (Exemplo: raiz(144), raiz_3(27)).
      * Use 'a / b' para frações (Exemplo: 5 / 2).
      * Use '*' para multiplicação.
    - NÃO inclua saudações nem introdução. Comece direto na Seção 1.
    """

    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
    )
    return response.text
# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Me. Eric Souza da Silva**")

    st.caption("""
Licenciado em Matemática (UERJ), Mestre em Matemática pelo PROFMAT/UERJ e especialista em Tecnologias Digitais Aplicadas ao Ensino (IFRJ).

Professor de Matemática da Prefeitura de Macaé (Matrícula nº 48.836) e da Prefeitura de Casimiro de Abreu (Matrícula nº 15.035).

Atua em Educação Matemática, Tecnologias Digitais no Ensino, História da Educação Matemática, Políticas Públicas, Educação Ambiental e Esquemas Colaborativos na Educação.
    """)

    st.divider()

    st.subheader("📬 Contato & Suporte")
    st.markdown("💬 **WhatsApp:** [(21) 97048-1891](https://wa.me/5521970481891)")
    st.markdown("✉️ **E-mail:** [ericmatsouza@gmail.com](mailto:ericmatsouza@gmail.com)")

    st.divider()

    st.info("💡 Aplicação para geração de materiais didáticos multidisciplinares ob a perspectiva da Pedagogia Histórico-Crítica e Hegemonia Gramsciana.")

# --- INTERFACE PRINCIPAL ---
st.title("📚 Gerador de Aulas")

st.markdown("""
    <div class="author-card">
        <div class="author-name">👨‍🏫 Desenvolvido por Prof. Me. Eric Souza da Silva</div>
        <div class="author-desc">Plataforma pedagógica para elaboração de materiais didáticos multidisciplinares.</div>
        <div>
            <a href="https://wa.me/5521970481891" target="_blank" class="contact-badge contact-badge-wa">📱 WhatsApp: (21) 97048-1891</a>
            <a href="mailto:ericmatsouza@gmail.com" class="contact-badge">✉️ ericmatsouza@gmail.com</a>
        </div>
    </div>
""", unsafe_allow_html=True)

api_key = os.getenv("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.text_input("🔑 Informe sua chave da API do Gemini para começar:", type="password")

col_disc, col_ano = st.columns(2)

with col_disc:
    disciplina = st.text_input("Disciplina / Componente Curricular", placeholder="Ex: Matemática, História, Física...")

with col_ano:
    ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 8º ano, 1º ano do EM...")

assunto = st.text_input("Assunto / Conteúdo Específico", placeholder="Ex: Potenciação e Radiciação, Revolução Industrial...")

if st.button("✨ Gerar Material Didático (PDF)"):
    if not api_key:
        st.error("Por favor, informe a chave da API do Gemini para continuar.")
    elif not disciplina or not ano_escolar or not assunto:
        st.warning("Preencha a Disciplina, Ano/Série e o Assunto antes de gerar.")
    else:
        try:
            with st.spinner("🧠 Elaborando o plano de aula crítico e compilando o PDF..."):
                conteudo_md = gerar_conteudo_phc(api_key, disciplina, ano_escolar, assunto)
                pdf_bytes = gerar_pdf_fpdf(conteudo_md, disciplina, ano_escolar, assunto)

            st.success("🎉 Material gerado com sucesso!")

            st.download_button(
                label="📥 Baixar PDF Compilado",
                data=pdf_bytes,
                file_name=f"Aula_{disciplina}_{assunto.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )

            with st.expander("👀 Visualizar texto gerado"):
                st.markdown(conteudo_md)
                
        except APIError as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                 st.warning("⚠️ Os servidores da Inteligência Artificial estão muito ocupados no momento. Por favor, aguarde alguns segundos e clique no botão novamente.")
            else:
                 st.error(f"Erro de comunicação com a Inteligência Artificial: {e}")
        except Exception as e:
            st.error(f"Ocorreu um erro interno ao processar o PDF: {e}")

st.markdown("""
    <div class="footer">
        © Desenvolvido por <b>Prof. Mestre Eric Souza da Silva</b> <br>
        Dúvidas, sugestões ou suporte? Entre em contato via <a href="https://wa.me/5521970481891" target="_blank">WhatsApp</a> ou <a href="mailto:ericmatsouza@gmail.com">E-mail</a>.
    </div>
""", unsafe_allow_html=True)
