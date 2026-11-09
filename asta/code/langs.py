"""Linguagens de programação que o Code conhece: extensões, arquivos-manifesto, comandos de teste/build e as bibliotecas e frameworks mais usados de cada ecossistema.

O catálogo serve para três coisas: (1) `detect()` descobre as linguagens de um projeto (para a IA e para a tela); (2) `commands()` sugere o comando certo de teste/build/formatação
de cada ecossistema (sempre como **lista de argumentos**, nunca como texto de shell); (3) o `guide` de cada linguagem entra no system prompt do agente (`prompts/langs/*.md`).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# id → rótulo, extensões, manifestos que identificam o ecossistema, gerenciador, bibliotecas/frameworks conhecidos (as «bibliotecas derivadas» de cada linguagem)
LANGS: Dict[str, Dict[str, Any]] = {
    "python": {"label": "Python", "exts": (".py", ".pyi", ".pyw", ".ipynb"), "manifests": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock", "environment.yml"),
               "manager": "pip", "guide": "python",
               "libs": ("numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "pytorch", "tensorflow", "keras", "transformers", "fastapi", "flask", "django", "requests", "httpx", "pydantic", "sqlalchemy",
                        "pytest", "pygame", "opencv", "pillow", "beautifulsoup", "scrapy", "celery", "asyncio", "tkinter", "pyqt", "streamlit", "gradio", "langchain")},
    "html": {"label": "HTML", "exts": (".html", ".htm", ".xhtml", ".svg"), "manifests": ("index.html",), "manager": "", "guide": "web", "libs": ("semantic HTML", "ARIA", "Web Components", "canvas", "SVG", "htmx")},
    "css": {"label": "CSS", "exts": (".css", ".scss", ".sass", ".less"), "manifests": ("tailwind.config.js", "postcss.config.js"), "manager": "", "guide": "web",
            "libs": ("Flexbox", "Grid", "Tailwind", "Bootstrap", "Sass", "CSS variables", "animations")},
    "javascript": {"label": "JavaScript", "exts": (".js", ".mjs", ".cjs", ".jsx"), "manifests": ("package.json",), "manager": "npm", "guide": "web",
                   "libs": ("Node.js", "React", "Vue", "Svelte", "Express", "Next.js", "Vite", "jQuery", "Three.js", "D3", "Electron", "Jest", "Vitest", "Playwright", "Phaser", "Socket.IO")},
    "typescript": {"label": "TypeScript", "exts": (".ts", ".tsx", ".mts", ".cts"), "manifests": ("tsconfig.json",), "manager": "npm", "guide": "web",
                   "libs": ("Angular", "NestJS", "React", "Next.js", "Deno", "Zod", "tRPC", "Prisma", "Vite")},
    "java": {"label": "Java", "exts": (".java",), "manifests": ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"), "manager": "maven", "guide": "java",
             "libs": ("Spring Boot", "Maven", "Gradle", "JUnit", "Hibernate", "Lombok", "Jackson", "Android SDK", "JavaFX", "Netty")},
    "kotlin": {"label": "Kotlin", "exts": (".kt", ".kts"), "manifests": ("build.gradle.kts",), "manager": "gradle", "guide": "java", "libs": ("Ktor", "Jetpack Compose", "Coroutines", "Android", "Spring")},
    "rust": {"label": "Rust", "exts": (".rs",), "manifests": ("Cargo.toml",), "manager": "cargo", "guide": "rust",
             "libs": ("tokio", "serde", "clap", "axum", "actix-web", "rayon", "reqwest", "anyhow", "thiserror", "bevy", "wgpu", "tauri", "sqlx")},
    "c": {"label": "C", "exts": (".c", ".h"), "manifests": ("Makefile", "CMakeLists.txt", "meson.build"), "manager": "make", "guide": "c", "libs": ("libc", "POSIX", "SDL2", "OpenGL", "libcurl", "SQLite", "pthreads", "GTK")},
    "cpp": {"label": "C++", "exts": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".ipp"), "manifests": ("CMakeLists.txt", "Makefile", "meson.build", "conanfile.txt", "vcpkg.json"), "manager": "cmake", "guide": "c",
            "libs": ("STL", "Boost", "Qt", "SFML", "SDL2", "Eigen", "OpenCV", "gtest", "Catch2", "fmt", "Vulkan", "OpenGL")},
    "csharp": {"label": "C#", "exts": (".cs", ".csx"), "manifests": ("*.csproj", "*.sln", "global.json"), "manager": "dotnet", "guide": "csharp",
               "libs": (".NET", "ASP.NET Core", "Entity Framework", "Unity", "MonoGame", "Blazor", "xUnit", "NUnit", "WPF", "MAUI", "LINQ")},
    "go": {"label": "Go", "exts": (".go",), "manifests": ("go.mod",), "manager": "go", "guide": "go", "libs": ("net/http", "gin", "echo", "gorm", "cobra", "testify", "goroutines", "grpc")},
    "php": {"label": "PHP", "exts": (".php",), "manifests": ("composer.json",), "manager": "composer", "guide": "generic", "libs": ("Laravel", "Symfony", "Composer", "PHPUnit", "WordPress")},
    "ruby": {"label": "Ruby", "exts": (".rb", ".erb", ".rake"), "manifests": ("Gemfile",), "manager": "bundler", "guide": "generic", "libs": ("Rails", "Sinatra", "RSpec", "Rake", "Sidekiq")},
    "swift": {"label": "Swift", "exts": (".swift",), "manifests": ("Package.swift",), "manager": "swift", "guide": "generic", "libs": ("SwiftUI", "UIKit", "Combine", "Vapor", "XCTest")},
    "dart": {"label": "Dart", "exts": (".dart",), "manifests": ("pubspec.yaml",), "manager": "dart", "guide": "generic", "libs": ("Flutter", "Riverpod", "Bloc", "Dio")},
    "lua": {"label": "Lua", "exts": (".lua",), "manifests": ("rockspec",), "manager": "", "guide": "generic", "libs": ("LÖVE", "Roblox Luau", "LuaJIT", "busted")},
    "shell": {"label": "Shell", "exts": (".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"), "manifests": (), "manager": "", "guide": "generic", "libs": ("POSIX sh", "bash", "PowerShell", "coreutils")},
    "sql": {"label": "SQL", "exts": (".sql",), "manifests": (), "manager": "", "guide": "generic", "libs": ("SQLite", "PostgreSQL", "MySQL", "migrations")},
    "r": {"label": "R", "exts": (".r", ".rmd"), "manifests": ("DESCRIPTION",), "manager": "", "guide": "generic", "libs": ("tidyverse", "ggplot2", "shiny", "dplyr")},
    "scala": {"label": "Scala", "exts": (".scala", ".sc"), "manifests": ("build.sbt",), "manager": "sbt", "guide": "java", "libs": ("Akka", "Spark", "cats", "ZIO")},
    "gdscript": {"label": "GDScript", "exts": (".gd",), "manifests": ("project.godot",), "manager": "", "guide": "generic", "libs": ("Godot", "signals", "scenes")},
    "markdown": {"label": "Markdown", "exts": (".md", ".mdx", ".rst"), "manifests": (), "manager": "", "guide": "generic", "libs": ()},
}

EXT_LANG: Dict[str, str] = {e: k for k, v in LANGS.items() for e in v["exts"]}
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", "dist", "build", "out", ".next", ".nuxt",
             ".gradle", ".idea", ".vscode", "bin", "obj", "vendor", "site-packages", ".dart_tool", ".cache", "coverage", ".turbo", "Pods", "DerivedData"}
CODE_LANGS = tuple(k for k in LANGS if k not in ("markdown",))


def language_of(path: str) -> str:
    return EXT_LANG.get(Path(path).suffix.lower(), "")


def catalog() -> List[Dict[str, Any]]:
    """O catálogo para a tela (Configuração e ajuda do Code)."""
    return [{"id": k, "label": v["label"], "exts": list(v["exts"]), "libs": list(v["libs"])} for k, v in LANGS.items()]


def _manifest_hit(root: Path, pattern: str) -> bool:
    if "*" in pattern:
        try:
            return any(root.glob(pattern))
        except OSError:
            return False
    return (root / pattern).is_file()


def detect(root: Path, max_files: int = 6000) -> Dict[str, Any]:
    """Linguagens do projeto: contagem de arquivos e de bytes por linguagem (ignora pastas de dependências e de build) + manifestos encontrados na raiz."""
    counts: Dict[str, int] = {}
    sizes: Dict[str, int] = {}
    seen = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git")]
            for fn in filenames:
                lang = EXT_LANG.get(os.path.splitext(fn)[1].lower())
                seen += 1
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
                    try:
                        sizes[lang] = sizes.get(lang, 0) + os.path.getsize(os.path.join(dirpath, fn))
                    except OSError:
                        pass
                if seen >= max_files:
                    break
            if seen >= max_files:
                break
    except OSError:
        pass
    manifests = [m for lang in LANGS.values() for m in lang["manifests"] if _manifest_hit(root, m)]
    ranked = sorted(counts, key=lambda k: (sizes.get(k, 0), counts[k]), reverse=True)
    main = [k for k in ranked if k != "markdown"]
    return {"languages": [{"id": k, "label": LANGS[k]["label"], "files": counts[k], "bytes": sizes.get(k, 0)} for k in ranked], "main": main[0] if main else "",
            "manifests": list(dict.fromkeys(manifests)), "truncated": seen >= max_files}


def _read(p: Path, limit: int = 200000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lockb").is_file() or (root / "bun.lock").is_file():
        return "bun"
    return "npm"


def commands(root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Comandos sugeridos por ecossistema, como `{"label", "argv"}`: `test`, `build`, `lint`, `format`, `install`. Só entram os que o projeto realmente tem (manifesto/arquivo de configuração)."""
    out: Dict[str, List[Dict[str, Any]]] = {"test": [], "build": [], "lint": [], "format": [], "install": []}

    def add(kind: str, label: str, argv: List[str]) -> None:
        if all(x["argv"] != argv for x in out[kind]):
            out[kind].append({"label": label, "argv": argv})

    py_files = _manifest_hit(root, "pyproject.toml") or _manifest_hit(root, "setup.py") or _manifest_hit(root, "requirements.txt") or any(root.glob("*.py")) or (root / "tests").is_dir()
    if py_files:
        pyproject = _read(root / "pyproject.toml")
        uses_pytest = (root / "pytest.ini").is_file() or (root / "conftest.py").is_file() or "[tool.pytest" in pyproject or "pytest" in _read(root / "requirements.txt").lower() or (root / "tox.ini").is_file() and "pytest" in _read(root / "tox.ini")
        tests = root / "tests"
        if uses_pytest:
            add("test", "pytest", ["python", "-m", "pytest", "-q"])
        elif tests.is_dir() or any(root.glob("test_*.py")):
            add("test", "unittest", ["python", "-m", "unittest", "discover", "-s", "tests", "-t", "."] if (tests / "__init__.py").is_file() else ["python", "-m", "unittest", "discover"])
        if "[tool.ruff" in pyproject or (root / "ruff.toml").is_file():
            add("lint", "ruff", ["python", "-m", "ruff", "check", "."])
            add("format", "ruff format", ["python", "-m", "ruff", "format", "."])
        elif (root / ".flake8").is_file():
            add("lint", "flake8", ["python", "-m", "flake8"])
        if "[tool.black" in pyproject:
            add("format", "black", ["python", "-m", "black", "."])
        if (root / "requirements.txt").is_file():
            add("install", "pip requirements", ["python", "-m", "pip", "install", "-r", "requirements.txt"])
        elif pyproject:
            add("install", "pip (projeto)", ["python", "-m", "pip", "install", "-e", "."])
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(_read(pkg) or "{}")
        except ValueError:
            data = {}
        scripts = data.get("scripts") if isinstance(data, dict) and isinstance(data.get("scripts"), dict) else {}
        pm = _package_manager(root)
        run = [pm] if pm == "yarn" else [pm, "run"]
        if "test" in scripts and "no test specified" not in str(scripts["test"]):
            add("test", f"{pm} test", [pm, "test"])
        for k in ("build", "compile"):
            if k in scripts:
                add("build", f"{pm} run {k}", run + [k])
                break
        if "lint" in scripts:
            add("lint", f"{pm} run lint", run + ["lint"])
        if "format" in scripts:
            add("format", f"{pm} run format", run + ["format"])
        add("install", f"{pm} install", [pm, "install"])
    if (root / "Cargo.toml").is_file():
        add("test", "cargo test", ["cargo", "test"])
        add("build", "cargo build", ["cargo", "build"])
        add("lint", "cargo clippy", ["cargo", "clippy"])
        add("format", "cargo fmt", ["cargo", "fmt"])
    if (root / "go.mod").is_file():
        add("test", "go test", ["go", "test", "./..."])
        add("build", "go build", ["go", "build", "./..."])
        add("lint", "go vet", ["go", "vet", "./..."])
        add("format", "gofmt", ["go", "fmt", "./..."])
    if (root / "pom.xml").is_file():
        add("test", "mvn test", ["mvn", "-q", "test"])
        add("build", "mvn package", ["mvn", "-q", "package", "-DskipTests"])
    if any((root / n).is_file() for n in ("build.gradle", "build.gradle.kts")):
        add("test", "gradle test", ["gradle", "test"])
        add("build", "gradle build", ["gradle", "build"])
    if _manifest_hit(root, "*.sln") or _manifest_hit(root, "*.csproj"):
        add("test", "dotnet test", ["dotnet", "test"])
        add("build", "dotnet build", ["dotnet", "build"])
        add("format", "dotnet format", ["dotnet", "format"])
    if (root / "CMakeLists.txt").is_file():
        add("build", "cmake configure", ["cmake", "-S", ".", "-B", "build"])
        add("build", "cmake build", ["cmake", "--build", "build"])
        add("test", "ctest", ["ctest", "--test-dir", "build", "--output-on-failure"])
    makefile = _read(root / "Makefile") if (root / "Makefile").is_file() else ""
    if makefile:
        if re.search(r"^test\s*:", makefile, re.M):
            add("test", "make test", ["make", "test"])
        if re.search(r"^(all|build)\s*:", makefile, re.M):
            add("build", "make", ["make"])
    if (root / "composer.json").is_file():
        add("test", "composer test", ["composer", "test"])
        add("install", "composer install", ["composer", "install"])
    if (root / "Gemfile").is_file():
        add("test", "rspec" if (root / "spec").is_dir() else "rake test", ["bundle", "exec", "rspec"] if (root / "spec").is_dir() else ["bundle", "exec", "rake", "test"])
        add("install", "bundle install", ["bundle", "install"])
    if (root / "pubspec.yaml").is_file():
        add("test", "dart test", ["dart", "test"])
    if (root / "Package.swift").is_file():
        add("test", "swift test", ["swift", "test"])
        add("build", "swift build", ["swift", "build"])
    return out


def describe(root: Path) -> Dict[str, Any]:
    """Resumo do projeto para o agente e para a tela: linguagens, manifestos, comandos e as bibliotecas conhecidas dessas linguagens."""
    d = detect(root)
    ids = [x["id"] for x in d["languages"]][:6]
    d["libs"] = {i: list(LANGS[i]["libs"])[:14] for i in ids if LANGS[i]["libs"]}
    d["commands"] = commands(root)
    d["empty"] = is_empty(root)
    return d


def is_empty(root: Path) -> bool:
    """A pasta não tem nenhum arquivo nem subpasta (fora o `.git`): o projeto começa do zero."""
    try:
        return not any(e.name != ".git" for e in root.iterdir())
    except OSError:
        return False


def guide_name(lang_id: Optional[str]) -> str:
    return LANGS.get(lang_id or "", {}).get("guide", "generic")


def guides_for(lang_ids: List[str]) -> List[str]:
    """Nomes dos guias (`prompts/langs/<nome>.md`) das linguagens dadas, sem repetir; sempre há ao menos o genérico."""
    out: List[str] = []
    for i in lang_ids:
        g = guide_name(i)
        if g not in out:
            out.append(g)
    return out or ["generic"]
