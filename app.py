def gerar_pdf_fpdf(texto_md: str, disciplina: str, ano_escolar: str, assunto: str) -> bytes:
    pdf = PDFMaterial(disciplina, ano_escolar, assunto)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Define a largura útil da página (210mm - 30mm de margens = 180mm)
    largura_util = pdf.epw 
    
    linhas = texto_md.split('\n')
    
    for linha in linhas:
        linha_str = linha.strip()
        if not linha_str:
            pdf.ln(3)
            continue
            
        # Tratamento de símbolos incompatíveis com a fonte Helvetica (Latin-1)
        linha_str = linha_str.replace('•', '-').replace('—', '-').replace('–', '-')
        texto_limpo = linha_str.encode('latin-1', 'replace').decode('latin-1')
            
        # Títulos (#, ##, ###)
        if linha_str.startswith('#'):
            texto_titulo = re.sub(r'^#+\s*', '', texto_limpo)
            pdf.set_font('Helvetica', 'B', 12)
            pdf.set_text_color(26, 42, 58)
            pdf.ln(3)
            pdf.multi_cell(largura_util, 6, texto_titulo, wrap_graphemes=True)
            pdf.ln(2)
            
        # Tópicos (- ou *)
        elif linha_str.startswith('- ') or linha_str.startswith('* '):
            texto_item = texto_limpo[2:].replace('**', '').replace('*', '')
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(largura_util, 5, f"- {texto_item}", wrap_graphemes=True)
            
        # Parágrafos comuns
        else:
            texto_paragrafo = texto_limpo.replace('**', '').replace('*', '')
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(largura_util, 5, texto_paragrafo, wrap_graphemes=True)
            pdf.ln(1)
            
    return bytes(pdf.output())
