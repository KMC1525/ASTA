"""Game Engine — exportação (Publish): web, Windows, macOS, Linux, Android e iOS.

O jogo é HTML/JS puro (nada de servidor, sem `fetch`), então **toda exportação leva o jogo jogável** — abre com dois cliques em qualquer navegador moderno. Para cada plataforma o ASTA monta, além disso,
um **projeto nativo pronto para compilar** (Electron no desktop, Capacitor no Android e no iOS) e um fluxo do GitHub Actions que gera os instaladores sem precisar das ferramentas na sua máquina:

    web      jogo + PWA (manifest, service worker, ícones)
    win      Jogar.bat (abre em janela de app) + projeto Electron (.exe instalador/portátil)
    macos    Jogar.command + projeto Electron (.dmg)
    linux    jogar.sh + .desktop + projeto Electron (AppImage/.deb)
    android  projeto Capacitor (APK/AAB pelo Gradle) + fluxo do GitHub Actions
    ios      projeto Capacitor (Xcode) + fluxo do GitHub Actions (build de simulador; aparelho/App Store exigem conta Apple Developer)

Limite honesto: o ASTA **não compila** binários nativos nem assina nada — isso exige o Node, o Android SDK ou o Xcode (e, no iOS, uma conta Apple). O que ele entrega é o pacote jogável e o projeto pronto."""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from .. import __version__
from ..util import new_id, slugify, text
from . import art, manager as M, schema as S

PLATFORMS = ("web", "win", "macos", "linux", "android", "ios")
PLATFORM_LABEL = {"web": "Web (HTML5 + PWA)", "win": "Windows", "macos": "macOS", "linux": "Linux", "android": "Android", "ios": "iOS"}
SUFFIX = {"web": "web", "win": "windows", "macos": "macos", "linux": "linux", "android": "android", "ios": "ios"}


def _slug(m: Dict[str, Any]) -> str:
    return slugify(m.get("name", "jogo"), "jogo", 32)


def _pkg_id(m: Dict[str, Any], pub: Dict[str, Any]) -> str:
    raw = re.sub(r"[^a-z0-9.]", "", str(pub.get("package") or (m.get("settings") or {}).get("package") or "").lower())
    if re.match(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$", raw):
        return raw
    return "com.asta.game." + re.sub(r"[^a-z0-9]", "", _slug(m)) or "com.asta.game.jogo"


def _version(pub: Dict[str, Any]) -> str:
    v = str(pub.get("version") or "1.0.0")
    return v if re.match(r"^\d+\.\d+\.\d+$", v) else "1.0.0"


def game_files(mgr: Any, pid: str, pwa: bool = False) -> Dict[str, bytes]:
    """Os arquivos do jogo jogável (URLs relativas): index.html, data.js, motor, three.js (3D/VR/AR), imagens, sons e scripts."""
    d = mgr.dir(pid)
    m = mgr.meta(pid)
    kind = m.get("kind", "2d")
    files: Dict[str, bytes] = {"index.html": mgr.index_html(pid, "", edit=False).encode("utf-8"), "data.js": mgr.data_js(pid, "").encode("utf-8")}
    for name in M.ENGINE_FILES:
        files["engine/" + name] = (M.RUNTIME / name).read_bytes()
    if S.KINDS.get(kind, S.KINDS["2d"])["dim"] == "3d":
        files["vendor/three.min.js"] = M.THREE.read_bytes()
        lic = M.THREE.with_name("THREE_LICENSE.txt")
        if lic.is_file():
            files["vendor/THREE_LICENSE.txt"] = lic.read_bytes()
    game = d / "game"
    for p in sorted(game.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(game).as_posix()
        if rel.startswith(("scenes/", "maps/")):   # já estão dentro do data.js
            continue
        files["game/" + rel] = p.read_bytes()
    if pwa:
        pub = m.get("publish") or {}
        icon = _icon(mgr, pid, m, 512)
        files["icons/icon-512.png"] = icon
        files["icons/icon-192.png"] = _icon(mgr, pid, m, 192)
        files["manifest.webmanifest"] = json.dumps({"name": m.get("name", "Jogo"), "short_name": m.get("name", "Jogo")[:12], "start_url": "./index.html", "display": "fullscreen" if (m.get("settings") or {}).get("fullscreen", True) else "standalone",
                                                   "orientation": {"landscape": "landscape", "portrait": "portrait"}.get((m.get("settings") or {}).get("orientation", "landscape"), "any"), "background_color": "#000000", "theme_color": "#000000",
                                                   "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}, ensure_ascii=False, indent=2).encode("utf-8")
        names = sorted(k for k in files if not k.startswith("icons/")) + ["manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"]
        files["sw.js"] = ("const C='asta-ge-" + str(int(time.time())) + "';const F=" + json.dumps(["./"] + names) + ";\nself.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(F))));\n"
                          "self.addEventListener('fetch',e=>e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))));\n").encode("utf-8")
        idx = files["index.html"].decode("utf-8").replace("</head>", '<link rel="manifest" href="manifest.webmanifest"><link rel="icon" href="icons/icon-192.png"><meta name="mobile-web-app-capable" content="yes"></head>')
        idx = idx.replace("</body>", "<script>if('serviceWorker' in navigator&&location.protocol.indexOf('http')===0)navigator.serviceWorker.register('sw.js').catch(function(){});</script></body>")
        files["index.html"] = idx.encode("utf-8")
    return files


def _icon(mgr: Any, pid: str, m: Dict[str, Any], size: int) -> bytes:
    custom = mgr.dir(pid) / "game" / "assets" / "icon.png"
    if custom.is_file() and custom.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and size == 512:
        return custom.read_bytes()
    c = S.THEME_COLORS.get(m.get("theme"), S.THEME_COLORS["forest"])
    return art.icon_png(size, m.get("name", "A"), c["accent"] if m.get("theme") != "snow" else "#3a86ff", c["top"])


def _readme(m: Dict[str, Any], platform: str, pub: Dict[str, Any]) -> str:
    pt = m.get("language", "pt") == "pt"
    L = (lambda a, b: a if pt else b)
    name = m.get("name", "Jogo")
    steps = {
        "web": L("1. Abra `index.html` no navegador (Chrome, Edge, Firefox ou Safari recentes) — funciona sem servidor.\n2. Para publicar (itch.io, GitHub Pages…), envie esta pasta inteira; o jogo também instala como app (PWA).", "1. Open `index.html` in a browser (recent Chrome, Edge, Firefox or Safari) — no server needed.\n2. To publish (itch.io, GitHub Pages…), upload this whole folder; the game also installs as an app (PWA)."),
        "win": L("**Jogar já:** dê dois cliques em `Jogar.bat` (abre em janela de app no Edge/Chrome).\n\n**Instalador/portátil (.exe):** instale o Node.js, abra esta pasta no terminal e rode `build-windows.bat`. O resultado fica em `dist/`.\nSem Node na sua máquina? Envie esta pasta para um repositório do GitHub: o fluxo `.github/workflows/build.yml` gera o .exe na aba Actions.",
                "**Play now:** double-click `Jogar.bat` (opens in an app window in Edge/Chrome).\n\n**Installer/portable (.exe):** install Node.js, open this folder in a terminal and run `build-windows.bat`. The result is in `dist/`.\nNo Node on your machine? Push this folder to a GitHub repository: `.github/workflows/build.yml` builds the .exe in the Actions tab."),
        "macos": L("**Jogar já:** `chmod +x Jogar.command && ./Jogar.command` (ou dois cliques).\n\n**.dmg:** instale o Node.js e rode `./build-macos.sh` (em um Mac). Distribuir fora da App Store exige assinatura e notarização da Apple.\nOu envie para o GitHub: o fluxo `.github/workflows/build.yml` compila no macOS.",
                   "**Play now:** `chmod +x Jogar.command && ./Jogar.command` (or double-click).\n\n**.dmg:** install Node.js and run `./build-macos.sh` (on a Mac). Distributing outside the App Store requires Apple signing and notarization.\nOr push to GitHub: `.github/workflows/build.yml` builds on macOS."),
        "linux": L("**Jogar já:** `chmod +x jogar.sh && ./jogar.sh`.\n\n**AppImage/.deb:** instale o Node.js e rode `./build-linux.sh`; o resultado fica em `dist/`. Ou envie para o GitHub (fluxo pronto em `.github/workflows/build.yml`).",
                   "**Play now:** `chmod +x jogar.sh && ./jogar.sh`.\n\n**AppImage/.deb:** install Node.js and run `./build-linux.sh`; the result is in `dist/`. Or push to GitHub (workflow ready in `.github/workflows/build.yml`)."),
        "android": L("**Jogar já:** abra `www/index.html` no navegador do celular (ou publique `www/` e instale como PWA).\n\n**APK:** instale o Node.js, o JDK 17 e o Android SDK; rode `./build-android.sh` (ou `build-android.bat`). O APK de teste fica em `android/app/build/outputs/apk/debug/`.\nSem as ferramentas? Envie para o GitHub: o fluxo `.github/workflows/build.yml` gera o APK. Publicar na Play Store exige assinar o app (keystore) e uma conta de desenvolvedor.",
                    "**Play now:** open `www/index.html` in the phone browser (or publish `www/` and install as a PWA).\n\n**APK:** install Node.js, JDK 17 and the Android SDK; run `./build-android.sh` (or `build-android.bat`). The debug APK is in `android/app/build/outputs/apk/debug/`.\nNo tools? Push to GitHub: `.github/workflows/build.yml` builds the APK. Publishing on Google Play requires signing (keystore) and a developer account."),
        "ios": L("**Jogar já:** abra `www/index.html` no Safari do iPhone/iPad (ou publique `www/` e use «Adicionar à Tela de Início»).\n\n**App nativo:** só em um Mac com Xcode: `./build-ios.sh` abre o projeto no Xcode. Rodar em aparelho e publicar na App Store exigem conta Apple Developer (assinatura).\nO fluxo `.github/workflows/build.yml` compila um build de simulador no GitHub (sem assinatura).",
                 "**Play now:** open `www/index.html` in Safari on iPhone/iPad (or publish `www/` and use “Add to Home Screen”).\n\n**Native app:** only on a Mac with Xcode: `./build-ios.sh` opens the project in Xcode. Running on a device and publishing on the App Store require an Apple Developer account (signing).\n`.github/workflows/build.yml` builds a simulator build on GitHub (unsigned)."),
    }[platform]
    return "\n".join([f"# {name} — {PLATFORM_LABEL[platform]}", "", L("Gerado pelo [ASTA](https://github.com/KMC1525/ASTA) Game Engine.", "Generated by the [ASTA](https://github.com/KMC1525/ASTA) Game Engine."), "", f"- {L('Versão', 'Version')}: {_version(pub)}", f"- {L('Identificador', 'Identifier')}: `{_pkg_id(m, pub)}`", "",
                      f"## {L('Como usar', 'How to use')}", "", steps, "", f"## {L('Limites', 'Limits')}", "",
                      L("O ASTA não compila nem assina binários nativos: isto é o jogo jogável + um projeto pronto para compilar. WebXR (VR/AR) funciona no navegador do aparelho (Quest Browser, Chrome Android); não foi testado em headset real.",
                        "ASTA does not compile or sign native binaries: this is the playable game + a ready-to-build project. WebXR (VR/AR) works in the device browser (Quest Browser, Chrome Android); it was not tested on a real headset."), ""])


def _electron(m: Dict[str, Any], pub: Dict[str, Any], platform: str) -> Dict[str, bytes]:
    name = m.get("name", "Jogo")
    slug = _slug(m)
    full = (m.get("settings") or {}).get("fullscreen", True)
    targets = {"win": '"win": {"target": ["nsis", "portable"], "icon": "icon.png"}', "macos": '"mac": {"target": ["dmg", "zip"], "category": "public.app-category.games", "icon": "icon.png"}', "linux": '"linux": {"target": ["AppImage", "deb"], "category": "Game", "icon": "icon.png"}'}
    pkg = {"name": slug, "productName": name, "version": _version(pub), "description": m.get("description", "")[:200] or name, "main": "main.js", "author": text(pub.get("author"), "ASTA", 60), "license": "UNLICENSED", "private": True,
           "scripts": {"start": "electron .", "dist": "electron-builder --publish never"}, "devDependencies": {"electron": "^33.0.0", "electron-builder": "^25.1.8"},
           "build": {"appId": _pkg_id(m, pub), "productName": name, "files": ["main.js", "app/**/*", "icon.png"], "directories": {"output": "dist"}}}
    key = {"win": "win", "macos": "mac", "linux": "linux"}[platform]
    pkg["build"][key] = json.loads("{" + targets[platform] + "}")[key]
    main = ("const { app, BrowserWindow } = require('electron');\nconst path = require('path');\nfunction create() {\n  const win = new BrowserWindow({ width: 1280, height: 720, fullscreen: " + ("true" if full else "false") + ", autoHideMenuBar: true, backgroundColor: '#000000', title: " + json.dumps(name)
            + ",\n    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });\n  win.loadFile(path.join(__dirname, 'app', 'index.html'));\n}\napp.whenReady().then(create);\napp.on('window-all-closed', () => app.quit());\n")
    return {"package.json": json.dumps(pkg, ensure_ascii=False, indent=2).encode("utf-8"), "main.js": main.encode("utf-8")}


def _workflow(m: Dict[str, Any], platform: str) -> str:
    os_ = {"win": "windows-latest", "macos": "macos-latest", "linux": "ubuntu-latest"}.get(platform)
    if platform in ("win", "macos", "linux"):
        return ("name: build\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\njobs:\n  build:\n    runs-on: " + os_ + "\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 20\n"
                "      - run: npm install\n      - run: npx electron-builder --publish never\n      - uses: actions/upload-artifact@v4\n        with:\n          name: game-" + platform + "\n          path: |\n            dist/*.exe\n            dist/*.dmg\n            dist/*.zip\n            dist/*.AppImage\n            dist/*.deb\n")
    if platform == "android":
        return ("name: build\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\njobs:\n  apk:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 20\n"
                "      - uses: actions/setup-java@v4\n        with:\n          distribution: temurin\n          java-version: 17\n      - run: npm install\n      - run: npx cap add android\n      - run: npx cap sync android\n"
                "      - run: sed -i 's/<activity /<activity android:screenOrientation=\"" + ((m.get("settings") or {}).get("orientation") if (m.get("settings") or {}).get("orientation") in ("landscape", "portrait") else "unspecified") + "\" /' android/app/src/main/AndroidManifest.xml\n"
                "      - run: cd android && ./gradlew assembleDebug\n      - uses: actions/upload-artifact@v4\n        with:\n          name: game-android-apk\n          path: android/app/build/outputs/apk/debug/*.apk\n")
    return ("name: build\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\njobs:\n  ios-simulator:\n    runs-on: macos-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 20\n"
            "      - run: npm install\n      - run: npx cap add ios\n      - run: npx cap sync ios\n      - run: cd ios/App && xcodebuild -scheme App -sdk iphonesimulator -configuration Debug -derivedDataPath build CODE_SIGNING_ALLOWED=NO build\n"
            "      - uses: actions/upload-artifact@v4\n        with:\n          name: game-ios-simulator\n          path: ios/App/build/Build/Products/Debug-iphonesimulator/App.app\n")


def _capacitor(m: Dict[str, Any], pub: Dict[str, Any], platform: str) -> Dict[str, bytes]:
    name = m.get("name", "Jogo")
    pkg = {"name": _slug(m), "version": _version(pub), "private": True, "description": name,
           "dependencies": {"@capacitor/core": "^6.1.2", "@capacitor/cli": "^6.1.2", ("@capacitor/android" if platform == "android" else "@capacitor/ios"): "^6.1.2"}}
    cfg = {"appId": _pkg_id(m, pub), "appName": name, "webDir": "www", "bundledWebRuntime": False, "server": {"androidScheme": "https"}}
    return {"package.json": json.dumps(pkg, indent=2).encode("utf-8"), "capacitor.config.json": json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8")}


def _zip(files: Dict[str, bytes], prefix: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if name.endswith((".sh", ".command")) else 0o644) << 16
            zf.writestr(info, files[name])
    return buf.getvalue()


def export(mgr: Any, pid: str, platform: str, opts: Dict[str, Any]) -> Dict[str, Any]:
    m = mgr.meta(pid)
    pub = dict(m.get("publish") or {})
    for k in ("version", "package", "author"):
        if isinstance(opts.get(k), str) and opts[k]:
            pub[k] = text(opts[k], "", 80)
    if pub != (m.get("publish") or {}):
        mgr.update_meta(pid, {"publish": pub})
    name = m.get("name", "Jogo")
    slug = _slug(m)
    notes: List[str] = []
    files: Dict[str, bytes] = {}
    if platform == "web":
        files = game_files(mgr, pid, pwa=True)
        files["LEIA-ME.md"] = _readme(m, "web", pub).encode("utf-8")
    elif platform in ("win", "macos", "linux"):
        game = game_files(mgr, pid)
        files = {"app/" + k: v for k, v in game.items()}
        files.update(_electron(m, pub, platform))
        files["icon.png"] = _icon(mgr, pid, m, 512)
        files[".github/workflows/build.yml"] = _workflow(m, platform).encode("utf-8")
        files[".gitignore"] = b"node_modules/\ndist/\n"
        if platform == "win":
            files["Jogar.bat"] = ('@echo off\r\nset "P=%~dp0app\\index.html"\r\nset "U=file:///%P:\\=/%"\r\nif exist "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe" ("%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe" --app="%U%" & exit /b)\r\n'
                                  'if exist "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" ("%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" --app="%U%" & exit /b)\r\nstart "" "%P%"\r\n').encode("utf-8")
            files["build-windows.bat"] = b"@echo off\r\nnpm install && npx electron-builder --win --publish never\r\necho Pronto: veja a pasta dist\r\npause\r\n"
        elif platform == "macos":
            files["Jogar.command"] = b'#!/bin/bash\ncd "$(dirname "$0")"\nP="$PWD/app/index.html"\nif [ -d "/Applications/Google Chrome.app" ]; then open -na "Google Chrome" --args --app="file://$P"; else open "$P"; fi\n'
            files["build-macos.sh"] = b"#!/bin/bash\nset -e\ncd \"$(dirname \"$0\")\"\nnpm install\nnpx electron-builder --mac --publish never\necho 'Pronto: veja a pasta dist'\n"
        else:
            files["jogar.sh"] = b'#!/bin/bash\ncd "$(dirname "$0")"\nP="$PWD/app/index.html"\nfor b in google-chrome chromium chromium-browser microsoft-edge; do command -v $b >/dev/null && exec $b --app="file://$P"; done\nxdg-open "$P"\n'
            files["build-linux.sh"] = b"#!/bin/bash\nset -e\ncd \"$(dirname \"$0\")\"\nnpm install\nnpx electron-builder --linux --publish never\necho 'Pronto: veja a pasta dist'\n"
            files[slug + ".desktop"] = f"[Desktop Entry]\nType=Application\nName={name}\nExec=sh -c 'cd \"$(dirname \"%k\")\" && ./jogar.sh'\nIcon=icon\nCategories=Game;\nTerminal=false\n".encode("utf-8")
        files["README.md"] = _readme(m, platform, pub).encode("utf-8")
        notes.append("Projeto Electron incluído; o instalador nativo precisa do Node.js (ou do fluxo do GitHub Actions).")
    else:
        game = game_files(mgr, pid, pwa=True)
        files = {"www/" + k: v for k, v in game.items()}
        files.update(_capacitor(m, pub, platform))
        files[".github/workflows/build.yml"] = _workflow(m, platform).encode("utf-8")
        files[".gitignore"] = b"node_modules/\nandroid/\nios/\n"
        files["README.md"] = _readme(m, platform, pub).encode("utf-8")
        if platform == "android":
            files["build-android.sh"] = b"#!/bin/bash\nset -e\ncd \"$(dirname \"$0\")\"\nnpm install\n[ -d android ] || npx cap add android\nnpx cap sync android\ncd android && ./gradlew assembleDebug\necho 'APK em android/app/build/outputs/apk/debug/'\n"
            files["build-android.bat"] = b"@echo off\r\nnpm install\r\nif not exist android npx cap add android\r\nnpx cap sync android\r\ncd android && gradlew.bat assembleDebug\r\necho APK em android\\app\\build\\outputs\\apk\\debug\\\r\npause\r\n"
            notes.append("Projeto Capacitor; o APK precisa do Node.js, JDK 17 e Android SDK (ou do fluxo do GitHub Actions).")
        else:
            files["build-ios.sh"] = b"#!/bin/bash\nset -e\ncd \"$(dirname \"$0\")\"\nnpm install\n[ -d ios ] || npx cap add ios\nnpx cap sync ios\nnpx cap open ios\n"
            notes.append("Projeto Capacitor; o app nativo exige um Mac com Xcode e conta Apple Developer para aparelho/App Store.")
    data = _zip(files, "")
    fname = f"{slug}-{SUFFIX[platform]}-{_version(pub)}-{time.strftime('%Y%m%d%H%M%S')}.zip"
    ed = mgr.dir(pid) / "exports"
    ed.mkdir(exist_ok=True)
    (ed / fname).write_bytes(data)
    for old in sorted(ed.glob(f"{slug}-{SUFFIX[platform]}-*.zip"))[:-5]:   # guarda as 5 últimas de cada plataforma
        old.unlink()
    mgr.log(pid, "export", f"{PLATFORM_LABEL[platform]}: {fname}")
    return {"file": fname, "platform": platform, "size": len(data), "files": len(files), "notes": notes, "url": f"/api/engine/projects/{pid}/exports/{fname}"}


def list_exports(mgr: Any, pid: str) -> List[Dict[str, Any]]:
    out = []
    ed = mgr.dir(pid) / "exports"
    for p in sorted(ed.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True) if ed.is_dir() else []:
        plat = next((k for k, v in SUFFIX.items() if f"-{v}-" in p.name), "web")
        out.append({"file": p.name, "platform": plat, "size": p.stat().st_size, "t": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)), "url": f"/api/engine/projects/{pid}/exports/{p.name}"})
    return out


def export_path(mgr: Any, pid: str, fname: str) -> Path:
    if not re.match(r"^[\w][\w .+@()-]*\.zip$", fname or "") or ".." in fname:
        raise M.EngineError(404, "Exportação não encontrada.")
    p = mgr.dir(pid) / "exports" / fname
    if not p.is_file():
        raise M.EngineError(404, "Exportação não encontrada.")
    return p


def delete_export(mgr: Any, pid: str, fname: str) -> None:
    export_path(mgr, pid, fname).unlink()


# ============================================================================ conexões opcionais com o Studio e o Canvas
def send_audio_to_studio(app: Any, mgr: Any, pid: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Envia sons do jogo (caminhos em game/assets/sound) para um projeto do Studio — o existente ou um novo."""
    ss = getattr(getattr(app, "studio_routes", None), "ss", None)
    if ss is None:
        raise M.EngineError(400, "O Studio não está disponível.")
    m = mgr.meta(pid)
    paths = [x for x in (body.get("paths") if isinstance(body.get("paths"), list) else []) if isinstance(x, str)][:40]
    if not paths:
        raise M.EngineError(400, "Escolha pelo menos um som.")
    sid = text(body.get("studio_project"), "", 60) or (m.get("connections") or {}).get("studio_project", "")
    proj = ss.get(sid) if sid else None
    if not proj:
        proj = ss.create({"name": f"Game Engine · {m.get('name', '')}"[:80], "origin": "manual", "premise": "Sons do jogo " + m.get("name", ""), "prompt": ""})
        sid = proj["id"]
    added = []
    for rel in paths:
        p = mgr.raw_path(pid, "game", rel)
        if p.suffix.lower() not in M.SND_EXT:
            continue
        mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac"}[p.suffix.lower()]
        rec = ss.add_asset(sid, p.read_bytes(), p.suffix.lower().lstrip("."), "audio", name=p.name, mime=mime, source="game-engine")
        if rec:
            added.append(rec["id"])
    mgr.update_meta(pid, {"connections": {"studio_project": sid}})
    return {"studio_project": sid, "added": len(added)}


def send_media_to_canvas(app: Any, mgr: Any, pid: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Envia imagens/sons do jogo para um Canvas (existente ou novo): ficam na biblioteca de mídia dele."""
    cs = getattr(getattr(app, "canvas_routes", None), "cs", None)
    if cs is None:
        raise M.EngineError(400, "O Canvas não está disponível.")
    m = mgr.meta(pid)
    paths = [x for x in (body.get("paths") if isinstance(body.get("paths"), list) else []) if isinstance(x, str)][:40]
    if not paths:
        raise M.EngineError(400, "Escolha pelo menos um arquivo.")
    cid = text(body.get("canvas"), "", 60) or (m.get("connections") or {}).get("canvas", "")
    cv = cs.get(cid) if cid else None
    if not cv:
        cv = cs.create(f"Game Engine · {m.get('name', '')}"[:80], "blank", "")
        cid = cv["id"]
    added = 0
    mimes = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    for rel in paths:
        p = mgr.raw_path(pid, "game", rel)
        mime = mimes.get(p.suffix.lower())
        if not mime:
            continue
        if cs.add_asset(cid, p.read_bytes(), p.suffix.lower().lstrip("."), mime.split("/")[0], name=p.name, mime=mime, provider="game-engine"):
            added += 1
    mgr.update_meta(pid, {"connections": {"canvas": cid}})
    return {"canvas": cid, "added": added}
