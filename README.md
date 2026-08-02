# 📚 Gerador de Aulas Críticas (Multidisciplinar)
> **Sistematização de Materiais Didáticos sob a perspectiva da Pedagogia Histórico-Crítica e da Teoria Gramsciana da Hegemonia.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?style=flat-square&logo=streamlit)
![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-8E44AD?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 📌 Sobre o Projeto

O **Gerador de Aulas Críticas** é uma aplicação web voltada para educadores que buscam planejar materiais didáticos alinhados à emancipação humana e ao rigor científico. 

Diferente de geradores de conteúdo tradicionais — que costumam reproduzir abordagens pragmáticas, neotecnicistas ou puramente instrumentais —, esta ferramenta utiliza Inteligência Artificial generativa orientada por prompts estruturados nos referenciais da **Pedagogia Histórico-Crítica (PHC)** e dos conceitos de **Hegemonia, Contra-hegemonia e Autogoverno (Antonio Gramsci)**.

### 🎯 Pilares Pedagógicos das Aulas Geradas
* **Prática Social e Gênese Histórica:** Apresenta a origem social e as necessidades humanas concretas que motivaram a criação/sistematização do conhecimento.
* **Socialização do Saber Erudito:** Garantia do rigor técnico, formal e conceitual de qualquer disciplina (Matemática, Ciências, História, Linguagens, etc.), superando a dualidade entre ensino instrumental para a classe trabalhadora e ensino humanista para as elites.
* **Consciência Crítica e Contra-Hegemonia:** Exercícios e desafios contextualizados que exigem a leitura crítica da realidade, o questionamento de discursos hegemônicos e a formação de cidadãos capazes de exercer o autogoverno.

---

## 🛠️ Tecnologias Utilizadas

* **[Python](https://www.python.org/):** Linguagem base da aplicação.
* **[Streamlit](https://streamlit.io/):** Framework para a construção da interface web responsiva e interativa.
* **[Google Gemini API (`google-genai`)](https://ai.google.dev/):** Modelo de linguagem avançado responsável pela síntese pedagógica dos planos de aula.
* **[WeasyPrint](https://weasyprint.org/):** Motor de renderização HTML/CSS para compilação direta de arquivos PDF prontos para impressão em padrão A4.
* **[Markdown](https://pypi.org/project/Markdown/):** Conversão de texto estruturado.

---

## 🚀 Como Executar o Projeto Localmente

### Pré-requisitos
* Python 3.10 ou superior instalado.
* Chave de API do Google Gemini (`GEMINI_API_KEY`).

### Passo a Passo

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/ericmatsouza-gif/gerador-de-aulas-phc.git](https://github.com/ericmatsouza-gif/gerador-de-aulas-phc.git)
   cd gerador-de-aulas-phc
