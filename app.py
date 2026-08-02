import os
import re
from flask import Flask, render_template, request, send_file, flash, redirect, url_url
import google.generativeai as genai
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = Flask(__name__)
app.secret_key = "sua_chave_secreta_aqui"

# Configuração da API do Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ------------------------------------------------------------------------------
# 1. FUNÇÃO DE SANITIZAÇÃO REFORÇADA (Resolve acentos, \hat, $, potências e LaTeX)
# ------------------------------------------------------------------------------
def sanitizar(texto: str) -> str:
    """Limpa e formata textos vindos do Gemini para renderização segura no ReportLab."""
    if not texto:
        return ""

    # 1. Tratamento de acentos/comandos LaTeX residuais específicos (\hat{n} -> ^n)
    texto = re.sub(r'\\hat\{([^}]+)\}', r'^\1', texto)
    texto = re.sub(r'\\hat\b', '^', texto)

    # 2. Remoção de cifrões de formatação/LaTeX inline
    texto = texto.replace('$', '')

    # 3. Substituição de comandos matemáticos LaTeX estruturais
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'raiz_\1(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}', r'raiz(\1)', texto)
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\(cdot|times)', ' * ', texto)
    texto = re.sub(r'\\div\b', ' / ', texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)  # Limpa qualquer outro comando \comando isolado

    # 4. Normalização de operadores comparativos
    texto = texto.replace('!=', '≠')
    texto = texto.replace('>=', '≥')
    texto = texto.replace('<=', '≤')

    # 5. Potências com chaves -> parênteses ex: ^{mn} -> ^(mn)
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)

    # 6. Sobrescritos Unicode para expoentes isolados de 1 dígito
    texto = re.sub(r'\^0(?!\d)', '⁰', texto)
    texto = re.sub(r'\^1(?!\d)', '¹', texto)
    texto = re.sub(r'\^2(?!\d)', '²', texto)
    texto = re.sub(r'\^3(?!\d)', '³', texto)
    texto = re.sub(r'\^4(?!\d)', '⁴', texto)
    texto = re.sub(r'\^5(?!\d)', '⁵', texto)
    texto = re.sub(r'\^6(?!\d)', '⁶', texto)
    texto = re.sub(r'\^7(?!\d)', '⁷', texto)
    texto = re.sub(r'\^8(?!\d)', '⁸', texto)
    texto = re.sub(r'\^9(?!\d)', '⁹', texto)

    # 7. Símbolos matemáticos e caracteres especiais
    mapa = {
        r'\times': '×', r'\div': '÷', r'\cdot': '·',
        r'\approx': '≈', r'\neq': '≠', r'\le': '≤', r'\leq': '≤',
        r'\ge': '≥', r'\geq': '≥', r'\pm': '±', r'\infty': '∞',
        r'\rightarrow': '→', r'\Rightarrow': '⇒',
        r'\pi': 'π', r'\alpha': 'α', r'\beta': 'β', r'\Delta': 'Δ',
    }
    for latex, uni in mapa.items():
        texto = texto.replace(latex, uni)

    # 8. Limpeza de formatações Markdown incompatíveis ou residuos
    texto = texto.replace('`', '')

    return texto.strip()


# ------------------------------------------------------------------------------
# 2. GERAÇÃO DE PDF VIA REPORTLAB
# ------------------------------------------------------------------------------
def gerar_pdf(conteudo_limpo, caminho_saida):
    doc = SimpleDocTemplate(
        caminho_saida,
        pagesize=letter,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Estilos customizados para o PDF
    estilo_titulo = ParagraphStyle(
        "TituloPDF",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=10,
    )

    estilo_subtitulo = ParagraphStyle(
        "SubtituloPDF",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=10,
        spaceAfter=6,
    )

    estilo_corpo = ParagraphStyle(
        "CorpoPDF",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=6,
    )

    story = []
    linhas = conteudo_limpo.split("\n")

    for linha in linhas:
        linha_str = linha.strip()
        if not linha_str:
            story.append(Spacer(1, 4))
            continue

        if linha_str.startswith("# "):
            texto_p = linha_str.replace("# ", "").strip()
            story.append(Paragraph(f"<b>{texto_p}</b>", estilo_titulo))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))
        elif linha_str.startswith("## "):
            texto_p = linha_str.replace("## ", "").strip()
            story.append(Paragraph(f"<b>{texto_p}</b>", estilo_subtitulo))
        elif linha_str.startswith("### "):
            texto_p = linha_str.replace("### ", "").strip()
            story.append(Paragraph(f"<b>{texto_p}</b>", estilo_subtitulo))
        else:
            # Converte marcação simples de negrito Markdown (**) para HTML do ReportLab (<b>)
            linha_formatada = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', linha_str)
            story.append(Paragraph(linha_formatada, estilo_corpo))

    doc.build(story)


# ------------------------------------------------------------------------------
# 3. ROTAS DA APLICAÇÃO FLASK
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        topico = request.form.get("topico")
        nivel = request.form.get("nivel", "Ensino Médio")

        if not topico:
            flash("Por favor, insira um tópico para a atividade.", "danger")
            return redirect(url_for("index"))

        # Prompt blindado contra notações LaTeX / cifrões / \hat
        prompt = f"""
        Você é um assistente pedagógico especializado em criar materiais didáticos de Matemática e Física.
        Crie uma lista de exercícios/atividade pedagógica sobre o tema: "{topico}", nível "{nivel}".

        REGRAS RÍGIDAS DE FORMATAÇÃO:
        1. NÃO USE sintaxe LaTeX em hipótese alguma (proibido o uso de $, \\frac, \\hat, \\text, \\sqrt, etc.).
        2. NÃO utilize cifrões ($) no texto.
        3. Para potências e expoentes, use apenas a notação simples de teclado com circunflexo. Exemplo: a^n, (1+i)^t, 2^10.
        4. NUNCA escreva comandos como \\hat{{n}} ou a\\hat{{n}}n. Escreva simplesmente a^n.
        5. Use marcadores Markdown simples (# para Título Principal, ## para Subtítulos, **texto** para negrito).
        6. Organize a atividade em:
           - Cabeçalho / Título
           - Breve Resumo Teórico / Conceitos Chave
           - Questões Propostas (com opções ou espaço para resposta)
           - Gabarito Comentado no final.
        """

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)

            # Aplica a sanitização rigorosa ao texto retornado
            texto_sanitizado = sanitizar(response.text)

            caminho_pdf = os.path.join("static", "atividade.pdf")
            os.makedirs("static", exist_ok=True)

            gerar_pdf(texto_sanitizado, caminho_pdf)

            return send_file(caminho_pdf, as_attachment=True, download_name="atividade_didatica.pdf")

        except Exception as e:
            flash(f"Ocorreu um erro ao gerar a atividade: {str(e)}", "danger")
            return redirect(url_for("index"))

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
