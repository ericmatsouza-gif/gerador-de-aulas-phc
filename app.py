import os
import re
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
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
# TRATAMENTO DE TEXTO (Remove os erros visuais de ^, \hat, cifrões e LaTeX)
# ------------------------------------------------------------------------------
def sanitizar(texto: str) -> str:
    if not texto:
        return ""

    # 1. Corrige a acentuação e potências como \hat{n} ou a\hat{n}n
    texto = re.sub(r'\\hat\{([^}]+)\}', r'^\1', texto)
    texto = re.sub(r'\\hat\b', '^', texto)

    # 2. Remove os cifrões do Gemini ($)
    texto = texto.replace('$', '')

    # 3. Limpa estruturas LaTeX e converte para texto normal
    texto = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', texto)
    texto = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}', r'raiz_\1(\2)', texto)
    texto = re.sub(r'\\sqrt\{([^}]+)\}', r'raiz(\1)', texto)
    texto = re.sub(r'\\text\{([^}]+)\}', r'\1', texto)
    texto = re.sub(r'\\(cdot|times)', ' * ', texto)
    texto = re.sub(r'\\div\b', ' / ', texto)
    texto = re.sub(r'\\(left|right|displaystyle|limits|nolimits)', '', texto)
    texto = re.sub(r'\\[a-zA-Z]+', '', texto)

    # 4. Ajusta operadores e expoentes
    texto = texto.replace('!=', '≠').replace('>=', '≥').replace('<=', '≤')
    texto = re.sub(r'\^\{([^}]+)\}', r'^(\1)', texto)

    # Sobrescritos diretos para expoentes de 1 dígito
    sobrescritos = {'0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹'}
    for num, sub in sobrescritos.items():
        texto = re.sub(rf'\^{num}(?!\d)', sub, texto)

    # Símbolos matemáticos
    mapa = {
        r'\times': '×', r'\div': '÷', r'\cdot': '·',
        r'\approx': '≈', r'\neq': '≠', r'\le': '≤', r'\leq': '≤',
        r'\ge': '≥', r'\geq': '≥', r'\pm': '±', r'\infty': '∞',
        r'\pi': 'π', r'\alpha': 'α', r'\beta': 'β', r'\Delta': 'Δ',
    }
    for latex, uni in mapa.items():
        texto = texto.replace(latex, uni)

    return texto.replace('`', '').strip()


# ------------------------------------------------------------------------------
# GERAÇÃO DE PDF VIA REPORTLAB
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
        elif linha_str.startswith("## ") or linha_str.startswith("### "):
            texto_p = re.sub(r'^#{2,3}\s*', '', linha_str)
            story.append(Paragraph(f"<b>{texto_p}</b>", estilo_subtitulo))
        else:
            linha_formatada = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', linha_str)
            story.append(Paragraph(linha_formatada, estilo_corpo))

    doc.build(story)


# ------------------------------------------------------------------------------
# ROTAS FLASK
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        topico = request.form.get("topico")
        nivel = request.form.get("nivel", "Ensino Médio")

        if not topico:
            flash("Por favor, insira um tópico para a atividade.", "danger")
            return redirect(url_for("index"))

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
           - Questões Propostas
           - Gabarito Comentado no final.
        """

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)

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
