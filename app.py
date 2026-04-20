import streamlit as st
from core import (
    parse_kmz, fetch_power, calc_stats, make_charts,
    get_geoforma, make_mapa_satelital, texto_clima, texto_geoforma, generate_docx,
    UC_SHP_PATH, EXCEL_PATH,
)

st.set_page_config(page_title="Informe de Aprovechamiento", layout="centered")
st.title("Análisis de Predio — Informe de Aprovechamiento Forestal")

# ── Inputs ────────────────────────────────────────────────────────────────────
kmz_file = st.file_uploader("Archivo KMZ del predio", type=["kmz"])

col1, col2 = st.columns(2)
start_year = col1.number_input("Año inicio", min_value=1990, max_value=2024, value=2015)
end_year   = col2.number_input("Año fin",    min_value=1991, max_value=2025, value=2025)

analizar = st.button("Analizar predio", type="primary", disabled=kmz_file is None)

# ── Análisis ──────────────────────────────────────────────────────────────────
if analizar and kmz_file is not None:
    with st.spinner("Analizando predio..."):
        try:
            # 1. KMZ → geometría
            predio_geom = parse_kmz(kmz_file.read())
            centroid = predio_geom.centroid
            lat, lon = centroid.y, centroid.x
            st.caption(f"Centroide: {lat:.5f}, {lon:.5f}")

            # 2. Clima
            with st.spinner("Descargando datos de NASA POWER..."):
                df = fetch_power(lat, lon, int(start_year), int(end_year))
            stats = calc_stats(df)
            precip_png, temp_png = make_charts(stats["monthly"])
            clima_txt = texto_clima(stats, int(start_year), int(end_year))

            # 3. Geomorfología
            geo_txt = None
            geo_warn = None
            mapa_png = None
            try:
                simbolo, df_uc, uc_geom = get_geoforma(predio_geom)
                if df_uc is not None:
                    geo_txt = texto_geoforma(simbolo, df_uc)
                    st.caption(f"Unidad UC identificada: **{simbolo}**")
                    with st.spinner("Generando imagen satelital..."):
                        mapa_png = make_mapa_satelital(predio_geom, uc_geom)
                else:
                    geo_warn = "El predio no intersecta ninguna UC en el shapefile."
                    mapa_png = make_mapa_satelital(predio_geom)
            except FileNotFoundError as e:
                geo_warn = str(e)
            except Exception as e:
                geo_warn = f"Error en geomorfología: {e}"

        except Exception as e:
            st.error(f"Error al analizar el predio: {e}")
            st.stop()

    # ── Resultados ────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    c1.image(precip_png, use_container_width=True)
    c2.image(temp_png,   use_container_width=True)

    st.subheader("Bloque: Clima")
    st.text_area("", value=clima_txt, height=200, key="clima_txt", label_visibility="collapsed")
    st.download_button("Descargar texto clima (.txt)", data=clima_txt,
                       file_name="clima.txt", mime="text/plain")

    if geo_warn:
        st.warning(geo_warn)

    if mapa_png:
        st.subheader("Imagen satelital — predio y geoforma")
        st.image(mapa_png, use_container_width=True)
    else:
        st.warning("No se pudo generar la imagen satelital. Verifica la conexión a internet o los logs del servidor.")

    if geo_txt:
        st.subheader("Bloque: Geomorfología")
        st.text_area("", value=geo_txt, height=250, key="geo_txt", label_visibility="collapsed")
        st.download_button("Descargar texto geomorfología (.txt)", data=geo_txt,
                           file_name="geoforma.txt", mime="text/plain")

    st.divider()
    st.subheader("📄 Descargar Informe Completo")
    docx_bytes = generate_docx(clima_txt, geo_txt, precip_png, temp_png, mapa_png)
    st.download_button(
        "Descargar consolidado en Word (.docx)", 
        data=docx_bytes,
        file_name="informe_predio.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
