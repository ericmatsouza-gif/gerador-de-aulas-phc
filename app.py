def gerar_conteudo_phc(
    client, disciplina: str, ano_escolar: str, assunto: str, codigo_bncc: str = ""
) -> str:
    bncc_str = f"com referência à BNCC: {codigo_bncc}" if codigo_bncc else ""

    # Usamos string bruta r"""...""" para o LaTeX não conflitar com caracteres de escape
    template_prompt = r"""Você é um professor de {disciplina} do {ano_escolar} seguindo a Pedagogia Histórico-Crítica (PHC).

Gere um plano de aula completo sobre "{assunto}" {bncc_str}.

Estrutura obrigatória (use exatamente estes cabeçalhos):
# 1. Prática Social
# 2. Fixação
# 3. Leitura Crítica
# 4. Gabarito

REGRAS RIGOROSAS DE FORMATAÇÃO (PROIBIÇÕES E OBRIGAÇÕES):
- NUNCA use blocos de código (triplas crases ```) para formatar texto, exemplos ou matemática.
- NUNCA escreva notação matemática solta no texto como 3^0, 3^1, x^2. Use SEMPRE a notação LaTeX embutida: $3^0$, $3^1$, $x^2$.
- Para exibições em listas ou passos organizados, use listas comuns do Markdown (com traço "-") e insira as variáveis/expressões em LaTeX. Exemplo:
  - Instante $t = 0$: 1 pessoa original ($3^0$)
  - Instante $t = 1$: 3 novas pessoas ($3^1$)
- Use LaTeX ($...$) para QUALQUER variável, expressão, fórmula, igualdade ou notação de potência/radiciação no texto (ex: $t = 0$, $x$, $A = l^2$).
- Expressões matemáticas em destaque (fórmulas, equações em bloco próprio): $$expressão$$ — exemplo: $$M = C \cdot (1+i)^t$$
- Use notação LaTeX padrão: \frac{num}{den}, \sqrt{x}, \sqrt[3]{x}, x^{2}, \cdot, \pm, \leq, \geq
- NUNCA coloque números isolados ou texto simples dentro de $ (escreva "3 voltas", "4 lados" normalmente como texto).
- NÃO use $ para indicar moeda (escreva "reais", "R$" com espaço após o símbolo, ou "BRL").
- Negrito para termos importantes: **termo**.
- Texto corrido em português fora dos delimitadores matemáticos.
"""

    prompt = template_prompt.format(
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        assunto=assunto,
        bncc_str=bncc_str,
    )

    config = types.GenerateContentConfig(
        max_output_tokens=8192, temperature=0.7
    )
    response = client.models.generate_content(
        model="gemini-flash-latest", contents=prompt, config=config
    )
    return response.text
