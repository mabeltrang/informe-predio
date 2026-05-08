# ── Holdridge ─────────────────────────────────────────────────────────────────

def calc_biotemperatura(monthly_data: list) -> float:
    """Biotemperatura media anual (°C) según Holdridge.
    Aproximación con datos mensuales: trunca T2M mensual a [0, 30] y promedia.
    Para datos diarios sería más preciso, pero en zonas tropicales colombianas
    (T2M mensual siempre entre 0 y 30) el resultado coincide con la T media.
    """
    temps = [max(0.0, min(30.0, d["t2m"])) for d in monthly_data]
    return round(sum(temps) / len(temps), 2)


def clasificar_holdridge(biotemp: float, prec_anual: float) -> dict:
    """Clasifica zona de vida de Holdridge a partir de biotemperatura (°C)
    y precipitación anual (mm). Devuelve dict con código, nombre, piso,
    provincia de humedad y relación ETP/P.
    """
    # ETP anual ≈ biotemp * 58.93 (Holdridge)
    etp_anual = biotemp * 58.93
    etp_p = etp_anual / prec_anual if prec_anual > 0 else float("inf")

    # Piso altitudinal por biotemperatura
    if   biotemp >= 24:   piso, sufijo = "Tropical",     "T"
    elif biotemp >= 18:   piso, sufijo = "Premontano",   "PM"
    elif biotemp >= 12:   piso, sufijo = "Montano Bajo", "MB"
    elif biotemp >= 6:    piso, sufijo = "Montano",      "M"
    elif biotemp >= 3:    piso, sufijo = "Subalpino",    "SA"
    elif biotemp >= 1.5:  piso, sufijo = "Alpino",       "A"
    else:                 piso, sufijo = "Nival",        "N"

    # Provincia de humedad por relación ETP/P
    if   etp_p > 16:    provincia, formacion = "superárido",  "desierto"
    elif etp_p > 8:     provincia, formacion = "perárido",    "matorral desértico"
    elif etp_p > 4:     provincia, formacion = "árido",       "monte espinoso"
    elif etp_p > 2:     provincia, formacion = "semiárido",   "bosque muy seco"
    elif etp_p > 1:     provincia, formacion = "subhúmedo",   "bosque seco"
    elif etp_p > 0.5:   provincia, formacion = "húmedo",      "bosque húmedo"
    elif etp_p > 0.25:  provincia, formacion = "perhúmedo",   "bosque muy húmedo"
    else:               provincia, formacion = "superhúmedo", "bosque pluvial"

    # Código compacto: bs-T, bh-PM, etc.
    codigo_formacion = {
        "desierto": "d", "matorral desértico": "md", "monte espinoso": "me",
        "bosque muy seco": "bms", "bosque seco": "bs", "bosque húmedo": "bh",
        "bosque muy húmedo": "bmh", "bosque pluvial": "bp",
    }[formacion]
    codigo = f"{codigo_formacion}-{sufijo}"
    nombre = f"{formacion.capitalize()} {piso}"

    return {
        "codigo":    codigo,
        "nombre":    nombre,
        "piso":      piso,
        "provincia": provincia,
        "biotemp":   biotemp,
        "etp_anual": round(etp_anual, 0),
        "etp_p":     round(etp_p, 2),
    }


def texto_holdridge(holdridge: dict, prec_anual: float) -> str:
    """Genera el párrafo descriptivo de la zona de vida."""
    return (
        f"Según el sistema de zonas de vida de Holdridge, el predio se clasifica como "
        f"{holdridge['nombre']} ({holdridge['codigo']}). Esta clasificación se obtiene a partir "
        f"de una biotemperatura media anual de {holdridge['biotemp']:.1f}°C, una precipitación "
        f"total anual de {prec_anual:.0f} mm y una evapotranspiración potencial estimada de "
        f"{holdridge['etp_anual']:.0f} mm anuales (relación ETP/P = {holdridge['etp_p']:.2f}), "
        f"correspondiente a una provincia de humedad {holdridge['provincia']} dentro del piso "
        f"altitudinal {holdridge['piso']}.\n\n"
        f"Fuente: Holdridge, L. R. (1967). Life Zone Ecology. Tropical Science Center, San José, "
        f"Costa Rica. Cálculo basado en datos climáticos de NASA POWER. Elaboración propia."
    )
