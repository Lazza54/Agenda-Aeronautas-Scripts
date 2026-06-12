import os
import io
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from tkinter import filedialog, messagebox
import tkinter as tk

# =========================
# CONFIGURAÇÕES
# =========================
PASTA_PDFS = "pdfs"
AUTOR = "Ricardo Lazzarini"
NOME_SAIDA = f"BOOK_FINAL_{AUTOR.replace(' ', '_')}.pdf"

TITULO = "BOOK DOCUMENTAL"

CRIAR_CAPA = True
CRIAR_INDICE = True
NUMERAR_PAGINAS = True
MARCA_DAGUA = ""  # ex: "CONFIDENCIAL" ou "" para desligar
# =========================


def extrair_nome_aeronauta_para_arquivo(nome_arquivo: str) -> str | None:
    """Extrai o trecho do nome do aeronauta para usar no nome final do BOOK."""
    base = os.path.splitext(os.path.basename(nome_arquivo))[0]
    m = re.search(r"(?i)^escala_[pe]_(.+?)_(?:[A-Z]{3,4})(?:_|$)", base)
    if not m:
        return None

    nome_bruto = m.group(1).strip(" _-")
    if not nome_bruto:
        return None

    return nome_bruto


def detectar_nome_aeronauta_para_saida(arquivos_pdf: list[str]) -> str | None:
    """Detecta nome do aeronauta a partir dos PDFs presentes no diretório."""
    for arq in arquivos_pdf:
        nome = extrair_nome_aeronauta_para_arquivo(arq)
        if nome:
            return nome
    return None


def _modo_sem_popup() -> bool:
    return os.environ.get("AERO_NO_POPUP", "").strip().lower() in {"1", "true", "yes", "sim"}


def _obter_pasta_pdfs() -> str | None:
    """Obtém pasta de trabalho via ambiente; se ausente, pergunta ao usuário."""
    pasta_env = os.environ.get("AERO_OUTPUT_DIR", "").strip()
    if pasta_env and os.path.isdir(pasta_env):
        return pasta_env

    # Em modo sem popup (execução automática), usa o diretório atual.
    if _modo_sem_popup():
        pasta_cwd = os.getcwd()
        if os.path.isdir(pasta_cwd):
            print(f"ℹ️ AERO_OUTPUT_DIR não definido. Usando diretório atual: {pasta_cwd}")
            return pasta_cwd
        print("❌ Diretório atual inválido para processamento automático.")
        return None

    root = tk.Tk()
    root.withdraw()
    pasta = filedialog.askdirectory(title="Selecione a pasta contendo os arquivos PDF")
    if not pasta:
        messagebox.showwarning("Cancelado", "Nenhuma pasta foi selecionada. Operação cancelada.")
        return None
    return pasta


def _encontrar_subpasta_case_insensitive(base_dir: str, nome_subpasta: str) -> str | None:
    """Procura por uma subpasta com case-insensitive."""
    if not os.path.isdir(base_dir):
        print(f"⚠️ Base dir não existe: {base_dir}")
        return None
    
    try:
        for item in os.listdir(base_dir):
            caminho = os.path.join(base_dir, item)
            if os.path.isdir(caminho) and item.lower() == nome_subpasta.lower():
                print(f"✅ Subpasta encontrada: {caminho}")
                return caminho
    except Exception as e:
        print(f"⚠️ Erro ao listar {base_dir}: {e}")
        return None
    
    print(f"⚠️ Subpasta '{nome_subpasta}' não encontrada em: {base_dir}")
    return None


def _listar_pdfs_holerites(pasta_pdfs: str) -> tuple[str | None, list[str]]:
    """
    Retorna todos os PDFs da subpasta holerites.
    Busca estratégias:
    1) procura em pasta_pdfs/holerites (case-insensitive)
    2) fallback: procura em pasta_pdfs/../holerites (pasta pai)
    3) inclui PDFs recursivamente dentro da pasta holerites
    """
    pasta_holerites = None
    
    # Estratégia 1: Procura no nível atual (pasta_pdfs)
    print(f"🔍 Procurando holerites em: {pasta_pdfs}")
    pasta_holerites = _encontrar_subpasta_case_insensitive(pasta_pdfs, "holerites")
    
    # Estratégia 2: Procura no nível superior (pai do aeronauta)
    if not pasta_holerites:
        pasta_pai = os.path.dirname(pasta_pdfs.rstrip("\\/"))
        print(f"🔍 Procurando holerites em pasta pai: {pasta_pai}")
        if pasta_pai:
            pasta_holerites = _encontrar_subpasta_case_insensitive(pasta_pai, "holerites")
    
    if not pasta_holerites:
        print("⚠️ Pasta 'Holerites' não encontrada.")
        return None, []
    
    print(f"✅ Pasta 'Holerites' encontrada: {pasta_holerites}")
    
    arquivos = []
    for raiz, _, nomes in os.walk(pasta_holerites):
        for nome in nomes:
            if nome.lower().endswith(".pdf"):
                caminho_rel = os.path.relpath(os.path.join(raiz, nome), pasta_holerites)
                arquivos.append(caminho_rel)

    arquivos = sorted(arquivos)
    print(f"✅ {len(arquivos)} arquivo(s) PDF encontrado(s) em holerites")
    return pasta_holerites, arquivos


def _detectar_pdf_escala_automatico(pasta_pdfs: str) -> str | None:
    """
    Busca a escala no diretório atual e em Auditoria_Calculos/Auditori_Calculos.
    Regra: PDF com padrão de data de escala (ddmmaaaa_ddmmaaaa).
    """
    # Padrão de escala: termina com ddmmaaaa_ddmmaaaa.pdf
    padrao_escala = re.compile(r"\d{8}_\d{8}\.pdf$", re.IGNORECASE)

    def _selecionar_escala_em(diretorio: str) -> str | None:
        if not diretorio or not os.path.isdir(diretorio):
            return None

        pdfs = [f for f in os.listdir(diretorio) if f.lower().endswith(".pdf")]
        if not pdfs:
            return None

        # Filtro 1: Procura por PDFs com padrão de escala (ddmmaaaa_ddmmaaaa)
        candidatos = [f for f in pdfs if padrao_escala.search(f)]
        
        # Filtro 2: Exclui RELATORIO DE CONFORMIDADES e outros relatórios
        if candidatos:
            candidatos = [
                f for f in candidatos 
                if not f.upper().startswith("BOOK_FINAL_") 
                and "CONFORMIDADE" not in f.upper()
                and "RELATORIO" not in f.upper()
            ]
        
        # Se não encontrou com padrão de data, tenta buscar por "ESCALA" no nome
        if not candidatos:
            candidatos = [
                f for f in pdfs
                if "ESCALA" in f.upper() and not f.upper().startswith("BOOK_FINAL_")
            ]

        if not candidatos:
            return None

        candidatos.sort(key=lambda nome: os.path.getmtime(os.path.join(diretorio, nome)), reverse=True)
        return os.path.join(diretorio, candidatos[0])

    # 1) Primeiro tenta o diretório atual (modo automático usa Auditoria_Calculos direto)
    achado = _selecionar_escala_em(pasta_pdfs)
    if achado:
        return achado

    # 2) Fallback: subpastas históricas
    pasta_auditoria = (
        _encontrar_subpasta_case_insensitive(pasta_pdfs, "Auditoria_Calculos")
        or _encontrar_subpasta_case_insensitive(pasta_pdfs, "Auditori_Calculos")
    )
    if not pasta_auditoria:
        return None

    return _selecionar_escala_em(pasta_auditoria)


# ---------- CAPA ----------
def criar_capa(arquivo):
    from reportlab.lib.units import cm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    
    c = canvas.Canvas(arquivo, pagesize=A4)
    w, h = A4
    
    # Margens
    margem_esquerda = 2.5 * cm
    margem_direita = w - 2.5 * cm
    largura_texto = margem_direita - margem_esquerda

    # TÍTULO PRINCIPAL
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w/2, h - 2*cm, TITULO)
    
    # Linha decorativa
    c.setLineWidth(2)
    c.line(w/2 - 5*cm, h - 2.5*cm, w/2 + 5*cm, h - 2.5*cm)
    
    # PREFÁCIO
    y = h - 4*cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margem_esquerda, y, "Prefácio")
    
    y -= 0.7*cm
    c.setFont("Helvetica", 10)
    
    # Texto do prefácio dividido em parágrafos
    paragrafos = [
        "Este trabalho reúne, de forma estruturada, cronológica e documental, o histórico completo das atividades operacionais desempenhadas pelo aeronauta Ricardo Lazzarini, contemplando registros detalhados de horas de apresentação, períodos diurnos, noturnos e especiais, jornadas, operações, plantões, repousos, reservas, tempos de solo, treinamentos e demais eventos relacionados à rotina profissional.",
        
        "Organizado ano a ano, com discriminação de datas, trechos voados, origens e destinos, o presente Book tem como finalidade oferecer transparência, rastreabilidade e precisão técnica sobre a totalidade das horas trabalhadas, permitindo análise clara da composição das escalas, dos períodos de atividade e descanso, bem como da correta aplicação dos critérios previstos na Lei nº 13.475 (Lei do Aeronauta) e demais normativos operacionais.",
        
        "Mais do que um simples compilado de dados, este documento constitui um instrumento de memória profissional e comprovação objetiva, reunindo informações essenciais para conferências administrativas, auditorias, validações contratuais, cálculos trabalhistas, planejamento operacional e eventual suporte jurídico. Sua elaboração prioriza a fidelidade aos registros originais, a padronização das informações e a facilidade de consulta por meio de índices e demonstrativos consolidados.",
        
        "Ao consolidar anos de dedicação, deslocamentos e responsabilidades inerentes à atividade aérea, este Book evidencia não apenas números e tempos, mas a dimensão do compromisso, da disciplina e da continuidade exigidos pela profissão de aeronauta.",
        
        "Que este material sirva, portanto, como fonte segura de referência, análise e comprovação, refletindo com exatidão a trajetória operacional aqui documentada."
    ]
    
    # Função para quebrar texto em linhas
    def quebrar_texto(texto, largura_max, fonte, tamanho):
        palavras = texto.split()
        linhas = []
        linha_atual = []
        
        for palavra in palavras:
            teste = ' '.join(linha_atual + [palavra])
            if stringWidth(teste, fonte, tamanho) <= largura_max:
                linha_atual.append(palavra)
            else:
                if linha_atual:
                    linhas.append(' '.join(linha_atual))
                linha_atual = [palavra]
        
        if linha_atual:
            linhas.append(' '.join(linha_atual))
        
        return linhas
    
    # Renderizar parágrafos
    espaco_entre_linhas = 0.45*cm
    espaco_entre_paragrafos = 0.6*cm
    
    for paragrafo in paragrafos:
        linhas = quebrar_texto(paragrafo, largura_texto, "Helvetica", 10)
        
        for linha in linhas:
            c.drawString(margem_esquerda, y, linha)
            y -= espaco_entre_linhas
        
        y -= espaco_entre_paragrafos
    
    # ASSINATURA E DATA
    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margem_esquerda, y, AUTOR)
    
    y -= 0.5*cm
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(margem_esquerda, y, "Autor")
    
    y -= 0.5*cm
    c.setFont("Helvetica", 10)
    c.drawString(margem_esquerda, y, datetime.now().strftime("%d de janeiro de %Y"))

    c.save()


def _converter_txt_conformidade_para_pdf(txt_path: str, pdf_path: str):
    """Converte arquivo TXT de conformidade para PDF simples (texto corrido)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                conteudo = f.read()
        except UnicodeDecodeError:
            with open(txt_path, "r", encoding="latin-1", errors="replace") as f:
                conteudo = f.read()

        c = canvas.Canvas(pdf_path, pagesize=A4)
        largura, altura = A4

        margem_esq = 2.0 * cm
        margem_dir = 2.0 * cm
        y = altura - 2.0 * cm
        altura_linha = 12
        max_chars = 120

        c.setFont("Helvetica", 9)
        for linha in conteudo.splitlines():
            texto = linha if linha else " "
            blocos = [texto[i:i + max_chars] for i in range(0, len(texto), max_chars)] or [" "]
            for bloco in blocos:
                if y <= 2.0 * cm:
                    c.showPage()
                    c.setFont("Helvetica", 9)
                    y = altura - 2.0 * cm
                c.drawString(margem_esq, y, bloco)
                y -= altura_linha

        c.save()
        print(f"✓ PDF de conformidade gerado com sucesso!")
    except Exception as exc:
        print(f"⚠️ Falha ao converter '{txt_path}' para PDF: {exc}")


# ---------- ÍNDICE ----------
def extrair_nome_relatorio(nome_arquivo):
    """Extrai o nome limpo do relatório do nome do arquivo"""
    try:
        nome_sem_ext = os.path.splitext(nome_arquivo)[0]
        nome_upper = nome_sem_ext.upper()
        # RELATÓRIO DE CONFORMIDADE
        if 'CONFORMIDADE' in nome_upper:
            return 'RELATÓRIO DE CONFORMIDADE'
        # SUMÁRIO
        if 'SUMARIO' in nome_upper or 'SUMÁRIO' in nome_upper:
            if 'APRESENTA' in nome_upper:
                return 'SUMÁRIO APRESENTAÇÃO'
            elif 'JORNADA' in nome_upper:
                return 'SUMÁRIO JORNADA'
            elif 'OPERACAO' in nome_upper or 'OPERAÇÃO' in nome_upper:
                return 'SUMÁRIO OPERAÇÃO'
            elif 'PLANTAO' in nome_upper or 'PLANTÃO' in nome_upper:
                return 'SUMÁRIO PLANTÃO'
            elif 'REPOUSO' in nome_upper and 'EXTRA' in nome_upper:
                return 'SUMÁRIO REPOUSO EXTRA'
            elif 'REPOUSO' in nome_upper:
                return 'SUMÁRIO REPOUSO'
            elif 'RESERVA' in nome_upper:
                return 'SUMÁRIO RESERVA'
            elif 'CORTE' in nome_upper:
                return 'SUMÁRIO CORTE'
            elif 'SOLO' in nome_upper:
                return 'SUMÁRIO SOLO'
            elif 'TREINAMENTO' in nome_upper:
                return 'SUMÁRIO TREINAMENTO'
            else:
                return 'SUMÁRIO'
        # RELATÓRIO SIMPLES
        if 'APRESENTA' in nome_upper and 'RELATORIO' in nome_upper:
            return 'APRESENTAÇÃO RELATÓRIO'
        elif 'JORNADA' in nome_upper and 'RELATORIO' in nome_upper:
            return 'JORNADA RELATÓRIO'
        elif ('OPERACAO' in nome_upper or 'OPERAÇÃO' in nome_upper) and 'RELATORIO' in nome_upper:
            return 'OPERAÇÃO RELATÓRIO'
        elif ('PLANTAO' in nome_upper or 'PLANTÃO' in nome_upper) and 'RELATORIO' in nome_upper:
            return 'PLANTÃO RELATÓRIO'
        elif 'REPOUSO' in nome_upper and 'EXTRA' in nome_upper and 'RELATORIO' in nome_upper:
            return 'REPOUSO EXTRA RELATÓRIO'
        elif 'REPOUSO' in nome_upper and 'RELATORIO' in nome_upper:
            return 'REPOUSO RELATÓRIO'
        elif 'RESERVA' in nome_upper and 'RELATORIO' in nome_upper:
            return 'RESERVA RELATÓRIO'
        elif 'CORTE' in nome_upper and 'RELATORIO' in nome_upper:
            return 'CORTE RELATÓRIO'
        elif 'SOLO' in nome_upper and 'RELATORIO' in nome_upper:
            return 'SOLO RELATÓRIO'
        elif 'TREINAMENTO' in nome_upper and 'RELATORIO' in nome_upper:
            return 'TREINAMENTO RELATÓRIO'
        # Se não encontrou nenhum tipo conhecido, retorna o nome original
        return nome_arquivo
    except:
        return nome_arquivo

def criar_indice(arquivo, capitulos):
    c = canvas.Canvas(arquivo, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, h-60, "ÍNDICE")

    y = h - 120
    c.setFont("Helvetica", 12)
    
    # Posições para alinhamento
    x_esquerda = 60
    x_direita = w - 60  # Margem direita

    for idx, (nome, pagina) in enumerate(capitulos):
        nome_limpo = extrair_nome_relatorio(nome)
        
        # Desenhar nome do relatório à esquerda
        c.drawString(x_esquerda, y, nome_limpo)
        
        # Desenhar número da página à direita (alinhado à direita)
        pagina_str = str(pagina)
        pagina_width = c.stringWidth(pagina_str, "Helvetica", 12)
        c.drawRightString(x_direita, y, pagina_str)
        
        # Desenhar linha pontilhada entre nome e número
        nome_width = c.stringWidth(nome_limpo, "Helvetica", 12)
        x_inicio_pontos = x_esquerda + nome_width + 10
        x_fim_pontos = x_direita - pagina_width - 10
        
        # Linha de pontos
        c.saveState()
        c.setDash(1, 3)
        c.line(x_inicio_pontos, y + 2, x_fim_pontos, y + 2)
        c.restoreState()
        
        y -= 20
    
    c.save()



# ---------- NUMERAÇÃO + MARCA D’ÁGUA ----------
def numerar_paginas(input_pdf, output_pdf):
    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages, start=1):
        # Copiar a página original sem modificação
        writer.add_page(page)

    # Salvar primeiro sem overlay
    with open(output_pdf, "wb") as f:
        writer.write(f)
    
    # Agora adicionar numeração usando reportlab em um segundo passo
    # Reabrir o arquivo salvo
    reader2 = PdfReader(output_pdf)
    writer2 = PdfWriter()
    
    for i, page in enumerate(reader2.pages, start=1):
        if NUMERAR_PAGINAS or (CRIAR_INDICE and i > (2 if CRIAR_CAPA else 1)):
            overlay_path = f"__overlay_tmp_{i}.pdf"
            c = canvas.Canvas(overlay_path, pagesize=A4)
            w, h = A4

            if NUMERAR_PAGINAS:
                c.setFont("Helvetica", 9)
                c.drawCentredString(w/2, 20, f"Página {i}")
            
            # Adicionar texto "Voltar ao Índice"
            pagina_indice = 2 if CRIAR_CAPA else 1
            if CRIAR_INDICE and i > pagina_indice:
                c.setFont("Helvetica", 8)
                c.setFillColorRGB(0, 0, 0.8)
                texto = "← Índice"
                text_width = c.stringWidth(texto, "Helvetica", 8)
                x_pos = w - 50
                y_pos = h - 30
                c.drawString(x_pos - text_width, y_pos, texto)

            if MARCA_DAGUA:
                c.saveState()
                c.setFont("Helvetica", 60)
                c.setFillGray(0.85)
                c.translate(w/2, h/2)
                c.rotate(45)
                c.drawCentredString(0, 0, MARCA_DAGUA)
                c.restoreState()

            c.save()

            # Fazer merge apenas se tiver overlay
            overlay = PdfReader(overlay_path)
            page.merge_page(overlay.pages[0])
            os.remove(overlay_path)
        
        writer2.add_page(page)

    writer2.add_metadata({
        "/Title": TITULO,
        "/Author": AUTOR
    })

    # Tentar remover arquivo existente se estiver bloqueado
    if os.path.exists(output_pdf):
        try:
            os.remove(output_pdf)
        except PermissionError:
            print(f"\n⚠️ ATENÇÃO: O arquivo '{output_pdf}' está aberto em outro programa!")
            print("   Feche o arquivo e execute novamente.")
            raise PermissionError(f"Não foi possível sobrescrever '{output_pdf}'. Feche o arquivo e tente novamente.")
    
    with open(output_pdf, "wb") as f:
        writer2.write(f)


# ---------- APLICAR TODAS AS CORREÇÕES DE LINKS ----------
def aplicar_links_completo(pdf_path, capitulos, arquivos, pasta_pdfs, mapeamento_global):
    """
    Aplica TODAS as correções de links no PDF final:
    1. Corrige links internos dos PDFs mesclados (incluindo sumários)
    2. Adiciona bookmarks de navegação
    3. Adiciona links clicáveis no índice
    4. Adiciona links "Voltar ao Índice"
    
    IMPORTANTE: Esta função deve ser chamada APÓS salvar o arquivo temporário,
    pois ela reabre o PDF e aplica todas as modificações de uma vez só.
    """
    try:
        from pypdf.generic import (DictionaryObject, ArrayObject, NameObject, 
                                   NumberObject, FloatObject, IndirectObject)
        
        print("\n🔧 Aplicando correções de links no BOOK...")
        
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Copiar todas as páginas
        for page in reader.pages:
            writer.add_page(page)
        
        # ETAPA 1: Recriar links internos dos PDFs originais (sumários e relatórios)
        # ABORDAGEM: Remove os links quebrados do BOOK e recria com destinos corretos
        print("\n  📚 Carregando PDFs originais para correção de links...")
        pdfs_cache = {}
        for arquivo in arquivos:
            caminho_completo = os.path.join(pasta_pdfs, arquivo)
            try:
                pdfs_cache[arquivo] = PdfReader(caminho_completo)
            except Exception as e:
                print(f"     ⚠️ Erro ao carregar {arquivo}: {e}")
        
        total_links = 0
        
        for arquivo in arquivos:
            try:
                pdf_original = pdfs_cache.get(arquivo)
                if pdf_original is None:
                    continue
                
                print(f"  🔗 Corrigindo links: {arquivo}")
                links_arquivo = 0
                
                for idx_orig, page_orig in enumerate(pdf_original.pages):
                    idx_book = mapeamento_global.get((arquivo, idx_orig))
                    if idx_book is None or idx_book >= len(writer.pages):
                        continue
                    
                    page_book = writer.pages[idx_book]
                    
                    if '/Annots' not in page_orig:
                        continue
                    
                    annots_orig = page_orig['/Annots']
                    if not annots_orig:
                        continue
                    
                    # Coletar novos links corrigidos para esta página
                    novos_links = []
                    
                    for annot_ref in annots_orig:
                        try:
                            if isinstance(annot_ref, IndirectObject):
                                annot_orig = annot_ref.get_object()
                            else:
                                annot_orig = annot_ref
                            
                            if not isinstance(annot_orig, DictionaryObject):
                                continue
                            if annot_orig.get('/Subtype') != '/Link':
                                continue
                            if '/Rect' not in annot_orig:
                                continue
                            
                            # Encontrar referência da página de destino
                            page_dest_ref = None
                            
                            if '/Dest' in annot_orig:
                                dest = annot_orig['/Dest']
                                if isinstance(dest, ArrayObject) and len(dest) > 0:
                                    page_dest_ref = dest[0]
                            elif '/A' in annot_orig:
                                action = annot_orig['/A']
                                if isinstance(action, DictionaryObject):
                                    if action.get('/S') == '/GoTo' and '/D' in action:
                                        dest = action['/D']
                                        if isinstance(dest, ArrayObject) and len(dest) > 0:
                                            page_dest_ref = dest[0]
                            
                            if page_dest_ref is None or not isinstance(page_dest_ref, IndirectObject):
                                continue
                            
                            # Encontrar qual página do PDF original este link aponta
                            idx_dest_orig = None
                            for idx_p, p in enumerate(pdf_original.pages):
                                if hasattr(p, 'indirect_reference') and p.indirect_reference == page_dest_ref:
                                    idx_dest_orig = idx_p
                                    break
                            
                            # Se não encontrou no mesmo PDF, procurar em outros (cross-PDF)
                            idx_dest_book = None
                            if idx_dest_orig is not None:
                                idx_dest_book = mapeamento_global.get((arquivo, idx_dest_orig))
                            else:
                                for outro_arq in arquivos:
                                    if outro_arq == arquivo:
                                        continue
                                    outro_pdf = pdfs_cache.get(outro_arq)
                                    if outro_pdf is None:
                                        continue
                                    for idx_p, p in enumerate(outro_pdf.pages):
                                        if hasattr(p, 'indirect_reference') and p.indirect_reference == page_dest_ref:
                                            idx_dest_book = mapeamento_global.get((outro_arq, idx_p))
                                            break
                                    if idx_dest_book is not None:
                                        break
                            
                            if idx_dest_book is None or idx_dest_book >= len(writer.pages):
                                continue
                            
                            # Criar NOVO link com destino correto no BOOK
                            rect = annot_orig['/Rect']
                            link = DictionaryObject()
                            link.update({
                                NameObject('/Type'): NameObject('/Annot'),
                                NameObject('/Subtype'): NameObject('/Link'),
                                NameObject('/Rect'): rect,
                                NameObject('/Border'): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
                                NameObject('/Dest'): ArrayObject([
                                    writer.pages[idx_dest_book].indirect_reference,
                                    NameObject('/Fit')
                                ])
                            })
                            novos_links.append(link)
                            links_arquivo += 1
                            print(f"     📎 Pág {idx_orig+1} → Pág {idx_dest_orig+1 if idx_dest_orig is not None else '?'} (orig) → Pág {idx_dest_book+1} (BOOK)")
                        
                        except Exception:
                            continue
                    
                    # Substituir links na página do BOOK: remove quebrados, adiciona corrigidos
                    if novos_links:
                        # Preservar anotações não-link existentes
                        annots_preservar = ArrayObject()
                        if '/Annots' in page_book:
                            for a_ref in page_book['/Annots']:
                                try:
                                    a_obj = a_ref.get_object() if isinstance(a_ref, IndirectObject) else a_ref
                                    if isinstance(a_obj, DictionaryObject) and a_obj.get('/Subtype') == '/Link':
                                        continue  # Remove links antigos (referências quebradas)
                                    annots_preservar.append(a_ref)
                                except:
                                    annots_preservar.append(a_ref)
                        
                        page_book[NameObject('/Annots')] = annots_preservar
                        for link in novos_links:
                            link_ref = writer._add_object(link)
                            page_book['/Annots'].append(link_ref)
                
                if links_arquivo > 0:
                    print(f"     ✅ {links_arquivo} link(s) recriado(s) com destinos corretos")
                    total_links += links_arquivo
                else:
                    print(f"     ℹ️ Nenhum link interno encontrado/corrigível")
            
            except Exception as e:
                print(f"     ⚠️ Erro ao processar links de {arquivo}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if total_links > 0:
            print(f"\n  ✅ Total: {total_links} links internos recriados!")
        
        # ETAPA 2: Adicionar bookmarks de navegação
        print("\n  📑 Adicionando bookmarks de navegação:")
        for nome, pagina_destino in capitulos:
            nome_limpo = extrair_nome_relatorio(nome)
            print(f"     • '{nome_limpo}' → página {pagina_destino}")
            writer.add_outline_item(nome_limpo, pagina_destino - 1)
        
        # ETAPA 3: Adicionar links clicáveis no índice
        pagina_indice = 1 if CRIAR_CAPA else 0
        indice_page = writer.pages[pagina_indice]
        
        page_height = 841.89
        y_inicial = page_height - 120
        altura_linha = 20
        x_esquerda = 55
        x_direita = 540
        
        if '/Annots' not in indice_page:
            indice_page[NameObject('/Annots')] = ArrayObject()
        
        print("\n  🖱️ Criando áreas clicáveis no índice:")
        for idx, (nome, pagina_destino) in enumerate(capitulos):
            y_pos = y_inicial - (idx * altura_linha)
            nome_limpo = extrair_nome_relatorio(nome)
            
            link = DictionaryObject()
            link.update({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([
                    NumberObject(x_esquerda),
                    NumberObject(y_pos - 3),
                    NumberObject(x_direita),
                    NumberObject(y_pos + 12)
                ]),
                NameObject('/Border'): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject('/Dest'): ArrayObject([
                    writer.pages[pagina_destino - 1].indirect_reference,
                    NameObject('/Fit')
                ])
            })
            
            link_ref = writer._add_object(link)
            indice_page['/Annots'].append(link_ref)
        
        print(f"     ✅ {len(capitulos)} link(s) do índice criados")
        
        # ETAPA 4: Adicionar links "Voltar ao Índice"
        print("\n  ↩️ Adicionando links 'Voltar ao Índice':")
        page_width = 595.276
        text_width = 30
        x_pos = page_width - 50
        y_pos = page_height - 30
        
        links_voltar = 0
        for i, page in enumerate(writer.pages):
            if i <= pagina_indice:
                continue  # Pular capa e índice
            
            if '/Annots' not in page:
                page[NameObject('/Annots')] = ArrayObject()
            
            link = DictionaryObject()
            link.update({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([
                    NumberObject(x_pos - text_width - 2),
                    NumberObject(y_pos - 2),
                    NumberObject(x_pos + 2),
                    NumberObject(y_pos + 10)
                ]),
                NameObject('/Border'): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject('/A'): DictionaryObject({
                    NameObject('/S'): NameObject('/GoTo'),
                    NameObject('/D'): ArrayObject([
                        writer.pages[pagina_indice].indirect_reference,
                        NameObject('/XYZ'),
                        NumberObject(0),
                        NumberObject(page_height),
                        NumberObject(0)
                    ])
                })
            })
            
            link_ref = writer._add_object(link)
            page['/Annots'].append(link_ref)
            links_voltar += 1
        
        print(f"     ✅ {links_voltar} link(s) 'Voltar ao Índice' adicionados")
        
        # Salvar PDF com todas as correções
        with open(pdf_path, "wb") as f:
            writer.write(f)
        
        print("\n✅ Todas as correções de links aplicadas com sucesso!")
        
    except Exception as e:
        print(f"⚠️ Erro ao aplicar correções de links: {e}")
        import traceback
        traceback.print_exc()


def adicionar_links_indice(pdf_path, capitulos):
    """Adiciona links clicáveis nas linhas do índice e bookmarks de navegação"""
    try:
        from pypdf.generic import DictionaryObject, ArrayObject, NameObject, NumberObject, FloatObject
        
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Copiar todas as páginas primeiro
        for page in reader.pages:
            writer.add_page(page)
        
        # Adicionar bookmarks (outline) para navegação - isso é o que faz funcionar corretamente
        print("\n🔗 Adicionando bookmarks e links no índice:")
        for nome, pagina_destino in capitulos:
            nome_limpo = extrair_nome_relatorio(nome)
            print(f"   • '{nome_limpo}' → página {pagina_destino} (índice {pagina_destino - 1})")
            writer.add_outline_item(nome_limpo, pagina_destino - 1)
        
        # Determinar qual é a página do índice
        pagina_indice = 1 if CRIAR_CAPA else 0
        indice_page = writer.pages[pagina_indice]
        
        # Dimensões da página A4
        page_height = 841.89
        
        y_inicial = page_height - 120
        altura_linha = 20
        x_esquerda = 55
        x_direita = 540
        
        # Criar ou obter array de anotações
        if '/Annots' not in indice_page:
            indice_page[NameObject('/Annots')] = ArrayObject()
        
        print("\n🖱️ Criando áreas clicáveis no índice:")
        for idx, (nome, pagina_destino) in enumerate(capitulos):
            y_pos = y_inicial - (idx * altura_linha)
            nome_limpo = extrair_nome_relatorio(nome)
            
            print(f"   Linha {idx}: '{nome_limpo}' → página {pagina_destino} (y={y_pos:.2f})")
            
            # Criar anotação de link interno - usando índice de página diretamente
            link = DictionaryObject()
            link.update({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([
                    NumberObject(x_esquerda),
                    NumberObject(y_pos - 3),
                    NumberObject(x_direita),
                    NumberObject(y_pos + 12)
                ]),
                NameObject('/Border'): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject('/Dest'): ArrayObject([
                    writer.pages[pagina_destino - 1].indirect_reference,
                    NameObject('/Fit')
                ])
            })
            
            # Adicionar link ao writer e à página
            link_ref = writer._add_object(link)
            indice_page['/Annots'].append(link_ref)
        
        # Adicionar links "Voltar ao Índice" em todas as páginas de relatórios
        adicionar_links_voltar_indice(writer)
        
        # Salvar PDF com links
        with open(pdf_path, "wb") as f:
            writer.write(f)
        
        print("✅ Links do índice adicionados com sucesso!")
        
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível adicionar links no índice: {e}")
        import traceback
        traceback.print_exc()


# ---------- ADICIONAR LINKS VOLTAR AO ÍNDICE ----------
def adicionar_links_voltar_indice(writer):
    """Adiciona links 'Voltar ao Índice' em todas as páginas de relatórios"""
    try:
        from pypdf.generic import DictionaryObject, ArrayObject, NameObject, NumberObject
        
        # Determinar página do índice
        pagina_indice_idx = 1 if CRIAR_CAPA else 0
        indice_page = writer.pages[pagina_indice_idx]
        
        # Dimensões da página A4
        page_width = 595.276
        page_height = 841.89
        
        # Posição do link "← Índice"
        texto = "← Índice"
        text_width = 30  # Aproximadamente
        x_pos = page_width - 50
        y_pos = page_height - 30
        
        # Adicionar link em todas as páginas exceto capa e índice
        for i, page in enumerate(writer.pages):
            if i <= pagina_indice_idx:
                continue  # Pular capa e índice
            
            # Criar ou obter array de anotações
            if '/Annots' not in page:
                page[NameObject('/Annots')] = ArrayObject()
            
            # Criar anotação de link para voltar ao índice
            link = DictionaryObject()
            link.update({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([
                    NumberObject(x_pos - text_width - 2),
                    NumberObject(y_pos - 2),
                    NumberObject(x_pos + 2),
                    NumberObject(y_pos + 10)
                ]),
                NameObject('/Border'): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject('/A'): DictionaryObject({
                    NameObject('/S'): NameObject('/GoTo'),
                    NameObject('/D'): ArrayObject([
                        indice_page.indirect_reference,
                        NameObject('/XYZ'),
                        NumberObject(0),
                        NumberObject(page_height),
                        NumberObject(0)
                    ])
                })
            })
            
            # Adicionar link ao writer e à página
            link_ref = writer._add_object(link)
            page['/Annots'].append(link_ref)
        
        print("✅ Links 'Voltar ao Índice' adicionados com sucesso!")
        
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível adicionar links 'Voltar ao Índice': {e}")
        import traceback
        traceback.print_exc()


def adicionar_links_manual_indice(writer, capitulos, pagina_indice_idx):
    """Adiciona links clicáveis manualmente nas linhas do índice"""
    try:
        from pypdf.generic import DictionaryObject, ArrayObject, NameObject, NumberObject
        
        indice_page = writer.pages[pagina_indice_idx]
        
        # Dimensões da página A4
        page_height = 841.89
        
        y_inicial = page_height - 120
        altura_linha = 20
        x_esquerda = 55
        x_direita = 540
        
        # Criar ou obter array de anotações
        if '/Annots' not in indice_page:
            indice_page[NameObject('/Annots')] = ArrayObject()
        else:
            # Limpar anotações existentes
            indice_page[NameObject('/Annots')] = ArrayObject()
        
        print("\n🖱️ Recriando áreas clicáveis no índice (com ESCALA):")
        for idx, (nome, pagina_destino) in enumerate(capitulos):
            y_pos = y_inicial - (idx * altura_linha)
            nome_limpo = extrair_nome_relatorio(nome) if nome != "ESCALA" else "ESCALA"
            
            print(f"   Linha {idx}: '{nome_limpo}' → página {pagina_destino} (y={y_pos:.2f})")
            
            # Criar anotação de link interno
            link = DictionaryObject()
            link.update({
                NameObject('/Type'): NameObject('/Annot'),
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([
                    NumberObject(x_esquerda),
                    NumberObject(y_pos - 3),
                    NumberObject(x_direita),
                    NumberObject(y_pos + 12)
                ]),
                NameObject('/Border'): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject('/Dest'): ArrayObject([
                    writer.pages[pagina_destino - 1].indirect_reference,
                    NameObject('/Fit')
                ])
            })
            
            # Adicionar link ao writer e à página
            link_ref = writer._add_object(link)
            indice_page['/Annots'].append(link_ref)
        
        print("✅ Links do índice atualizados com sucesso!")
        
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível atualizar links no índice: {e}")
        import traceback
        traceback.print_exc()


def ordenar_relatorios(arquivo):
    """Define a ordem de apresentação dos relatórios no book"""
    arquivo_upper = arquivo.upper()
    
    # Verificar na ordem de prioridade (mais específico primeiro)
    # SUMARIOS devem vir PRIMEIRO (são mais específicos)
    if ('SUMARIO' in arquivo_upper or 'SUMÁRIO' in arquivo_upper):
        if 'APRESENTA' in arquivo_upper:
            return 1  # SUMARIO_HORAS_APRESENTACAO
        elif 'EXTRA' in arquivo_upper and 'REPOUSO' in arquivo_upper:
            return 5  # SUMARIO_HORAS_REPOUSO_EXTRA
        elif 'CORTE' in arquivo_upper:
            return 9  # SUMARIO_HORAS_TEMPO_CORTE
        else:
            return 13  # SUMARIO DE HORAS EM SOLO (original)
    
    # Relatórios normais
    if 'APRESENTA' in arquivo_upper:
        return 2
    elif 'OPERACAO' in arquivo_upper or 'OPERAÇÃO' in arquivo_upper:
        return 3
    elif 'PLANTAO' in arquivo_upper or 'PLANTÃO' in arquivo_upper:
        return 4
    elif 'EXTRA' in arquivo_upper and 'REPOUSO' in arquivo_upper:
        return 6  # REPOUSO EXTRA
    elif 'REPOUSO' in arquivo_upper:
        return 7
    elif 'RESERVA' in arquivo_upper:
        return 8
    elif 'CORTE' in arquivo_upper:
        return 10
    elif 'JORNADA' in arquivo_upper:
        return 11
    elif 'SOLO' in arquivo_upper:
        return 12
    elif 'TREINAMENTO' in arquivo_upper:
        return 14
    else:
        return 999


def remover_arquivos_duplicados(arquivos):
    """Remove versões antigas de arquivos duplicados, mantendo apenas o mais recente"""
    # Agrupar arquivos por tipo (base do nome sem timestamp)
    grupos = {}
    
    for arquivo in arquivos:
        # Extrair base do nome removendo timestamps (formato YYYYMMDD_HHMMSS)
        import re
        # Remove padrões como _20260128_092432 do nome
        base_nome = re.sub(r'_\d{8}_\d{6}', '', arquivo)
        
        if base_nome not in grupos:
            grupos[base_nome] = []
        grupos[base_nome].append(arquivo)
    
    # Para cada grupo, manter apenas o arquivo mais recente
    arquivos_finais = []
    removidos = []
    
    for base_nome, lista_arquivos in grupos.items():
        if len(lista_arquivos) > 1:
            # Ordenar por nome (timestamps estão no nome, então ordem alfabética = ordem cronológica)
            lista_arquivos.sort()
            arquivo_mantido = lista_arquivos[-1]  # Último (mais recente)
            
            print(f"\n⚠️ Encontrados {len(lista_arquivos)} versões de '{base_nome}.pdf':")
            for arq in lista_arquivos:
                if arq == arquivo_mantido:
                    print(f"   ✅ USANDO: {arq}")
                else:
                    print(f"   ❌ IGNORANDO: {arq}")
            
            arquivos_finais.append(arquivo_mantido)
            removidos.extend([a for a in lista_arquivos if a != arquivo_mantido])
        else:
            arquivos_finais.append(lista_arquivos[0])
    
    if removidos:
        print(f"\n📊 Total de arquivos duplicados ignorados: {len(removidos)}")
    
    return arquivos_finais


# PROCESSAMENTO PRINCIPAL
# =========================
def main():
    global NOME_SAIDA

    def _arquivo_corresponde_prefixo(arquivo: str, prefixo: str) -> bool:
        """
        Faz match por prefixo com proteção para evitar colisão entre:
        - REPOUSO vs REPOUSO_EXTRA
        - SUMARIO_HORAS_REPOUSO vs SUMARIO_HORAS_REPOUSO_EXTRA
        """
        if not arquivo.startswith(prefixo):
            return False

        arq_upper = arquivo.upper()
        pref_upper = prefixo.upper()

        if "_REPOUSO_" in pref_upper and "_REPOUSO_EXTRA_" not in pref_upper:
            if "_REPOUSO_EXTRA_" in arq_upper:
                return False

        if "SUMARIO_HORAS_REPOUSO_" in pref_upper and "SUMARIO_HORAS_REPOUSO_EXTRA_" not in pref_upper:
            if "SUMARIO_HORAS_REPOUSO_EXTRA_" in arq_upper:
                return False

        return True

    global NOME_SAIDA, AUTOR

    pasta_pdfs = _obter_pasta_pdfs()
    if not pasta_pdfs:
        return
    
    # Tenta detectar a escala na pasta e subpastas de auditoria
    arquivo_escala = _detectar_pdf_escala_automatico(pasta_pdfs)
    
    nome_aeronauta_detectado = None
    re_aero = None
    base_escala = None
    
    if arquivo_escala:
        base_escala = os.path.splitext(os.path.basename(arquivo_escala))[0]
        nome_aeronauta_detectado = extrair_nome_aeronauta_para_arquivo(arquivo_escala)
        # Tenta extrair o RE do nome base da escala (ex: escala_p_Italo_Pinheiro_GRU__3829849___LATAM_CMTE...)
        m_re = re.search(r"__(\d+)___", base_escala)
        if m_re:
            re_aero = m_re.group(1)

    # Procura por arquivos TXT de conformidade pertencentes a este aeronauta para converter para PDF
    arquivos_txt = [
        f for f in os.listdir(pasta_pdfs)
        if f.lower().endswith(".txt") and "CONFORMIDADE" in f.upper()
    ]
    for f_txt in arquivos_txt:
        pertence = False
        f_txt_upper = f_txt.upper()
        if not nome_aeronauta_detectado:
            pertence = True
        elif base_escala and f_txt_upper.startswith(base_escala.upper()):
            pertence = True
        elif re_aero and str(re_aero) in f_txt_upper:
            pertence = True
        else:
            nome_norm = nome_aeronauta_detectado.upper().replace('_', ' ')
            partes_nome = [p for p in nome_norm.split() if len(p) > 2]
            if partes_nome and all(part in f_txt_upper.replace('_', ' ') for part in partes_nome):
                pertence = True
                
        if pertence:
            pdf_correspondente = f_txt[:-4] + ".pdf"
            txt_caminho = os.path.join(pasta_pdfs, f_txt)
            pdf_caminho = os.path.join(pasta_pdfs, pdf_correspondente)
            
            if not os.path.exists(pdf_caminho) or os.path.getmtime(txt_caminho) > os.path.getmtime(pdf_caminho):
                print(f"📄 Convertendo relatório de conformidade '{f_txt}' para PDF...")
                _converter_txt_conformidade_para_pdf(txt_caminho, pdf_caminho)

    # Lista arquivos PDF no diretório
    arquivos_pasta = [
        f for f in os.listdir(pasta_pdfs)
        if f.lower().endswith(".pdf") and not f.upper().startswith("BOOK_FINAL_")
    ]

    # Se a escala não localizou o aeronauta, tenta inspecionando os PDFs na pasta
    if not nome_aeronauta_detectado:
        nome_aeronauta_detectado = detectar_nome_aeronauta_para_saida(arquivos_pasta)

    # Configuração dinâmica de AUTOR e NOME_SAIDA
    sufixo_data_processamento = f"_{datetime.now().strftime('%d%m%Y')}"
    if nome_aeronauta_detectado:
        AUTOR = nome_aeronauta_detectado.replace('_', ' ').strip().title()
        NOME_SAIDA = f"BOOK_FINAL_{nome_aeronauta_detectado}{sufixo_data_processamento}.pdf"
    else:
        NOME_SAIDA = f"BOOK_FINAL_{AUTOR.replace(' ', '_')}{sufixo_data_processamento}.pdf"

    # Mapeamento dinâmico e ordenado das categorias de relatórios
    categorias_relatorios = [
        {
            "id": "CONFORMIDADE",
            "titulo": "RELATÓRIO DE CONFORMIDADE",
            "matches": lambda f: "CONFORMIDADE" in f.upper()
        },
        {
            "id": "APRESENTACAO_REL",
            "titulo": "APRESENTAÇÃO RELATÓRIO",
            "matches": lambda f: ("APRESENTACAO" in f.upper() or "APRESENTAÇÃO" in f.upper()) and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "APRESENTACAO_SUM",
            "titulo": "SUMÁRIO APRESENTAÇÃO",
            "matches": lambda f: ("APRESENTACAO" in f.upper() or "APRESENTAÇÃO" in f.upper()) and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "CORTE_REL",
            "titulo": "CORTE RELATÓRIO",
            "matches": lambda f: "CORTE" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "CORTE_SUM",
            "titulo": "SUMÁRIO CORTE",
            "matches": lambda f: "CORTE" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "OPERACAO_REL",
            "titulo": "OPERAÇÃO RELATÓRIO",
            "matches": lambda f: ("OPERACAO" in f.upper() or "OPERAÇÃO" in f.upper()) and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "OPERACAO_SUM",
            "titulo": "SUMÁRIO OPERAÇÃO",
            "matches": lambda f: ("OPERACAO" in f.upper() or "OPERAÇÃO" in f.upper()) and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "SOLO_REL",
            "titulo": "SOLO RELATÓRIO",
            "matches": lambda f: "SOLO" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "SOLO_SUM",
            "titulo": "SUMÁRIO SOLO",
            "matches": lambda f: "SOLO" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "JORNADA_REL",
            "titulo": "JORNADA RELATÓRIO",
            "matches": lambda f: "JORNADA" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "JORNADA_SUM",
            "titulo": "SUMÁRIO JORNADA",
            "matches": lambda f: "JORNADA" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "REPOUSO_REL",
            "titulo": "REPOUSO RELATÓRIO",
            "matches": lambda f: "REPOUSO" in f.upper() and "EXTRA" not in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "REPOUSO_SUM",
            "titulo": "SUMÁRIO REPOUSO",
            "matches": lambda f: "REPOUSO" in f.upper() and "EXTRA" not in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "REPOUSO_EXTRA_REL",
            "titulo": "REPOUSO EXTRA RELATÓRIO",
            "matches": lambda f: "REPOUSO" in f.upper() and "EXTRA" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "REPOUSO_EXTRA_SUM",
            "titulo": "SUMÁRIO REPOUSO EXTRA",
            "matches": lambda f: "REPOUSO" in f.upper() and "EXTRA" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "RESERVA_REL",
            "titulo": "RESERVA RELATÓRIO",
            "matches": lambda f: "RESERVA" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "RESERVA_SUM",
            "titulo": "SUMÁRIO RESERVA",
            "matches": lambda f: "RESERVA" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper() or "EXPLORAR" in f.upper())
        },
        {
            "id": "PLANTAO_REL",
            "titulo": "PLANTÃO RELATÓRIO",
            "matches": lambda f: ("PLANTAO" in f.upper() or "PLANTÃO" in f.upper()) and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "PLANTAO_SUM",
            "titulo": "SUMÁRIO PLANTÃO",
            "matches": lambda f: ("PLANTAO" in f.upper() or "PLANTÃO" in f.upper()) and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        },
        {
            "id": "TREINAMENTO_REL",
            "titulo": "TREINAMENTO RELATÓRIO",
            "matches": lambda f: "TREINAMENTO" in f.upper() and "SUMARIO" not in f.upper() and "SUMÁRIO" not in f.upper()
        },
        {
            "id": "TREINAMENTO_SUM",
            "titulo": "SUMÁRIO TREINAMENTO",
            "matches": lambda f: "TREINAMENTO" in f.upper() and ("SUMARIO" in f.upper() or "SUMÁRIO" in f.upper())
        }
    ]

    def _pertence_ao_aeronauta(nome_arquivo: str) -> bool:
        if not nome_aeronauta_detectado:
            return True
            
        f_upper = nome_arquivo.upper()
        
        # Caso comece com o nome base da escala
        if base_escala and f_upper.startswith(base_escala.upper()):
            return True
            
        # Caso contenha o RE
        if re_aero and str(re_aero) in f_upper:
            return True
            
        # Caso contenha o nome do aeronauta (em partes)
        nome_norm = nome_aeronauta_detectado.upper().replace('_', ' ')
        partes_nome = [p for p in nome_norm.split() if len(p) > 2]
        if partes_nome and all(part in f_upper.replace('_', ' ') for part in partes_nome):
            return True
            
        return False

    # Filtrar relatórios
    arquivos = []
    print("\n🔍 Analisando relatórios na pasta de PDFs...")
    for cat in categorias_relatorios:
        encontrados = []
        for f in arquivos_pasta:
            if cat["matches"](f) and _pertence_ao_aeronauta(f):
                encontrados.append(f)
        if encontrados:
            # Seleciona o mais recente por timestamp (ordem alfabética é robusta para o formato de data YYYYMMDD_HHMMSS)
            arquivo_usar = sorted(encontrados)[-1]
            arquivos.append(arquivo_usar)
            print(f"  ✓ Encontrado {cat['titulo']}: {arquivo_usar}")

    # Anexar holerites automaticamente (subpasta "holerites")
    pasta_holerites, arquivos_holerite = _listar_pdfs_holerites(pasta_pdfs)
    if arquivos_holerite:
        print(f"\n📎 Serão incluídos {len(arquivos_holerite)} holerite(s) automaticamente ao final do BOOK:")
        for arq in arquivos_holerite:
            print(f"   - {arq}")
    else:
        print("\nℹ️ Subpasta 'holerites' inexistente ou sem PDFs. BOOK será criado sem holerites.")

    print(f"\nEncontrados {len(arquivos)} arquivos PDF na ordem definida:")
    for arq in arquivos:
        print(f"  - {arq}")
    print()

    writer = PdfWriter()
    capitulos = []
    pagina_atual = 1

    # CAPA
    if CRIAR_CAPA:
        criar_capa("__capa_tmp.pdf")
        capa_reader = PdfReader("__capa_tmp.pdf")
        for page in capa_reader.pages:
            writer.add_page(page)
        pagina_atual += 1

    # PDFs PRINCIPAIS
    print("\n➡️ Adicionando PDFs ao BOOK:")
    mapeamento_global = {}
    capitulos = []
    for idx_arquivo, arquivo in enumerate(arquivos):
        try:
            caminho_completo = os.path.join(pasta_pdfs, arquivo)
            pdf_reader = PdfReader(caminho_completo)
            num_paginas = len(pdf_reader.pages)
            print(f"  📄 {arquivo}")
            print(f"     Páginas no arquivo original: {num_paginas}")
            offset_paginas = len(writer.pages)
            print(f"     Offset de páginas no BOOK: {offset_paginas}")
            for idx_orig in range(num_paginas):
                idx_no_book = offset_paginas + idx_orig
                mapeamento_global[(arquivo, idx_orig)] = idx_no_book
            for idx_page, page in enumerate(pdf_reader.pages):
                try:
                    writer.add_page(page)
                except Exception as e:
                    print(f"     ⚠️ Erro ao adicionar página {idx_page + 1}: {str(e)[:100]}")
                    continue
            # Sempre usar o nome do arquivo para o índice
            capitulos.append((arquivo, offset_paginas + 1))
        except Exception as e:
            print(f"  ⚠️ Erro ao processar {arquivo}: {e}")
            print(f"     Este arquivo será IGNORADO no BOOK final.")


    # Adicionar holerites ao final, cada um com sua entrada no índice
    holerite_primeira_pagina = None
    for arquivo_holerite in arquivos_holerite:
        caminho_completo = os.path.join(pasta_holerites, arquivo_holerite) if pasta_holerites else os.path.join(pasta_pdfs, arquivo_holerite)
        try:
            pdf_reader = PdfReader(caminho_completo)
            num_paginas = len(pdf_reader.pages)
            print(f"  📄 (HOLERITE) {arquivo_holerite} - {num_paginas} página(s)")
            offset_paginas = len(writer.pages)
            if holerite_primeira_pagina is None:
                holerite_primeira_pagina = offset_paginas + 1
            for idx_page, page in enumerate(pdf_reader.pages):
                writer.add_page(page)
        except Exception as e:
            print(f"  ⚠️ Erro ao processar holerite {arquivo_holerite}: {e}")
            print(f"     Este holerite será IGNORADO no BOOK final.")
    # Adiciona apenas uma entrada "HOLERITES" no índice, se houver holerites
    if arquivos_holerite and holerite_primeira_pagina is not None:
        capitulos.append(("HOLERITES", holerite_primeira_pagina))

    print(f"\n📊 Total de páginas no BOOK (antes da numeração): {len(writer.pages)}\n")

    # SALVAR ARQUIVO TEMPORÁRIO (sem correção de links ainda)
    with open("__book_tmp.pdf", "wb") as f:
        writer.write(f)

    print("\n🔍 Verificando integridade antes da numeração...")
    test_reader = PdfReader("__book_tmp.pdf")
    print(f"   Total de páginas no arquivo temporário: {len(test_reader.pages)}")

    # Copiar arquivo temporário para pasta de PDFs
    import shutil
    nome_saida_final = os.path.join(pasta_pdfs, NOME_SAIDA)
    shutil.copy("__book_tmp.pdf", nome_saida_final)
    print(f"\n✅ Arquivo base criado (SEM numeração para preservar conteúdo): {nome_saida_final}")

    # Anexar escala automaticamente via subpasta Auditoria_Calculos
    arquivo_escala = _detectar_pdf_escala_automatico(pasta_pdfs)
    if arquivo_escala:
        print(f"\n📎 Anexando escala ao BOOK...")
        print(f"   Arquivo: {os.path.basename(arquivo_escala)}")
        try:
            adicionar_escala_ao_book(nome_saida_final, arquivo_escala, capitulos)
            # Índice foi inserido: todas as páginas deslocaram +1
            mapeamento_global = {k: v + 1 for k, v in mapeamento_global.items()}
            capitulos = [(nome, pag + 1) for nome, pag in capitulos]
            # Adicionar escala aos capítulos
            escala_reader_tmp = PdfReader(arquivo_escala)
            book_reader_tmp = PdfReader(nome_saida_final)
            pagina_escala = len(book_reader_tmp.pages) - len(escala_reader_tmp.pages) + 1
            capitulos.append(("ESCALA", pagina_escala))
            print(f"   ✅ Escala anexada. Mapeamento atualizado (+1 por inserção do índice).")
        except Exception as e:
            print(f"   ❌ Erro ao anexar escala: {e}")
            import traceback
            traceback.print_exc()
            if not _modo_sem_popup():
                messagebox.showerror("Erro", f"Não foi possível anexar a escala:\n{e}")
    else:
        print("\nℹ️ Nenhum PDF de escala elegível encontrado. Inserindo índice remissivo sem anexo de escala...")
        try:
            inserir_indice_no_book(nome_saida_final, capitulos)
            # Índice foi inserido: todas as páginas deslocaram +1
            mapeamento_global = {k: v + 1 for k, v in mapeamento_global.items()}
            capitulos = [(nome, pag + 1) for nome, pag in capitulos]
            print("   ✅ Índice remissivo inserido com sucesso.")
        except Exception as e:
            print(f"   ❌ Erro ao inserir índice remissivo: {e}")
            import traceback
            traceback.print_exc()
            if not _modo_sem_popup():
                messagebox.showerror("Erro", f"Não foi possível inserir o índice remissivo:\n{e}")

    # Aplicar correção de links E adicionar links do índice NO FINAL
    # (após toda a montagem, incluindo escala se houver)
    aplicar_links_completo(nome_saida_final, capitulos, arquivos + arquivos_holerite, pasta_pdfs, mapeamento_global)

    # Limpeza
    for f in ["__capa_tmp.pdf", "__indice_tmp.pdf", "__book_tmp.pdf"]:
        if os.path.exists(f):
            os.remove(f)

    print(f"\n✅ BOOK FINAL criado com sucesso: {nome_saida_final}")
    print(f"   Localização: {os.path.dirname(nome_saida_final)}")
    if not _modo_sem_popup():
        messagebox.showinfo("Sucesso", f"BOOK criado com sucesso!\n\nArquivo: {os.path.basename(nome_saida_final)}\nLocalização: {os.path.dirname(nome_saida_final)}\n\nTotal de {len(arquivos) + len(arquivos_holerite)} PDFs unidos.")


def adicionar_escala_ao_book(book_path, arquivo_escala, capitulos_originais):
    """
    Adiciona PDF da escala e página de índice ao BOOK.
    Usa CÓPIA ÚNICA (book_reader → new_writer) para preservar links internos.
    NÃO adiciona bookmarks/links de navegação (isso é feito por aplicar_links_completo depois).
    """
    try:
        from pypdf.generic import NameObject, ArrayObject
        
        # Ler BOOK atual e escala
        book_reader = PdfReader(book_path)
        escala_reader = PdfReader(arquivo_escala)
        num_paginas_book = len(book_reader.pages)
        num_paginas_escala = len(escala_reader.pages)
        print(f"   Páginas no BOOK atual: {num_paginas_book}")
        print(f"   Páginas na escala: {num_paginas_escala}")
        
        # Calcular capítulos ajustados (+1 pelo índice inserido)
        capitulos_ajustados = [(nome, pagina + 1) for nome, pagina in capitulos_originais]
        pagina_escala = num_paginas_book + 1  # +1 pelo índice inserido
        capitulos_com_escala = capitulos_ajustados + [("ESCALA", pagina_escala)]
        
        # Criar página de índice com conteúdo visual correto
        indice_buffer = io.BytesIO()
        criar_indice(indice_buffer, capitulos_com_escala)
        indice_buffer.seek(0)
        indice_pdf = PdfReader(indice_buffer)
        
        # CÓPIA ÚNICA: book_reader → new_writer diretamente
        new_writer = PdfWriter()
        
        # 1. Capa (se houver)
        if CRIAR_CAPA:
            new_writer.add_page(book_reader.pages[0])
        
        # 2. Página de índice (inserida)
        new_writer.add_page(indice_pdf.pages[0])
        
        # 3. Conteúdo do BOOK (todas as páginas exceto capa)
        start_idx = 1 if CRIAR_CAPA else 0
        for i in range(start_idx, num_paginas_book):
            new_writer.add_page(book_reader.pages[i])
        
        # 4. Páginas da escala
        for page in escala_reader.pages:
            new_writer.add_page(page)
        
        print(f"   Total de páginas no BOOK com escala e índice: {len(new_writer.pages)}")
        
        # Salvar (sem bookmarks/links — serão adicionados por aplicar_links_completo)
        with open(book_path, "wb") as f:
            new_writer.write(f)
        
        print(f"   ✅ {num_paginas_escala} página(s) da escala e página de índice inseridas!")
    
    except Exception as e:
        raise e


def inserir_indice_no_book(book_path, capitulos_originais):
    """Insere apenas a página de índice no BOOK (sem anexar escala)."""
    try:
        book_reader = PdfReader(book_path)
        num_paginas_book = len(book_reader.pages)
        print(f"   Páginas no BOOK atual: {num_paginas_book}")

        capitulos_ajustados = [(nome, pagina + 1) for nome, pagina in capitulos_originais]

        indice_buffer = io.BytesIO()
        criar_indice(indice_buffer, capitulos_ajustados)
        indice_buffer.seek(0)
        indice_pdf = PdfReader(indice_buffer)

        new_writer = PdfWriter()

        # 1. Capa (se houver)
        if CRIAR_CAPA:
            new_writer.add_page(book_reader.pages[0])

        # 2. Índice
        new_writer.add_page(indice_pdf.pages[0])

        # 3. Conteúdo restante
        start_idx = 1 if CRIAR_CAPA else 0
        for i in range(start_idx, num_paginas_book):
            new_writer.add_page(book_reader.pages[i])

        with open(book_path, "wb") as f:
            new_writer.write(f)

        print("   ✅ Página de índice inserida no BOOK.")

    except Exception as e:
        raise e


if __name__ == "__main__":
    main()

