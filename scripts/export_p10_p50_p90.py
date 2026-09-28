# -*- coding: utf-8 -*-
"""
export_p10_p50_p90.py
===========================================================================
QGIS PROCESSING SCRIPT
Genera una figura a 4 pannelli in fila:  P10 | P50 | P90 | P90 - P10

- P10, P50, P90: stessa scala colore lineare (min/max calcolati insieme
  sui tre raster, oppure impostati manualmente)
- P90 - P10: calcolata automaticamente con la Calcolatrice Raster,
  stile con scala colore DIVERGENTE centrata sullo zero (evidenzia dove
  l'intervallo di incertezza e' piu' ampio)
- Stessa estensione, stessa posizione pozzi/lago, stessa simbologia su
  tutti i pannelli
- Etichette e legenda dimensionate sul testo reale (nessun taglio)

COME INSTALLARLO
-----------------
Stessa cartella script del file export_griglia_kriging.py:
  Processing -> Script -> clic destro "Scripts" -> "Apri cartella script"
Copia qui il file, poi "Aggiungi Script agli Strumenti..." per registrarlo
(o "Apri Script Esistente" + Esegui, se preferisci ricaricarlo cosi').

COME USARLO
-----------
Lancia lo strumento "Esporta P10-P50-P90 + differenza" dal Processing
Toolbox, indica i tre raster P10/P50/P90, gli shapefile opzionali
(pozzi, lago), la cartella di output e le due rampe colore (una per
P10/P50/P90, una divergente per la differenza).
===========================================================================
"""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsRasterLayer,
    QgsRasterShader,
    QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer,
    QgsStyle,
    QgsSimpleMarkerSymbolLayer,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsMapSettings,
    QgsMapRendererCustomPainterJob,
    QgsRectangle,
    QgsWkbTypes,
    QgsUnitTypes,
)
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter


class EsportaP10P50P90(QgsProcessingAlgorithm):

    RASTER_P10 = "RASTER_P10"
    RASTER_P50 = "RASTER_P50"
    RASTER_P90 = "RASTER_P90"
    RASTER_DIFF = "RASTER_DIFF"
    SHAPEFILE_POZZI = "SHAPEFILE_POZZI"
    SHAPEFILE_LAGO = "SHAPEFILE_LAGO"
    OUTPUT_DIR = "OUTPUT_DIR"
    RAMPA_NOME = "RAMPA_NOME"
    INVERTI_RAMPA = "INVERTI_RAMPA"
    RAMPA_DIVERGENTE = "RAMPA_DIVERGENTE"
    INVERTI_RAMPA_DIVERGENTE = "INVERTI_RAMPA_DIVERGENTE"
    LARGHEZZA_PX = "LARGHEZZA_PX"
    ALTEZZA_PX = "ALTEZZA_PX"
    MOSTRA_LETTERA_SINGOLI = "MOSTRA_LETTERA_SINGOLI"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER_P10, "Raster P10"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER_P50, "Raster P50"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER_P90, "Raster P90"))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.RASTER_DIFF,
            "Raster P90-P10 gia' calcolato (opzionale: se lo indichi, "
            "lo script lo usa direttamente invece di ricalcolarlo)",
            optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SHAPEFILE_POZZI, "Shapefile pozzi (opzionale)", optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SHAPEFILE_LAGO, "Shapefile lago di Bracciano (opzionale)", optional=True))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_DIR, "Cartella di output"))
        self.addParameter(QgsProcessingParameterString(
            self.RAMPA_NOME,
            "Rampa colore per P10/P50/P90 (nome da QGIS Style Manager)",
            defaultValue="Spectral"))
        self.addParameter(QgsProcessingParameterBoolean(
            self.INVERTI_RAMPA, "Inverti rampa P10/P50/P90",
            defaultValue=False))
        self.addParameter(QgsProcessingParameterString(
            self.RAMPA_DIVERGENTE,
            "Rampa colore DIVERGENTE per P90-P10 (es. RdBu)",
            defaultValue="RdBu"))
        self.addParameter(QgsProcessingParameterBoolean(
            self.INVERTI_RAMPA_DIVERGENTE, "Inverti rampa differenza",
            defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.LARGHEZZA_PX, "Larghezza singolo pannello (px)",
            type=QgsProcessingParameterNumber.Integer, defaultValue=900))
        self.addParameter(QgsProcessingParameterNumber(
            self.ALTEZZA_PX, "Altezza singolo pannello (px)",
            type=QgsProcessingParameterNumber.Integer, defaultValue=900))
        self.addParameter(QgsProcessingParameterBoolean(
            self.MOSTRA_LETTERA_SINGOLI,
            "Includi la lettera identificativa (es. 'a)') nei pannelli "
            "singoli esportati",
            defaultValue=True))

    def name(self):
        return "esporta_p10_p50_p90"

    def displayName(self):
        return "Esporta P10-P50-P90 + differenza"

    def group(self):
        return "Tesi - Kriging"

    def groupId(self):
        return "tesi_kriging"

    def createInstance(self):
        return EsportaP10P50P90()

    def flags(self):
        from qgis.core import QgsProcessingAlgorithm as _A
        return super().flags() | _A.FlagNoThreading

    # ------------------------------------------------------------------
    def carica_font(self, ImageFont, dimensione, grassetto=False):
        candidati = (
            ["arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if grassetto else
            ["arial.ttf", "calibri.ttf", "DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
        for nome in candidati:
            try:
                return ImageFont.truetype(nome, dimensione)
            except Exception:
                continue
        try:
            return ImageFont.load_default(size=dimensione)
        except TypeError:
            return ImageFont.load_default()

    # ------------------------------------------------------------------
    def applica_stile(self, layer, vmin, vmax, nome_rampa, inverti, feedback=None):
        shader = QgsRasterShader()
        style_mgr = QgsStyle().defaultStyle()
        color_ramp = style_mgr.colorRamp(nome_rampa)
        rampa_effettiva = nome_rampa
        if color_ramp is None:
            if feedback is not None:
                feedback.pushWarning(
                    f"Rampa '{nome_rampa}' non trovata in QGIS Style "
                    "Manager: uso 'Spectral' come fallback. Controlla "
                    "il nome esatto (case-sensitive) in Impostazioni "
                    "-> Stili.")
            color_ramp = style_mgr.colorRamp("Spectral")
            rampa_effettiva = "Spectral (fallback)"
        if inverti:
            color_ramp = color_ramp.clone()
            color_ramp.invert()
            rampa_effettiva += " (invertita)"
        if feedback is not None:
            feedback.pushInfo(
                f"Rampa applicata a '{layer.name()}': {rampa_effettiva}")
        color_ramp_shader = QgsColorRampShader(vmin, vmax, color_ramp)
        color_ramp_shader.setColorRampType(QgsColorRampShader.Interpolated)
        color_ramp_shader.classifyColorRamp()
        shader.setRasterShaderFunction(color_ramp_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        renderer.setClassificationMin(vmin)
        renderer.setClassificationMax(vmax)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    def crea_pannello_singolo_annotato(self, ImageModule, ImageDraw, percorso_pannello,
                                        percorso_output, larghezza, altezza, lettera,
                                        titolo, vmin, vmax, lut_colori, font, font_small,
                                        pozzi_layer=None, lago_layer=None,
                                        etichetta_scala="Valore", metri_per_pixel=None,
                                        mostra_lettera=True):
        """Crea, a partire dal PNG grezzo di un pannello, una versione
        completa e autonoma (titolo, freccia Nord, barra di scala,
        legenda colore e, opzionalmente, lettera identificativa)
        pronta per essere inserita da sola nel testo, senza dover fare
        riferimento alla figura multipannello.

        La barra di scala e la lettera (se richiesta con
        'mostra_lettera') condividono la stessa striscia sotto
        l'immagine: la barra resta allineata a sinistra, la lettera
        centrata, esattamente come nella figura multipannello."""
        pannello = ImageModule.open(percorso_pannello).convert("RGB")
        dummy = ImageModule.new("RGB", (10, 10))
        dcalc = ImageDraw.Draw(dummy)

        def largh_testo(t, f):
            b = dcalc.textbbox((0, 0), t, font=f)
            return b[2] - b[0]

        def alt_testo(t, f):
            b = dcalc.textbbox((0, 0), t, font=f)
            return b[3] - b[1]

        dim_font_titolo = font.size if hasattr(font, "size") else 40
        dim_font_piccolo = font_small.size if hasattr(font_small, "size") else 30
        padding = int(dim_font_piccolo * 0.6)
        spessore_barra = max(25, int(dim_font_piccolo * 1.1))
        h_font_piccolo = alt_testo("Ag", font_small)
        gap_piccolo = int(h_font_piccolo * 0.5)

        testi = [f"{vmax:.2f}", f"{vmin:.2f}", etichetta_scala]
        if pozzi_layer is not None:
            testi.append("Pozzi")
        if lago_layer is not None:
            testi.append("Lago di Bracciano")
        largh_legenda_testo = max([largh_testo(t, font_small) for t in testi] or [0])
        legenda_w = spessore_barra + padding * 3 + largh_legenda_testo

        titolo_h = max(70, int(dim_font_titolo * 1.8))
        lettera_h = max(30, int(h_font_piccolo * 1.7))

        # altezza della striscia sotto l'immagine: deve contenere la
        # barra di scala (se disponibile) e/o la lettera (se richiesta);
        # se nessuna delle due e' richiesta, la striscia si azzera
        blocco_scala_h = self._altezza_blocco_barra_scala(font_small, h_font_piccolo)
        componenti_striscia = []
        if metri_per_pixel and metri_per_pixel > 0:
            componenti_striscia.append(blocco_scala_h)
        if mostra_lettera:
            componenti_striscia.append(lettera_h)
        striscia_inferiore_h = max(componenti_striscia) if componenti_striscia else 0

        n_voci_shape = int(pozzi_layer is not None) + int(lago_layer is not None)
        altezza_barra = max(120, int(altezza * 0.30))
        contenuto_legenda_h = (
            padding + h_font_piccolo + gap_piccolo + altezza_barra
            + gap_piccolo + h_font_piccolo + gap_piccolo + h_font_piccolo
            + int(h_font_piccolo * 1.3) + n_voci_shape * int(h_font_piccolo * 2.2)
            + padding)

        larghezza_totale = larghezza + legenda_w
        altezza_totale = titolo_h + max(altezza + striscia_inferiore_h, contenuto_legenda_h)

        canvas = ImageModule.new("RGB", (larghezza_totale, altezza_totale), "white")
        draw = ImageDraw.Draw(canvas)

        draw.text((larghezza // 2, titolo_h // 2), titolo, fill="black",
                   font=font, anchor="mm")
        canvas.paste(pannello, (0, titolo_h))
        self.disegna_freccia_nord(draw, 0, titolo_h, larghezza, altezza, font_small)

        y0_striscia = titolo_h + altezza
        if mostra_lettera:
            self.disegna_lettera_sotto_pannello(
                draw, 0, y0_striscia + striscia_inferiore_h // 2, larghezza,
                lettera, font_small)
        if metri_per_pixel and metri_per_pixel > 0:
            y_top_scala = y0_striscia + (striscia_inferiore_h - blocco_scala_h) // 2
            self.disegna_barra_scala(draw, 0, y_top_scala, larghezza,
                                      metri_per_pixel, font_small, h_font_piccolo)

        leg_x0 = larghezza + padding
        y = titolo_h + padding
        draw.text((leg_x0, y), f"{vmax:.2f}", fill="black", font=font_small)
        y += h_font_piccolo + gap_piccolo
        barra_y0 = y
        barra_y1 = y + altezza_barra
        for yy in range(barra_y0, barra_y1):
            t = (yy - barra_y0) / (barra_y1 - barra_y0)
            idx = int(round((1 - t) * (len(lut_colori) - 1)))
            draw.line([(leg_x0, yy), (leg_x0 + spessore_barra, yy)], fill=lut_colori[idx])
        y = barra_y1 + gap_piccolo
        draw.text((leg_x0, y), f"{vmin:.2f}", fill="black", font=font_small)
        y += h_font_piccolo + gap_piccolo
        draw.text((leg_x0, y), etichetta_scala, fill="black", font=font_small)
        y += h_font_piccolo + int(h_font_piccolo * 1.3)

        raggio = max(4, int(dim_font_piccolo * 0.3))
        if pozzi_layer is not None:
            cx, cy = leg_x0 + raggio, y + h_font_piccolo // 2
            draw.ellipse([cx - raggio, cy - raggio, cx + raggio, cy + raggio],
                         fill=(0, 0, 0), outline=(255, 255, 255))
            draw.text((leg_x0 + raggio * 3, cy), "Pozzi",
                      fill="black", font=font_small, anchor="lm")
            y += int(h_font_piccolo * 2.2)
        if lago_layer is not None:
            cy = y + h_font_piccolo // 2
            draw.line([(leg_x0, cy), (leg_x0 + raggio * 2, cy)],
                       fill=(30, 60, 200), width=3)
            draw.text((leg_x0 + raggio * 3, cy), "Lago di Bracciano",
                      fill="black", font=font_small, anchor="lm")

        canvas.save(percorso_output)

    # ------------------------------------------------------------------
    def disegna_freccia_nord(self, draw, x0, y0, larghezza_p, altezza_p,
                              font_lettera):
        """Disegna nell'angolo in alto a destra del pannello una
        freccia Nord (senza sfondo), con l'etichetta 'N'.
        L'INGOMBRO TOTALE (lettera + triangolo) viene calcolato prima,
        poi l'intero blocco viene forzato (clampato) dentro i confini
        [x0, x0+larghezza_p] x [y0, y0+altezza_p]: questo garantisce
        che la freccia resti sempre visibile dentro il pannello, anche
        se le metriche del font di sistema (Windows/Linux) differiscono
        da quelle previste."""
        dim_freccia = max(24, int(min(larghezza_p, altezza_p) * 0.055))
        margine = max(14, int(dim_freccia * 0.8))
        larghezza_base = dim_freccia * 0.6

        n_bbox = draw.textbbox((0, 0), "N", font=font_lettera)
        n_w = n_bbox[2] - n_bbox[0]
        n_h = n_bbox[3] - n_bbox[1]
        gap = max(2, int(dim_freccia * 0.12))

        # ingombro totale del blocco (lettera + gap + triangolo)
        blocco_larghezza = larghezza_base
        blocco_altezza = n_h + gap + dim_freccia * 0.9

        # posizione desiderata (in alto a destra, con margine)
        blocco_x0 = x0 + larghezza_p - margine - blocco_larghezza
        blocco_y0 = y0 + margine

        # CLAMP: costringo il blocco dentro i confini del pannello,
        # qualunque cosa succeda con le metriche del font
        blocco_x0 = max(x0 + 2, min(blocco_x0, x0 + larghezza_p - blocco_larghezza - 2))
        blocco_y0 = max(y0 + 2, min(blocco_y0, y0 + altezza_p - blocco_altezza - 2))

        cx = blocco_x0 + blocco_larghezza / 2
        y_n_top = blocco_y0
        draw.text((cx - n_w / 2, y_n_top - n_bbox[1]), "N",
                   fill="black", font=font_lettera)

        y_tri_top = y_n_top + n_h + gap
        punta = (cx, y_tri_top)
        sinistra = (cx - larghezza_base / 2, y_tri_top + dim_freccia * 0.9)
        destra = (cx + larghezza_base / 2, y_tri_top + dim_freccia * 0.9)
        centro_base = (cx, y_tri_top + dim_freccia * 0.55)
        draw.polygon([punta, sinistra, centro_base], fill=(0, 0, 0))
        draw.polygon([punta, centro_base, destra], fill=(255, 255, 255),
                     outline=(0, 0, 0))

    # ------------------------------------------------------------------
    def disegna_lettera_sotto_pannello(self, draw, x0, y_centro_striscia,
                                        larghezza_p, lettera, font_lettera):
        """Disegna la lettera identificativa del pannello (es. 'a)')
        centrata SOTTO il pannello, come testo semplice senza riquadro."""
        testo = f"{lettera})"
        cx = x0 + larghezza_p / 2
        draw.text((cx, y_centro_striscia), testo, fill="black",
                   font=font_lettera, anchor="mm")

    # ------------------------------------------------------------------
    def _arrotonda_valore_carino(self, valore):
        """Arrotonda 'valore' al numero piu' vicino della sequenza
        1-2-5-10-20-50-100... (come nelle barre di scala cartografiche),
        cosi' l'etichetta della barra di scala e' sempre un numero
        leggibile (es. 5, 10, 20 km) e non un valore arbitrario."""
        import math
        if valore <= 0:
            return 1.0
        esponente = math.floor(math.log10(valore))
        frazione = valore / (10 ** esponente)
        if frazione < 1.5:
            base = 1
        elif frazione < 3.5:
            base = 2
        elif frazione < 7.5:
            base = 5
        else:
            base = 10
        return base * (10 ** esponente)

    def _formatta_km(self, valore):
        """Formatta un valore in km senza decimali inutili (5 invece
        di 5.0), ma mantiene un decimale se serve (es. 2.5)."""
        if valore == int(valore):
            return str(int(valore))
        return f"{valore:.1f}"

    # ------------------------------------------------------------------
    def _altezza_blocco_barra_scala(self, font_piccolo, h_font_piccolo):
        """Altezza totale (etichette + barra) occupata dalla barra di
        scala. Usata sia per dimensionare la striscia sotto l'immagine
        sia, con gli stessi identici valori, per disegnarla davvero:
        cosi' lo spazio riservato e quello effettivamente usato
        coincidono sempre."""
        dim_font_piccolo = font_piccolo.size if hasattr(font_piccolo, "size") else 30
        altezza_barra = max(10, int(dim_font_piccolo * 0.5))
        gap_etichette = int(h_font_piccolo * 0.35)
        return h_font_piccolo + gap_etichette + altezza_barra

    def disegna_barra_scala(self, draw, x0, y_top, larghezza_p,
                             metri_per_pixel, font_piccolo, h_font_piccolo):
        """Disegna, a partire dall'angolo superiore sinistro (x0, y_top)
        dello spazio riservato SOTTO l'immagine, una barra di scala a
        doppia graduazione (meta' sinistra a passo dimezzato, meta'
        destra a passo intero, alternando nero/bianco) con le
        etichette SOPRA la barra, nello stile classico delle carte
        topografiche:

            U   0   U   2U km
          [##][  ][####][    ]

        La lunghezza dell'unita' U viene scelta automaticamente (valore
        "carino" 1-2-5-10-20-50...) in modo che la barra intera occupi
        circa il 28% della larghezza disponibile. Richiede
        'metri_per_pixel' (unita' mappa per pixel, assumendo un SR
        proiettato in metri, es. UTM): se non disponibile o invalido,
        non disegna nulla."""
        if not metri_per_pixel or metri_per_pixel <= 0:
            return

        larghezza_bersaglio_px = larghezza_p * 0.28
        km_bersaglio = (larghezza_bersaglio_px * metri_per_pixel) / 1000.0
        u_km_grezzo = km_bersaglio / 3.0
        u_km = self._arrotonda_valore_carino(u_km_grezzo)
        u_px = (u_km * 1000.0) / metri_per_pixel
        mezzo_u_px = u_px / 2.0

        dim_font_piccolo = font_piccolo.size if hasattr(font_piccolo, "size") else 30
        altezza_barra = max(10, int(dim_font_piccolo * 0.5))
        gap_etichette = int(h_font_piccolo * 0.35)
        margine_x = max(14, int(altezza_barra * 1.4))

        bx0 = x0 + margine_x
        by0 = y_top + h_font_piccolo + gap_etichette
        by1 = by0 + altezza_barra

        segmenti = [
            (bx0, bx0 + mezzo_u_px, (0, 0, 0)),
            (bx0 + mezzo_u_px, bx0 + u_px, (255, 255, 255)),
            (bx0 + u_px, bx0 + 2 * u_px, (0, 0, 0)),
            (bx0 + 2 * u_px, bx0 + 3 * u_px, (255, 255, 255)),
        ]
        for xa, xb, colore in segmenti:
            draw.rectangle([xa, by0, xb, by1], fill=colore,
                            outline=(0, 0, 0), width=1)

        etichette = [
            (bx0, self._formatta_km(u_km)),
            (bx0 + u_px, "0"),
            (bx0 + 2 * u_px, self._formatta_km(u_km)),
            (bx0 + 3 * u_px, f"{self._formatta_km(2 * u_km)} km"),
        ]
        for xe, testo in etichette:
            draw.text((xe, y_top), testo, fill="black",
                       font=font_piccolo, anchor="ma")

    # ------------------------------------------------------------------
    def campiona_colori_rampa(self, nome_rampa, inverti=False, n=256):
        ramp = QgsStyle().defaultStyle().colorRamp(nome_rampa)
        if ramp is None:
            ramp = QgsStyle().defaultStyle().colorRamp("Spectral")
        if inverti:
            ramp = ramp.clone()
            ramp.invert()
        colori = []
        for i in range(n):
            t = i / (n - 1)
            c = ramp.color(t)
            colori.append((c.red(), c.green(), c.blue()))
        return colori

    # ------------------------------------------------------------------
    def stile_pozzi(self, layer):
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        marker = QgsSimpleMarkerSymbolLayer()
        marker.setShape(QgsSimpleMarkerSymbolLayer.Circle)
        marker.setColor(QColor(0, 0, 0))
        marker.setStrokeColor(QColor(255, 255, 255))
        marker.setSize(2.6)
        symbol.changeSymbolLayer(0, marker)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    def stile_lago(self, layer):
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol_layer = symbol.symbolLayer(0)
        if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            symbol.setColor(QColor(0, 0, 0, 0))
            symbol_layer.setStrokeColor(QColor(30, 60, 200))
            symbol_layer.setStrokeWidth(0.6)
        else:
            symbol_layer.setColor(QColor(30, 60, 200))
            symbol_layer.setWidth(0.6)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    def esporta_pannello(self, raster_layer, layer_vettoriali, estensione,
                          larghezza, altezza, out_path):
        layers = list(layer_vettoriali) + [raster_layer]
        ms = QgsMapSettings()
        ms.setLayers(layers)
        ms.setBackgroundColor(QColor(255, 255, 255))
        ms.setOutputSize(QSize(larghezza, altezza))
        ms.setExtent(estensione)

        img = QImage(QSize(larghezza, altezza), QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255).rgb())
        painter = QPainter(img)
        job = QgsMapRendererCustomPainterJob(ms, painter)
        job.start()
        job.waitForFinished()
        painter.end()
        img.save(out_path, "PNG")

    # ------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        p10 = self.parameterAsRasterLayer(parameters, self.RASTER_P10, context)
        p50 = self.parameterAsRasterLayer(parameters, self.RASTER_P50, context)
        p90 = self.parameterAsRasterLayer(parameters, self.RASTER_P90, context)
        diff_layer_fornito = self.parameterAsRasterLayer(parameters, self.RASTER_DIFF, context)
        pozzi_layer = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_POZZI, context)
        lago_layer = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_LAGO, context)
        out_dir = self.parameterAsString(parameters, self.OUTPUT_DIR, context)
        nome_rampa = self.parameterAsString(parameters, self.RAMPA_NOME, context)
        inverti_rampa = self.parameterAsBool(parameters, self.INVERTI_RAMPA, context)
        nome_rampa_div = self.parameterAsString(parameters, self.RAMPA_DIVERGENTE, context)
        inverti_rampa_div = self.parameterAsBool(
            parameters, self.INVERTI_RAMPA_DIVERGENTE, context)
        larghezza = self.parameterAsInt(parameters, self.LARGHEZZA_PX, context)
        altezza = self.parameterAsInt(parameters, self.ALTEZZA_PX, context)
        mostra_lettera_singoli = self.parameterAsBool(
            parameters, self.MOSTRA_LETTERA_SINGOLI, context)

        os.makedirs(out_dir, exist_ok=True)

        # --- 1. min/max condivisi su P10/P50/P90 ---
        vmin, vmax = None, None
        for lyr in (p10, p50, p90):
            stats = lyr.dataProvider().bandStatistics(1)
            vmin = stats.minimumValue if vmin is None else min(vmin, stats.minimumValue)
            vmax = stats.maximumValue if vmax is None else max(vmax, stats.maximumValue)
        feedback.pushInfo(f"Min/Max condivisi P10-P50-P90: {vmin:.3f} / {vmax:.3f}")

        # --- 2. raster differenza P90 - P10: uso quello fornito
        # dall'utente se presente, altrimenti lo calcolo ---
        estensione = QgsRectangle(p90.extent())
        estensione.combineExtentWith(p10.extent())
        estensione.combineExtentWith(p50.extent())

        # metri (unita' mappa) per pixel, usati per la barra di scala
        # dei pannelli singoli: valido se il SR e' proiettato in metri
        # (es. EPSG:23033 - ED50 / UTM zone 33N, usato in questo progetto)
        metri_per_pixel = estensione.width() / larghezza if larghezza else None

        if p90.crs().mapUnits() != QgsUnitTypes.DistanceMeters:
            feedback.pushWarning(
                f"Il SR di P90 ({p90.crs().authid()}) non ha unita' in "
                "metri: la barra di scala dei pannelli singoli potrebbe "
                "non essere corretta.")

        if diff_layer_fornito is not None:
            feedback.pushInfo(
                f"Uso il raster P90-P10 gia' fornito: "
                f"{diff_layer_fornito.source()}")
            diff_layer = diff_layer_fornito
            estensione.combineExtentWith(diff_layer.extent())
        else:
            percorso_diff = os.path.join(out_dir, "differenza_p90_p10.tif")
            entry_p90 = QgsRasterCalculatorEntry()
            entry_p90.ref = "p90@1"
            entry_p90.raster = p90
            entry_p90.bandNumber = 1
            entry_p10 = QgsRasterCalculatorEntry()
            entry_p10.ref = "p10@1"
            entry_p10.raster = p10
            entry_p10.bandNumber = 1

            calc = QgsRasterCalculator(
                "p90@1 - p10@1", percorso_diff, "GTiff",
                estensione, p90.width(), p90.height(),
                [entry_p90, entry_p10])
            risultato = calc.processCalculation()
            if risultato != 0:
                feedback.reportError(
                    "Errore nel calcolo della differenza P90-P10 "
                    f"(codice {risultato}). Controlla che i raster P10/P90 "
                    "abbiano stessa estensione e risoluzione, oppure genera "
                    "tu il raster differenza e forniscilo direttamente nel "
                    "campo 'Raster P90-P10 gia' calcolato'.")
                return {self.OUTPUT_DIR: out_dir}
            feedback.pushInfo(f"Raster differenza salvato in: {percorso_diff}")
            diff_layer = QgsRasterLayer(percorso_diff, "differenza")

        stats_diff = diff_layer.dataProvider().bandStatistics(1)
        k = max(abs(stats_diff.minimumValue), abs(stats_diff.maximumValue))
        vmin_diff, vmax_diff = -k, k
        feedback.pushInfo(f"Scala divergente differenza: -{k:.3f} / +{k:.3f}")

        # includo l'estensione del lago, se presente
        if lago_layer is not None:
            estensione.combineExtentWith(lago_layer.extent())

        # --- 3. stile ---
        self.applica_stile(p10, vmin, vmax, nome_rampa, inverti_rampa, feedback)
        self.applica_stile(p50, vmin, vmax, nome_rampa, inverti_rampa, feedback)
        self.applica_stile(p90, vmin, vmax, nome_rampa, inverti_rampa, feedback)
        self.applica_stile(diff_layer, vmin_diff, vmax_diff,
                            nome_rampa_div, inverti_rampa_div, feedback)

        layer_vettoriali = []
        if pozzi_layer is not None:
            self.stile_pozzi(pozzi_layer)
            layer_vettoriali.append(pozzi_layer)
        if lago_layer is not None:
            self.stile_lago(lago_layer)
            layer_vettoriali.append(lago_layer)

        # --- 4. esporto i 4 pannelli ---
        pannelli = [("P10", p10), ("P50", p50), ("P90", p90),
                    ("P90 - P10", diff_layer)]
        percorsi = {}
        for i, (nome, lyr) in enumerate(pannelli):
            if feedback.isCanceled():
                break
            out_path = os.path.join(out_dir, f"pannello_{nome}.png".replace(" ", "_"))
            self.esporta_pannello(lyr, layer_vettoriali, estensione,
                                   larghezza, altezza, out_path)
            percorsi[nome] = out_path
            feedback.setProgress(int(100 * (i + 1) / 4))
            feedback.pushInfo(f"Esportato: {out_path}")

        # --- 5. composizione finale con Pillow ---
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            feedback.pushWarning(
                "Pillow non installato: i pannelli singoli sono stati "
                "esportati ma la composizione finale e' stata saltata.")
            return {self.OUTPUT_DIR: out_dir}

        dim_font_titolo = max(48, int(min(larghezza, altezza) * 0.07))
        dim_font_piccolo = max(36, int(min(larghezza, altezza) * 0.05))
        font = self.carica_font(ImageFont, dim_font_titolo, grassetto=True)
        font_small = self.carica_font(ImageFont, dim_font_piccolo, grassetto=False)

        dummy = Image.new("RGB", (10, 10))
        dcalc = ImageDraw.Draw(dummy)

        def larghezza_testo(testo, f):
            bbox = dcalc.textbbox((0, 0), testo, font=f)
            return bbox[2] - bbox[0]

        padding = int(dim_font_piccolo * 0.6)
        spessore_barra = max(25, int(dim_font_piccolo * 1.1))

        testi_1 = [f"{vmax:.2f}", f"{vmin:.2f}"]
        testi_2 = [f"{vmax_diff:.2f}", f"{vmin_diff:.2f}", "0.00"]
        if pozzi_layer is not None:
            testi_1.append("Pozzi")
        if lago_layer is not None:
            testi_1.append("Lago di Bracciano")
        larghezza_leg1 = max([larghezza_testo(t, font_small) for t in testi_1] or [0])
        larghezza_leg2 = max([larghezza_testo(t, font_small) for t in testi_2] or [0])
        legenda_w = spessore_barra + padding * 3 + max(larghezza_leg1, larghezza_leg2)

        etichetta_h = max(80, int(dim_font_titolo * 1.8))
        lettera_h = max(30, int(dim_font_piccolo * 1.7))

        n_pannelli = 4
        larghezza_totale = n_pannelli * larghezza + legenda_w
        altezza_totale = etichetta_h + altezza + lettera_h

        griglia = Image.new("RGB", (larghezza_totale, altezza_totale), "white")
        draw = ImageDraw.Draw(griglia)

        import string
        lettere = string.ascii_lowercase
        lut1 = self.campiona_colori_rampa(nome_rampa, inverti_rampa, n=256)
        lut2 = self.campiona_colori_rampa(nome_rampa_div, inverti_rampa_div, n=256)
        for i, (nome, _) in enumerate(pannelli):
            x = i * larghezza + larghezza // 2
            draw.text((x, etichetta_h // 2), nome, fill="black",
                       font=font, anchor="mm")
            pannello = Image.open(percorsi[nome])
            x0 = i * larghezza
            griglia.paste(pannello, (x0, etichetta_h))
            self.disegna_freccia_nord(draw, x0, etichetta_h, larghezza, altezza, font_small)
            self.disegna_lettera_sotto_pannello(
                draw, x0, etichetta_h + altezza + lettera_h // 2, larghezza,
                lettere[i], font_small)

            # versione standalone del singolo pannello: usa la scala
            # lineare condivisa per P10/P50/P90, quella divergente per
            # il pannello differenza
            e_diff = (nome == "P90 - P10")
            v_min_p = vmin_diff if e_diff else vmin
            v_max_p = vmax_diff if e_diff else vmax
            lut_p = lut2 if e_diff else lut1
            etichetta_p = "P90 - P10" if e_diff else "P10 / P50 / P90"
            percorso_annotato = os.path.join(
                out_dir, f"pannello_{nome}_singolo.png".replace(" ", "_"))
            self.crea_pannello_singolo_annotato(
                Image, ImageDraw, percorsi[nome], percorso_annotato,
                larghezza, altezza, lettere[i], nome,
                v_min_p, v_max_p, lut_p, font, font_small,
                pozzi_layer, lago_layer, etichetta_p, metri_per_pixel,
                mostra_lettera_singoli)

        # legenda 1: scala lineare P10/P50/P90 (sotto i primi 3 pannelli,
        # mostrata come barra verticale a destra dei primi tre)
        leg_x0 = n_pannelli * larghezza + padding
        alt_barra = int((altezza_totale - etichetta_h - 80) * 0.42)
        leg1_y0 = etichetta_h + 20
        leg1_y1 = leg1_y0 + alt_barra
        for y in range(leg1_y0, leg1_y1):
            t = (y - leg1_y0) / (leg1_y1 - leg1_y0)
            idx = int(round((1 - t) * (len(lut1) - 1)))
            draw.line([(leg_x0, y), (leg_x0 + spessore_barra, y)], fill=lut1[idx])
        draw.text((leg_x0, leg1_y0 - dim_font_piccolo - 5), f"{vmax:.2f}",
                   fill="black", font=font_small)
        draw.text((leg_x0, leg1_y1 + 5), f"{vmin:.2f}",
                   fill="black", font=font_small)
        draw.text((leg_x0, leg1_y1 + dim_font_piccolo + 30), "P10 / P50 / P90",
                   fill="black", font=font_small)

        # legenda 2: scala divergente differenza (sotto la prima)
        lut2 = self.campiona_colori_rampa(nome_rampa_div, inverti_rampa_div, n=256)
        leg2_y0 = leg1_y1 + dim_font_piccolo * 2 + 60
        leg2_y1 = leg2_y0 + alt_barra
        for y in range(leg2_y0, leg2_y1):
            t = (y - leg2_y0) / (leg2_y1 - leg2_y0)
            idx = int(round((1 - t) * (len(lut2) - 1)))
            draw.line([(leg_x0, y), (leg_x0 + spessore_barra, y)], fill=lut2[idx])
        draw.text((leg_x0, leg2_y0 - dim_font_piccolo - 5), f"{vmax_diff:.2f}",
                   fill="black", font=font_small)
        draw.text((leg_x0, leg2_y1 + 5), f"{vmin_diff:.2f}",
                   fill="black", font=font_small)
        draw.text((leg_x0, leg2_y1 + dim_font_piccolo + 30), "P90 - P10",
                   fill="black", font=font_small)

        # legenda simboli shapefile, sotto le due barre
        y_shape = leg2_y1 + dim_font_piccolo * 2 + 70
        raggio = max(4, int(dim_font_piccolo * 0.3))
        if pozzi_layer is not None:
            cx, cy = leg_x0 + raggio, y_shape
            draw.ellipse([cx - raggio, cy - raggio, cx + raggio, cy + raggio],
                         fill=(0, 0, 0), outline=(255, 255, 255))
            draw.text((leg_x0 + raggio * 3, cy), "Pozzi",
                      fill="black", font=font_small, anchor="lm")
            y_shape += int(dim_font_piccolo * 2.2)
        if lago_layer is not None:
            draw.line([(leg_x0, y_shape), (leg_x0 + raggio * 2, y_shape)],
                       fill=(30, 60, 200), width=3)
            draw.text((leg_x0 + raggio * 3, y_shape), "Lago di Bracciano",
                      fill="black", font=font_small, anchor="lm")

        out_finale = os.path.join(out_dir, "p10_p50_p90_differenza.png")
        griglia.save(out_finale)
        feedback.pushInfo(f"Figura finale salvata in: {out_finale}")

        return {self.OUTPUT_DIR: out_dir}
