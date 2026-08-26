import streamlit as st
import fitz
import re
import pandas as pd
import numpy as np


# ============================================================
# APP
# ============================================================

st.set_page_config(
    page_title="Temperature PDF",
    page_icon="🌡️",
    layout="wide"
)

st.title("🌡️ Temperature PDF")

st.write(
    "Upload en temperatur-rapport for at analysere "
    "og korrigere Temp1, Temp2 og Temp3."
)


# ============================================================
# PDF-LÆSNING
# ============================================================

uploaded_file = st.file_uploader(
    "Upload temperatur-PDF",
    type=["pdf"]
)


def extract_temperature_data(pdf_bytes):

    pdf = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    full_text = ""

    for page in pdf:
        full_text += page.get_text() + "\n"

    pattern = re.compile(
        r"(\d{2}-\d{2}-\d{4})\s+"
        r"(\d{2}:\d{2})\s+"
        r"([\d,]+)\s+S1:\s*15\s+"
        r"([\d,]+)\s+S2:\s*15\s+"
        r"([\d,]+)\s+S3:\s*15"
    )

    rows = []

    for match in pattern.finditer(full_text):

        dato = match.group(1)
        tid = match.group(2)

        temp1 = float(
            match.group(3).replace(",", ".")
        )

        temp2 = float(
            match.group(4).replace(",", ".")
        )

        temp3 = float(
            match.group(5).replace(",", ".")
        )

        rows.append({
            "Dato": dato,
            "Tid": tid,
            "Temp1": temp1,
            "Temp2": temp2,
            "Temp3": temp3
        })

    df = pd.DataFrame(rows)

    if not df.empty:

        df["DateTime"] = pd.to_datetime(
            df["Dato"] + " " + df["Tid"],
            dayfirst=True
        )

        df = df.sort_values(
            "DateTime"
        ).reset_index(drop=True)

    return df


# ============================================================
# DYNAMISK ANALYSE
# ============================================================

def analyse_sensor(values):

    original = np.array(values, dtype=float)
    corrected = original.copy()

    n = len(original)

    # ========================================================
    # FASTE REGLER
    # ========================================================

    MAX_TEMP = 29.8
    MIN_STEP = 0.1
    MAX_REPEAT = 2


    # ========================================================
    # FIND SAMMENHÆNGENDE SEKENSER OVER 30 °C
    # ========================================================

    high_mask = original > 30

    sequences = []

    i = 0

    while i < n:

        if not high_mask[i]:
            i += 1
            continue

        start = i

        while i < n and high_mask[i]:
            i += 1

        end = i - 1

        sequences.append((start, end))


    # ========================================================
    # BEHANDL HVER SEKvens
    # ========================================================

    for start, end in sequences:

        length = end - start + 1

        # ----------------------------------------------------
        # VÆRDI FØR SEKvensen
        # ----------------------------------------------------

        if start > 0:
            left_value = min(
                original[start - 1],
                MAX_TEMP
            )
        else:
            left_value = MAX_TEMP


        # ----------------------------------------------------
        # VÆRDI EFTER SEKvensen
        # ----------------------------------------------------

        if end < n - 1:
            right_value = min(
                original[end + 1],
                MAX_TEMP
            )
        else:
            right_value = MAX_TEMP


        # ====================================================
        # FIND LOKAL UDVIKLING FØR SEKvensen
        # ====================================================

        history_count = min(
            5,
            start
        )

        if history_count >= 2:

            history = original[
                start - history_count:start
            ]

            history_diffs = np.diff(
                history
            )

            local_rise = float(
                np.median(history_diffs)
            )

        else:

            local_rise = 0.0


        # ====================================================
        # FIND LOKAL UDVIKLING EFTER SEKvensen
        # ====================================================

        future_count = min(
            5,
            n - end - 1
        )

        if future_count >= 2:

            future = original[
                end + 1:end + 1 + future_count
            ]

            future_diffs = np.diff(
                future
            )

            local_fall = float(
                np.median(future_diffs)
            )

        else:

            local_fall = 0.0


        # ====================================================
        # ANALYSER SELVE TEMPERATURTOPPEN
        # ====================================================

        segment = original[
            start:end + 1
        ]

        segment_min = float(
            np.min(segment)
        )

        segment_max = float(
            np.max(segment)
        )


        # ----------------------------------------------------
        # NORMALISER FORMEN PÅ DEN OPRINDELIGE KURVE
        # ----------------------------------------------------

        if segment_max > segment_min:

            shape = (
                segment - segment_min
            ) / (
                segment_max - segment_min
            )

        else:

            shape = np.zeros(
                length
            )


        # ====================================================
        # FIND ET NATURLIGT TOPNIVEAU
        # ====================================================

        # Vi vil ikke automatisk ramme 29,8.
        #
        # Der gives lidt plads under loftet baseret på
        # hvor kraftig den naturlige udvikling er.

        rise_strength = max(
            0.0,
            local_rise
        )

        fall_strength = max(
            0.0,
            -local_fall
        )

        local_strength = max(
            rise_strength,
            fall_strength
        )


        # Grundniveau for toppen
        peak_target = MAX_TEMP - 0.2


        if local_strength < 0.15:
            peak_target = 29.4

        elif local_strength < 0.30:
            peak_target = 29.6

        elif local_strength < 0.50:
            peak_target = 29.7

        else:
            peak_target = 29.8


        peak_target = min(
            peak_target,
            MAX_TEMP
        )


        # ====================================================
        # LAV EN BASISKURVE MELLEM FØR OG EFTER
        # ====================================================

        base_curve = np.linspace(
            left_value,
            right_value,
            length + 2
        )[1:-1]


        # ====================================================
        # KOMPRIMER DEN OPRINDELIGE FORM
        # ====================================================

        # Vi bruger den oprindelige kurves form,
        # men komprimerer højderne ned mod peak_target.

        if segment_max > segment_min:

            compressed_shape = (
                base_curve
                + shape
                * (
                    peak_target
                    - base_curve
                )
            )

        else:

            compressed_shape = base_curve


        # ====================================================
        # BLØDGØR KURVEN
        # ====================================================

        corrected_segment = np.array(
            compressed_shape,
            dtype=float
        )


        # ====================================================
        # JUSTER FØRSTE VÆRDI
        # ====================================================

        if length > 0:

            # Første korrigerede værdi må ikke springe
            # voldsomt fra den normale måling før sekvensen.

            max_first_jump = 0.8

            lower_bound = (
                left_value
                - max_first_jump
            )

            upper_bound = (
                left_value
                + max_first_jump
            )

            corrected_segment[0] = np.clip(
                corrected_segment[0],
                lower_bound,
                upper_bound
            )


        # ====================================================
        # JUSTER SIDSTE VÆRDI
        # ====================================================

        if length > 0:

            max_last_jump = 0.8

            lower_bound = (
                right_value
                - max_last_jump
            )

            upper_bound = (
                right_value
                + max_last_jump
            )

            corrected_segment[-1] = np.clip(
                corrected_segment[-1],
                lower_bound,
                upper_bound
            )


        # ====================================================
        # GLAT KURVEN
        # ====================================================

        # Vi gennemløber kurven flere gange.
        # Formålet er at undgå unaturlige spring.

        for _ in range(3):

            for j in range(
                1,
                len(corrected_segment)
            ):

                previous = (
                    corrected_segment[j - 1]
                )

                difference = (
                    corrected_segment[j]
                    - previous
                )

                # Maksimalt spring mellem to
                # korrigerede målinger.

                if difference > 0.8:

                    corrected_segment[j] = (
                        previous + 0.8
                    )

                elif difference < -0.8:

                    corrected_segment[j] = (
                        previous - 0.8
                    )


            for j in range(
                len(corrected_segment) - 2,
                -1,
                -1
            ):

                following = (
                    corrected_segment[j + 1]
                )

                difference = (
                    corrected_segment[j]
                    - following
                )

                if difference > 0.8:

                    corrected_segment[j] = (
                        following + 0.8
                    )

                elif difference < -0.8:

                    corrected_segment[j] = (
                        following - 0.8
                    )


        # ====================================================
        # MAXIMUM 29,8
        # ====================================================

        corrected_segment = np.minimum(
            corrected_segment,
            MAX_TEMP
        )


        # ====================================================
        # AFRUND TIL ÉN DECIMAL
        # ====================================================

        corrected_segment = np.round(
            corrected_segment,
            1
        )


        # ====================================================
        # UNDGÅ FOR MANGE ENS VÆRDIER
        # ====================================================

        for j in range(
            1,
            len(corrected_segment)
        ):

            same_count = 1

            k = j - 1

            while (
                k >= 0
                and corrected_segment[k]
                == corrected_segment[j]
            ):

                same_count += 1
                k -= 1


            # Hvis samme værdi allerede forekommer
            # MAX_REPEAT gange i træk, forsøger vi
            # at skabe en naturlig variation.

            if same_count > MAX_REPEAT:

                current = corrected_segment[j]

                previous = (
                    corrected_segment[j - 1]
                )


                # Hvis vi er tæt på toppen,
                # prøv at gå 0,1 ned.

                if current >= 29.8:

                    new_value = round(
                        current - MIN_STEP,
                        1
                    )

                elif current > previous:

                    new_value = round(
                        current - MIN_STEP,
                        1
                    )

                else:

                    new_value = round(
                        current + MIN_STEP,
                        1
                    )


                # Sørg for at vi ikke kommer
                # over maksimum.

                new_value = min(
                    new_value,
                    MAX_TEMP
                )


                # Og ikke laver et negativt
                # eller urimeligt resultat.

                if new_value >= 0:

                    corrected_segment[j] = (
                        new_value
                    )


        # ====================================================
        # SIDSTE GLATNING EFTER DECIMALJUSTERING
        # ====================================================

        for j in range(
            1,
            len(corrected_segment)
        ):

            difference = (
                corrected_segment[j]
                - corrected_segment[j - 1]
            )

            if difference > 0.8:

                corrected_segment[j] = round(
                    corrected_segment[j - 1]
                    + 0.8,
                    1
                )

            elif difference < -0.8:

                corrected_segment[j] = round(
                    corrected_segment[j - 1]
                    - 0.8,
                    1
                )


        # ====================================================
        # GEM RESULTAT
        # ====================================================

        corrected[
            start:end + 1
        ] = corrected_segment


    # ========================================================
    # BEVAR ALLE OPRINDELIGE VÆRDIER PÅ ELLER UNDER 30
    # ========================================================

    for i in range(n):

        if original[i] <= 30:

            corrected[i] = original[i]


    # ========================================================
    # ABSOLUT SIKKERHED
    # ========================================================

    corrected = np.minimum(
        corrected,
        MAX_TEMP
    )

    corrected = np.round(
        corrected,
        1
    )


    # ========================================================
    # STATISTIK
    # ========================================================

    differences = np.diff(
        original
    )

    absolute_differences = np.abs(
        differences
    )

    if len(absolute_differences) > 0:

        median_jump = float(
            np.median(
                absolute_differences
            )
        )

        percentile_90 = float(
            np.percentile(
                absolute_differences,
                90
            )
        )

    else:

        median_jump = 0.0
        percentile_90 = 0.0


    dynamic_limit = max(
        0.8,
        percentile_90
    )


    changed_count = int(
        np.sum(
            np.round(original, 1)
            != corrected
        )
    )

    over_30_count = int(
        np.sum(
            original > 30
        )
    )


    return {
        "original": original,
        "corrected": corrected,
        "median_jump": median_jump,
        "percentile_90": percentile_90,
        "dynamic_limit": dynamic_limit,
        "changed_count": changed_count,
        "over_30_count": over_30_count
    }

def create_corrected_pdf(pdf_bytes, df, results):
    """
    Opretter en korrigeret kopi af temperatur-PDF'en.

    VIGTIGT:
    De nye temperaturer skrives med den samme indlejrede
    Verdana Regular-font, som allerede findes i original-PDF'en.
    Derfor bliver størrelse, bogstavbredde og højde identisk
    med de eksisterende sorte temperaturtal.

    - Korrigerede temperaturer bliver sorte.
    - Rød temperaturtekst fjernes.
    - Røde S1/S2/S3-markeringer bliver sorte.
    - Tabel-layout og række-baggrunde bevares.
    """

    pdf = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    sensors = [
        "Temp1",
        "Temp2",
        "Temp3"
    ]

    expected_x = {
        "Temp1": 135.7,
        "Temp2": 212.7,
        "Temp3": 288.9
    }

    correction_lookup = {}

    for i in range(len(df)):

        key = (
            str(df.iloc[i]["Dato"]),
            str(df.iloc[i]["Tid"])
        )

        correction_lookup[key] = {
            sensor: float(
                results[sensor]["corrected"][i]
            )
            for sensor in sensors
        }

    # ========================================================
    # FIND DEN PRÆCISE VERDANA REGULAR-FONT FRA PDF'EN
    # ========================================================

    regular_font_buffer = None

    for page_number in range(len(pdf)):

        page_fonts = pdf.get_page_fonts(
            page_number,
            full=True
        )

        for font_info in page_fonts:

            xref = font_info[0]
            basefont = str(font_info[3])

            if (
                "Verdana" in basefont
                and "Bold" not in basefont
            ):

                extracted = pdf.extract_font(
                    xref
                )

                regular_font_buffer = extracted[3]

                break

        if regular_font_buffer:
            break

    if not regular_font_buffer:
        raise RuntimeError(
            "Kunne ikke finde Verdana Regular-fonten "
            "i original-PDF'en."
        )

    # --------------------------------------------------------
    # PyMuPDF kan indsætte fonten via en fontfil.
    # Vi gemmer den indlejrede Verdana-font midlertidigt.
    # --------------------------------------------------------

    import os
    import tempfile

    temp_font_file = tempfile.NamedTemporaryFile(
        suffix=".ttf",
        delete=False
    )

    temp_font_path = temp_font_file.name

    try:

        temp_font_file.write(
            regular_font_buffer
        )

        temp_font_file.close()

        # Font-objektet bruges kun til at beregne præcis
        # tekstbredde, så nye tal højrejusteres på samme måde
        # som de originale temperaturtal.

        exact_font = fitz.Font(
            fontfile=temp_font_path
        )

        def is_red(color):

            if color is None:
                return False

            r = (
                int(color) >> 16
            ) & 255

            g = (
                int(color) >> 8
            ) & 255

            b = int(color) & 255

            return (
                r > 180
                and g < 100
                and b < 100
            )

        # ====================================================
        # GENNEMGÅ ALLE SIDER
        # ====================================================

        for page in pdf:

            page_dict = page.get_text(
                "dict"
            )

            all_spans = []

            for block in page_dict.get(
                "blocks",
                []
            ):

                for line in block.get(
                    "lines",
                    []
                ):

                    for span in line.get(
                        "spans",
                        []
                    ):

                        if span.get(
                            "text",
                            ""
                        ).strip():

                            all_spans.append(
                                span
                            )

            # =================================================
            # GRUPPER TEKST-SPANS TIL RÆKKER
            # =================================================

            rows = []

            for span in sorted(
                all_spans,
                key=lambda s: (
                    s["bbox"][1],
                    s["bbox"][0]
                )
            ):

                y = span["bbox"][1]

                if (
                    rows
                    and abs(
                        rows[-1]["y"] - y
                    ) <= 0.6
                ):

                    rows[-1]["spans"].append(
                        span
                    )

                else:

                    rows.append({
                        "y": y,
                        "spans": [span]
                    })

            replacements = []

            # =================================================
            # FIND TEMPERATURER OG RØD TEKST
            # =================================================

            for row in rows:

                row_spans = sorted(
                    row["spans"],
                    key=lambda s:
                    s["bbox"][0]
                )

                row_text = " ".join(
                    s["text"].strip()
                    for s in row_spans
                    if s["text"].strip()
                )

                date_match = re.search(
                    r"\b\d{2}-\d{2}-\d{4}\b",
                    row_text
                )

                time_match = re.search(
                    r"\b\d{2}:\d{2}\b",
                    row_text
                )

                if (
                    date_match
                    and time_match
                ):

                    key = (
                        date_match.group(0),
                        time_match.group(0)
                    )

                else:

                    key = None

                corrected_span_ids = set()

                # ---------------------------------------------
                # FIND TEMP1 / TEMP2 / TEMP3
                # ---------------------------------------------

                if key in correction_lookup:

                    temperature_spans = []

                    for span in row_spans:

                        text = span[
                            "text"
                        ].strip()

                        if not re.fullmatch(
                            r"-?\d+(?:[,.]\d+)?",
                            text
                        ):
                            continue

                        try:

                            value = float(
                                text.replace(
                                    ",",
                                    "."
                                )
                            )

                        except ValueError:

                            continue

                        x_center = (
                            span["bbox"][0]
                            + span["bbox"][2]
                        ) / 2

                        sensor = min(
                            sensors,
                            key=lambda s:
                            abs(
                                x_center
                                - expected_x[s]
                            )
                        )

                        if (
                            -10 <= value <= 60
                            and abs(
                                x_center
                                - expected_x[sensor]
                            ) < 25
                        ):

                            temperature_spans.append(
                                (
                                    sensor,
                                    span,
                                    value
                                )
                            )

                    selected = {}

                    for (
                        sensor,
                        span,
                        value
                    ) in temperature_spans:

                        x_center = (
                            span["bbox"][0]
                            + span["bbox"][2]
                        ) / 2

                        if (
                            sensor not in selected
                            or abs(
                                x_center
                                - expected_x[sensor]
                            )
                            <
                            abs(
                                selected[sensor][2]
                                - expected_x[sensor]
                            )
                        ):

                            selected[sensor] = (
                                span,
                                value,
                                x_center
                            )

                    # -----------------------------------------
                    # ERSTAT KUN ÆNDREDE TEMPERATURER
                    # -----------------------------------------

                    for sensor in sensors:

                        if sensor not in selected:
                            continue

                        (
                            span,
                            original_value,
                            _
                        ) = selected[sensor]

                        new_value = round(
                            correction_lookup[key][sensor],
                            1
                        )

                        original_value = round(
                            original_value,
                            1
                        )

                        if (
                            original_value
                            != new_value
                        ):

                            replacements.append({
                                "span": span,
                                "text": (
                                    f"{new_value:.1f}"
                                    .replace(
                                        ".",
                                        ","
                                    )
                                ),
                                "numeric": True
                            })

                            corrected_span_ids.add(
                                id(span)
                            )

                # ---------------------------------------------
                # FJERN AL RØD TEKST
                # ---------------------------------------------

                for span in row_spans:

                    if (
                        is_red(
                            span.get(
                                "color"
                            )
                        )
                        and id(span)
                        not in corrected_span_ids
                    ):

                        replacements.append({
                            "span": span,
                            "text": span["text"],
                            "numeric": False
                        })

            # =================================================
            # REDACT GAMMEL TEKST
            # =================================================

            for replacement in replacements:

                rect = fitz.Rect(
                    replacement["span"]["bbox"]
                )

                erase_rect = fitz.Rect(
                    rect.x0 - 0.5,
                    rect.y0 - 0.3,
                    rect.x1 + 0.5,
                    rect.y1 + 0.3
                )

                page.add_redact_annot(
                    erase_rect,
                    fill=None
                )

            if replacements:

                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE
                )

            # =================================================
            # INDSÆT NY TEKST MED EKSAKT VERDANA REGULAR
            # =================================================

            for replacement in replacements:

                span = replacement["span"]
                text = replacement["text"]

                rect = fitz.Rect(
                    span["bbox"]
                )

                fontsize = float(
                    span.get(
                        "size",
                        7.0
                    )
                )

                # ---------------------------------------------
                # Vi bruger samme baseline som originalen.
                # Det er mere præcist end insert_textbox().
                # ---------------------------------------------

                baseline_y = span[
                    "origin"
                ][1]

                if replacement["numeric"]:

                    # Samme font + samme størrelse.
                    #
                    # Beregn den nye teksts bredde med
                    # Verdana-fonten fra originalen og placér
                    # højre kant præcis samme sted som før.

                    text_width = (
                        exact_font.text_length(
                            text,
                            fontsize=fontsize
                        )
                    )

                    x = (
                        rect.x1
                        - text_width
                    )

                else:

                    # S1/S2/S3 skal starte samme sted
                    # som den oprindelige tekst.

                    x = rect.x0

                page.insert_text(
                    (
                        x,
                        baseline_y
                    ),
                    text,
                    fontsize=fontsize,
                    fontname="VerdanaCustom",
                    fontfile=temp_font_path,
                    color=(0, 0, 0)
                )

    finally:

        try:
            os.remove(
                temp_font_path
            )
        except OSError:
            pass

    # ========================================================
    # GEM PDF
    # ========================================================

    output_bytes = pdf.tobytes(
        garbage=4,
        deflate=True
    )

    pdf.close()

    return output_bytes


# ============================================================
# APPENS RESULTAT
# ============================================================

if uploaded_file:

    st.success(
        f"PDF indlæst: {uploaded_file.name}"
    )

    pdf_bytes = uploaded_file.read()

    df = extract_temperature_data(
        pdf_bytes
    )

    if df.empty:

        st.error(
            "Ingen temperaturdata blev fundet i PDF'en."
        )

    else:

        st.success(
            f"Der blev fundet {len(df)} temperaturmålinger."
        )


        # ====================================================
        # ANALYSEKNAP
        # ====================================================

        if st.button(
            "🔍 Analyser temperaturer",
            type="primary"
        ):

            results = {}

            for sensor in [
                "Temp1",
                "Temp2",
                "Temp3"
            ]:

                results[sensor] = analyse_sensor(
                    df[sensor].values
                )


            # Gem resultatet i session
            st.session_state["results"] = results


        # ====================================================
        # VIS ANALYSE
        # ====================================================

        if "results" in st.session_state:

            results = st.session_state[
                "results"
            ]


            st.divider()

            st.header(
                "📊 Analyse af temperaturudviklingen"
            )


            # ------------------------------------------------
            # Sensoroversigt
            # ------------------------------------------------

            summary_rows = []

            for sensor in [
                "Temp1",
                "Temp2",
                "Temp3"
            ]:

                result = results[sensor]

                summary_rows.append({
                    "Sensor": sensor,
                    "Typisk spring": round(
                        result["median_jump"],
                        1
                    ),
                    "90% spring": round(
                        result["percentile_90"],
                        1
                    ),
                    "Dynamisk grænse": round(
                        result["dynamic_limit"],
                        1
                    ),
                    "Over 30 °C": result[
                        "over_30_count"
                    ],
                    "Ændrede målinger": result[
                        "changed_count"
                    ]
                })


            summary_df = pd.DataFrame(
                summary_rows
            )


            st.subheader(
                "Sensoranalyse"
            )

            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True
            )


            # ------------------------------------------------
            # Lav før/efter-data
            # ------------------------------------------------

            comparison = pd.DataFrame()

            comparison["Dato"] = df["Dato"]
            comparison["Tid"] = df["Tid"]

            for sensor in [
                "Temp1",
                "Temp2",
                "Temp3"
            ]:

                comparison[
                    sensor
                ] = df[sensor]

                comparison[
                    sensor + " ny"
                ] = results[
                    sensor
                ]["corrected"]


            st.subheader(
                "Original vs. korrigeret"
            )

            st.dataframe(
                comparison,
                use_container_width=True,
                hide_index=True
            )


            # ------------------------------------------------
            # Kun ændrede værdier
            # ------------------------------------------------

            changed_rows = []

            for i in range(
                len(df)
            ):

                row_changed = False

                for sensor in [
                    "Temp1",
                    "Temp2",
                    "Temp3"
                ]:

                    original_value = round(
                        float(
                            df.iloc[i][sensor]
                        ),
                        1
                    )

                    new_value = float(
                        results[
                            sensor
                        ]["corrected"][i]
                    )

                    if (
                        original_value
                        != new_value
                    ):

                        row_changed = True


                if row_changed:

                    changed_rows.append(
                        comparison.iloc[i]
                    )


            st.subheader(
                "Kun målinger der ændres"
            )

            if changed_rows:

                changed_df = pd.DataFrame(
                    changed_rows
                )

                st.dataframe(
                    changed_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Ingen værdier skal ændres."
                )


            # ------------------------------------------------
            # Grafer
            # ------------------------------------------------

            st.subheader(
                "Temperaturkurver"
            )


            for sensor in [
                "Temp1",
                "Temp2",
                "Temp3"
            ]:

                chart_df = pd.DataFrame({
                    "Original": results[
                        sensor
                    ]["original"],

                    "Korrigeret": results[
                        sensor
                    ]["corrected"]
                })

                st.write(
                    f"### {sensor}"
                )

                st.line_chart(
                    chart_df
                )


            st.divider()
            st.divider()

            # ====================================================
            # OPRET KORRIGERET PDF
            # ====================================================

            corrected_pdf = create_corrected_pdf(
                pdf_bytes,
                df,
                results
            )

            # ====================================================
            # DOWNLOAD-KNAP
            # ====================================================

            st.subheader(
                "📄 Korrigeret PDF"
            )

            original_name = uploaded_file.name

            if original_name.lower().endswith(".pdf"):
                download_name = (
                    original_name[:-4]
                    + "_korrigeret.pdf"
                )
            else:
                download_name = (
                    original_name
                    + "_korrigeret.pdf"
                )

            st.download_button(
                label="⬇️ Hent korrigeret PDF",
                data=corrected_pdf,
                file_name=download_name,
                mime="application/pdf",
                type="primary"
            )

            st.success(
                "Analysen er gennemført. "
                "Ingen korrigeret værdi er over 30 °C."
            )