> [Versión en español → README.md](README.md)

# Technical Notes to Article Converter

Transforms disorganized technical notes into professional, publish-ready articles. Runs entirely on your machine — no external services, no usage limits, no data sent to third-party servers.

---

## What it does

If you have notes, Joplin exports, Jupyter notebooks or any text files with technical content and you want to turn them into well-structured articles (Medium, Dev.to or corporate blog style), this script does that work automatically.

**Real-world use cases:**

- You have folders of Markdown notes on Docker, SQL or Machine Learning and want to publish them on a blog.
- You export your Joplin notes and want articles with introduction, examples, troubleshooting and conclusion.
- You have Jupyter notebooks with experiments and want readable documentation for your team.
- You batch-process dozens of files at once, without manual supervision.

---

## Workflow

```
Input directory
       │
       ▼
Detects dominant file type (.md, .txt, .ipynb, .rst)
       │
       ▼
Queries available engines in Ollama
       │
       ▼
Recommends the most suitable engine for the file type
       │
       ▼
You choose the output language (Spanish, English or both)
       │
       ▼
Processes each file: reads → applies template → generates article → cleans output
       │
       ▼
Saves each article to <directory>_processed/<language>/
preserving the original folder structure
```

For each file the script applies an instruction template with a mandatory 8-section structure (title, introduction, concepts, hands-on, examples, pro tips, troubleshooting and conclusion) and minimum quality criteria (1200-1500 words, code blocks, 5+ best practices).

---

## The two scripts in this project

| Script | Version | Description |
|---|---|---|
| `generar_articulos_folders.py` | v1.0 | Original. Only `.md`, fixed engine via environment variable, basic template. |
| `generar_articulos_mejorado.py` | v4.0 | Current version. Language selection, interactive engine selection, automatic recommendation, multi-format support, output cleanup. |

---

## What's new in version 4.0

### 1. Output language selection
The first thing the script asks is which language you want the articles in:

```
================================================================================
OUTPUT LANGUAGE
================================================================================

  1. Español                          → <dir>_processed/es/
  2. English                          → <dir>_processed/en/
  3. Ambos / Both (ES + EN separated) → <dir>_processed/es/  and  /en/
  4. Bilingual enhanced (ES + EN in one file) → <dir>_processed/bilingue/

Choose output language [1/2/3/4]:
```

Depending on the choice, articles are saved in specific subdirectories:

| Option | Directory | Description |
|---|---|---|
| 1 – Español | `<dir>_processed/es/` | One Spanish article per file |
| 2 – English | `<dir>_processed/en/` | One English article per file |
| 3 – Both | `<dir>_processed/es/`  and  `<dir>_processed/en/` | Two independent passes, one directory per language |
| 4 – Bilingual | `<dir>_processed/bilingue/` | One file containing both enhanced versions |

With **option 3 – Both**, each file is processed twice: first the Spanish version, then the English one.

With **option 4 – Bilingual enhanced**, each file is processed in **a single call**: the engine writes the complete Spanish article first, then the complete English article. Both versions are independent and mutually enriched (not literal translations of each other). The output file uses the `_bilingue.md` suffix and contains both versions separated by a Markdown divider. The output token limit is doubled (8192) so the engine has room for two full articles.

### 2. Interactive engine selection
v1.0 always used the engine set in `OLLAMA_MODEL`. v4.0 queries Ollama at runtime and shows a menu:

```
  Available engines:

    1. huihui_ai/deepseek-r1-abliterated:14b
    2. qwen2.5:14b-instruct-q5_K_M
    3. mistral:latest
    4. qwen3:14b
    5. gemma3:12b
    6. deepseek-r1:14b  <-- RECOMMENDED

    0. Use recommended  (deepseek-r1:14b)
```

### 3. Recommendation by file type
The script analyses the input directory, detects the dominant extension and recommends the most suitable engine:

| File type | Recommended engine | Reason |
|---|---|---|
| `.md` | `deepseek-r1:14b` | Technical notes → in-depth analysis |
| `.ipynb` | `deepseek-r1:14b` | Notebooks with code → in-depth analysis |
| `.txt` | `qwen2.5:14b-instruct` | Plain text → multilingual and precise |
| `.rst` | `qwen2.5:14b-instruct` | Structured documentation |
| `.pdf` | `qwen2.5:14b-instruct` | PDF with text layer → precise and multilingual |

### 4. Automatic output cleanup
Some engines include an internal processing block between `<think>...</think>` tags in their response. The script detects and removes it automatically before saving the article.

### 5. Support for more formats
- **v1.0:** only `.md` files
- **v4.0:** `.md`, `.txt`, `.rst` and `.ipynb` (Jupyter notebooks are extracted cell by cell, separating text sections and code blocks)
- **v5.0:** adds `.pdf` — extracts text and tables page by page with `pdfplumber`; tables are automatically converted to Markdown; pages without a text layer (scanned documents) are skipped with a warning

### 6. Improved instruction template
The template includes a mandatory 8-section structure, explicit quality criteria and content-type rules (tutorial, concept, code, configuration).

### 7. Better error handling
- Detects empty files and skips them with a warning
- Distinguishes connection errors, engine errors and problematic files
- Shows final statistics: successfully processed vs. errors

---

## Requirements

### Software

| Requirement | Minimum version | Purpose |
|---|---|---|
| Python | 3.8+ | Run the script |
| [Ollama](https://ollama.com) | any | Local processing engine |
| curl | any | Communication with Ollama |
| pdfplumber *(optional)* | 0.9+ | Read PDF files |

The script uses only standard library modules for text formats. For PDF support, install `pdfplumber`:

```bash
pip install pdfplumber
```

If `pdfplumber` is not installed the script starts normally — it simply skips `.pdf` files and the startup screen shows the install command.

### Available engines

You need at least one engine installed in Ollama. Engines tested with this script:

```bash
ollama pull deepseek-r1:14b           # In-depth technical analysis
ollama pull qwen2.5:14b-instruct      # Great in Spanish, multilingual
ollama pull gemma3:12b                # Balanced, versatile
ollama pull mistral                   # Lightweight and fast
ollama pull qwen3:14b                 # Latest Qwen generation
```

The script automatically excludes embedding-only engines (such as `nomic-embed-text`) since they are not suitable for text generation.

### Recommended hardware

14B-parameter engines run at reasonable speed on a GPU with at least 10 GB of VRAM. Ollama can also use CPU+RAM (slower). Lighter engines like Mistral (~4 GB) work well on modest hardware.

---

## Installation

```bash
# 1. Clone or copy the repository
git clone <this-repository>
cd crear_articulos

# 2. Check that Ollama is running
ollama list

# 3. (Optional) Pull the engines you want to use
ollama pull deepseek-r1:14b

# 4. Done — nothing else to install
```

---

## Usage

```bash
python3 generar_articulos_mejorado.py <input_directory>
```

**Example with a notes folder:**

```bash
python3 generar_articulos_mejorado.py my_notes/
```

The script automatically creates `my_notes_processed/es/` or `my_notes_processed/en/` (depending on the chosen language), preserving the original subfolder structure and appending `_articulo.md` to each file name.

**Using Ollama on another machine in the network:**

```bash
OLLAMA_HOST=http://192.168.1.100:11434 python3 generar_articulos_mejorado.py my_notes/
```

### Full session example

```
================================================================================
ARTICLE GENERATOR - VERSION 4.0
================================================================================
  OLLAMA_HOST       : http://localhost:11434
  Input directory   : my_notes/
  Output directory  : my_notes_processed/<language>/

================================================================================
OUTPUT LANGUAGE
================================================================================

  1. Español
  2. English
  3. Both  (generates ES + EN, two directories)

Choose output language [1/2/3]: 2

[OK] Language selected: English

Querying available engines...
Engines found: 6

================================================================================
ENGINE SELECTION
================================================================================

  Detected file type : .md
  Recommended engine : deepseek-r1:14b
  Reason             : technical Markdown notes → in-depth analysis

  Available engines:

    1. huihui_ai/deepseek-r1-abliterated:14b
    2. qwen2.5:14b-instruct-q5_K_M
    3. mistral:latest
    4. qwen3:14b
    5. gemma3:12b
    6. deepseek-r1:14b  <-- RECOMMENDED

    0. Use recommended  (deepseek-r1:14b)

Enter engine number [0 for recommended]: 0

[OK] Using recommended engine: deepseek-r1:14b

================================================================================
PROCESSING STARTED
================================================================================

Active engine   : deepseek-r1:14b
Output cleanup  : YES
Extensions      : .ipynb, .md, .rst, .txt
Language(s)     : EN
Output base     : my_notes_processed/

[1] [EN] my_notes/docker/install.md
     [OK] -> my_notes_processed/en/docker/install_articulo.md
          Time: 47.3s  |  Words: 1342  |  Chars: 8891

[2] [EN] my_notes/sql/joins.md
     [OK] -> my_notes_processed/en/sql/joins_articulo.md
          Time: 52.1s  |  Words: 1487  |  Chars: 9654

================================================================================
PROCESSING COMPLETE
================================================================================
  Successfully processed : 2
  Errors / skipped       : 0
  Output directory(s)    :
    my_notes_processed/en/
```

---

## Structure of the generated article

The instruction template always produces this structure:

1. **Title and subtitle** — compelling, 60-70 characters
2. **Introduction** — 150-200 words, opens with a real problem or question
3. **Core concepts** — explanation using real-world analogies
4. **Hands-on section** — numbered steps or thematic subsections with code
5. **Practical examples** — at least 2-3, with input/process/expected output
6. **Pro Tips** — at least 5 best practices (performance, security, scalability)
7. **Troubleshooting** — common errors in `[ERROR] | Cause | Solution` format
8. **Summary and call to action** — recommended next step

---

## Advantages

| Aspect | This script | External services |
|---|---|---|
| Cost | Free | Subscription or pay-per-use |
| Privacy | Data stays 100% local | Data sent to third parties |
| Usage limits | None | Quotas and restrictions |
| Customisation | Full | Limited |
| Works offline | Yes | No |
| Batch processing | Yes, unrestricted | Subject to limits |

---

## Frequently asked questions

**Do I need a Python virtual environment (venv/conda)?**
No. The script has no external dependencies. It runs with the system Python directly.

**Does it work on Windows?**
The script uses `curl` and standard file paths, so it works on Linux and macOS without changes. On Windows it would work with WSL or if `curl` is available in the PATH.

**Can I process thousands of files?**
Yes. The script recursively walks the input directory. Processing time depends on the chosen engine: typically 30-90 seconds per file on a mid-range GPU.

**What happens if a file is empty or has very little content?**
The script detects it, shows a warning and skips it. At the end it displays the count of skipped files.

**Can I change the instruction template?**
Yes. The full template is inside the `generar_articulo_con_ollama()` function in `generar_articulos_mejorado.py`. You can adjust the tone, length, language or structure.

**What if Ollama is on another machine on the network?**
Use the `OLLAMA_HOST` environment variable:
```bash
OLLAMA_HOST=http://192.168.1.50:11434 python3 generar_articulos_mejorado.py notes/
```
