# app.spec - Version Manuelle et Fiable

import os
import sys

# On ne cherche plus les chemins automatiquement.
# On se fie à l'analyse de PyInstaller, aidée par les hiddenimports.

block_cipher = None

binaries = [
    ('bin/ffmpeg.exe', '.'),
    ('bin/libopus-0.x64.dll', '.')
]

# datas est maintenant très simple. On ne copie NI nacl NI cffi ici.
datas = [
    ('assets', 'assets')
]

# C'est ici que toute la magie opère.
# On liste TOUT ce qui est nécessaire pour forcer PyInstaller à tout trouver.
hiddenimports = [
    'playify_bot',
    'pystray._win32',
    'PIL.Image',
    'discord.ext.commands',
    'discord.ext.tasks',
    
    # --- Forçage de PyNaCl et CFFI ---
    'nacl',
    'nacl.secret',
    'nacl.utils',
    'nacl.bindings',
    'nacl.hash',
    'nacl.pwhash',
    'nacl.signing',
    'nacl.public',
    'cffi',
    'cffi._cffi_backend'
]

# --- Le reste du fichier de build ---
a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[], # Plus besoin du hook avec cette méthode
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
    name='Playify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/images/playify.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Playify',
)
