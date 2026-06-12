import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

from pypdf import PdfReader, PdfWriter


def extrair_data_do_nome(nome_arquivo: str):
    """
    Tenta extrair data do nome do arquivo em formatos comuns.
    Retorna datetime ou None.
    """
    nome = os.path.splitext(os.path.basename(nome_arquivo))[0]

    padroes = [
        # DDMMYYYY
        (r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)", "%d%m%Y"),
        # YYYYMMDD
        (r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", "%Y%m%d"),
        # DD-MM-YYYY / DD_MM_YYYY / DD.MM.YYYY / DD/MM/YYYY
        (r"(?<!\d)(\d{2})[-_./](\d{2})[-_./](\d{4})(?!\d)", "%d%m%Y"),
        # YYYY-MM-DD / YYYY_MM_DD / YYYY.MM.DD / YYYY/MM/DD
        (r"(?<!\d)(\d{4})[-_./](\d{2})[-_./](\d{2})(?!\d)", "%Y%m%d"),
        # DDMMYY
        (r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", "%d%m%y"),
    ]

    for regex, fmt in padroes:
        m = re.search(regex, nome)
        if not m:
            continue

        token = "".join(m.groups())
        try:
            return datetime.strptime(token, fmt)
        except ValueError:
            continue

    return None


def chave_ordenacao_pdf(caminho_pdf: str):
    """
    Ordena por data no nome do arquivo.
    Se não encontrar data, usa data de modificação do arquivo.
    """
    data_nome = extrair_data_do_nome(caminho_pdf)
    if data_nome is not None:
        return (0, data_nome, os.path.basename(caminho_pdf).lower())

    data_mtime = datetime.fromtimestamp(os.path.getmtime(caminho_pdf))
    return (1, data_mtime, os.path.basename(caminho_pdf).lower())


def unir_pdfs(caminhos_ordenados, caminho_saida):
    """
    Une PDFs em sequência.

    Regra fixa de cabeçalho:
    - 1º PDF: mantém todas as páginas
    - PDFs seguintes: remove a 1ª página (cabeçalho), se houver mais de 1 página
    """
    writer = PdfWriter()

    total_paginas_adicionadas = 0
    total_cabecalhos_removidos = 0

    for i, caminho in enumerate(caminhos_ordenados):
        reader = PdfReader(caminho)
        qtd_paginas = len(reader.pages)

        pagina_inicial = 0
        if i > 0:
            if qtd_paginas > 1:
                pagina_inicial = 1
                total_cabecalhos_removidos += 1
            else:
                print(f"Aviso: '{os.path.basename(caminho)}' tem apenas 1 página; nada para remover.")

        for p in range(pagina_inicial, qtd_paginas):
            writer.add_page(reader.pages[p])
            total_paginas_adicionadas += 1

    with open(caminho_saida, "wb") as f:
        writer.write(f)

    return total_paginas_adicionadas, total_cabecalhos_removidos


def main():
    root = tk.Tk()
    root.withdraw()

    arquivos = filedialog.askopenfilenames(
        title="Selecione os PDFs para unir",
        filetypes=[("Arquivos PDF", "*.pdf")],
    )

    if not arquivos:
        messagebox.showwarning("Cancelado", "Nenhum arquivo selecionado.")
        return

    arquivos = list(arquivos)
    arquivos_ordenados = sorted(arquivos, key=chave_ordenacao_pdf)

    print("\nOrdem final de união:")
    for idx, arq in enumerate(arquivos_ordenados, start=1):
        data = extrair_data_do_nome(arq)
        if data:
            print(f"{idx:02d}. {os.path.basename(arq)}  | data_nome={data.strftime('%d/%m/%Y')}")
        else:
            print(f"{idx:02d}. {os.path.basename(arq)}  | data_nome=não encontrada (usando modificação)")

    pasta_padrao = os.path.dirname(arquivos_ordenados[0])
    nome_padrao = f"PDF_UNIFICADO_{datetime.now().strftime('%d%m%Y_%H%M%S')}.pdf"

    saida = filedialog.asksaveasfilename(
        title="Salvar PDF unificado como",
        defaultextension=".pdf",
        filetypes=[("Arquivos PDF", "*.pdf")],
        initialdir=pasta_padrao,
        initialfile=nome_padrao,
    )

    if not saida:
        messagebox.showwarning("Cancelado", "Salvamento cancelado.")
        return

    try:
        paginas, cabecalhos = unir_pdfs(
            caminhos_ordenados=arquivos_ordenados,
            caminho_saida=saida,
        )

        msg = (
            f"PDFs unidos com sucesso!\n\n"
            f"Arquivo: {saida}\n"
            f"Total de PDFs: {len(arquivos_ordenados)}\n"
            f"Páginas no resultado: {paginas}\n"
            f"Cabeçalhos removidos (1ª página dos PDFs após o primeiro): {cabecalhos}"
        )
        print("\n" + msg)
        messagebox.showinfo("Sucesso", msg)

    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao unir PDFs: {e}")
        print(f"Erro ao unir PDFs: {e}")


if __name__ == "__main__":
    main()
