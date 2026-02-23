# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# List of scripts
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('arquivos', 'arquivos'),
        ('config_example.json', '.'),
        ('LICENSE', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'requests',
        'json',
        'asyncio',
        'psutil',
        'GPUtil',
        'speedtest',
        'httpx',
        'telegram',
        'telegram.ext',
        'docx',
        'PyPDF2',
        'langchain',
        'chromadb',
        'pysqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AtendimentoBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False to hide the terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app_icon.ico', # Add icon if available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AtendimentoBot',
)
