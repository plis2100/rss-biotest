import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator


PAGINA_NOTICIAS = (
    "https://www.biotest.com/de/en/investor_relations/"
    "news_and_publications/biotest_press_releases.cfm"
)

URL_RSS = (
    "https://raw.githubusercontent.com/"
    "plis2100/rss-biotest/main/docs/feed.xml"
)

ARCHIVO_RSS = Path("docs/feed.xml")

PATRON_COMUNICADO = re.compile(
    r"(20\d{2}-\d{2}-\d{2})\s*-\s*(.+?)(?=\s+PDF\b|\s+Download\b|$)",
    re.IGNORECASE,
)


def limpiar_texto(texto):
    return " ".join((texto or "").split()).strip()


def descargar_pagina():
    cabeceras = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    respuesta = requests.get(
        PAGINA_NOTICIAS,
        headers=cabeceras,
        timeout=(10, 40),
    )
    respuesta.raise_for_status()

    if len(respuesta.text) < 500:
        raise RuntimeError(
            "Biotest devolvió una página vacía o incompleta."
        )

    return respuesta.text


def encontrar_datos_del_pdf(enlace_pdf):
    """
    Busca el bloque más pequeño que contiene el PDF y una sola
    fecha con su correspondiente título.
    """
    nodo = enlace_pdf

    for _ in range(10):
        nodo = nodo.parent

        if nodo is None:
            break

        texto = limpiar_texto(nodo.get_text(" ", strip=True))
        coincidencias = list(PATRON_COMUNICADO.finditer(texto))

        if len(coincidencias) == 1:
            coincidencia = coincidencias[0]

            return {
                "fecha": coincidencia.group(1),
                "titulo": limpiar_texto(coincidencia.group(2)),
            }

        # Si ya hemos llegado a una zona que contiene muchos
        # comunicados, no seguimos ascendiendo.
        if len(coincidencias) > 3:
            break

    return None


def obtener_comunicados():
    html = descargar_pagina()
    sopa = BeautifulSoup(html, "html.parser")

    comunicados = []
    enlaces_vistos = set()

    for enlace_pdf in sopa.select("a[href]"):
        href = enlace_pdf.get("href", "").strip()

        if not href:
            continue

        enlace_absoluto = urljoin(PAGINA_NOTICIAS, href)

        # Los comunicados oficiales se publican en PDF.
        if ".pdf" not in enlace_absoluto.lower():
            continue

        if enlace_absoluto in enlaces_vistos:
            continue

        datos = encontrar_datos_del_pdf(enlace_pdf)

        if not datos:
            continue

        titulo = datos["titulo"]
        fecha_texto = datos["fecha"]

        if not titulo or len(titulo) < 8:
            continue

        try:
            fecha = datetime.strptime(
                fecha_texto,
                "%Y-%m-%d",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        enlaces_vistos.add(enlace_absoluto)

        comunicados.append(
            {
                "titulo": titulo,
                "enlace": enlace_absoluto,
                "fecha": fecha,
                "descripcion": (
                    f"Comunicado oficial de Biotest publicado "
                    f"el {fecha.strftime('%d/%m/%Y')}. "
                    f"El documento completo está disponible en PDF."
                ),
            }
        )

    comunicados.sort(
        key=lambda comunicado: comunicado["fecha"],
        reverse=True,
    )

    if not comunicados:
        raise RuntimeError(
            "No se encontraron comunicados de Biotest. "
            "El RSS anterior no será eliminado."
        )

    print(f"Se encontraron {len(comunicados)} comunicados.")

    for comunicado in comunicados[:10]:
        print(
            comunicado["fecha"].strftime("%Y-%m-%d"),
            "-",
            comunicado["titulo"],
        )

    return comunicados[:50]


def crear_rss(comunicados):
    ahora = datetime.now(timezone.utc)

    generador = FeedGenerator()
    generador.id(PAGINA_NOTICIAS)
    generador.title("Biotest - Press Releases")
    generador.description(
        "Últimos comunicados de prensa oficiales de Biotest"
    )
    generador.language("en")

    generador.link(
        href=PAGINA_NOTICIAS,
        rel="alternate",
    )
    generador.link(
        href=URL_RSS,
        rel="self",
    )

    generador.lastBuildDate(ahora)

    # FeedGen coloca primero el último elemento añadido.
    for comunicado in reversed(comunicados):
        entrada = generador.add_entry()

        entrada.id(comunicado["enlace"])
        entrada.guid(
            comunicado["enlace"],
            permalink=True,
        )
        entrada.title(comunicado["titulo"])
        entrada.link(href=comunicado["enlace"])
        entrada.description(comunicado["descripcion"])
        entrada.pubDate(comunicado["fecha"])

    ARCHIVO_RSS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    generador.rss_file(
        str(ARCHIVO_RSS),
        pretty=True,
    )

    if not ARCHIVO_RSS.exists():
        raise RuntimeError("No se creó docs/feed.xml.")

    if ARCHIVO_RSS.stat().st_size < 300:
        raise RuntimeError(
            "docs/feed.xml está vacío o incompleto."
        )

    raiz = ET.parse(ARCHIVO_RSS).getroot()
    noticias = raiz.findall("./channel/item")

    if not noticias:
        raise RuntimeError(
            "El RSS se creó, pero no contiene noticias."
        )

    print(
        f"RSS creado correctamente con {len(noticias)} noticias: "
        f"{ARCHIVO_RSS}"
    )


def main():
    comunicados = obtener_comunicados()
    crear_rss(comunicados)


if __name__ == "__main__":
    main()
