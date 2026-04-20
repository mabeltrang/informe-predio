"""
Lógica pura del análisis de predio.
Se puede importar desde cualquier automatización sin arrastrar la UI.
"""
import os, zipfile, io, calendar, base64, logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, MultiPolygon
import geopandas as gpd

logger = logging.getLogger(__name__)

CARTOGRAFIA_DIR  = Path(os.getenv("CARTOGRAFIA_DIR", "./data"))
UC_SHP_NAME      = os.getenv("UC_SHAPEFILE_NAME",   "Unidades_Cronoestratigraficas.shp")
EXCEL_NAME       = os.getenv("GEOFORMA_EXCEL_NAME", "Diccionario_UC_Geomorfologia.xlsx")
UC_SHP_PATH      = CARTOGRAFIA_DIR / UC_SHP_NAME
EXCEL_PATH       = CARTOGRAFIA_DIR / EXCEL_NAME

MONTH_LABELS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


def parse_kmz(file_bytes: bytes):
    """Extrae el primer polígono de un KMZ. Devuelve geometría Shapely."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        kml_name = next((f for f in z.namelist() if f.lower().endswith(".kml")), None)
        if not kml_name:
            raise ValueError("El KMZ no contiene un archivo KML válido.")
        kml_bytes = z.read(kml_name)

    root = ET.fromstring(kml_bytes)
    ns = "http://www.opengis.net/kml/2.2"
    polygons = []

    for coords_el in root.iter(f"{{{ns}}}coordinates"):
        text = coords_el.text.strip()
        points = []
        for triple in text.split():
            parts = triple.split(",")
            if len(parts) >= 2:
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                    points.append((lon, lat))
                except ValueError:
                    continue
        if len(points) >= 3:
            polygons.append(Polygon(points))

    if not polygons:
        raise ValueError("No se encontró ningún polígono en el KMZ.")
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def fetch_power(lat: float, lon: float, start: int = 2015, end: int = 2025) -> pd.DataFrame:
    """Descarga serie mensual de NASA POWER (sin API key)."""
    url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
    r = requests.get(url, params={
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN",
        "community": "AG",
        "longitude": round(lon, 4),
        "latitude":  round(lat, 4),
        "start": start, "end": end, "format": "JSON",
    }, timeout=60)
    r.raise_for_status()
    data = r.json()["properties"]["parameter"]

    rows = []
    for year in range(start, end + 1):
        for month in range(1, 13):
            key = f"{year}{month:02d}"
            pd_ = data["PRECTOTCORR"].get(key, -999)
            t2m = data["T2M"].get(key, -999)
            if pd_ == -999 or t2m == -999:
                continue
            rows.append({
                "year": year, "month": month,
                "prec_mm": round(pd_ * calendar.monthrange(year, month)[1], 1),
                "t2m":   t2m,
                "t_max": data["T2M_MAX"].get(key, t2m),
                "t_min": data["T2M_MIN"].get(key, t2m),
            })
    if not rows:
        raise ValueError("NASA POWER no devolvió datos para estas coordenadas.")
    return pd.DataFrame(rows)


def calc_stats(df: pd.DataFrame) -> dict:
    m = df.groupby("month").agg(
        prec=("prec_mm", "mean"), t2m=("t2m", "mean"),
        t_max=("t_max", "mean"), t_min=("t_min", "mean"),
    ).reset_index()

    m["seco"] = m["prec"] < 2 * m["t2m"]
    prec = m["prec"].tolist()
    peaks = sum(1 for i in range(12) if prec[i] > prec[(i-1)%12] and prec[i] > prec[(i+1)%12])

    return {
        "prec_anual":   round(m["prec"].sum(), 0),
        "t_media":      round(m["t2m"].mean(), 1),
        "t_max":        round(m["t_max"].max(), 1),
        "t_min":        round(m["t_min"].min(), 1),
        "prec_max_mes": round(m["prec"].max(), 0),
        "n_secos":      int(m["seco"].sum()),
        "regimen":      "bimodal" if peaks >= 2 else "monomodal",
        "monthly":      m.to_dict(orient="records"),
    }


def make_charts(monthly_data: list) -> Tuple[bytes, bytes]:
    """Devuelve (precip_png, temp_png) como bytes."""
    months = [d["month"] for d in monthly_data]
    prec   = [d["prec"]  for d in monthly_data]
    temp   = [d["t2m"]   for d in monthly_data]

    def _render(color, values, ylabel, title) -> bytes:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(months, values, color=color, linewidth=2, marker="o", markersize=4)
        if color == "#1565C0":
            ax.fill_between(months, values, alpha=0.12, color=color)
        ax.set_xticks(range(1, 13)); ax.set_xticklabels(MONTH_LABELS)
        ax.set_ylabel(ylabel); ax.set_title(title); ax.grid(alpha=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        plt.close(fig)
        return buf.getvalue()

    return (
        _render("#1565C0", prec, "Precipitación (mm/mes)", "Precipitación mensual promedio"),
        _render("#C62828", temp, "Temperatura media (°C)", "Temperatura mensual promedio"),
    )


def get_geoforma(
    predio_geom,
    uc_shp_path: Path = UC_SHP_PATH,
    excel_path:  Path = EXCEL_PATH,
    campo: str = "SimboloUC",
) -> Tuple[Optional[str], Optional[pd.DataFrame], Optional[object]]:
    """Intersecta el predio con el shapefile de UC y busca en el diccionario Excel.
    Retorna (simbolo, df_diccionario, geometria_uc_en_4326).
    """
    if not Path(uc_shp_path).exists():
        raise FileNotFoundError(f"Shapefile no encontrado: {uc_shp_path}")
    if not Path(excel_path).exists():
        raise FileNotFoundError(f"Excel no encontrado: {excel_path}")

    uc_gdf = gpd.read_file(str(uc_shp_path))
    if campo not in uc_gdf.columns:
        raise ValueError(f"El shapefile no tiene '{campo}'. Columnas: {list(uc_gdf.columns)}")

    predio_gdf = gpd.GeoDataFrame(geometry=[predio_geom], crs="EPSG:4326")
    predio_proj = predio_gdf.to_crs("EPSG:3116")
    uc_proj = uc_gdf.to_crs("EPSG:3116") if uc_gdf.crs else uc_gdf.set_crs("EPSG:3116")

    inter = gpd.overlay(predio_proj, uc_proj, how="intersection")
    if inter.empty:
        return None, None, None

    inter["_area"] = inter.geometry.area
    simbolo = inter.groupby(campo)["_area"].sum().idxmax()

    # Geometría completa de la UC dominante en WGS84
    uc_match = uc_proj[uc_proj[campo].astype(str) == str(simbolo)]
    uc_geom_4326 = uc_match.to_crs("EPSG:4326").geometry.unary_union

    try:
        df_dict = pd.read_excel(str(excel_path), engine="xlrd")
    except Exception:
        df_dict = pd.read_excel(str(excel_path), engine="openpyxl")

    df_uc = df_dict[df_dict[campo].astype(str) == str(simbolo)]
    return simbolo, (df_uc if not df_uc.empty else None), uc_geom_4326


def make_mapa_satelital(predio_geom, uc_geom=None) -> Optional[bytes]:
    """Genera PNG satelital con el polígono del predio y la geoforma superpuestos."""
    try:
        import contextily as ctx

        predio_gdf = gpd.GeoDataFrame(geometry=[predio_geom], crs="EPSG:4326")
        predio_web = predio_gdf.to_crs(epsg=3857)

        fig, ax = plt.subplots(figsize=(8, 8))

        if uc_geom is not None:
            uc_gdf = gpd.GeoDataFrame(geometry=[uc_geom], crs="EPSG:4326")
            uc_web = uc_gdf.to_crs(epsg=3857)
            uc_web.plot(ax=ax, facecolor="#FFD700", edgecolor="#FF8C00",
                        alpha=0.35, linewidth=2.5, zorder=2, label="Geoforma (UC)")

        predio_web.plot(ax=ax, facecolor="none", edgecolor="#FF0000",
                        linewidth=2.5, zorder=3, label="Predio")

        # Zoom al predio con buffer de 30 % (mínimo 500 m)
        bounds = predio_web.total_bounds
        dx = max((bounds[2] - bounds[0]) * 0.3, 500)
        dy = max((bounds[3] - bounds[1]) * 0.3, 500)
        ax.set_xlim(bounds[0] - dx, bounds[2] + dx)
        ax.set_ylim(bounds[1] - dy, bounds[3] + dy)

        ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, zoom="auto")

        ax.set_axis_off()
        ax.legend(loc="upper right", fontsize=9, framealpha=0.8)
        ax.set_title("Imagen satelital — predio y unidad geomorfológica", fontsize=11, pad=8)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"No se pudo generar imagen satelital: {type(e).__name__}: {e}")
        return None


def texto_clima(stats: dict, start: int, end: int) -> str:
    t = stats['t_media']
    clima_termico = "cálido" if t > 24 else "templado" if t > 18 else "frío" if t > 12 else "muy frío/páramo"
    return (
        f"El clima del predio se clasifica predominantemente como {clima_termico}, "
        f"con una temperatura media mensual que varía entre {stats['t_min']:.1f}°C y {stats['t_max']:.1f}°C "
        f"(promedio general de {stats['t_media']:.1f}°C).\n\n"
        f"El régimen de precipitación es {stats['regimen']}, alcanzando un acumulado anual promedio de "
        f"{stats['prec_anual']:.0f} mm para el periodo {start}-{end}. Durante la época seca las lluvias "
        f"disminuyen significativamente, identificándose {stats['n_secos']} meses secos por año "
        f"(criterio de Gaussen, P < 2T). En la temporada húmeda, los aportes hídricos llegan a topes de "
        f"{stats['prec_max_mes']:.0f} mm mensuales.\n\n"
        f"Fuente: NASA Prediction Of Worldwide Energy Resources (POWER), {start}-{end}. Elaboración propia."
    )

def generate_docx(
    clima_txt: str,
    geo_txt: str,
    precip_png: bytes,
    temp_png: bytes,
    mapa_png: Optional[bytes] = None,
) -> bytes:
    from docx import Document
    from docx.shared import Inches
    import io as _io

    doc = Document()
    doc.add_heading('Informe de Aprovechamiento Forestal', 0)

    doc.add_heading('1. Análisis Climático', level=1)
    doc.add_paragraph(clima_txt)
    doc.add_picture(_io.BytesIO(precip_png), width=Inches(5.5))
    doc.add_picture(_io.BytesIO(temp_png), width=Inches(5.5))

    doc.add_heading('2. Análisis Geomorfológico', level=1)
    if mapa_png:
        doc.add_picture(_io.BytesIO(mapa_png), width=Inches(5.5))
    if geo_txt:
        doc.add_paragraph(geo_txt)
    else:
        doc.add_paragraph("No se encontró información geomorfológica para el predio solicitado.")

    buf = _io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def texto_geoforma(simbolo: str, df_uc: pd.DataFrame) -> str:
    r0 = df_uc.iloc[0]
    bullets = "\n".join(
        f"• {r.get('Geoforma','')}: {r.get('DescGeoforma','')}"
        for _, r in df_uc.iterrows()
        if pd.notna(r.get("Geoforma")) and str(r.get("Geoforma")).strip()
    )
    return (
        f"De acuerdo con la cartografía geomorfológica disponible, el predio se ubica dentro de la unidad "
        f"geomorfológica {simbolo}, clasificada como \"{r0.get('NombreUC','')}\". Esta unidad corresponde a "
        f"{r0.get('TipoUnidad','')} de edad {r0.get('Edad','')}, compuesta por {r0.get('Materiales','')}. "
        f"{r0.get('ProcesoFormacion','')}\n\n"
        f"La unidad {simbolo} comprende las siguientes geoformas principales:\n{bullets}"
    )
