import os
import re
import markdown
import streamlit as st
from google import genai
from weasyprint import HTML

# --- CONFIGURAÇÃO DA PÁGINA WEB ---
st.set_page_config(
    page_title="Gerador de Aulas",
    page_icon="📚",
    layout="centered"
)

# Estilização CSS customizada (Botões, Cards de contato e Rodapé)
st.markdown("""
    <style>
    /* Estilo do Botão Principal */
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

    /* Card de Apresentação */
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

    /* Rodapé Fixo */
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


# --- FUNÇÕES DE PROCESSAMENTO E SANITIZAÇÃO ---

def limpar_e_formatar_math(texto: str) -> str:
    """
    Higieniza e converte notações LaTeX (frações, potências, raízes, símbolos)
    para HTML/Markdown limpo e compatível com o WeasyPrint.
    """
    if not texto:
        return ""

    # 1. Ajuste de listas com asteriscos soltos
    texto = re.sub(r'\s+\*\s+', '\n* ', texto)

    # 2. Remoção de comandos decorativos/formatadores LaTeX
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)

    # 3. Tabela de Símbolos Matemáticos e Científicos LaTeX -> Unicode/HTML
    simbolos = {
        r'\times': '×',
        r'\div': '÷',
        r'\cdot': '·',
        r'\approx': '≈',
        r'\neq': '≠',
        r'\le': '≤',
        r'\leq': '≤',
        r'\ge': '≥',
        r'\geq': '≥',
        r'\pm': '±',
        r'\infty': '∞',
        r'\degree': '°',
        r'\rightarrow': '→',
        r'\Rightarrow': '⇒',
        r'\pi': 'π',
        r'\alpha': 'α',
        r'\beta': 'β',
        r'\Delta': 'Δ',
    }
    for latex_simb, unicode_simb in simbolos.items():
        texto = re.sub(re.escape(latex_simb) + r'(?![a-zA-Z])', unicode_simb, texto)

    # 4. POTENCIAÇÃO (Sobrescritos)
    texto = re.sub(r'\^\{([^}]+)\}', r'<sup>\1</sup>', texto)
    texto = re.sub(r'\^([0-9a-zA-Z+-]+)', r'<sup>\1</sup>', texto)

    # 5. SUBSCRITOS (Termos de sequências, fórmulas químicas, etc.)
    texto = re.sub(r'_\{([^}]+)\}', r'<sub>\1</sub>', texto)
    texto = re.sub(r'_([0-9a-zA-Z]+)', r'<sub>\1</sub>', texto)

    # 6. RADICIAÇÃO (Raízes Quadradas e Enésimas)
    texto = re.sub(
        r'\\sqrt\[([^\]]+)\]\{([^}]+)\}',
        r'<sup style="font-size: 0.75em; vertical-align: 0.4em;">\1</sup>√<span style="border-top: 1px solid #2c3e50; padding-top: 1px;">\2</span>',
        texto
    )
    texto = re.sub(
        r'\\sqrt\{([^}]+)\}',
        r'√<span style="border-top: 1px solid #2c3e50; padding-top: 1px;">\1</span>',
        texto
    )

    # 7. FRAÇÕES (Suporte a até 2 níveis de aninhamento)
    padrao_frac = r'\\frac\{([^}]+)\}\{([^}]+)\}'
    for _ in range(2):
        texto = re.sub(
            padrao_frac,
            r'<span class="frac"><span>\1</span><span class="bar"></span><span>\2</span></span>',
            texto
        )

    # 8. Limpeza final de cifrões ($) do LaTeX
    texto = texto.replace('$', '')

    return texto


def gerar_conteudo_phc(api_key: str, disciplina: str, ano_escolar: str, assunto: str) -> str:
    """Consulta o Gemini com o Prompt fundado na Pedagogia Histórico-Crítica e Gramsci."""
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

    1. PRÁTICA SOCIAL E GÊNESE HISTÓRICA DO CONTEÚDO (Para o Quadro)
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

    REGRAS CRÍTICAS DE FORMATO DE TEXTO:
    - NUNCA use o asterisco (*) no meio de uma linha para separar itens. Use SEMPRE quebras de linha com "- " ou "* ".
    - Para expressões matemáticas/fórmulas, use a sintaxe limpa.
    - NÃO use comandos complexos como \\text{{}} dentro de equações.
    - NÃO inclua saudações nem introdução. Comece direto na Seção 1.
    """

    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
    )
    return response.text


def compilar_pdf(conteudo_markdown: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    """Converte o Markdown limpo em PDF compilado no formato A4 via WeasyPrint."""
    texto_formatado = limpar_e_formatar_math(conteudo_markdown)
    conteudo_html = markdown.markdown(texto_formatado, extensions=['tables', 'fenced_code'])

    html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
@page {{
    size: A4;
    margin: 18mm 15mm 18mm 15mm;
    @bottom-right {{ content: "Página " counter(page) " de " counter(pages); font-size: 8.5pt; color: #666; font-family: sans-serif; }}
    @bottom-left {{ content: "Elaborado por Prof. Me. Eric Souza | PHC"; font-size: 8.5pt; color: #666; font-family: sans-serif; }}
}}
body {{ font-family: 'Segoe UI', Georgia, serif; font-size: 10.5pt; line-height: 1.6; color: #2c3e50; margin: 0; }}

/* Suporte para Potenciação e Subscritos */
sup {{ font-size: 0.75em; line-height: 0; vertical-align: super; }}
sub {{ font-size: 0.75em; line-height: 0; vertical-align: sub; }}

/* CSS de Frações e Símbolos */
.frac {{ display: inline-block; vertical-align: -0.4em; text-align: center; font-size: 0.85em; padding: 0 2px; line-height: 1.1; }}
.frac > span {{ display: block; padding: 0 1px; }}
.frac span.bar {{ border-top: 1.2px solid #2c3e50; height: 0; margin: 1px 0; display: block; }}

.header {{ text-align: center; border-bottom: 2.5px solid #2980b9; padding-bottom: 8px; margin-bottom: 20px; }}
.title {{ font-size: 15pt; font-weight: bold; color: #1a2a3a; text-transform: uppercase; }}
.subtitle {{ font-size: 10pt; color: #2980b9; font-weight: bold; margin-top: 4px; }}

h1, h2, h3 {{ color: #1a2a3a; border-bottom: 1px solid #ecf0f1; padding-bottom: 4px; margin-top: 20px; margin-bottom: 10px; page-break-after: avoid; }}
p {{ margin-top: 6px; margin-bottom: 8px; }}
ul, ol {{ padding-left: 20px; margin-top: 6px; margin-bottom: 12px; }}
li {{ margin-bottom: 6px; page-break-inside: avoid; }}
strong {{ color: #16a085; }}
</style>
</head>
<body>
<div class="header">
    <div class="title">PLANO DE AULA E MATERIAL DIDÁTICO</div>
    <div class="subtitle">{disciplina.upper()} &nbsp;|&nbsp; {ano_escolar} &nbsp;|&nbsp; Assunto: {assunto}</div>
</div>
<div class="content">{conteudo_html}</div>
</body>
</html>"""

    return HTML(string=html_template).write_pdf()


# --- BARRA LATERAL (SIDEBAR) COM APRESENTAÇÃO E CONTATO ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/teacher.png", width=70)
    st.title("Sobre o Autor")
    st.markdown("**Prof. Mestre Eric Souza da Silva**")
    st.caption("Especialista em Didática e Pedagogia Histórico-Crítica.")

    st.divider()

    st.subheader("📬 Contato & Suporte")
    st.markdown("💬 **WhatsApp:** [ (21) 97048-1891](https://wa.me/5521970481891)")
    st.markdown("✉️ **E-mail:** [ericmatsouza@gmail.com](mailto:ericmatsouza@gmail.com)")

    st.divider()
    st.info(
        "💡 Aplicação para geração de materiais didáticos multidisciplinares fundamentados na Pedagogia Histórico-Crítica e Hegemonia Gramsciana.")

# --- INTERFACE PRINCIPAL ---

st.title("📚 Gerador de Aulas")

# Card de Destaque no Topo da Página
st.markdown("""
    <div class="author-card">
        <div class="author-name">👨‍🏫 Desenvolvido por Prof. Me. Eric Souza da Silva</div>
        <div class="author-desc">Plataforma pedagógica para elaboração de materiais didáticos multidisciplinares sob a perspectiva da <b>Pedagogia Histórico-Crítica</b> e <b>Hegemonia Gramsciana</b>.</div>
        <div>
            <a href="https://wa.me/5521970481891" target="_blank" class="contact-badge contact-badge-wa">📱 WhatsApp: (21) 97048-1891</a>
            <a href="mailto:ericmatsouza@gmail.com" class="contact-badge">✉️ ericmatsouza@gmail.com</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# Busca a chave de API das variáveis de ambiente
api_key = os.getenv("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.text_input("🔑 Informe sua chave da API do Gemini para começar:", type="password")

col_disc, col_ano = st.columns(2)

with col_disc:
    disciplina = st.text_input("Disciplina / Componente Curricular", placeholder="Ex: Matemática, História, Física...")

with col_ano:
    ano_escolar = st.text_input("Ano / Série", placeholder="Ex: 6º ano, 1º ano do EM...")

assunto = st.text_input("Assunto / Conteúdo Específico",
                        placeholder="Ex: Potenciação e Radiciação, Revolução Industrial...")

if st.button("✨ Gerar Material Didático (PDF)"):
    if not api_key:
        st.error("Por favor, informe a chave da API do Gemini para continuar.")
    elif not disciplina or not ano_escolar or not assunto:
        st.warning("Preencha a Disciplina, Ano/Série e o Assunto antes de gerar.")
    else:
        try:
            with st.spinner("🧠 Elaborando o plano de aula crítico e compilando o PDF..."):
                # 1. Gera o texto pedagógico crítico via Gemini
                conteudo_md = gerar_conteudo_phc(api_key, disciplina, ano_escolar, assunto)

                # 2. Compila para PDF formatado em A4
                pdf_bytes = compilar_pdf(conteudo_md, disciplina, ano_escolar, assunto)

            st.success("🎉 Material gerado com sucesso!")

            # Botão para download direto do arquivo
            st.download_button(
                label="📥 Baixar PDF Compilado",
                data=pdf_bytes,
                file_name=f"Aula_{disciplina}_{assunto.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )

            # Exibe prévia do texto na interface
            with st.expander("👀 Visualizar texto gerado"):
                st.markdown(conteudo_md)

        except Exception as e:
            st.error(f"Ocorreu um erro ao processar a solicitação: {e}")

# --- RODAPÉ DA PÁGINA ---
st.markdown("""
    <div class="footer">
        © Desenvolvido por <b>Prof. Mestre Eric Souza da Silva</b> <br>
        Dúvidas, sugestões ou suporte? Entre em contato via <a href="https://wa.me/5521970481891" target="_blank">WhatsApp</a> ou <a href="mailto:ericmatsouza@gmail.com">E-mail</a>.
    </div>
""", unsafe_allow_html=True)
