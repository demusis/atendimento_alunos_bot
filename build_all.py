import os
import shutil
import subprocess
import sys

def run():
    print("🚀 Iniciando processo de compilação...")
    
    # 1. Limpeza
    for folder in ["build", "dist", "installer"]:
        if os.path.exists(folder):
            print(f"🧹 Removendo {folder}...")
            shutil.rmtree(folder)
    
    # 2. PyInstaller
    print("📦 Gerando executável com PyInstaller...")
    res = subprocess.run(["pyinstaller", "--clean", "AtendimentoBot.spec"])
    if res.returncode != 0:
        print("❌ Erro na compilação do PyInstaller!")
        sys.exit(res.returncode)
    
    # 3. Inno Setup
    iscc = os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Inno Setup 6", "ISCC.exe")
    if not os.path.exists(iscc):
        iscc = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Inno Setup 6", "ISCC.exe")
    if not os.path.exists(iscc):
        # Check Local AppData
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            iscc = os.path.join(local_appdata, "Programs", "Inno Setup 6", "ISCC.exe")
    
    if os.path.exists(iscc):
        print("🔨 Gerando instalador (Setup) com Inno Setup...")
        res = subprocess.run([iscc, "installer_script.iss"])
        if res.returncode == 0:
            print("✅ Instalador criado com sucesso em: .\\installer\\Setup_AtendimentoBot.exe")
        else:
            print("⚠️ Falha ao gerar o instalador Inno Setup.")
    else:
        print("ℹ️ Inno Setup não encontrado. O executável standalone está disponível na pasta .\\dist\\AtendimentoBot")
    
    print("🏁 Processo concluído!")

if __name__ == "__main__":
    run()
