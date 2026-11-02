import streamlit as st
import fitz
import re
import pandas as pd
import numpy as np
import os
import tempfile


# ============================================================
# APP
# ============================================================

st.set_page_config(
    page_title="Kleventa - Temperature PDF",
    page_icon="🌡️",
    layout="wide"
)

st.title("🌡️ Kleventa - Temperature PDF")

st.write(
    "Upload en temperatur-rapport fra Kleventa for at analysere "
    "og korrigere Stock1, Stock2 og Stock3."
)


# ============================================================
# PDF-LÆSNING
# ============================================================

uploaded_file = st.file_uploader(
    "Upload Kleventa temperatur-PDF",
    type=["pdf"]
)


def temperature_rows(page):
    """Read complete table rows by position, independent of PDF text order."""
    rows = []
    for word in sorted(page.get_text("words"), key=lambda w: (w[1], w[0])):
        if not rows or abs(rows[-1]["y"] - word[1]) > 2:
            rows.append({"y": word[1], "words": [word]})
        else:
            rows[-1]["words"].append(word)

    for row in rows:
        words = sorted(row["words"], key=lambda w: w[0])
        date = next((w for w in words if re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}", w[4])), None)
        time = next((w for w in words if re.fullmatch(r"\d{2}:\d{2}", w[4])), None)
        if date is None or time is None:
            continue
        temperatures = [w for w in words if w[0] >= time[2]
                        and re.fullmatch(r"-?\d+(?:[,.]\d+)?(?:°C)?", w[4])]
        # Reject partial rows rather than shifting one sensor into another column.
        if len(temperatures) != 6:
            continue
        yield date[4], time[4], temperatures


def extract_temperature_data(pdf_bytes):
    rows = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            for date, time, words in temperature_rows(page):
                values = [float(w[4].replace("°C", "").replace(",", ".")) for w in words]
                rows.append(dict(zip(
                    ["Dato", "Tid", "Stock1", "Stock2", "Stock3", "Outside", "Water", "Inlet"],
                    [date, time, *values]
                )))
    df = pd.DataFrame(rows)
    if not df.empty:
        df["DateTime"] = pd.to_datetime(
            df["Dato"].str.replace("/", "-", regex=False) + " " + df["Tid"],
            format="%d-%m-%Y %H:%M"
        )
        df = df.sort_values("DateTime", kind="stable").reset_index(drop=True)
    return df


# ============================================================
# DYNAMISK ANALYSE
# SAMME LOGIK SOM LINKITALL
# ============================================================

def analyse_sensor(values):

    original = np.array(
        values,
        dtype=float
    )

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

        sequences.append(
            (start, end)
        )

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

        # ====================================================
        # NORMALISER FORMEN
        # ====================================================

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
        # FIND NATURLIGT TOPNIVEAU
        # ====================================================

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
        # BASISKURVE
        # ====================================================

        base_curve = np.linspace(
            left_value,
            right_value,
            length + 2
        )[1:-1]

        # ====================================================
        # KOMPRIMER ORIGINAL KURVE
        # ====================================================

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

        corrected_segment = np.array(
            compressed_shape,
            dtype=float
        )

        # ====================================================
        # JUSTER FØRSTE VÆRDI
        # ====================================================

        if length > 0:

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

            if same_count > MAX_REPEAT:

                current = corrected_segment[j]

                previous = (
                    corrected_segment[j - 1]
                )

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

                new_value = min(
                    new_value,
                    MAX_TEMP
                )

                if new_value >= 0:

                    corrected_segment[j] = (
                        new_value
                    )

        # ====================================================
        # SIDSTE GLATNING
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


# ============================================================
# OPRET KORRIGERET KLEVENTA PDF
# ============================================================

def create_corrected_pdf(pdf_bytes, df, results):
    sensors = ["Stock1", "Stock2", "Stock3"]
    lookup = {}
    for i, row in df.iterrows():
        lookup.setdefault((row["Dato"], row["Tid"]), []).append(i)
    used_rows = {}

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            spans = [span for block in page.get_text("dict")["blocks"]
                     if "lines" in block for line in block["lines"] for span in line["spans"]]
            replacements = []
            for date, time, words in temperature_rows(page):
                key = (date, time)
                position = used_rows.get(key, 0)
                if key not in lookup or position >= len(lookup[key]):
                    raise ValueError("PDF-rækkerne stemmer ikke overens med analysen.")
                index = lookup[key][position]
                used_rows[key] = position + 1
                for sensor, word in zip(sensors, words[:3]):
                    value = round(float(results[sensor]["corrected"][index]), 1)
                    if value == round(float(df.iloc[index][sensor]), 1):
                        continue
                    span = next(s for s in spans
                                if fitz.Rect(s["bbox"]).contains(fitz.Rect(word[:4])))
                    text = f"{value:.1f}"
                    if "," in word[4]:
                        text = text.replace(".", ",")
                    if word[4].endswith("°C"):
                        text += "°C"
                    font = "heit" if "Oblique" in span["font"] or "Italic" in span["font"] else "helv"
                    color = fitz.sRGB_to_pdf(span["color"])
                    replacements.append((word, text, span, font, color))
            for word, *_ in replacements:
                page.add_redact_annot(fitz.Rect(word[:4]), fill=None)
            if replacements:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                      graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                      text=fitz.PDF_REDACT_TEXT_REMOVE)
            for word, text, span, font, color in replacements:
                page.insert_text((word[0], span["origin"][1]), text,
                                 fontname=font, fontsize=span["size"], color=color, overlay=True)
        return pdf.tobytes(garbage=4, deflate=True)

# ============================================================
# APPENS RESULTAT
# ============================================================

if uploaded_file:

    st.success(
        f"PDF indlæst: {uploaded_file.name}"
    )

    pdf_bytes = uploaded_file.read()

    if st.session_state.get("kleventa_pdf_bytes") != pdf_bytes:
        st.session_state.pop("kleventa_results", None)
        st.session_state["kleventa_pdf_bytes"] = pdf_bytes

    df = extract_temperature_data(
        pdf_bytes
    )

    if df.empty:

        st.error(
            "Ingen Kleventa temperaturdata blev fundet i PDF'en."
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
                "Stock1",
                "Stock2",
                "Stock3"
            ]:

                results[sensor] = analyse_sensor(
                    df[sensor].values
                )

            st.session_state[
                "kleventa_results"
            ] = results

        # ====================================================
        # VIS ANALYSE
        # ====================================================

        if "kleventa_results" in st.session_state:

            results = st.session_state[
                "kleventa_results"
            ]

            st.divider()

            st.header(
                "📊 Analyse af temperaturudviklingen"
            )

            # =================================================
            # SENSOROVERSIGT
            # =================================================

            summary_rows = []

            for sensor in [
                "Stock1",
                "Stock2",
                "Stock3"
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

            # =================================================
            # ORIGINAL VS KORRIGERET
            # =================================================

            comparison = pd.DataFrame()

            comparison["Dato"] = df["Dato"]
            comparison["Tid"] = df["Tid"]

            for sensor in [
                "Stock1",
                "Stock2",
                "Stock3"
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

            # =================================================
            # KUN ÆNDREDE VÆRDIER
            # =================================================

            changed_rows = []

            for i in range(
                len(df)
            ):

                row_changed = False

                for sensor in [
                    "Stock1",
                    "Stock2",
                    "Stock3"
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

            # =================================================
            # GRAFER
            # =================================================

            st.subheader(
                "Temperaturkurver"
            )

            for sensor in [
                "Stock1",
                "Stock2",
                "Stock3"
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

            # =================================================
            # OPRET KORRIGERET PDF
            # =================================================

            corrected_pdf = create_corrected_pdf(
                pdf_bytes,
                df,
                results
            )

            # =================================================
            # DOWNLOAD
            # =================================================

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
                "Ingen korrigeret Stock-værdi er over 30 °C."
            )
