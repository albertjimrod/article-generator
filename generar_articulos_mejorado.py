#!/usr/bin/env python3
"""
Script mejorado para generar articulos con Ollama
Seleccion interactiva de idioma, modelo y recomendacion por tipo de archivo
Soporte Mermaid, documentos extensos y cobertura completa de contenido
Version: 6.0
Fecha: Febrero 2026
"""

import os
import re
import subprocess
import json
import time
import tempfile
import sys

try:
    import pdfplumber
    PDF_DISPONIBLE = True
except ImportError:
    PDF_DISPONIBLE = False

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip("/")

# ── Tipos de archivo soportados ───────────────────────────────────────────────
EXTENSIONES_BASE = {".md", ".txt", ".rst", ".ipynb"}
EXTENSIONES_SOPORTADAS = EXTENSIONES_BASE | ({".pdf"} if PDF_DISPONIBLE else set())

# Motor recomendado por extension
RECOMENDACIONES_MODELO = {
    ".md":    ("deepseek-r1:14b",              "notas tecnicas Markdown → razonamiento profundo"),
    ".ipynb": ("deepseek-r1:14b",              "Jupyter notebooks → codigo + razonamiento"),
    ".txt":   ("qwen2.5:14b-instruct-q5_K_M", "texto plano → instruccion y multilingue"),
    ".rst":   ("qwen2.5:14b-instruct-q5_K_M", "documentacion RST → instruccion y estructura"),
    ".pdf":   ("qwen2.5:14b-instruct-q5_K_M", "PDF con texto → instruccion precisa y multilingue"),
}

# Configuracion de idiomas disponibles
IDIOMAS = {
    "1": {
        "codigo":  "es",
        "nombre":  "Español                          → <dir>_procesado/es/",
        "instruccion": (
            "IDIOMA DE SALIDA: Escribe TODO el articulo en ESPAÑOL. "
            "Ningun parrafo, titulo ni seccion puede estar en otro idioma."
        ),
    },
    "2": {
        "codigo":  "en",
        "nombre":  "English                          → <dir>_procesado/en/",
        "instruccion": (
            "OUTPUT LANGUAGE: Write the ENTIRE article in ENGLISH. "
            "Every section, title, paragraph and example must be in English. "
            "Do not use Spanish at all."
        ),
    },
    "3": {
        "codigo":  "both",
        "nombre":  "Ambos / Both (ES + EN separados) → <dir>_procesado/es/  y  /en/",
        "instruccion": None,
    },
    "4": {
        "codigo":  "bilingue",
        "nombre":  "Bilingüe mejorado (ES + EN en un archivo) → <dir>_procesado/bilingue/",
        "instruccion": None,
    },
}

# ── Tipos de diagrama Mermaid reconocidos ─────────────────────────────────────
MERMAID_TIPOS = {
    "flowchart":       ("Diagrama de flujo",            "representa un proceso o algoritmo con nodos y flechas dirigidas"),
    "graph":           ("Diagrama de grafo",             "representa relaciones y conexiones entre elementos"),
    "sequencediagram": ("Diagrama de secuencia",         "representa interacciones temporales entre actores o componentes"),
    "classdiagram":    ("Diagrama de clases",            "representa la estructura OOP: clases, atributos, metodos y herencia"),
    "erdiagram":       ("Diagrama entidad-relacion",     "representa el modelo de datos: entidades, atributos y relaciones"),
    "gantt":           ("Diagrama de Gantt",             "representa la planificacion temporal de tareas y fases"),
    "pie":             ("Diagrama de tarta",             "representa la distribucion proporcional de categorias"),
    "statediagram":    ("Diagrama de estados",           "representa los estados de un sistema y las transiciones entre ellos"),
    "mindmap":         ("Mapa mental",                   "representa ideas organizadas en estructura jerarquica ramificada"),
    "journey":         ("Mapa de experiencia de usuario","representa el recorrido y emociones del usuario en un proceso"),
    "gitgraph":        ("Diagrama de ramas Git",         "representa el historial de commits y la estructura de ramas"),
    "xychart-beta":    ("Grafico de barras/lineas",      "representa datos cuantitativos en ejes cartesianos"),
    "block-beta":      ("Diagrama de bloques",           "representa la arquitectura o componentes de un sistema"),
    "quadrantchart":   ("Grafico de cuadrantes",         "clasifica elementos segun dos ejes en cuatro zonas"),
    "timeline":        ("Linea de tiempo",               "representa eventos ordenados cronologicamente"),
    "zenuml":          ("Diagrama ZenUML",               "representa interacciones entre componentes en estilo ZenUML"),
}

# Umbral de caracteres a partir del cual se procesa por secciones
UMBRAL_SECCIONADO = 20000


# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def obtener_modelos_ollama():
    """Consulta la API de Ollama y devuelve la lista de modelos disponibles
    excluyendo los de embeddings."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{OLLAMA_HOST}/api/tags"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        data = json.loads(result.stdout.decode("utf-8"))
        modelos = [m["name"] for m in data.get("models", [])]
        modelos = [m for m in modelos if "embed" not in m.lower()]
        return modelos
    except Exception as e:
        print(f"[ADVERTENCIA] No se pudo consultar Ollama: {e}")
        return []


def detectar_extension_dominante(directorio):
    """Devuelve la extension de archivo mas frecuente entre las soportadas."""
    contador = {}
    for carpeta_raiz, _, archivos in os.walk(directorio):
        for archivo in archivos:
            ext = os.path.splitext(archivo)[1].lower()
            if ext in EXTENSIONES_SOPORTADAS:
                contador[ext] = contador.get(ext, 0) + 1
    if not contador:
        return None
    return max(contador, key=contador.get)


def modelo_tiene_thinking(nombre_modelo):
    """Comprueba si el modelo genera bloques de pensamiento interno."""
    nombre_lower = nombre_modelo.lower()
    return any(patron in nombre_lower for patron in ("deepseek-r1", "qwen3"))


def limpiar_pensamiento(texto):
    """Elimina bloques <think>...</think> del razonamiento interno del modelo."""
    limpio = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL | re.IGNORECASE)
    limpio = re.sub(r"</think>", "", limpio, flags=re.IGNORECASE)
    return limpio.strip()


# ── Mermaid ───────────────────────────────────────────────────────────────────

def detectar_tipo_mermaid(codigo):
    """Detecta el tipo de diagrama Mermaid a partir de la primera linea del codigo."""
    primera = codigo.strip().split("\n")[0].strip().lower()
    for clave, (nombre, descripcion) in MERMAID_TIPOS.items():
        if primera.startswith(clave):
            return nombre, descripcion
    return "Diagrama tecnico", "representa informacion tecnica de forma visual"


def preprocesar_mermaid(contenido):
    """
    Detecta bloques ```mermaid...``` en el contenido y los anota con instrucciones
    para que el motor:
      1. Conserve el bloque original intacto en la salida (se renderizara correctamente).
      2. Analice el diagrama y escriba una seccion de analisis justo despues.
    Devuelve (contenido_anotado, numero_de_diagramas_encontrados).
    """
    patron = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
    contador = [0]

    def anotar(match):
        contador[0] += 1
        n = contador[0]
        codigo = match.group(1).strip()
        tipo, descripcion = detectar_tipo_mermaid(codigo)
        return (
            f"\n\n"
            f"[DIAGRAMA-{n} | {tipo.upper()} | {descripcion}]\n"
            f"[INSTRUCCION OBLIGATORIA PARA EL REDACTOR — DIAGRAMA {n}:\n"
            f" Este bloque es un {tipo} que {descripcion}.\n"
            f" En el articulo debes:\n"
            f"   a) Incluir el bloque ```mermaid siguiente EXACTAMENTE como esta (no lo modifiques).\n"
            f"   b) Justo despues del bloque, añadir un parrafo titulado '**Analisis del diagrama**'\n"
            f"      que explique: que representa, cuales son sus elementos o nodos principales,\n"
            f"      que relaciones o flujos muestra, y por que es relevante para el tema del articulo.\n"
            f"]\n\n"
            f"```mermaid\n{codigo}\n```\n"
        )

    anotado = patron.sub(anotar, contenido)
    return anotado, contador[0]


# ── Manejo de documentos extensos ─────────────────────────────────────────────

def extraer_encabezados(contenido):
    """Extrae los encabezados Markdown del documento para asegurar cobertura completa."""
    return re.findall(r"^#{1,3} .+", contenido, re.MULTILINE)


def dividir_por_secciones(contenido, max_chars=18000):
    """
    Divide el contenido en trozos de max_chars usando los encabezados como puntos
    de corte naturales. Si un parrafo individual supera max_chars, lo incluye entero
    (el motor tiene tolerancia razonable).
    """
    partes = re.split(r"(?=\n#{1,2} )", contenido)
    partes = [p.strip() for p in partes if p.strip()]

    secciones = []
    chunk = ""
    for parte in partes:
        if chunk and len(chunk) + len(parte) > max_chars:
            secciones.append(chunk.strip())
            chunk = parte
        else:
            chunk += ("\n\n" if chunk else "") + parte
    if chunk:
        secciones.append(chunk.strip())

    return secciones if secciones else [contenido]


# ── Llamada HTTP a Ollama (helper compartido) ──────────────────────────────────

def _llamar_ollama(payload, modelo):
    """
    Ejecuta la llamada curl a Ollama, limpia el pensamiento si aplica
    y devuelve el texto de respuesta limpio.
    Lanza RuntimeError si hay fallo.
    """
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
            json.dump(payload, f)
            temp_file_path = f.name

        result = subprocess.run(
            ["curl", f"{OLLAMA_HOST}/api/chat", "-s",
             "-H", "Content-Type: application/json",
             "-d", f"@{temp_file_path}"],
            check=True,
            stdout=subprocess.PIPE
        )
        data = json.loads(result.stdout.decode("utf-8"))
        output = data.get("message", {}).get("content", "").strip()

        if not output:
            raise RuntimeError("Respuesta vacia del motor")

        if modelo_tiene_thinking(modelo):
            output = limpiar_pensamiento(output)

        if not output:
            raise RuntimeError("Respuesta vacia tras eliminar el bloque de pensamiento")

        return output

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Error en llamada al motor: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# ─────────────────────────────────────────────────────────────────────────────
# Menus interactivos
# ─────────────────────────────────────────────────────────────────────────────

def seleccionar_idioma():
    """Muestra el menu de seleccion de idioma de salida."""
    print("\n" + "=" * 80)
    print("IDIOMA DE SALIDA")
    print("=" * 80)
    print()
    for clave, cfg in IDIOMAS.items():
        print(f"  {clave}. {cfg['nombre']}")
    print()

    opciones_validas = list(IDIOMAS.keys())
    while True:
        try:
            eleccion = input(f"Elige el idioma de salida [{'/'.join(opciones_validas)}]: ").strip()
            if eleccion in IDIOMAS:
                cfg = IDIOMAS[eleccion]
                nombre_corto = cfg["nombre"].split("→")[0].strip()
                print(f"\n[OK] Modo seleccionado: {nombre_corto}")
                return cfg["codigo"]
            print(f"[!] Opcion invalida. Elige {', '.join(opciones_validas)}.")
        except KeyboardInterrupt:
            print("\n[!] Abortado por el usuario.")
            sys.exit(0)


def seleccionar_modelo(modelos_disponibles, extension_dominante):
    """Muestra un menu interactivo para elegir el motor de Ollama."""
    print("\n" + "=" * 80)
    print("SELECCION DE MOTOR")
    print("=" * 80)

    modelo_sugerido = None
    razon_sugerida = ""
    if extension_dominante and extension_dominante in RECOMENDACIONES_MODELO:
        candidato, razon = RECOMENDACIONES_MODELO[extension_dominante]
        if candidato in modelos_disponibles:
            modelo_sugerido = candidato
            razon_sugerida = razon
        else:
            modelo_sugerido = modelos_disponibles[0]
            razon_sugerida = "recomendado no disponible, se usa el primero de la lista"

    if extension_dominante:
        print(f"\n  Tipo de archivo detectado : {extension_dominante}")
    if modelo_sugerido:
        print(f"  Motor recomendado         : {modelo_sugerido}")
        print(f"  Motivo                    : {razon_sugerida}")

    print("\n  Motores disponibles:\n")
    for i, modelo in enumerate(modelos_disponibles, 1):
        marca = "  <-- RECOMENDADO" if modelo == modelo_sugerido else ""
        print(f"    {i}. {modelo}{marca}")

    if modelo_sugerido:
        print(f"\n    0. Usar recomendado  ({modelo_sugerido})")

    while True:
        try:
            prompt_input = "Elige el numero del motor"
            if modelo_sugerido:
                prompt_input += " [0 para recomendado]"
            eleccion = input(f"\n{prompt_input}: ").strip()

            if eleccion == "" or eleccion == "0":
                if modelo_sugerido:
                    print(f"\n[OK] Usando motor recomendado: {modelo_sugerido}")
                    return modelo_sugerido
                else:
                    print("[!] No hay recomendacion, elige un numero de la lista.")
                    continue

            idx = int(eleccion) - 1
            if 0 <= idx < len(modelos_disponibles):
                elegido = modelos_disponibles[idx]
                print(f"\n[OK] Motor seleccionado: {elegido}")
                return elegido
            else:
                print(f"[!] Numero invalido. Elige entre 1 y {len(modelos_disponibles)}.")

        except ValueError:
            print("[!] Introduce un numero valido.")
        except KeyboardInterrupt:
            print("\n[!] Abortado por el usuario.")
            sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de archivos
# ─────────────────────────────────────────────────────────────────────────────

def leer_pdf(ruta):
    """
    Extrae el texto de un PDF con pdfplumber pagina a pagina.
    Las tablas se convierten a Markdown. Las paginas sin texto se omiten con aviso.
    """
    partes = []
    paginas_sin_texto = 0

    with pdfplumber.open(ruta) as pdf:
        total_paginas = len(pdf.pages)
        for pagina in pdf.pages:
            tablas = pagina.extract_tables()
            for tabla in tablas:
                if not tabla:
                    continue
                filas_md = []
                for j, fila in enumerate(tabla):
                    celdas = [str(c or "").replace("\n", " ").strip() for c in fila]
                    filas_md.append("| " + " | ".join(celdas) + " |")
                    if j == 0:
                        filas_md.append("|" + "|".join(["---"] * len(celdas)) + "|")
                partes.append("\n".join(filas_md))

            texto = pagina.extract_text(x_tolerance=3, y_tolerance=3)
            if texto and texto.strip():
                partes.append(texto.strip())
            else:
                paginas_sin_texto += 1

    if not partes:
        raise ValueError(
            f"No se pudo extraer texto del PDF '{os.path.basename(ruta)}'. "
            f"Puede ser un PDF escaneado sin capa de texto OCR."
        )

    aviso = ""
    if paginas_sin_texto > 0:
        aviso = (
            f"\n\n[NOTA: {paginas_sin_texto} de {total_paginas} paginas "
            f"no tenian capa de texto y fueron omitidas.]\n\n"
        )
    return aviso + "\n\n---\n\n".join(partes)


def leer_archivo(ruta):
    """Lee el contenido de un archivo segun su extension y lo devuelve como texto."""
    ext = os.path.splitext(ruta)[1].lower()

    if ext == ".pdf":
        return leer_pdf(ruta)

    if ext == ".ipynb":
        with open(ruta, "r", encoding="utf-8") as f:
            nb = json.load(f)
        partes = []
        for celda in nb.get("cells", []):
            tipo = celda.get("cell_type", "")
            source = "".join(celda.get("source", []))
            if not source.strip():
                continue
            if tipo == "markdown":
                partes.append(source)
            elif tipo == "code":
                partes.append(f"```python\n{source}\n```")
        return "\n\n".join(partes)

    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────────
# Generacion del articulo
# ─────────────────────────────────────────────────────────────────────────────

def construir_instruccion_idioma(codigo_idioma):
    """Devuelve el bloque de instruccion de idioma para el prompt."""
    for cfg in IDIOMAS.values():
        if cfg["codigo"] == codigo_idioma and cfg["instruccion"]:
            return cfg["instruccion"]
    return IDIOMAS["1"]["instruccion"]


def _bloque_cobertura_completa(encabezados, n_mermaid):
    """Construye el bloque de instrucciones de cobertura completa y Mermaid."""
    lineas = [
        "COBERTURA COMPLETA DEL CONTENIDO (REGLA ABSOLUTA):\n",
        "- DEBES cubrir TODA la informacion del documento original SIN excepcion.\n",
        "- NO resumas, NO omitas, NO simplifiques ningun concepto, dato, comando,\n",
        "  ejemplo, configuracion, valor numerico ni resultado.\n",
        "- Si el documento es extenso, el articulo tambien debe serlo.\n",
        "  Es preferible un articulo largo y completo a uno corto con informacion perdida.\n",
        "- Cada concepto, herramienta, parametro o paso del documento original\n",
        "  debe aparecer en el articulo con su explicacion correspondiente.\n",
        "- Los bloques de codigo deben reproducirse completos, no recortados.\n",
    ]
    if encabezados:
        lineas.append(
            f"- El documento original tiene {len(encabezados)} secciones. "
            f"TODAS deben estar reflejadas en el articulo:\n"
        )
        for h in encabezados:
            lineas.append(f"    {h}\n")
    if n_mermaid > 0:
        lineas += [
            f"\nDIAGRAMAS MERMAID ({n_mermaid} encontrado(s)):\n",
            "- Cada bloque ```mermaid debe aparecer INTACTO en el articulo (no lo modifiques).\n",
            "- Justo despues de cada bloque mermaid, escribe un parrafo '**Analisis del diagrama**'\n",
            "  explicando: que representa, sus elementos principales, relaciones o flujos que muestra\n",
            "  y por que es relevante para entender el tema del articulo.\n",
        ]
    return "".join(lineas)


def generar_articulo_con_ollama(contenido_md, modelo, codigo_idioma,
                                 n_mermaid=0, encabezados=None):
    """
    Genera un articulo completo a partir del contenido proporcionado.
    Parametros:
      n_mermaid   - numero de diagramas Mermaid detectados en el contenido
      encabezados - lista de encabezados del documento original (para cobertura completa)
    """
    instruccion_idioma = construir_instruccion_idioma(codigo_idioma)
    bloque_cobertura = _bloque_cobertura_completa(encabezados or [], n_mermaid)

    prompt_usuario = (
        "INSTRUCCION PRINCIPAL:\n"
        "Eres un redactor tecnico experto en ciencia de datos, machine learning e ingenieria de software. "
        "Tu mision es transformar notas tecnicas en articulos profesionales, educativos y altamente legibles. "
        "El resultado debe ser comparable a articulos publicados en blogs tecnicos de alto nivel "
        "(Medium, Dev.to, blogs corporativos).\n\n"

        + bloque_cobertura + "\n\n"

        "OBJETIVO FINAL:\n"
        "Crear un articulo que sea:\n"
        "- Preciso y COMPLETO en contenido tecnico (ningun detalle del original puede faltar)\n"
        "- Accesible para nivel medio-avanzado\n"
        "- Bien estructurado y facil de seguir\n"
        "- Practico con ejemplos ejecutables\n"
        "- Atractivo para lectores profesionales\n\n"

        "ESTRUCTURA DEL ARTICULO (OBLIGATORIA):\n\n"

        "A) TITULO Y SUBTITULO\n"
        "   - Titulo: Atractivo, descriptivo, 60-70 caracteres maximo\n"
        "   - Subtitulo: Explica beneficio o resultado en 1 linea\n\n"

        "B) INTRODUCCION (1-2 parrafos, 150-200 palabras)\n"
        "   - Empieza con una pregunta o problema real\n"
        "   - Explica POR QUE esto es importante para el lector\n"
        "   - Anuncia lo que el lector aprendera\n\n"

        "C) CONCEPTOS BASICOS (si es necesario)\n"
        "   - Explica conceptos clave sin asumirlos conocidos\n"
        "   - Usa analogias del mundo real para conceptos complejos\n\n"

        "D) SECCION PRACTICA PRINCIPAL\n"
        "   - Divide en pasos numerados si es procedimiento\n"
        "   - Cada paso: Explicacion + Codigo/Ejemplo + Resultado esperado\n"
        "   - Bloques de codigo con ```bash o ```python\n"
        "   - Comentarios en el codigo explicando cada parte\n\n"

        "E) EJEMPLOS PRACTICOS\n"
        "   - Minimo 2-3 ejemplos reales y diferentes\n"
        "   - Con comandos exactos que pueden copiar-pegar\n"
        "   - Entrada, proceso, salida esperada\n\n"

        "F) MEJORES PRACTICAS Y TIPS (minimo 5)\n"
        "   - Rendimiento, seguridad, escalabilidad\n"
        "   - Formato de vinetas\n\n"

        "G) TROUBLESHOOTING (Errores Comunes)\n"
        "   - Formato: [ERROR] | Causa | Solucion\n"
        "   - Minimo 2-3 errores tipicos con solucion paso a paso\n\n"

        "H) RESUMEN Y LLAMADO A ACCION\n"
        "   - Recapitula puntos principales (3-4 lineas)\n"
        "   - Proximo paso logico recomendado\n\n"

        "ESTILO:\n"
        "- Profesional pero amigable (mentor senior)\n"
        "- Parrafos cortos, oraciones directas\n"
        "- ### para subsecciones, - para listas, numeros solo para procedimientos\n"
        "- **negrita** para enfasis, *cursiva* para terminos nuevos\n"
        "- CERO caracteres asiaticos\n\n"

        "REGLAS ESPECIALES:\n"
        "SI ES TUTORIAL: numera pasos, indica tiempo estimado, requisitos previos.\n"
        "SI ES CONCEPTO: empieza con analogia, ejemplos graduados, casos de uso al final.\n"
        "SI HAY CODIGO: version simple primero, luego avanzada, explica dependencias.\n"
        "SI HAY CONFIGURACION: ejemplos genericos + concretos, explica cada valor.\n\n"

        "AHORA, TRANSFORMA ESTE CONTENIDO EN UN ARTICULO PROFESIONAL:\n\n"
        "===========================================================================\n\n"
        + contenido_md +
        "\n\n"
        "===========================================================================\n\n"
        "IMPORTANTE — LISTA DE VERIFICACION FINAL:\n"
        "[ ] Estructura de 8 secciones completa\n"
        "[ ] TODA la informacion del documento original esta cubierta\n"
        "[ ] Los bloques de codigo estan completos (no recortados)\n"
        "[ ] Los diagramas Mermaid aparecen intactos con su analisis justo despues\n"
        "[ ] CERO caracteres asiaticos\n"
        "[ ] Responde DIRECTAMENTE con el articulo, sin preambulos\n"
        f"[ ] {instruccion_idioma}\n"
        "[ ] PROHIBIDO mencionar que el articulo fue generado, redactado o asistido "
        "por ninguna herramienta automatica. Debe leer como escrito por un experto humano.\n"
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt_usuario}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 8192,
            "num_ctx": 16384,
        }
    }

    try:
        return _llamar_ollama(payload, modelo)
    except RuntimeError as e:
        return f"[ERROR] {e}"


def generar_seccion_articulo(seccion_md, modelo, codigo_idioma, n_mermaid=0):
    """
    Desarrolla una seccion del documento de forma completa y precisa.
    Se usa cuando el documento es demasiado extenso para procesarlo en una sola llamada.
    NO genera estructura de articulo completo: solo desarrolla el contenido de la seccion.
    """
    instruccion_idioma = construir_instruccion_idioma(codigo_idioma)
    instruccion_mermaid = ""
    if n_mermaid > 0:
        instruccion_mermaid = (
            "\nDIAGRAMAS MERMAID: Si hay bloques ```mermaid en el contenido, conservalos "
            "intactos y añade justo despues un parrafo '**Analisis del diagrama**' que explique "
            "que representa, sus elementos principales y por que es relevante.\n"
        )

    prompt_usuario = (
        "Eres un redactor tecnico experto. Desarrolla el siguiente contenido tecnico "
        "de forma COMPLETA y PRECISA, convirtiendolo en texto profesional y educativo.\n\n"

        "REGLAS ABSOLUTAS:\n"
        "- Cubre TODA la informacion del contenido: ningun dato, comando, ejemplo, "
        "configuracion ni concepto puede faltar.\n"
        "- No resumas ni simpliques. Si el contenido tiene muchos detalles, desarrollalos todos.\n"
        "- Los bloques de codigo deben reproducirse completos.\n"
        "- Usa ### para subsecciones, bloques de codigo con ```, listas con -.\n"
        + instruccion_mermaid +
        f"- {instruccion_idioma}\n"
        "- PROHIBIDO mencionar herramientas automaticas. Escribe como un experto humano.\n"
        "- CERO caracteres asiaticos.\n\n"

        "CONTENIDO A DESARROLLAR:\n"
        "===========================================================================\n\n"
        + seccion_md +
        "\n\n===========================================================================\n\n"
        "Responde DIRECTAMENTE con el contenido desarrollado, sin preambulos.\n"
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt_usuario}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 4096,
            "num_ctx": 16384,
        }
    }

    try:
        return _llamar_ollama(payload, modelo)
    except RuntimeError as e:
        return f"[ERROR] {e}"


def generar_articulo_grande(contenido, modelo, codigo_idioma, n_mermaid, encabezados):
    """
    Procesa documentos extensos dividiendolos en secciones.
    Genera intro + cuerpo por secciones + conclusion, luego los combina.
    """
    secciones = dividir_por_secciones(contenido)
    n = len(secciones)
    print(f"          Dividido en {n} secciones para procesamiento completo.")

    partes = []
    for i, seccion in enumerate(secciones, 1):
        etiqueta = f"seccion {i}/{n}"
        if i == 1:
            etiqueta = f"introduccion + {etiqueta}"
        if i == n:
            etiqueta = f"{etiqueta} + conclusion"
        print(f"          Procesando {etiqueta} ({len(seccion)} chars)...")

        # Primera seccion incluye contexto de encabezados para coherencia
        encabezados_seccion = encabezados if i == 1 else None
        resultado = generar_seccion_articulo(seccion, modelo, codigo_idioma, n_mermaid)

        if resultado.startswith("[ERROR]"):
            return resultado
        partes.append(resultado)

    # Encabezado del articulo + cuerpo completo
    instruccion_idioma = construir_instruccion_idioma(codigo_idioma)
    titulo_seccion = "## Contenido desarrollado" if "es" in codigo_idioma else "## Developed content"
    return f"{titulo_seccion}\n\n" + "\n\n---\n\n".join(partes)


def procesar_documento(contenido_raw, modelo, codigo_idioma):
    """
    Orquesta el procesamiento de un documento:
    1. Pre-procesa los diagramas Mermaid.
    2. Si el documento es pequeno: genera el articulo en una sola llamada.
    3. Si el documento es extenso (> UMBRAL_SECCIONADO): procesa por secciones.
    """
    # 1. Preprocesar Mermaid
    contenido, n_mermaid = preprocesar_mermaid(contenido_raw)
    if n_mermaid > 0:
        print(f"          Diagramas Mermaid detectados: {n_mermaid}")

    # 2. Extraer encabezados para cobertura completa
    encabezados = extraer_encabezados(contenido)

    # 3. Estrategia segun tamaño
    if len(contenido) <= UMBRAL_SECCIONADO:
        return generar_articulo_con_ollama(contenido, modelo, codigo_idioma,
                                           n_mermaid=n_mermaid, encabezados=encabezados)
    else:
        print(f"          Documento extenso ({len(contenido):,} chars). Procesando por secciones...")
        return generar_articulo_grande(contenido, modelo, codigo_idioma, n_mermaid, encabezados)


def generar_articulo_bilingue_con_ollama(contenido_md, modelo):
    """
    Genera un articulo bilingue mejorado en una sola llamada.
    Devuelve ES completo + separador markdown + EN completo.
    """
    SEPARADOR = "---ENGLISH-VERSION---"
    contenido_proc, n_mermaid = preprocesar_mermaid(contenido_md)
    if n_mermaid > 0:
        print(f"          Diagramas Mermaid detectados: {n_mermaid}")

    encabezados = extraer_encabezados(contenido_proc)
    bloque_cobertura = _bloque_cobertura_completa(encabezados, n_mermaid)

    prompt_usuario = (
        "MISION:\n"
        "Eres un redactor tecnico senior multilingue. A partir del contenido tecnico que se "
        "te proporciona, crearas DOS versiones completas e independientes del mismo articulo: "
        "una en ESPAÑOL y otra en INGLES. Ambas son la mejor expresion del contenido en su idioma, "
        "no traducciones literales entre si.\n\n"

        + bloque_cobertura + "\n\n"

        "ESTRUCTURA DE TU RESPUESTA (OBLIGATORIA Y EXACTA):\n"
        "1. Version completa en ESPAÑOL.\n"
        f"2. Una linea con exactamente: {SEPARADOR}\n"
        "3. Version completa en INGLES.\n\n"

        "ESTRUCTURA DE CADA VERSION:\n\n"
        "A) TITULO Y SUBTITULO — atractivo, 60-70 chars\n"
        "B) INTRODUCCION — 150-200 palabras, problema real\n"
        "C) CONCEPTOS BASICOS — analogias del mundo real\n"
        "D) SECCION PRACTICA — pasos + codigo + resultado esperado\n"
        "E) EJEMPLOS PRACTICOS — minimo 2-3, entrada/proceso/salida\n"
        "F) PRO TIPS — minimo 5, rendimiento/seguridad/escalabilidad\n"
        "G) TROUBLESHOOTING — [ERROR] | Causa | Solucion, minimo 2-3\n"
        "H) RESUMEN Y LLAMADO A ACCION — 3-4 puntos + proximo paso\n\n"

        "CRITERIOS POR VERSION:\n"
        "- 1200-1500 palabras\n"
        "- Minimo 2-3 bloques de codigo ejecutables\n"
        "- Lenguaje natural y fluido (no traduccion mecanica)\n"
        "- CERO caracteres asiaticos\n\n"

        "PROHIBIDO en ambas versiones: mencionar herramientas automaticas. "
        "Ambas deben leer como escritas por un experto humano.\n\n"

        "CONTENIDO:\n"
        "===========================================================================\n\n"
        + contenido_proc +
        "\n\n===========================================================================\n\n"
        "Responde DIRECTAMENTE. Primero ESPAÑOL completo, luego "
        f"'{SEPARADOR}', luego ENGLISH completo.\n"
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt_usuario}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 16384,
            "num_ctx": 16384,
        }
    }

    try:
        output = _llamar_ollama(payload, modelo)
    except RuntimeError as e:
        return f"[ERROR] {e}"

    output = re.sub(
        r"\n*" + re.escape(SEPARADOR) + r"\n*",
        "\n\n---\n\n## English Version\n\n",
        output
    )
    if "---" not in output:
        output += (
            "\n\n---\n\n"
            "> **Note:** the engine did not produce a clear language separator. "
            "The English version may not be present or may be merged with the Spanish one."
        )
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Procesamiento de archivos
# ─────────────────────────────────────────────────────────────────────────────

def procesar_en_idioma(directorio_entrada, directorio_base_salida,
                       modelo, codigo_idioma, etiqueta, num_offset=0):
    """
    Procesa todos los archivos del directorio en un idioma concreto.
    Devuelve (total_ok, total_errores).
    """
    directorio_salida = os.path.join(directorio_base_salida, codigo_idioma)
    os.makedirs(directorio_salida, exist_ok=True)

    total = 0
    errores = 0

    for carpeta_raiz, _, archivos in os.walk(directorio_entrada):
        for archivo in sorted(archivos):
            ext = os.path.splitext(archivo)[1].lower()
            if ext not in EXTENSIONES_SOPORTADAS:
                continue

            ruta_entrada = os.path.join(carpeta_raiz, archivo)
            subruta = os.path.relpath(carpeta_raiz, directorio_entrada)
            nombre_base = os.path.splitext(archivo)[0]
            nombre_salida = f"{nombre_base}_articulo.md"
            ruta_salida = os.path.join(directorio_salida, subruta, nombre_salida)

            os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

            num = num_offset + total + errores + 1
            print(f"[{num}] [{etiqueta}] {ruta_entrada}")

            try:
                contenido = leer_archivo(ruta_entrada)

                if not contenido.strip():
                    print(f"     [ADVERTENCIA] Archivo vacio, se omite.\n")
                    errores += 1
                    continue

                start = time.time()
                articulo = procesar_documento(contenido, modelo, codigo_idioma)
                duracion = time.time() - start

                if articulo.startswith("[ERROR]"):
                    print(f"     {articulo}\n")
                    errores += 1
                    continue

                with open(ruta_salida, "w", encoding="utf-8") as f:
                    f.write(articulo)

                palabras = len(articulo.split())
                print(f"     [OK] -> {ruta_salida}")
                print(f"          Tiempo: {duracion:.1f}s  |  Palabras: {palabras}  |  Chars: {len(articulo)}\n")
                total += 1

            except Exception as e:
                print(f"     [ERROR] {e}\n")
                errores += 1

    return total, errores


def procesar_en_bilingue(directorio_entrada, directorio_base_salida, modelo, num_offset=0):
    """
    Genera articulos bilingues mejorados (ES + EN en un solo archivo).
    Devuelve (total_ok, total_errores).
    """
    directorio_salida = os.path.join(directorio_base_salida, "bilingue")
    os.makedirs(directorio_salida, exist_ok=True)

    total = 0
    errores = 0

    for carpeta_raiz, _, archivos in os.walk(directorio_entrada):
        for archivo in sorted(archivos):
            ext = os.path.splitext(archivo)[1].lower()
            if ext not in EXTENSIONES_SOPORTADAS:
                continue

            ruta_entrada = os.path.join(carpeta_raiz, archivo)
            subruta = os.path.relpath(carpeta_raiz, directorio_entrada)
            nombre_base = os.path.splitext(archivo)[0]
            nombre_salida = f"{nombre_base}_bilingue.md"
            ruta_salida = os.path.join(directorio_salida, subruta, nombre_salida)

            os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

            num = num_offset + total + errores + 1
            print(f"[{num}] [BILINGUE] {ruta_entrada}")

            try:
                contenido = leer_archivo(ruta_entrada)

                if not contenido.strip():
                    print(f"     [ADVERTENCIA] Archivo vacio, se omite.\n")
                    errores += 1
                    continue

                start = time.time()
                articulo = generar_articulo_bilingue_con_ollama(contenido, modelo)
                duracion = time.time() - start

                if articulo.startswith("[ERROR]"):
                    print(f"     {articulo}\n")
                    errores += 1
                    continue

                with open(ruta_salida, "w", encoding="utf-8") as f:
                    f.write(articulo)

                palabras = len(articulo.split())
                print(f"     [OK] -> {ruta_salida}")
                print(f"          Tiempo: {duracion:.1f}s  |  Palabras: {palabras}  |  Chars: {len(articulo)}\n")
                total += 1

            except Exception as e:
                print(f"     [ERROR] {e}\n")
                errores += 1

    return total, errores


def procesar_archivos(directorio_entrada, directorio_base_salida, modelo, idioma):
    """
    Punto de entrada del procesamiento.
    Gestiona los cuatro modos: es, en, both, bilingue.
    """
    if not os.path.isdir(directorio_entrada):
        print(f"[ERROR] El directorio no existe: {directorio_entrada}")
        sys.exit(1)

    print(f"\nMotor activo    : {modelo}")
    print(f"Limpieza salida : {'SI' if modelo_tiene_thinking(modelo) else 'NO'}")
    print(f"Extensiones     : {', '.join(sorted(EXTENSIONES_SOPORTADAS))}")
    print(f"Mermaid         : SI (deteccion y analisis automatico)")
    print(f"Docs extensos   : seccionado automatico si > {UMBRAL_SECCIONADO:,} chars")
    print(f"Modo            : {idioma.upper()}")
    print(f"Salida base     : {directorio_base_salida}/")
    print("\nIniciando procesamiento...\n")

    total_global = 0
    errores_global = 0

    if idioma == "bilingue":
        ok, err = procesar_en_bilingue(directorio_entrada, directorio_base_salida, modelo)
        total_global += ok
        errores_global += err

    else:
        if idioma == "both":
            pasadas = [("es", "ES"), ("en", "EN")]
        else:
            pasadas = [(idioma, idioma.upper())]

        offset = 0
        for codigo, etiqueta in pasadas:
            if len(pasadas) > 1:
                print("-" * 80)
                print(f"  PASADA: {etiqueta}  →  {directorio_base_salida}/{codigo}/")
                print("-" * 80 + "\n")

            ok, err = procesar_en_idioma(
                directorio_entrada, directorio_base_salida,
                modelo, codigo, etiqueta, num_offset=offset
            )
            total_global += ok
            errores_global += err
            offset += ok + err

    print("=" * 80)
    print("PROCESAMIENTO FINALIZADO")
    print("=" * 80)
    print(f"  Procesados correctamente : {total_global}")
    print(f"  Errores / omitidos       : {errores_global}")
    print(f"  Directorio(s) de salida  :")
    if idioma == "both":
        print(f"    {directorio_base_salida}/es/")
        print(f"    {directorio_base_salida}/en/")
    elif idioma == "bilingue":
        print(f"    {directorio_base_salida}/bilingue/")
    else:
        print(f"    {directorio_base_salida}/{idioma}/")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 generar_articulos_mejorado.py <directorio_entrada>")
        print("Ej:  python3 generar_articulos_mejorado.py DQ/")
        sys.exit(1)

    DIRECTORIO_ENTRADA = sys.argv[1]
    base_nombre = os.path.basename(os.path.normpath(DIRECTORIO_ENTRADA))
    DIRECTORIO_BASE_SALIDA = f"{base_nombre}_procesado"

    print("=" * 80)
    print("GENERADOR DE ARTICULOS - VERSION 6.0")
    print("=" * 80)
    print(f"  OLLAMA_HOST       : {OLLAMA_HOST}")
    print(f"  Directorio entrada: {DIRECTORIO_ENTRADA}")
    print(f"  Directorio salida : {DIRECTORIO_BASE_SALIDA}/<idioma>/")
    if PDF_DISPONIBLE:
        print(f"  Soporte PDF       : SI (pdfplumber)")
    else:
        print(f"  Soporte PDF       : NO  →  instala con: pip install pdfplumber")

    # 1. Seleccion de idioma
    idioma_elegido = seleccionar_idioma()

    # 2. Detectar tipo de archivo predominante
    extension_dominante = detectar_extension_dominante(DIRECTORIO_ENTRADA)

    # 3. Obtener motores disponibles
    print("\nConsultando motores disponibles...")
    modelos = obtener_modelos_ollama()
    if not modelos:
        print("[ERROR] No se encontraron motores. Comprueba que Ollama esta activo.")
        sys.exit(1)
    print(f"Motores encontrados: {len(modelos)}")

    # 4. Seleccion de motor
    modelo_elegido = seleccionar_modelo(modelos, extension_dominante)

    print("\n" + "=" * 80)
    print("INICIO DE PROCESAMIENTO")
    print("=" * 80)

    # 5. Procesar
    procesar_archivos(
        DIRECTORIO_ENTRADA,
        DIRECTORIO_BASE_SALIDA,
        modelo_elegido,
        idioma_elegido
    )
