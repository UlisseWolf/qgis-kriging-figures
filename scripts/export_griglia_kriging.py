# -*- coding: utf-8 -*-
"""
export_griglia_kriging.py
===========================================================================
QGIS PROCESSING SCRIPT
Esporta una griglia multipannello (righe = range di variogramma,
colonne = modello: sferico / esponenziale / gaussiano) con:
  - min/max colore calcolati automaticamente sull'intero gruppo di raster
    (oppure impostati manualmente)
  - stesso stile (pseudocolore a banda singola) su tutti i pannelli
  - stessa estensione e stessa scala su tutti i pannelli
  - shapefile (es. pozzi) sovrapposto con simbologia identica
  - export PNG di ogni pannello
  - composizione automatica della griglia finale con etichette di riga
    (range) e di colonna (modello) e un'unica legenda condivisa

COME INSTALLARLO
-----------------
1. In QGIS: Processing -> Strumenti -> Script -> Apri cartella script
   (oppure Processing Toolbox -> icona Script -> "Aggiungi script dalla
   cartella script attiva")
2. Copia questo file nella cartella script di QGIS (di solito:
   Windows:  %APPDATA%\QGIS\QGIS3\profiles\default\processing\scripts
   Linux:    ~/.local/share/QGIS/QGIS3/profiles/default/processing/scripts
   macOS:    ~/Library/Application Support/QGIS/QGIS3/profiles/default/processing/scripts
3. Riavvia QGIS o fai clic destro su "Script" nel Processing Toolbox ->
   "Aggiorna script dalla cartella"
4. Lo script compare in Processing Toolbox come
   "Scripts -> Esporta griglia kriging (range x modello)"

COME USARLO
-----------
- Prepara un CSV di configurazione (vedi esempio sotto) con 3 colonne:
      riga;colonna;percorso_raster
  dove "riga" e "colonna" sono le etichette che vuoi mostrare
  (es. "10 m";"Sferico";"C:/dati/sph_10.tif")
- Lancia lo script dal Processing Toolbox, indica il CSV, lo shapefile
  dei pozzi (opzionale), la cartella di output e se vuoi min/max
  automatici o fissati manualmente.
- Al termine trovi nella cartella di output: un PNG per ogni pannello
  e un PNG finale "griglia_finale.png" con la matrice completa.

ESEMPIO DI CSV (separatore ;)
------------------------------
riga;colonna;percorso_raster
10 m;Sferico;C:/dati/sph_10.tif
10 m;Esponenziale;C:/dati/exp_10.tif
10 m;Gaussiano;C:/dati/gau_10.tif
500 m;Sferico;C:/dati/sph_500.tif
500 m;Esponenziale;C:/dati/exp_500.tif
500 m;Gaussiano;C:/dati/gau_500.tif
...
===========================================================================
"""

import csv
import os

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsProject,
    QgsMapSettings,
    QgsMapRendererCustomPainterJob,
    QgsRectangle,
    QgsRasterShader,
    QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer,
    QgsStyle,
    QgsSimpleMarkerSymbolLayer,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont


class EsportaGrigliaKriging(QgsProcessingAlgorithm):

    CSV_CONFIG = "CSV_CONFIG"
    SHAPEFILE_POZZI = "SHAPEFILE_POZZI"
    SHAPEFILE_LAGO = "SHAPEFILE_LAGO"
    OUTPUT_DIR = "OUTPUT_DIR"
    MIN_MANUALE = "MIN_MANUALE"
    MAX_MANUALE = "MAX_MANUALE"
    USA_MANUALE = "USA_MANUALE"
    LARGHEZZA_PX = "LARGHEZZA_PX"
    ALTEZZA_PX = "ALTEZZA_PX"
    RAMPA_NOME = "RAMPA_NOME"
    INVERTI_RAMPA = "INVERTI_RAMPA"
    MOSTRA_LETTERA_SINGOLI = "MOSTRA_LETTERA_SINGOLI"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.CSV_CONFIG, "CSV di configurazione (riga;colonna;percorso_raster)",
            extension="csv"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SHAPEFILE_POZZI, "Shapefile pozzi (opzionale)", optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SHAPEFILE_LAGO, "Shapefile lago di Bracciano (opzionale)",
            optional=True))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_DIR, "Cartella di output"))
        self.addParameter(QgsProcessingParameterBoolean(
            self.USA_MANUALE, "Usa min/max manuali invece che automatici",
            defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_MANUALE, "Min manuale (se attivato sopra)",
            type=QgsProcessingParameterNumber.Double, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_MANUALE, "Max manuale (se attivato sopra)",
            type=QgsProcessingParameterNumber.Double, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.LARGHEZZA_PX, "Larghezza singolo pannello (px)",
            type=QgsProcessingParameterNumber.Integer, defaultValue=900))
        self.addParameter(QgsProcessingParameterNumber(
            self.ALTEZZA_PX, "Altezza singolo pannello (px)",
            type=QgsProcessingParameterNumber.Integer, defaultValue=700))
        self.addParameter(QgsProcessingParameterString(
            self.RAMPA_NOME,
            "Nome rampa colore (deve esistere in QGIS Style Manager, "
            "es. Spectral, RdYlGn, Terrain, RdYlBu, Viridis...)",
            defaultValue="Spectral"))
        self.addParameter(QgsProcessingParameterBoolean(
            self.INVERTI_RAMPA, "Inverti la rampa colore",
            defaultValue=False))
        self.addParameter(QgsProcessingParameterBoolean(
            self.MOSTRA_LETTERA_SINGOLI,
            "Includi la lettera identificativa (es. 'a)') nei pannelli "
            "singoli esportati",
            defaultValue=True))

    def name(self):
        return "esporta_griglia_kriging"

    def displayName(self):
        return "Esporta griglia kriging (range x modello)"

    def group(self):
        return "Tesi - Kriging"

    def groupId(self):
        return "tesi_kriging"

    def createInstance(self):
        return EsportaGrigliaKriging()

    def flags(self):
        # Il rendering di mappe (QPainter/QImage) richiede il thread
        # principale di QGIS: eseguire questo script in un thread in
        # background puo' causare il crash dell'intera applicazione.
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

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
    def leggi_csv(self, path):
        righe_ordine = []
        colonne_ordine = []
        celle = {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for r in reader:
                riga = r["riga"].strip()
                colonna = r["colonna"].strip()
                raster_path = r["percorso_raster"].strip()
                if riga not in righe_ordine:
                    righe_ordine.append(riga)
                if colonna not in colonne_ordine:
                    colonne_ordine.append(colonna)
                celle[(riga, colonna)] = raster_path
        return righe_ordine, colonne_ordine, celle

    # ------------------------------------------------------------------
    def calcola_min_max_globali(self, celle, feedback):
        vmin, vmax = None, None
        for path in celle.values():
            lyr = QgsRasterLayer(path, "tmp")
            if not lyr.isValid():
                feedback.pushWarning(f"Raster non valido: {path}")
                continue
            stats = lyr.dataProvider().bandStatistics(1)
            if vmin is None or stats.minimumValue < vmin:
                vmin = stats.minimumValue
            if vmax is None or stats.maximumValue > vmax:
                vmax = stats.maximumValue
        return vmin, vmax

    # ------------------------------------------------------------------
    def campiona_colori_rampa(self, nome_rampa, inverti, n=256):
        """Restituisce n colori (r,g,b) campionati lungo la rampa
        effettivamente usata sui raster, cosi' la legenda finale mostra
        i colori ESATTI e non un'approssimazione."""
        ramp = QgsStyle().defaultStyle().colorRamp(nome_rampa)
        if ramp is None:
            ramp = QgsStyle().defaultStyle().colorRamp("Viridis")
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
    def applica_stile(self, layer, vmin, vmax, nome_rampa, inverti):
        shader = QgsRasterShader()
        color_ramp = QgsStyle().defaultStyle().colorRamp(nome_rampa)
        if color_ramp is None:
            color_ramp = QgsStyle().defaultStyle().colorRamp("Viridis")
        if inverti:
            color_ramp.invert()
        color_ramp_shader = QgsColorRampShader(vmin, vmax, color_ramp)
        color_ramp_shader.setColorRampType(QgsColorRampShader.Interpolated)
        color_ramp_shader.classifyColorRamp()
        shader.setRasterShaderFunction(color_ramp_shader)
        renderer = QgsSingleBandPseudoColorRenderer(
            layer.dataProvider(), 1, shader)
        renderer.setClassificationMin(vmin)
        renderer.setClassificationMax(vmax)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

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

    # ------------------------------------------------------------------
    def stile_lago(self, layer):
        """Contorno del lago di Bracciano: solo bordo blu, ben visibile
        come riferimento geografico su ogni pannello. Gestisce sia il
        caso in cui lo shapefile sia un poligono (riempimento reso
        trasparente, si stila il bordo) sia il caso in cui sia una
        linea (si stila direttamente la linea)."""
        from qgis.core import QgsWkbTypes

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol_layer = symbol.symbolLayer(0)

        if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            symbol.setColor(QColor(0, 0, 0, 0))  # riempimento trasparente
            symbol_layer.setStrokeColor(QColor(30, 60, 200))
            symbol_layer.setStrokeWidth(0.6)
        else:
            # geometria lineare: si stila direttamente linea e spessore
            symbol_layer.setColor(QColor(30, 60, 200))
            symbol_layer.setWidth(0.6)

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    def esporta_pannello(self, raster_layer, layer_vettoriali, estensione,
                          larghezza, altezza, out_path):
        # In QgsMapSettings il primo layer della lista e' quello disegnato
        # piu' in alto: i pozzi devono stare sopra, il lago sotto (ma
        # sempre sopra al raster).
        layers = list(layer_vettoriali) + [raster_layer]

        ms = QgsMapSettings()
        ms.setLayers(layers)
        ms.setBackgroundColor(QColor(255, 255, 255))
        ms.setOutputSize(QSize(larghezza, altezza))
        ms.setExtent(estensione)

        img = QImage(QSize(larghezza, altezza), QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255).rgb())
        painter = QPainter(img)
        # Rendering sincrono: piu' stabile di ParallelJob+QEventLoop
        # quando eseguito dentro uno script Processing.
        job = QgsMapRendererCustomPainterJob(ms, painter)
        job.start()
        job.waitForFinished()
        painter.end()
        img.save(out_path, "PNG")

    # ------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        from qgis.core import QgsProcessingUtils

        csv_path = self.parameterAsFile(parameters, self.CSV_CONFIG, context)
        out_dir = self.parameterAsString(parameters, self.OUTPUT_DIR, context)
        usa_manuale = self.parameterAsBool(parameters, self.USA_MANUALE, context)
        larghezza = self.parameterAsInt(parameters, self.LARGHEZZA_PX, context)
        altezza = self.parameterAsInt(parameters, self.ALTEZZA_PX, context)
        nome_rampa = self.parameterAsString(parameters, self.RAMPA_NOME, context)
        inverti_rampa = self.parameterAsBool(parameters, self.INVERTI_RAMPA, context)
        mostra_lettera_singoli = self.parameterAsBool(
            parameters, self.MOSTRA_LETTERA_SINGOLI, context)
        pozzi_layer = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_POZZI, context)
        lago_layer = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_LAGO, context)

        os.makedirs(out_dir, exist_ok=True)

        righe_ordine, colonne_ordine, celle = self.leggi_csv(csv_path)
        feedback.pushInfo(f"Righe: {righe_ordine}")
        feedback.pushInfo(f"Colonne: {colonne_ordine}")

        # --- min/max ---
        if usa_manuale:
            vmin = self.parameterAsDouble(parameters, self.MIN_MANUALE, context)
            vmax = self.parameterAsDouble(parameters, self.MAX_MANUALE, context)
        else:
            vmin, vmax = self.calcola_min_max_globali(celle, feedback)
        feedback.pushInfo(f"Min/Max usati per TUTTI i pannelli: {vmin} / {vmax}")

        # --- estensione comune: unione di tutti i raster ---
        estensione = None
        for path in celle.values():
            lyr = QgsRasterLayer(path, "tmp")
            if not lyr.isValid():
                continue
            if estensione is None:
                estensione = QgsRectangle(lyr.extent())
            else:
                estensione.combineExtentWith(lyr.extent())

        # metri (unita' mappa) per pixel, usati per la barra di scala
        # dei pannelli singoli: valido se il SR e' proiettato in metri
        # (es. EPSG:23033 - ED50 / UTM zone 33N, usato in questo progetto)
        metri_per_pixel = (
            estensione.width() / larghezza
            if estensione is not None and larghezza else None)

        crs_riferimento = None
        for path in celle.values():
            lyr_tmp = QgsRasterLayer(path, "tmp")
            if lyr_tmp.isValid():
                crs_riferimento = lyr_tmp.crs()
                break
        if (crs_riferimento is not None
                and crs_riferimento.mapUnits() != QgsUnitTypes.DistanceMeters):
            feedback.pushWarning(
                f"Il SR dei raster ({crs_riferimento.authid()}) non ha "
                "unita' in metri: la barra di scala dei pannelli singoli "
                "potrebbe non essere corretta.")

        # In QgsMapSettings il primo layer della lista e' quello disegnato
        # piu' in alto: i pozzi devono stare sopra, il lago sotto (ma
        # sempre sopra al raster).
        layer_vettoriali = []
        if pozzi_layer is not None:
            self.stile_pozzi(pozzi_layer)
            layer_vettoriali.append(pozzi_layer)  # disegnato sopra
        if lago_layer is not None:
            self.stile_lago(lago_layer)
            layer_vettoriali.append(lago_layer)   # disegnato sotto i pozzi
            if estensione is not None:
                estensione.combineExtentWith(lago_layer.extent())

        # --- esporta ogni pannello ---
        percorsi_pannelli = {}
        totale = len(celle)
        for i, ((riga, colonna), raster_path) in enumerate(celle.items()):
            if feedback.isCanceled():
                break
            lyr = QgsRasterLayer(raster_path, f"{riga}_{colonna}")
            if not lyr.isValid():
                feedback.pushWarning(f"Salto raster non valido: {raster_path}")
                continue
            self.applica_stile(lyr, vmin, vmax, nome_rampa, inverti_rampa)
            nome_file = f"pannello_{riga}_{colonna}.png".replace(" ", "_")
            out_path = os.path.join(out_dir, nome_file)
            self.esporta_pannello(lyr, layer_vettoriali, estensione,
                                   larghezza, altezza, out_path)
            percorsi_pannelli[(riga, colonna)] = out_path
            feedback.setProgress(int(100 * (i + 1) / totale))
            feedback.pushInfo(f"Esportato: {out_path}")

        # --- composizione griglia finale con Pillow ---
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            feedback.pushWarning(
                "Pillow non installato: i pannelli singoli sono stati "
                "esportati ma la composizione finale è stata saltata. "
                "Installa Pillow nell'ambiente Python di QGIS "
                "(OSGeo4W Shell: pip install pillow) per ottenere "
                "automaticamente 'griglia_finale.png'.")
            return {self.OUTPUT_DIR: out_dir}

        def carica_font(dimensione, grassetto=False):
            """Prova diversi font di sistema (Windows/Linux/macOS).
            Se nessuno e' trovato, usa comunque un font bitmap ma
            RISPETTANDO la dimensione richiesta (Pillow >= 9.2), invece
            di ricadere silenziosamente su un font minuscolo fisso."""
            candidati = (
                ["arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "Arial Bold.ttf"]
                if grassetto else
                ["arial.ttf", "calibri.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "Arial.ttf"]
            )
            for nome in candidati:
                try:
                    return ImageFont.truetype(nome, dimensione)
                except Exception:
                    continue
            try:
                # Pillow >= 9.2: load_default accetta un parametro size
                return ImageFont.load_default(size=dimensione)
            except TypeError:
                return ImageFont.load_default()

        # font proporzionati alla dimensione del pannello, non fissi
        dim_font_titolo = max(48, int(min(larghezza, altezza) * 0.07))
        dim_font_piccolo = max(36, int(min(larghezza, altezza) * 0.05))
        font = carica_font(dim_font_titolo, grassetto=True)
        font_small = carica_font(dim_font_piccolo, grassetto=False)

        # --- misuro il testo REALE per dimensionare gli spazi, cosi'
        # nessuna etichetta viene tagliata, qualunque sia la lunghezza
        # dei nomi di riga/colonna o della rampa/shapefile scelti ---
        dummy_img = Image.new("RGB", (10, 10))
        dcalc = ImageDraw.Draw(dummy_img)

        def larghezza_testo(testo, f):
            bbox = dcalc.textbbox((0, 0), testo, font=f)
            return bbox[2] - bbox[0]

        padding_etichetta = int(dim_font_titolo * 0.6)
        larghezza_max_riga = max(
            [larghezza_testo(r, font) for r in righe_ordine] or [0])
        etichetta_w = max(120, larghezza_max_riga + 2 * padding_etichetta)

        etichetta_h = max(80, int(dim_font_titolo * 1.8))

        padding_legenda = int(dim_font_piccolo * 0.6)
        spessore_barra_stimato = max(25, int(dim_font_piccolo * 1.1))
        testi_legenda = [f"{vmax:.2f}", f"{vmin:.2f}"]
        if pozzi_layer is not None:
            testi_legenda.append("Pozzi")
        if lago_layer is not None:
            testi_legenda.append("Lago di Bracciano")
        larghezza_max_legenda = max(
            [larghezza_testo(t, font_small) for t in testi_legenda] or [0])
        legenda_w = (spessore_barra_stimato + padding_legenda * 2
                     + larghezza_max_legenda + padding_legenda)

        n_righe = len(righe_ordine)
        n_colonne = len(colonne_ordine)

        lettera_h = max(30, int(dim_font_piccolo * 1.7))
        riga_step = altezza + lettera_h

        larghezza_totale = etichetta_w + n_colonne * larghezza + legenda_w
        altezza_totale = etichetta_h + n_righe * riga_step

        griglia = Image.new("RGB", (larghezza_totale, altezza_totale), "white")
        draw = ImageDraw.Draw(griglia)
        feedback.pushInfo(
            f"Font titolo: {getattr(font, 'path', type(font).__name__)} "
            f"({dim_font_titolo}px) | Font piccolo: "
            f"{getattr(font_small, 'path', type(font_small).__name__)} "
            f"({dim_font_piccolo}px)")

        # etichette colonne (modelli)
        for c, nome_colonna in enumerate(colonne_ordine):
            x = etichetta_w + c * larghezza + larghezza // 2
            draw.text((x, etichetta_h // 2), nome_colonna, fill="black",
                       font=font, anchor="mm")

        # etichette righe (range) + incolla pannelli
        import string
        lettere = string.ascii_lowercase
        indice_lettera = 0
        lut_colori = self.campiona_colori_rampa(nome_rampa, inverti_rampa, n=256)
        for r, nome_riga in enumerate(righe_ordine):
            y = etichetta_h + r * riga_step + altezza // 2
            draw.text((etichetta_w // 2, y), nome_riga, fill="black",
                       font=font, anchor="mm")
            for c, nome_colonna in enumerate(colonne_ordine):
                chiave = (nome_riga, nome_colonna)
                if chiave not in percorsi_pannelli:
                    continue
                pannello = Image.open(percorsi_pannelli[chiave])
                x0 = etichetta_w + c * larghezza
                y0 = etichetta_h + r * riga_step
                griglia.paste(pannello, (x0, y0))
                lettera = (lettere[indice_lettera] if indice_lettera < 26
                           else lettere[indice_lettera // 26 - 1] + lettere[indice_lettera % 26])
                self.disegna_freccia_nord(draw, x0, y0, larghezza, altezza, font_small)
                self.disegna_lettera_sotto_pannello(
                    draw, x0, y0 + altezza + lettera_h // 2, larghezza,
                    lettera, font_small)

                # versione standalone del singolo pannello, pronta per
                # essere inserita da sola nel testo della tesi
                percorso_annotato = os.path.join(
                    out_dir, f"pannello_{nome_riga}_{nome_colonna}_singolo.png"
                    .replace(" ", "_"))
                self.crea_pannello_singolo_annotato(
                    Image, ImageDraw, percorsi_pannelli[chiave], percorso_annotato,
                    larghezza, altezza, lettera,
                    f"{nome_colonna} \u2014 {nome_riga}",
                    vmin, vmax, lut_colori, font, font_small,
                    pozzi_layer, lago_layer, "Valore", metri_per_pixel,
                    mostra_lettera_singoli)

                indice_lettera += 1

        # legenda condivisa (barra colore verticale) con i colori REALI
        # della rampa usata sui raster, non un'approssimazione
        # spazio extra sotto la barra colore per la legenda degli
        # shapefile (pozzi e lago), se presenti
        n_voci_shape = int(pozzi_layer is not None) + int(lago_layer is not None)
        spazio_legenda_shape = n_voci_shape * int(dim_font_piccolo * 2.2) + 20

        lut_colori = self.campiona_colori_rampa(nome_rampa, inverti_rampa, n=256)
        spessore_barra = spessore_barra_stimato
        legenda_x0 = larghezza_totale - legenda_w + padding_legenda
        legenda_y0 = etichetta_h + 20
        legenda_y1 = altezza_totale - 20 - spazio_legenda_shape
        n_step = len(lut_colori)
        for y in range(legenda_y0, legenda_y1):
            t = (y - legenda_y0) / (legenda_y1 - legenda_y0)  # 0=alto..1=basso
            # alto della barra = valore massimo -> indice n_step-1 della LUT
            idx = int(round((1 - t) * (n_step - 1)))
            r_, g_, b_ = lut_colori[idx]
            draw.line([(legenda_x0, y), (legenda_x0 + spessore_barra, y)],
                       fill=(r_, g_, b_))
        draw.text((legenda_x0, legenda_y0 - dim_font_piccolo - 5), f"{vmax:.2f}",
                   fill="black", font=font_small)
        draw.text((legenda_x0, legenda_y1 + 5), f"{vmin:.2f}",
                   fill="black", font=font_small)

        # --- legenda simboli shapefile (pozzi / lago) ---
        y_shape = legenda_y1 + dim_font_piccolo + 25
        passo = int(dim_font_piccolo * 2.2)
        raggio_pallino = max(4, int(dim_font_piccolo * 0.3))

        if pozzi_layer is not None:
            cy = y_shape
            cx = legenda_x0 + raggio_pallino
            draw.ellipse(
                [cx - raggio_pallino, cy - raggio_pallino,
                 cx + raggio_pallino, cy + raggio_pallino],
                fill=(0, 0, 0), outline=(255, 255, 255))
            draw.text((legenda_x0 + raggio_pallino * 3, cy),
                      "Pozzi", fill="black", font=font_small, anchor="lm")
            y_shape += passo

        if lago_layer is not None:
            cy = y_shape
            draw.line([(legenda_x0, cy), (legenda_x0 + raggio_pallino * 2, cy)],
                       fill=(30, 60, 200), width=3)
            draw.text((legenda_x0 + raggio_pallino * 3, cy),
                      "Lago di Bracciano", fill="black", font=font_small,
                      anchor="lm")
            y_shape += passo

        out_finale = os.path.join(out_dir, "griglia_finale.png")
        griglia.save(out_finale)
        feedback.pushInfo(f"Griglia finale salvata in: {out_finale}")

        return {self.OUTPUT_DIR: out_dir}
