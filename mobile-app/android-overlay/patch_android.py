#!/usr/bin/env python3
"""Prepara o projeto Android que o Capacitor gerou (`npx cap add android`) para rodar o ASTA DENTRO do aparelho.

Uso (feito pelo workflow `release`, job `android`):  python3 patch_android.py <pasta mobile-app> <pasta do repositório> [versão do Chaquopy]

  1. Gradle: aplica o plugin Chaquopy (Python no app), sem pacotes pip (o ASTA só usa a biblioteca padrão), ABIs arm64/armeabi/x86_64;
  2. copia o pacote `asta` (sem testes nem artefatos do Rust) e o `asta_android.py` para src/main/python;
  3. troca a MainActivity pela que liga o ASTA; 4. AndroidManifest: tráfego local em HTTP, memória grande.
É idempotente (rodar duas vezes não duplica nada) e falha alto se algo esperado não existe (melhor o CI quebrar do que gerar um APK sem o ASTA).
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ABIS = '"arm64-v8a", "armeabi-v7a", "x86_64"'
PY_VERSION = "3.12"


def read(p: Path) -> str:
    if not p.is_file():
        raise SystemExit(f"[patch_android] arquivo esperado não existe: {p}")
    return p.read_text(encoding="utf-8")


def patch_root_gradle(path: Path, chaquopy: str) -> None:
    s = read(path)
    if "com.chaquo.python:gradle" not in s:
        s, n = re.subn(r"(buildscript\s*\{.*?dependencies\s*\{)", r"\1\n        classpath 'com.chaquo.python:gradle:%s'" % chaquopy, s, count=1, flags=re.S)
        if not n:
            raise SystemExit("[patch_android] não achei buildscript.dependencies em android/build.gradle")
    if "mavenCentral()" not in s.split("allprojects")[0]:   # o plugin Chaquopy está no Maven Central
        s, n = re.subn(r"(buildscript\s*\{.*?repositories\s*\{)", r"\1\n        mavenCentral()", s, count=1, flags=re.S)
        if not n:
            raise SystemExit("[patch_android] não achei buildscript.repositories em android/build.gradle")
    path.write_text(s, encoding="utf-8")


def patch_variables(path: Path) -> None:
    """O Python embutido pede Android 7.0 (API 24) ou mais; o Capacitor 6 vem com 22."""
    if not path.is_file():
        return
    s = path.read_text(encoding="utf-8")
    s = re.sub(r"minSdkVersion\s*=\s*(\d+)", lambda m: f"minSdkVersion = {max(int(m.group(1)), 24)}", s)
    path.write_text(s, encoding="utf-8")


def patch_app_gradle(path: Path) -> None:
    s = read(path)
    if "com.chaquo.python" in s:
        return
    s, n = re.subn(r"(apply plugin: ['\"]com\.android\.application['\"])", r"\1\napply plugin: 'com.chaquo.python'", s, count=1)
    if not n:
        raise SystemExit("[patch_android] não achei o plugin com.android.application em android/app/build.gradle")
    # ABIs e Python dentro de defaultConfig / bloco python
    s, n = re.subn(r"(defaultConfig\s*\{)", r"\1\n        ndk { abiFilters %s }" % ABIS, s, count=1)
    if not n:
        raise SystemExit("[patch_android] não achei defaultConfig em android/app/build.gradle")
    s += "\nchaquopy {\n    defaultConfig {\n        version \"%s\"\n    }\n}\n" % PY_VERSION
    path.write_text(s, encoding="utf-8")


def patch_manifest(path: Path) -> None:
    s = read(path)
    if 'android:usesCleartextTraffic' not in s:
        s = s.replace("<application", '<application android:usesCleartextTraffic="true"', 1)
    if 'android:largeHeap' not in s:
        s = s.replace("<application", '<application android:largeHeap="true"', 1)
    if "android.permission.INTERNET" not in s:
        s = s.replace("<application", '<uses-permission android:name="android.permission.INTERNET" />\n    <application', 1)
    if "android.permission.CAMERA" not in s:
        s = s.replace("<application", '<uses-permission android:name="android.permission.CAMERA" />\n    <uses-feature android:name="android.hardware.camera" android:required="false" />\n    <application', 1)
    path.write_text(s, encoding="utf-8")


def copy_python(repo: Path, overlay: Path, dest: Path) -> int:
    pkg = repo / "asta"
    if not (pkg / "server.py").is_file():
        raise SystemExit(f"[patch_android] pacote asta não encontrado em {pkg}")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "target", "src", "Cargo.lock", "*.so", "*.dylib", "*.dll", "tests")   # "src" = fontes do Rust (no Android o núcleo vai pronto em jniLibs)
    shutil.copytree(pkg, dest / "asta", ignore=ignore)
    shutil.copy2(overlay / "python" / "asta_android.py", dest / "asta_android.py")
    return sum(1 for _ in (dest / "asta").rglob("*.py"))


def main(argv: list) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    mobile, repo = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    chaquopy = argv[3] if len(argv) > 3 else "16.1.0"
    android, overlay = mobile / "android", mobile / "android-overlay"
    patch_root_gradle(android / "build.gradle", chaquopy)
    patch_variables(android / "variables.gradle")
    patch_app_gradle(android / "app" / "build.gradle")
    patch_manifest(android / "app" / "src" / "main" / "AndroidManifest.xml")
    n = copy_python(repo, overlay, android / "app" / "src" / "main" / "python")
    java_dir = android / "app" / "src" / "main" / "java" / "org" / "asta" / "mobile"
    java_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(overlay / "java" / "MainActivity.java", java_dir / "MainActivity.java")
    print(f"[patch_android] Chaquopy {chaquopy} · Python {PY_VERSION} · {n} módulos do ASTA copiados · MainActivity trocada")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
