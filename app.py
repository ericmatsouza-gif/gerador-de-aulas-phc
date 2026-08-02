import os
import re
import streamlit as st
from google import genai
from fpdf import FPDF

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Gerador de Aulas PHC",
    page_icon="📚",
    layout="centered"
)

# ------------------------------------------------------------------------------
# 1 e 2. SANITIZAÇÃO CORRIGIDA (Limpeza de margens, espaços e potências claras)
# ------------------------------------------------------------------------------
def sanitizar(texto: str) -> str:
    """Limpa e formata textos para evitar quebras de margem e erros de expoentes no FPDF."""
    if not texto:
        return ""

    # PONTO 1: Normalização de espaços para evitar estouro da margem direita no PDF
    # Remove múltiplos espaços em sequência e tabulações que empurram o texto para fora
    texto = re.sub(r'[ \t]{2,}', ' ', texto)

    # Tratamento de acentos/comandos LaTeX residuais (\hat{n} -> ^n)
    texto = re.sub(r'\\hat\{([^}]+)\}', r'^\1', texto)
    texto = re.sub(r'\\hat\b', '^', texto)

    # Remoção de cifrões de formatação
    texto = texto.replace('$', '')

    # Substituição de comandos matemáticos LaTeX
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'raiz_\1(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}', r'raiz(\1)', texto)
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\(cdot|times)', ' * ', texto)
    texto = re.sub(r'\\div\b', ' / ', texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)

    # Operadores comparativos
    texto = texto.replace('!=', '≠').replace('>=', '≥').replace('<=', '≤')

    # PONTO 2: Agrupamento claro de expoentes literais (ex: a^n -> a^(n), a^m+n -> a^(m+n))
    # Evita que caracteres fiquem soltos ou cortados sem suporte a Unicode na fonte Helvetica
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)
    texto = re.sub(r'\^([a-zA-Z0-9\+\-]+)', r'^(\1)', texto)

    # Sobrescritos isolados para números de 1 dígito (quando isolados)
    sobrescritos = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
                    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
    for num, sub in sobrescritos.items():
        texto = re.sub(rf'\^{num}(?!\d)', sub, texto)

    # Mapeamento de símbolos matemáticos
    mapa = {
        r'\times': '×', r'\div': '÷', r'\cdot': '·',
        r'\approx': '≈', r'\neq': '≠', r'\le': '≤', r'\leq': '≤',
        r'\ge': '≥', r'\geq': '≥', r'\pm': '±', r'\infty': '∞',
        r'\rightarrow': '→', r'\Rightarrow': '⇒',
        r'\pi': 'π', r'\alpha': 'α', r'\beta': 'β', r'\Delta': 'Δ',
    }
    for latex, uni in mapa.items():
        texto = texto.replace(latex, uni)

    return texto.replace('`', '').strip()


# ------------------------------------------------------------------------------
# 3. GERAÇÃO DO PDF COM IDENTIFICAÇÃO DE SUBTÍTULOS MANTIDA
# ------------------------------------------------------------------------------
class PDFAtividade(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(26, 54, 93)
        self.cell(0, 10, "Atividade Didática", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")

def gerar_pdf(texto_limpo: str) -> bytes:
    pdf = PDFAtividade()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    linhas = texto_limpo.split("\n")
    
    for linha in linhas:
        # PONTO 1 (no loop): Limpa espaços residuais nas extremidades de cada linha
        linha_str = re.sub(r'[ \t]{2,}', ' ', linha.strip())
        
        if not linha_str:
            pdf.ln(3)
            continue
            
        # PONTO 3: Identificação de títulos e subtítulos (incluindo padrões numerados ex: "1. POTENCIAÇÃO")
        is_titulo_numerado = bool(re.match(r'^\d+\.\s+[A-ZÁÉÍÓÚÃÕÂÊÔÇ]', linha_str))

        if linha_str.startswith("# "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(26, 54, 93)
            pdf.multi_cell(0, 8, linha_str.replace("# ", ""))
            pdf.ln(2)
        elif linha_str.startswith("## ") or linha_str.startswith("### ") or is_titulo_numerado:
            # Mantém e trata como subtítulo destacado em azul
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(43, 108, 176)
            texto_sub = re.sub(r'^#{2,3}\s*', '', linha_str)
            pdf.multi_cell(0, 7, texto_sub)
            pdf.ln(2)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(45, 55, 72)
            texto_sem_md = re.sub(r'\*\*(.*?)\*\*', r'\1', linha_str)
            pdf.multi_cell(0, 6, texto_sem_md)
            pdf.ln(1)
            
    return bytes(pdf.output())


# ------------------------------------------------------------------------------
# INTERFACE STREAMLIT
# ------------------------------------------------------------------------------
st.title("📚 Gerador de Aulas e Atividades PHC")

topico = st.text_input("Tópico da Aula / Atividade:", placeholder="Ex: Potenciação e Radiciação")
nivel = st.selectbox("Nível de Ensino:", ["Ensino Fundamental II", "Ensino Médio", "EJA", "Ensino Superior"])

if st.button("Gerar Atividade", type="primary"):
    if not topico:
        st.warning("Por favor, preencha o tópico da aula.")
    else:
        with st.spinner("Gerando conteúdo pedagógico..."):
            try:
                client = genai.Client()

                prompt = f"""
                Você é um assistente pedagógico especializado em criar materiais didáticos de Matemática e Física.
                Crie uma lista de exercícios/atividade pedagógica sobre o tema: "{topico}", nível "{nivel}".

                REGRAS RÍGIDAS DE FORMATAÇÃO:
                1. NÃO USE sintaxe LaTeX em hipótese alguma (proibido o uso de $, \\frac, \\hat, \\text, \\sqrt, etc.).
                2. NÃO utilize cifrões ($) no texto.
                3. Para potências e expoentes, use a notação com circunflexo agrupada. Exemplo: a^(n), (1+i)^(t), 2^(10).
                4. NUNCA escreva comandos como \\hat{{n}} ou a\\hat{{n}}n. Escreva simplesmente a^(n).
                5. Use marcadores Markdown simples (# para Título Principal, ## para Subtítulos, **texto** para negrito).
                6. Organize a atividade em:
                   - Cabeçalho / Título
                   - Breve Resumo Teórico / Conceitos Chave
                   - Questões Propostas
                   - Gabarito Comentado no final.
                """

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )

                texto_sanitizado = sanitizar(response.text)

                st.markdown("---")
                st.markdown(texto_sanitizado)

                pdf_bytes = gerar_pdf(texto_sanitizado)

                st.download_button(
                    label="📄 Baixar Atividade em PDF",
                    data=pdf_bytes,
                    file_name="atividade_didatica.pdf",
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Erro ao gerar a atividade: {str(e)}")
