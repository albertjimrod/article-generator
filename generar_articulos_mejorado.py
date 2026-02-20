#!/usr/bin/env python3
"""
Script mejorado para generar articulos con Ollama
Seleccion interactiva de idioma, modelo y recomendacion por tipo de archivo
Version: 5.0
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

# Motor recomendado por extension (nombre exacto en Ollama)
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
        "instruccion": None,   # se asigna por pasada
    },
    "4": {
        "codigo":  "bilingue",
        "nombre":  "Bilingüe mejorado (ES + EN en un archivo) → <dir>_procesado/bilingue/",
        "instruccion": None,   # gestionado por generar_articulo_bilingue_con_ollama
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def obtener_modelos_ollama():
    """Consulta la API de Ollama y devuelve la lista de modelos disponibles
    excluyendo los de embeddings, que no sirven para generacion de texto."""
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
                # Nombre limpio sin la parte de directorio para el mensaje
                nombre_corto = cfg['nombre'].split("→")[0].strip()
                print(f"\n[OK] Modo seleccionado: {nombre_corto}")
                return cfg["codigo"]
            print(f"[!] Opcion invalida. Elige {', '.join(opciones_validas)}.")
        except KeyboardInterrupt:
            print("\n[!] Abortado por el usuario.")
            sys.exit(0)


def seleccionar_modelo(modelos_disponibles, extension_dominante):
    """Muestra un menu interactivo para elegir el modelo de Ollama."""
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
                print(f"\n[OK] Modelo seleccionado: {elegido}")
                return elegido
            else:
                print(f"[!] Numero invalido. Elige entre 1 y {len(modelos_disponibles)}.")

        except ValueError:
            print("[!] Introduce un numero valido.")
        except KeyboardInterrupt:
            print("\n[!] Abortado por el usuario.")
            sys.exit(0)


def leer_pdf(ruta):
    """
    Extrae el texto de un PDF con pdfplumber.

    Estrategia por pagina:
    1. Intenta extraer texto normal (PDFs con capa de texto).
    2. Si la pagina no tiene texto, la omite con una nota (imagenes/escaneados).
    3. Preserva las tablas como bloques Markdown.
    4. Devuelve el contenido limpio listo para procesar.
    """
    partes = []
    paginas_sin_texto = 0

    with pdfplumber.open(ruta) as pdf:
        total_paginas = len(pdf.pages)
        for i, pagina in enumerate(pdf.pages, 1):
            # ── Tablas ──────────────────────────────────────────────────────
            tablas = pagina.extract_tables()
            texto_tablas = set()
            for tabla in tablas:
                if not tabla:
                    continue
                filas_md = []
                for j, fila in enumerate(tabla):
                    celdas = [str(c or "").replace("\n", " ").strip() for c in fila]
                    filas_md.append("| " + " | ".join(celdas) + " |")
                    if j == 0:
                        filas_md.append("|" + "|".join(["---"] * len(celdas)) + "|")
                bloque_tabla = "\n".join(filas_md)
                partes.append(bloque_tabla)
                texto_tablas.add(bloque_tabla)

            # ── Texto normal (excluye zonas ya cubiertas por tablas) ─────────
            texto = pagina.extract_text(x_tolerance=3, y_tolerance=3)
            if texto and texto.strip():
                partes.append(texto.strip())
            else:
                paginas_sin_texto += 1

    if not partes:
        raise ValueError(
            f"No se pudo extraer texto del PDF '{os.path.basename(ruta)}'. "
            f"Es posible que sea un PDF escaneado sin capa de texto OCR."
        )

    aviso = ""
    if paginas_sin_texto > 0:
        aviso = (
            f"\n\n[NOTA: {paginas_sin_texto} de {total_paginas} paginas no tenian "
            f"capa de texto y fueron omitidas (posiblemente imagenes escaneadas).]\n\n"
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
    # Fallback español
    return IDIOMAS["1"]["instruccion"]


def generar_articulo_con_ollama(contenido_md, modelo, codigo_idioma):
    """Genera un articulo usando Ollama con el modelo e idioma seleccionados."""

    instruccion_idioma = construir_instruccion_idioma(codigo_idioma)

    prompt_usuario = (
        "INSTRUCCION PRINCIPAL:\n"
        "Eres un redactor tecnico experto en ciencia de datos, machine learning e ingenieria de software. "
        "Tu mision es transformar notas tecnicas desorganizadas en articulos profesionales, educativos "
        "y altamente legibles. El resultado debe ser comparable a articulos publicados en blogs tecnico "
        "de alto nivel (Medium, Dev.to, blogs corporativos).\n\n"

        "OBJETIVO FINAL:\n"
        "Crear un articulo que sea:\n"
        "- Preciso en contenido tecnico\n"
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
        "   - Menciona el beneficio principal\n"
        "   - Anuncia lo que el lector aprendera\n\n"

        "C) CONCEPTOS BASICOS (si es necesario)\n"
        "   - Explica conceptos clave sin asumirlos conocidos\n"
        "   - Usa analogias del mundo real para conceptos complejos\n"
        "   - Secciona con headers claros\n\n"

        "D) SECCION PRACTICA PRINCIPAL\n"
        "   - Divide en pasos numerados si es procedimiento\n"
        "   - O en subsecciones tematicas si es concepto\n"
        "   - Cada paso: Explicacion + Codigo/Ejemplo + Resultado esperado\n"
        "   - Formato de codigo: Bloques con tres acentos grave (```bash o ```python)\n"
        "   - Incluye comentarios en codigo explicando que hace\n\n"

        "E) EJEMPLOS PRACTICOS\n"
        "   - Minimo 2-3 ejemplos reales y diferentes\n"
        "   - Con comandos exactos que pueden copiar-pegar\n"
        "   - Mostrar entrada, proceso, salida esperada\n"
        "   - Advertencias de errores comunes\n\n"

        "F) MEJORES PRACTICAS Y TIPS (minimo 5)\n"
        "   - Agrupa en seccion 'Pro Tips' o 'Consideraciones Importantes'\n"
        "   - Include rendimiento, seguridad, escalabilidad\n"
        "   - Usa formato de vinetas\n\n"

        "G) TROUBLESHOOTING (Errores Comunes)\n"
        "   - Formato: [ERROR] | Causa | Solucion\n"
        "   - Minimo 2-3 errores tipicos\n"
        "   - Soluciones paso a paso\n\n"

        "H) RESUMEN Y LLAMADO A ACCION\n"
        "   - Recapitula puntos principales (3-4 lineas)\n"
        "   - Proximo paso logico\n"
        "   - Invita a experimentar\n\n"

        "ESTILO DE ESCRITURA:\n\n"

        "TONO:\n"
        "- Profesional pero amigable (como un mentor senior)\n"
        "- Educativo sin ser condescendiente\n"
        "- Practico y orientado a resultados\n\n"

        "FORMATO:\n"
        "- Usa ### para subsecciones principales\n"
        "- Usa vinetas (-) para listas\n"
        "- Usa numeros (1. 2. 3.) solo para procedimientos con orden\n"
        "- Usa negrita **para enfasis** en puntos clave\n"
        "- Usa cursiva *para terminos introducidos por primera vez*\n\n"

        "CRITERIOS DE CALIDAD MINIMO:\n"
        "- Articulo de 1200-1500 palabras\n"
        "- Minimo 2-3 bloques de codigo ejecutables\n"
        "- Minimo 5 Pro Tips o mejores practicas\n"
        "- Seccion de Troubleshooting con errores comunes\n"
        "- Conclusion con proximo paso recomendado\n"
        "- CERO caracteres asiaticos\n\n"

        "REGLAS ESPECIALES:\n\n"

        "SI ES TUTORIAL: numera pasos, indica tiempo estimado, requisitos previos.\n"
        "SI ES CONCEPTO: empieza con analogia, ejemplos graduados, casos de uso al final.\n"
        "SI HAY CODIGO: version simple primero, luego avanzada, explica dependencias.\n"
        "SI HAY CONFIGURACION: ejemplos genericos + concretos, explica cada valor.\n\n"

        "AHORA, TRANSFORMA ESTE CONTENIDO EN UN ARTICULO PROFESIONAL:\n\n"
        "===========================================================================\n\n"
        + contenido_md +
        "\n\n"
        "===========================================================================\n\n"
        "IMPORTANTE:\n"
        "1. Respeta la estructura de 8 secciones descrita arriba\n"
        "2. Asegurate de alcanzar las 1200-1500 palabras\n"
        "3. CERO caracteres asiaticos\n"
        "4. El lector debe terminar el articulo sabiendo COMO HACER ESTO\n"
        "5. RESPONDE DIRECTAMENTE CON EL ARTICULO, sin preambulos ni explicaciones previas\n"
        f"6. {instruccion_idioma}\n"
        "7. PROHIBIDO mencionar en cualquier parte del articulo que ha sido generado, "
        "redactado, asistido o revisado por inteligencia artificial, modelos de lenguaje, "
        "herramientas automaticas o software de ningún tipo. "
        "El articulo debe leer como si lo hubiera escrito un experto humano.\n"
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt_usuario}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 4096,
        }
    }

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as temp_file:
            json.dump(payload, temp_file)
            temp_file_path = temp_file.name

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
            return "[ERROR] Articulo vacio"

        if modelo_tiene_thinking(modelo):
            output = limpiar_pensamiento(output)

        if not output:
            return "[ERROR] El articulo quedo vacio tras eliminar el bloque de pensamiento"

        return output

    except Exception as e:
        return f"[ERROR] Error generando articulo: {e}"
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def generar_articulo_bilingue_con_ollama(contenido_md, modelo):
    """
    Genera un articulo bilingüe mejorado en una sola llamada.
    Devuelve un texto con la version ES completa, un separador markdown,
    y la version EN completa. Ambas versiones son independientes y mejoradas,
    no traducciones literales la una de la otra.
    """

    SEPARADOR = "---ENGLISH-VERSION---"

    prompt_usuario = (
        "MISION:\n"
        "Eres un redactor tecnico senior multilingue especializado en ciencia de datos, "
        "machine learning e ingenieria de software. A partir del contenido tecnico que se "
        "te proporciona, crearás DOS versiones completas e independientes del mismo articulo "
        "profesional: una en ESPAÑOL y otra en INGLES.\n\n"

        "PRINCIPIO CLAVE: Cada version debe ser la mejor expresion posible del contenido "
        "en su propio idioma. NO son traducciones literales entre si. Aprovecha el doble "
        "pase para enriquecer ambas: si en una encuentras un ejemplo mas claro, reflejalo "
        "en la otra. Si un termino tecnico tiene mejor explicacion en un idioma, busca el "
        "equivalente optimo en el otro. El resultado deben ser dos articulos de maxima "
        "calidad que un lector nativo de cada idioma percibiria como escritos por un experto.\n\n"

        "ESTRUCTURA DE TU RESPUESTA (OBLIGATORIA Y EXACTA):\n\n"
        "1. Escribe la version en ESPAÑOL completa.\n"
        "2. En una linea nueva, escribe exactamente esto (sin espacios extra):\n"
        f"   {SEPARADOR}\n"
        "3. Escribe la version en INGLES completa.\n\n"

        "ESTRUCTURA DE CADA VERSION (aplicar a las dos):\n\n"

        "A) TITULO Y SUBTITULO / TITLE AND SUBTITLE\n"
        "   - Titulo atractivo, descriptivo, 60-70 caracteres maximo\n"
        "   - Subtitulo: beneficio o resultado en 1 linea\n\n"

        "B) INTRODUCCION / INTRODUCTION  (150-200 palabras)\n"
        "   - Abre con un problema o pregunta real del lector\n"
        "   - Explica POR QUE esto es importante\n"
        "   - Anuncia lo que el lector aprendera\n\n"

        "C) CONCEPTOS BASICOS / CORE CONCEPTS  (si aplica)\n"
        "   - Explica sin asumir conocimiento previo\n"
        "   - Usa analogias del mundo real\n\n"

        "D) SECCION PRACTICA / HANDS-ON SECTION\n"
        "   - Pasos numerados si es procedimiento, subsecciones si es concepto\n"
        "   - Cada paso: explicacion + codigo + resultado esperado\n"
        "   - Bloques de codigo con ```bash o ```python\n"
        "   - Comentarios en el codigo explicando cada parte\n\n"

        "E) EJEMPLOS PRACTICOS / PRACTICAL EXAMPLES\n"
        "   - Minimo 2-3 ejemplos reales, con entrada/proceso/salida\n"
        "   - Comandos exactos listos para copiar-pegar\n\n"

        "F) MEJORES PRACTICAS / PRO TIPS  (minimo 5)\n"
        "   - Rendimiento, seguridad, escalabilidad\n"
        "   - Formato de viñetas\n\n"

        "G) TROUBLESHOOTING / ERRORES COMUNES\n"
        "   - Formato: [ERROR] | Causa | Solucion\n"
        "   - Minimo 2-3 casos\n\n"

        "H) RESUMEN Y LLAMADO A ACCION / SUMMARY AND CALL TO ACTION\n"
        "   - Recapitula 3-4 puntos clave\n"
        "   - Proximo paso recomendado\n\n"

        "CRITERIOS DE CALIDAD (aplicar a CADA version por separado):\n"
        "- 1200-1500 palabras por version\n"
        "- Minimo 2-3 bloques de codigo ejecutables\n"
        "- Minimo 5 Pro Tips\n"
        "- Seccion de Troubleshooting con errores comunes\n"
        "- CERO caracteres asiaticos\n"
        "- Lenguaje natural y fluido en cada idioma (no traduccion mecanica)\n\n"

        "PROHIBIDO en ambas versiones: mencionar en ningun momento que el articulo ha sido "
        "generado, redactado, asistido o revisado por ninguna herramienta automatica. "
        "Ambas versiones deben leer como escritas por expertos humanos.\n\n"

        "CONTENIDO A TRANSFORMAR:\n"
        "===========================================================================\n\n"
        + contenido_md +
        "\n\n===========================================================================\n\n"
        "RECUERDA: responde DIRECTAMENTE sin preambulos.\n"
        "Primero la version completa en ESPAÑOL, luego exactamente la linea "
        f"'{SEPARADOR}', luego la version completa en ENGLISH.\n"
    )

    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt_usuario}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 8192,   # doble: dos articulos completos
        }
    }

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as temp_file:
            json.dump(payload, temp_file)
            temp_file_path = temp_file.name

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
            return "[ERROR] Articulo bilingüe vacio"

        if modelo_tiene_thinking(modelo):
            output = limpiar_pensamiento(output)

        if not output:
            return "[ERROR] Articulo bilingüe vacio tras limpiar salida"

        # Normalizar el separador a markdown estandar con cabeceras visibles
        output = re.sub(
            r"\n*" + re.escape(SEPARADOR) + r"\n*",
            "\n\n---\n\n## English Version\n\n",
            output
        )

        # Si el modelo no puso el separador, añadir una nota al final
        if "---" not in output:
            output += (
                "\n\n---\n\n"
                "> **Note:** the engine did not produce a clear language separator. "
                "The English version may not be present or may be merged with the Spanish one."
            )

        return output

    except Exception as e:
        return f"[ERROR] Error generando articulo bilingüe: {e}"
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# ─────────────────────────────────────────────────────────────────────────────
# Procesamiento de archivos
# ─────────────────────────────────────────────────────────────────────────────

def procesar_en_idioma(directorio_entrada, directorio_base_salida,
                       modelo, codigo_idioma, etiqueta, num_offset=0):
    """
    Procesa todos los archivos del directorio en un idioma concreto.
    Guarda los resultados en directorio_base_salida/<codigo_idioma>/

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
                articulo = generar_articulo_con_ollama(contenido, modelo, codigo_idioma)
                duracion = time.time() - start

                if articulo.startswith("[ERROR]"):
                    print(f"     {articulo}\n")
                    errores += 1
                    continue

                with open(ruta_salida, "w", encoding="utf-8") as f:
                    f.write(articulo)

                palabras = len(articulo.split())
                caracteres = len(articulo)

                print(f"     [OK] -> {ruta_salida}")
                print(f"          Tiempo: {duracion:.1f}s  |  Palabras: {palabras}  |  Chars: {caracteres}\n")
                total += 1

            except Exception as e:
                print(f"     [ERROR] {e}\n")
                errores += 1

    return total, errores


def procesar_en_bilingue(directorio_entrada, directorio_base_salida, modelo, num_offset=0):
    """
    Genera articulos bilingues mejorados (ES + EN en un solo archivo).
    Guarda los resultados en directorio_base_salida/bilingue/
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
                caracteres = len(articulo)

                print(f"     [OK] -> {ruta_salida}")
                print(f"          Tiempo: {duracion:.1f}s  |  Palabras: {palabras}  |  Chars: {caracteres}\n")
                total += 1

            except Exception as e:
                print(f"     [ERROR] {e}\n")
                errores += 1

    return total, errores


def procesar_archivos(directorio_entrada, directorio_base_salida, modelo, idioma):
    """
    Punto de entrada del procesamiento.
    Si idioma == 'both', procesa dos veces: primero ES, luego EN.
    """
    if not os.path.isdir(directorio_entrada):
        print(f"[ERROR] El directorio no existe: {directorio_entrada}")
        sys.exit(1)

    print(f"\nMotor activo    : {modelo}")
    print(f"Limpieza salida : {'SI' if modelo_tiene_thinking(modelo) else 'NO'}")
    print(f"Extensiones     : {', '.join(sorted(EXTENSIONES_SOPORTADAS))}")
    print(f"Modo            : {idioma.upper()}")
    print(f"Salida base     : {directorio_base_salida}/")
    print("\nIniciando procesamiento...\n")

    total_global = 0
    errores_global = 0

    if idioma == "bilingue":
        # Una sola pasada: genera ES + EN en cada archivo
        ok, err = procesar_en_bilingue(
            directorio_entrada, directorio_base_salida, modelo
        )
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
    print("GENERADOR DE ARTICULOS - VERSION 5.0")
    print("=" * 80)
    print(f"  OLLAMA_HOST       : {OLLAMA_HOST}")
    print(f"  Directorio entrada: {DIRECTORIO_ENTRADA}")
    print(f"  Directorio salida : {DIRECTORIO_BASE_SALIDA}/<idioma>/")
    if PDF_DISPONIBLE:
        print(f"  Soporte PDF       : SI (pdfplumber)")
    else:
        print(f"  Soporte PDF       : NO  →  instala con: pip install pdfplumber")

    # 1. Seleccion de idioma de salida
    idioma_elegido = seleccionar_idioma()

    # 2. Detectar tipo de archivo predominante
    extension_dominante = detectar_extension_dominante(DIRECTORIO_ENTRADA)

    # 3. Obtener motores disponibles desde Ollama
    print("\nConsultando motores disponibles...")
    modelos = obtener_modelos_ollama()
    if not modelos:
        print("[ERROR] No se encontraron motores. Comprueba que Ollama esta activo.")
        sys.exit(1)
    print(f"Motores encontrados: {len(modelos)}")

    # 4. Seleccion interactiva de motor
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
