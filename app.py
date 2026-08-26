import streamlit as st


# ============================================================
# SIDEOPSÆTNING
# ============================================================

st.set_page_config(
    page_title="Temperaturværktøj",
    page_icon="🌡️",
    layout="wide"
)


# ============================================================
# DESIGN
# ============================================================

st.markdown("""
<style>

/* Skjul Streamlit navigation */
[data-testid="stSidebar"] {
    display: none !important;
}

[data-testid="stSidebarCollapsedControl"] {
    display: none !important;
}

/* Baggrund */
.stApp {
    background: linear-gradient(
        135deg,
        #eef5f8,
        #f8fafb,
        #e8f0f4
    );
}

/* Hovedområde */
.block-container {
    max-width: 1050px;
    padding-top: 60px;
    padding-bottom: 40px;
}

/* Hero */
.hero {
    text-align: center;
    margin-bottom: 50px;
}

.hero-icon {
    font-size: 58px;
    margin-bottom: 5px;
}

.hero-title {
    font-size: 42px;
    font-weight: 700;
    color: #1f2933;
}

.hero-subtitle {
    font-size: 18px;
    color: #667580;
    margin-top: 10px;
}

/* Kort */
.card-icon {
    text-align: center;
    font-size: 48px;
    margin-bottom: 10px;
}

.card-title {
    text-align: center;
    font-size: 28px;
    font-weight: 700;
    color: #1f2933;
    margin-bottom: 15px;
}

.card-text {
    text-align: center;
    font-size: 16px;
    line-height: 1.6;
    color: #667580;
    min-height: 105px;
}

/* Knapper */
div.stButton > button {
    width: 100%;
    height: 50px;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 600;
}

/* Footer */
.footer {
    text-align: center;
    margin-top: 55px;
    color: #8a969d;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# HERO
# ============================================================

# ============================================================
# HERO
# ============================================================

st.markdown(
    """
    <div style="
        text-align: center;
        font-size: 58px;
        margin-bottom: 5px;
    ">
        🌡️
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<h1 style="text-align:center; color:#1f2933; font-size:42px; margin:0;">'
    'Temperaturværktøj'
    '</h1>',
    unsafe_allow_html=True
)

st.markdown(
    '<p style="text-align:center; color:#667580; font-size:18px; margin-top:10px; margin-bottom:50px;">'
    'Vælg den løsning, du vil bruge til behandling af temperatur-rapporter.'
    '</p>',
    unsafe_allow_html=True
)


# ============================================================
# DE TO LØSNINGER
# ============================================================

col1, col2 = st.columns(2, gap="large")


# ============================================================
# LINKITALL
# ============================================================

with col1:

    with st.container(border=True):

        st.markdown("""
<div class="card-icon">
    🔵
</div>

<div class="card-title">
    LinkitAll
</div>

<div class="card-text">
    Behandl temperatur-rapporter hentet fra LinkitAll-systemet.
    <br><br>
    Upload rapporten og få en korrigeret PDF.
</div>
""", unsafe_allow_html=True)

        st.write("")

        if st.button(
            "Åbn LinkitAll",
            key="linkitall_button",
            type="primary",
            width="stretch"
        ):
            st.switch_page("pages/linkitall.py")


# ============================================================
# KLEVENTA
# ============================================================

with col2:

    with st.container(border=True):

        st.markdown("""
<div class="card-icon">
    🟢
</div>

<div class="card-title">
    Kleventa
</div>

<div class="card-text">
    Behandl temperatur-rapporter hentet fra Kleventa-systemet.
    <br><br>
    Upload rapporten og få en korrigeret PDF.
</div>
""", unsafe_allow_html=True)

        st.write("")

        if st.button(
            "Åbn Kleventa",
            key="kleventa_button",
            width="stretch"
        ):
            st.switch_page("pages/kleventa.py")


# ============================================================
# FOOTER
# ============================================================

st.markdown("""
<div class="footer">
    Temperaturværktøj · PDF-behandling
</div>
""", unsafe_allow_html=True)
