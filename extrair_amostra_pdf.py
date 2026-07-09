import os
import tkinter as tk
from tkinter import filedialog
import pdfplumber

def main():
    root = tk.Tk()
    root.withdraw()
    
    caminho_pdf = filedialog.askopenfilename(
        title="Selecione o arquivo PDF da Escala CrewTopia",
        filetypes=[("Arquivos PDF", "*.pdf")]
    )
    
    if not caminho_pdf:
        print("Nenhum arquivo selecionado.")
        return

    print(f"Extraindo texto de: {caminho_pdf}")
    texto_extraido = []
    
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for i, pagina in enumerate(pdf.pages):
                # Usar layout=True preserva a formatação em colunas
                texto = pagina.extract_text(layout=True)
                if texto:
                    texto_extraido.append(f"--- PÁGINA {i+1} ---\n{texto}\n")
                else:
                    texto = pagina.extract_text()
                    texto_extraido.append(f"--- PÁGINA {i+1} (sem layout) ---\n{texto}\n")
                
        caminho_txt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amostra_crewtopia.txt")
        with open(caminho_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(texto_extraido))
            
        print(f"\nSucesso! O texto foi extraído e salvo em: {caminho_txt}")
        print("Volte para o chat e me avise que o arquivo 'amostra_crewtopia.txt' foi gerado para que eu possa lê-lo.")
        
    except Exception as e:
        print(f"Erro ao ler o PDF: {e}")
        
    input("Pressione ENTER para fechar...")

if __name__ == "__main__":
    main()
